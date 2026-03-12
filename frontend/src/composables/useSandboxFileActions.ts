import { ElMessage, ElMessageBox } from 'element-plus'

import { showDangerConfirm } from '@/composables/useDangerConfirm'
import type { useFilePreview } from '@/composables/useFilePreview'
import { renameSandboxFile, deleteSandboxFile, downloadSandboxFile } from '@/api/sandbox'
import { renameAsset, deleteAsset, refetchAsset } from '@/api/assets'

export interface SandboxFileActionTarget {
  label: string
  canPreview?: boolean
  canDownload?: boolean
  canRename?: boolean
  canRefetch?: boolean
  canDelete?: boolean
  previewUrl?: string
  downloadUrl?: string
  fileId?: number
  assetId?: number
  assetType?: string
  fileType?: string
  fileSize?: number
  conversationId?: number
}

interface DeleteDialogConfig {
  title: string
  subject: string
  detail: string
  confirmText: string
}

interface UseSandboxFileActionsOptions {
  filePreview: ReturnType<typeof useFilePreview>
  onRefresh: () => void | Promise<void>
  getDeleteDialogConfig: (target: SandboxFileActionTarget) => DeleteDialogConfig
}

function openExternalUrl(url?: string) {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

export function useSandboxFileActions(options: UseSandboxFileActionsOptions) {
  const { filePreview, onRefresh, getDeleteDialogConfig } = options

  async function handlePreview(
    target: SandboxFileActionTarget,
    options?: { startInEdit?: boolean },
  ) {
    if (!target.canPreview) return

    if (target.assetId) {
      if (target.assetType === 'URL' || target.assetType === 'YUQUE_URL') {
        openExternalUrl(target.previewUrl)
        return
      }
      await filePreview.openPreview({
        source: 'asset',
        assetId: target.assetId,
        label: target.label,
        fileType: target.fileType,
        fileSize: target.fileSize,
        autoOpenExternalUrl: true,
        startInEdit: options?.startInEdit === true,
      })
      return
    }

    if (!target.fileId || !target.conversationId) {
      openExternalUrl(target.previewUrl)
      return
    }

    await filePreview.openPreview({
      source: 'sandbox',
      conversationId: target.conversationId,
      fileId: target.fileId,
      label: target.label,
      fileType: target.fileType,
      fileSize: target.fileSize,
      autoOpenExternalUrl: true,
      startInEdit: options?.startInEdit === true,
    })
  }

  async function handleDownload(target: SandboxFileActionTarget) {
    if (!target.canDownload) return

    if (target.assetId) {
      await filePreview.openPreview({
        source: 'asset',
        assetId: target.assetId,
        label: target.label,
        fileType: target.fileType,
        fileSize: target.fileSize,
        autoOpenExternalUrl: false,
      })
      await filePreview.downloadCurrent()
      return
    }

    if (!target.fileId || !target.conversationId) {
      openExternalUrl(target.downloadUrl || target.previewUrl)
      return
    }

    try {
      const res = await downloadSandboxFile(target.conversationId, target.fileId)
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.download = target.label
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch {
      ElMessage.error('下载失败')
    }
  }

  async function handleRename(target: SandboxFileActionTarget) {
    if (!target.canRename) return

    try {
      const promptResult = await ElMessageBox.prompt('请输入新的文件名', '重命名文件', {
        inputValue: target.label,
        inputPlaceholder: '请输入新的文件名',
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        customClass: 'sandbox-confirm-dialog sandbox-rename-dialog',
        confirmButtonClass: 'sandbox-confirm-primary',
        cancelButtonClass: 'sandbox-confirm-secondary',
        inputValidator: (value: string) => {
          const next = value.trim()
          if (!next) return '文件名不能为空'
          if (next.includes('/') || next.includes('\\')) return '文件名不能包含路径分隔符'
          return true
        },
      })

      const nextName = typeof promptResult === 'object' && 'value' in promptResult ? String(promptResult.value).trim() : ''
      if (!nextName || nextName === target.label) return

      if (target.assetId) {
        const res = await renameAsset(target.assetId, nextName)
        if (res.code !== 0) {
          ElMessage.error(res.message || '重命名失败')
          return
        }
      } else if (target.fileId && target.conversationId) {
        const res = await renameSandboxFile(target.conversationId, target.fileId, nextName)
        if (res.code !== 0) {
          ElMessage.error(res.message || '重命名失败')
          return
        }
      } else {
        return
      }

      ElMessage.success('重命名成功')
      await onRefresh()
    } catch {
      // 用户取消
    }
  }

  async function handleDelete(target: SandboxFileActionTarget) {
    if (!target.canDelete) return

    try {
      await showDangerConfirm(getDeleteDialogConfig(target))

      if (target.assetId) {
        const res = await deleteAsset(target.assetId)
        if (res.code !== 0) {
          ElMessage.error(res.message || '删除失败')
          return
        }
      } else if (target.fileId && target.conversationId) {
        const res = await deleteSandboxFile(target.conversationId, target.fileId)
        if (res.code !== 0) {
          ElMessage.error(res.message || '删除失败')
          return
        }
      } else {
        return
      }

      ElMessage.success('删除成功')
      await onRefresh()
    } catch {
      // 用户取消
    }
  }

  async function handleRefetch(target: SandboxFileActionTarget) {
    if (!target.canRefetch || !target.assetId) return
    const res = await refetchAsset(target.assetId)
    if (res.code !== 0) {
      ElMessage.error(res.message || '重抓失败')
      return
    }
    ElMessage.success(res.message || '重抓任务已提交')
    await onRefresh()
  }

  return {
    handlePreview,
    handleDownload,
    handleRename,
    handleRefetch,
    handleDelete,
  }
}
