import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { downloadAssetFile, getAssetPreview } from '@/api/assets'
import { downloadSandboxFile, getSandboxFile, updateSandboxFileContent } from '@/api/sandbox'
import type { FilePreviewPayload, FilePreviewSheet, FilePreviewTarget, FilePreviewType } from '@/types/filePreview'
import { isYuqueUrl } from '@/utils/assetSync'

interface OpenPreviewOptions extends FilePreviewTarget {
  autoOpenExternalUrl?: boolean
  startInEdit?: boolean
}

function parseFilenameFromDisposition(disposition?: string): string {
  if (!disposition) return ''
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1])
  const quotedMatch = disposition.match(/filename="([^"]+)"/i)
  if (quotedMatch?.[1]) return quotedMatch[1]
  const plainMatch = disposition.match(/filename=([^;]+)/i)
  return plainMatch?.[1]?.trim() || ''
}

function openExternalUrl(url?: string) {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

function isExternalHttpUrl(url?: string): boolean {
  return Boolean(url && /^https?:\/\//i.test(url))
}

function isMarkdownPayload(payload: FilePreviewPayload | null): boolean {
  if (!payload) return false
  const fileType = (payload.file_type || '').toLowerCase()
  return payload.preview_type === 'markdown' || ['md', 'markdown'].includes(fileType)
}

function ensureMarkdownFilename(name: string): string {
  const trimmed = name.trim() || 'untitled'
  return /\.md$/i.test(trimmed) ? trimmed : `${trimmed}.md`
}

function resolveImageMimeType(fileType?: string): string {
  const normalized = (fileType || '').toLowerCase()
  if (normalized === 'jpg' || normalized === 'jpeg') return 'image/jpeg'
  if (normalized === 'svg') return 'image/svg+xml'
  if (normalized) return `image/${normalized}`
  return 'application/octet-stream'
}

export function useFilePreview() {
  const visible = ref(false)
  const loading = ref(false)
  const title = ref('')
  const fileType = ref('')
  const fileSize = ref(0)
  const mode = ref<FilePreviewType>('text')
  const content = ref('')
  const previewNotice = ref('')
  const previewUrl = ref('')
  const sheets = ref<FilePreviewSheet[]>([])
  const activeSheetName = ref('')
  const lastPayload = ref<FilePreviewPayload | null>(null)
  const currentTarget = ref<FilePreviewTarget | null>(null)
  const objectUrl = ref<string | null>(null)
  const canDownload = ref(true)
  const canEdit = ref(false)
  const saving = ref(false)
  const enterEditToken = ref(0)

  const currentSheet = computed<FilePreviewSheet | null>(() => {
    if (!sheets.value.length) return null
    const matched = sheets.value.find((sheet) => sheet.name === activeSheetName.value)
    return matched ?? sheets.value[0] ?? null
  })

  function resetState() {
    mode.value = 'text'
    content.value = ''
    previewNotice.value = ''
    previewUrl.value = ''
    sheets.value = []
    activeSheetName.value = ''
    lastPayload.value = null
    canDownload.value = true
    canEdit.value = false
    saving.value = false
  }

  function cleanupObjectUrl() {
    if (objectUrl.value) {
      URL.revokeObjectURL(objectUrl.value)
      objectUrl.value = null
    }
  }

  function close() {
    visible.value = false
    cleanupObjectUrl()
  }

  function openPayload(payload: FilePreviewPayload) {
    lastPayload.value = payload
    const payloadType = payload.preview_type
    const normalizedMode: FilePreviewType =
      payloadType === 'text' && ['md', 'markdown'].includes((payload.file_type || '').toLowerCase())
        ? 'markdown'
        : payloadType
    mode.value = normalizedMode
    previewUrl.value = payload.preview_url || payload.download_url || ''
    content.value = payload.content || ''
    previewNotice.value = payload.preview_notice || ''
    sheets.value = Array.isArray(payload.sheets) ? payload.sheets : []
    activeSheetName.value = sheets.value[0]?.name || ''
    fileType.value = payload.file_type || fileType.value
    fileSize.value = payload.file_size || fileSize.value
    canDownload.value = payload.preview_type !== 'download_only' || isYuqueUrl(payload.preview_url || payload.download_url)
    canEdit.value =
      Boolean(payload.can_edit) &&
      mode.value === 'markdown' &&
      currentTarget.value?.source === 'sandbox' &&
      Boolean(currentTarget.value?.conversationId) &&
      Boolean(currentTarget.value?.fileId)
    visible.value = true
  }

  async function resolveInlinePreviewUrl(
    target: OpenPreviewOptions,
    payload: FilePreviewPayload,
  ): Promise<FilePreviewPayload> {
    if (!['pdf', 'image'].includes(payload.preview_type)) return payload

    const rawUrl = payload.preview_url || payload.download_url
    if (!rawUrl || isExternalHttpUrl(rawUrl)) return payload

    try {
      let blob: Blob | null = null
      if (target.source === 'asset' && target.assetId) {
        const res = await downloadAssetFile(target.assetId)
        blob = res.data
      } else if (target.source === 'sandbox' && target.conversationId && target.fileId) {
        const res = await downloadSandboxFile(target.conversationId, target.fileId)
        blob = res.data
      }

      if (!blob) return payload

      if (payload.preview_type === 'pdf') {
        const pdfHeader = await blob.slice(0, 5).text()
        if (!pdfHeader.startsWith('%PDF-')) {
          let fallbackText = ''
          try {
            fallbackText = await blob.text()
          } catch {
            fallbackText = ''
          }
          return {
            ...payload,
            preview_type: 'text',
            preview_notice: 'PDF 预览失败：文件内容不是有效的 PDF 二进制。',
            content: fallbackText || payload.content || '',
          }
        }
      }

      cleanupObjectUrl()
      if (payload.preview_type === 'pdf') {
        objectUrl.value = window.URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }))
        return {
          ...payload,
          preview_url: objectUrl.value,
        }
      }

      objectUrl.value = window.URL.createObjectURL(new Blob([blob], { type: resolveImageMimeType(payload.file_type) }))
      return {
        ...payload,
        preview_url: objectUrl.value,
      }
    } catch {
      return payload
    }
  }

  async function openPreview(target: OpenPreviewOptions) {
    title.value = target.label
    fileType.value = target.fileType || ''
    fileSize.value = target.fileSize || 0
    currentTarget.value = target
    cleanupObjectUrl()
    resetState()

    loading.value = true
    try {
      let payload: FilePreviewPayload | null = null
      if (target.source === 'asset') {
        if (!target.assetId) {
          ElMessage.error('缺少资料 ID，无法预览')
          return
        }
        const res = await getAssetPreview(target.assetId)
        if (res.code !== 0) {
          ElMessage.error(res.message || '获取文件内容失败')
          return
        }
        payload = res.data
      } else {
        if (!target.conversationId || !target.fileId) {
          ElMessage.error('缺少会话文件信息，无法预览')
          return
        }
        const res = await getSandboxFile(target.conversationId, target.fileId)
        if (res.code !== 0) {
          ElMessage.error(res.message || '获取文件内容失败')
          return
        }
        payload = res.data
      }

      if (!payload) {
        ElMessage.error('获取文件内容失败')
        return
      }

      payload = await resolveInlinePreviewUrl(target, payload)

      if (
        target.autoOpenExternalUrl &&
        payload.preview_type === 'download_only' &&
        payload.preview_url &&
        isExternalHttpUrl(payload.preview_url)
      ) {
        openExternalUrl(payload.preview_url)
        return
      }
      openPayload(payload)
      if (target.startInEdit && canEdit.value) {
        enterEditToken.value += 1
      }
    } catch {
      ElMessage.error('获取文件内容失败')
    } finally {
      loading.value = false
    }
  }

  async function downloadCurrent() {
    const target = currentTarget.value
    if (!target) return

    const payload = lastPayload.value

    try {
      const directUrl = payload?.download_url || payload?.preview_url
      if (isExternalHttpUrl(directUrl)) {
        if (!isYuqueUrl(directUrl)) {
          ElMessage.warning('普通 URL 资料不支持下载，请使用“新窗口打开”。')
          return
        }
        if (!target.assetId) {
          ElMessage.error('缺少语雀资料标识，无法下载')
          return
        }
        // 语雀 URL 走后端下载端点，确保拿到此前 MCP 抓取的 Markdown 快照
        const res = await downloadAssetFile(target.assetId)
        const disposition = res.headers?.['content-disposition'] as string | undefined
        const filename = ensureMarkdownFilename(parseFilenameFromDisposition(disposition) || target.label)
        const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/markdown;charset=utf-8' }))
        const link = document.createElement('a')
        link.href = url
        link.download = filename
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
        return
      }

      if (target.source === 'asset') {
        if (!target.assetId) return
        if (isMarkdownPayload(payload)) {
          const markdown = payload?.content || ''
          const filename = ensureMarkdownFilename(target.label || 'untitled')
          const url = window.URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }))
          const link = document.createElement('a')
          link.href = url
          link.download = filename
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
          window.URL.revokeObjectURL(url)
          return
        }
        const res = await downloadAssetFile(target.assetId)
        const disposition = res.headers?.['content-disposition'] as string | undefined
        const filename = parseFilenameFromDisposition(disposition) || target.label
        const url = window.URL.createObjectURL(new Blob([res.data]))
        const link = document.createElement('a')
        link.href = url
        link.download = filename
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
        return
      }

      if (!target.conversationId || !target.fileId) return
      const res = await downloadSandboxFile(target.conversationId, target.fileId)
      const disposition = res.headers?.['content-disposition'] as string | undefined
      const filename = parseFilenameFromDisposition(disposition) || target.label
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch {
      ElMessage.error('下载失败')
    }
  }

  async function saveMarkdownEdit(nextContent: string) {
    const target = currentTarget.value
    if (!target || target.source !== 'sandbox' || !target.conversationId || !target.fileId) {
      ElMessage.error('当前文件不支持编辑')
      return false
    }
    if (!canEdit.value || mode.value !== 'markdown') {
      ElMessage.error('当前文件不支持编辑')
      return false
    }

    saving.value = true
    try {
      const res = await updateSandboxFileContent(target.conversationId, target.fileId, nextContent)
      if (res.code !== 0) {
        ElMessage.error(res.message || '保存失败')
        return false
      }

      const normalizedContent = res.data?.content ?? nextContent
      content.value = normalizedContent
      if (typeof res.data?.file_size === 'number') {
        fileSize.value = res.data.file_size
      }
      if (res.data?.file_type) {
        fileType.value = res.data.file_type
      }
      if (lastPayload.value) {
        lastPayload.value = {
          ...lastPayload.value,
          content: normalizedContent,
          file_size: res.data?.file_size ?? lastPayload.value.file_size,
          file_type: res.data?.file_type ?? lastPayload.value.file_type,
          can_edit: true,
        }
      }
      ElMessage.success(res.message || '保存成功')
      return true
    } catch {
      ElMessage.error('保存失败')
      return false
    } finally {
      saving.value = false
    }
  }

  function openCurrentInNewWindow() {
    if (mode.value === 'html') {
      const popup = window.open('', '_blank')
      if (!popup) {
        ElMessage.error('浏览器拦截了新窗口，请允许弹窗后重试')
        return
      }
      popup.document.open()
      popup.document.write(content.value || '')
      popup.document.close()
      if (title.value) {
        popup.document.title = title.value
      }
      return
    }

    const targetUrl = previewUrl.value || lastPayload.value?.download_url
    if (!targetUrl) {
      ElMessage.error('当前文件暂不支持新窗口打开')
      return
    }
    openExternalUrl(targetUrl)
  }

  onBeforeUnmount(() => {
    cleanupObjectUrl()
  })

  return {
    visible,
    loading,
    title,
    fileType,
    fileSize,
    mode,
    content,
    previewNotice,
    previewUrl,
    sheets,
    activeSheetName,
    currentSheet,
    canDownload,
    canEdit,
    saving,
    enterEditToken,
    openPreview,
    downloadCurrent,
    saveMarkdownEdit,
    openCurrentInNewWindow,
    close,
    openExternalUrl,
  }
}
