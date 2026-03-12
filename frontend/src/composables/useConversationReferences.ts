import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  clearReferenceSelection,
  confirmReferenceSelection,
  getReferencePanel,
  getReferenceState,
} from '@/api/references'
import type { ReferenceFileItem } from '@/api/references'
import type { ConversationBindingInfo } from '@/api/references'
import type { DangerConfirmOptions } from '@/composables/useDangerConfirm'
import { useFilePreview } from '@/composables/useFilePreview'
import { useSandboxFileActions } from '@/composables/useSandboxFileActions'
import type { ConversationFileTagType } from '@/utils/conversationFileTree'

export interface ReferenceStateLite {
  scope_snapshot_id: number | null
  selected_file_ids: number[]
  empty_mode: 'none' | 'sticky'
  selection_version: number
}

type ReferenceMode = 'persist_selection' | 'persist_empty' | 'turn_only_skip'

interface UseConversationReferencesOptions {
  getCurrentConversationId: () => number | null
  showDangerConfirm: (options: DangerConfirmOptions) => Promise<unknown>
}

export function useConversationReferences(options: UseConversationReferencesOptions) {
  const nextTurnReferenceMode = ref<'turn_only_skip' | null>(null)
  const referenceState = ref<ReferenceStateLite>({
    scope_snapshot_id: null,
    selected_file_ids: [],
    empty_mode: 'none',
    selection_version: 0,
  })
  const referenceAllFiles = ref<ReferenceFileItem[]>([])
  const referenceBinding = ref<ConversationBindingInfo | null>(null)
  const referenceSelectedIds = ref<number[]>([])
  const referenceFocusedFileId = ref<number | null>(null)
  const referenceDialogVisible = ref(false)
  const referenceDialogLoading = ref(false)
  let referenceDialogResolver: ((ok: boolean) => void) | null = null
  const referenceFilePreview = useFilePreview()

  const referenceTreeItems = computed(() =>
    referenceAllFiles.value.map((file) => ({
      key: file.file_id,
      label: file.file_name,
      path: formatReferenceDisplayPath(file, false),
      treePath: file.logical_path,
      displayPath: formatReferenceTreePath(file),
      fileType: file.mime_type || undefined,
      fileSize: file.file_size ?? undefined,
      updatedAt: file.updated_at ?? undefined,
      sourceLabel: undefined,
      sourceTagType: resolveReferenceSourceTagType(file.source_level),
      summary: file.summary || undefined,
      searchableText: `${file.file_name} ${file.logical_path} ${file.summary || ''} ${file.scope_title || ''} ${formatReferenceSourceLevel(file.source_level)}`.toLowerCase(),
      raw: file,
    })),
  )

  const focusedReferenceFile = computed(
    () => referenceAllFiles.value.find((file) => file.file_id === referenceFocusedFileId.value) || null,
  )

  const focusedReferenceInspectorTags = computed(() => {
    const file = focusedReferenceFile.value
    if (!file) return []
    const tags: Array<{
      label: string
      type?: 'primary' | 'success' | 'warning' | 'info' | 'danger'
      effect?: 'dark' | 'light' | 'plain'
    }> = [
      {
        label: formatReferenceSourceLevel(file.source_level),
        type: resolveReferenceSourceTagType(file.source_level),
      },
    ]
    if (referenceSelectedIds.value.includes(file.file_id)) {
      tags.push({ label: '已选', type: 'primary', effect: 'light' })
    }
    return tags
  })

  const focusedReferenceInspectorFields = computed(() => {
    const file = focusedReferenceFile.value
    if (!file) return []
    return [
      { label: '文件类型', value: file.mime_type || '未知' },
      { label: '文件大小', value: formatReferenceSize(file.file_size) },
      { label: '更新时间', value: formatReferenceTime(file.updated_at) },
      {
        label: '归属对象',
        value: formatReferenceScopeName(file.scope_type, file.scope_title, file.scope_id),
        multiline: true,
      },
    ]
  })

  const focusedReferenceInspectorSummary = computed(
    () => focusedReferenceFile.value?.summary || '该文件暂无摘要，可通过预览查看原始内容。',
  )

  const referenceSelectedCount = computed(() => referenceState.value.selected_file_ids.length)
  const showReferenceComposerBar = computed(
    () => !!options.getCurrentConversationId() && !!referenceState.value.scope_snapshot_id,
  )
  const referenceBindingSummary = computed(() => formatReferenceBindingSummary(referenceBinding.value))

  function resetReferenceStateLocal() {
    referenceState.value = {
      scope_snapshot_id: null,
      selected_file_ids: [],
      empty_mode: 'none',
      selection_version: 0,
    }
    referenceAllFiles.value = []
    referenceBinding.value = null
    referenceSelectedIds.value = []
    referenceFocusedFileId.value = null
    referenceDialogVisible.value = false
    referenceFilePreview.close()
    nextTurnReferenceMode.value = null
  }

  async function loadReferenceState(convId?: number | null) {
    const targetConvId = convId ?? options.getCurrentConversationId()
    if (!targetConvId) {
      resetReferenceStateLocal()
      return
    }
    try {
      const stateRes: any = await getReferenceState(targetConvId)
      const data = stateRes?.data || {}
      referenceState.value = {
        scope_snapshot_id: data.scope_snapshot_id ?? null,
        selected_file_ids: Array.isArray(data.selected_file_ids) ? data.selected_file_ids : [],
        empty_mode: data.empty_mode === 'sticky' ? 'sticky' : 'none',
        selection_version: Number(data.selection_version || 0),
      }
    } catch {
      resetReferenceStateLocal()
    }
  }

  async function loadReferencePanel(convId: number, query?: string) {
    const panelRes: any = await getReferencePanel(convId, query)
    const panelData = panelRes?.data || {}
    referenceAllFiles.value = Array.isArray(panelData.all_files) ? panelData.all_files : []
    referenceBinding.value = panelData?.binding || null
    if (panelData.scope_snapshot_id) {
      referenceState.value.scope_snapshot_id = panelData.scope_snapshot_id
    }
    syncFocusedReferenceFile()
  }

  function cancelReferenceDialog() {
    referenceDialogVisible.value = false
    referenceFilePreview.close()
    if (referenceDialogResolver) {
      referenceDialogResolver(false)
      referenceDialogResolver = null
    }
  }

  function resolveReferenceSourceTagType(sourceLevel: string): ConversationFileTagType {
    if (sourceLevel.includes('技能')) return 'warning'
    if (sourceLevel.includes('项目') || sourceLevel.includes('需求')) return 'success'
    return 'info'
  }

  function formatReferenceSourceLevel(sourceLevel?: string | null) {
    const value = String(sourceLevel || '').toUpperCase()
    if (value === 'PROJECT') return '项目资料'
    if (value === 'PROJECT_NODE') return '项目节点资料'
    if (value === 'REQUIREMENT') return '需求资料'
    if (value === 'REQUIREMENT_NODE') return '需求节点资料'
    if (value === 'WORKFLOW_CONVERSATION_SANDBOX') return '流程会话沙箱'
    return sourceLevel || '未标记'
  }

  function formatReferenceScopeName(scopeType?: string | null, scopeTitle?: string | null, scopeId?: number | null) {
    if (scopeTitle) return scopeTitle
    const normalized = String(scopeType || '').toUpperCase()
    if (normalized === 'PROJECT') return '未命名项目'
    if (normalized === 'REQUIREMENT') return '未命名需求'
    return '未命名范围'
  }

  function formatReferenceDisplayPath(file: ReferenceFileItem, includeCategory = true) {
    const parts: string[] = []
    if (includeCategory) {
      parts.push(formatReferenceSourceLevel(file.source_level))
    }
    parts.push(formatReferenceScopeName(file.scope_type, file.scope_title, file.scope_id))
    return parts.filter(Boolean).join(' / ')
  }

  function formatReferenceConversationLabel(file: ReferenceFileItem, conversationId: string) {
    const title = String(file.conversation_title || file.scope_title || '').trim()
    if (title) {
      if (title.includes(`#${conversationId}`) || title.includes(`会话 #${conversationId}`)) {
        return title
      }
      return `#${conversationId} ${title}`
    }
    return `#${conversationId}`
  }

  function formatReferenceTreePath(file: ReferenceFileItem): string {
    const rawParts = String(file.logical_path || '')
      .split('/')
      .map((part) => part.trim())
      .filter(Boolean)
    if (!rawParts.length) return formatReferenceDisplayPath(file, true)
    const firstUpper = rawParts[0]?.toUpperCase() || ''
    const hasConversationSegment = rawParts.some((part) => part.toUpperCase() === 'CONVERSATION')

    const displayParts = rawParts.map((part, idx) => {
      const upper = part.toUpperCase()
      const prevUpper = idx > 0 ? rawParts[idx - 1]?.toUpperCase() || '' : ''

      if (upper === 'WORKFLOW') {
        const scopeUpper = String(file.scope_type || '').toUpperCase()
        if (scopeUpper === 'PROJECT') return '项目'
        if (scopeUpper === 'REQUIREMENT') return '需求'
        return '流程'
      }
      if (upper === 'PROJECT') return '项目'
      if (upper === 'REQUIREMENT') return '需求'
      if (upper === 'CONVERSATION') return '对话'
      if (
        idx === 1
        && (firstUpper === 'PROJECT' || firstUpper === 'REQUIREMENT')
        && /^\d+$/.test(part)
      ) {
        const scopeTitle = String(file.scope_title || '').trim()
        if (scopeTitle) return scopeTitle
        return firstUpper === 'PROJECT' ? `项目 #${part}` : `需求 #${part}`
      }
      if (idx === 1 && firstUpper === 'WORKFLOW' && /^\d+$/.test(part)) {
        const scopeName = formatReferenceScopeName(file.scope_type, file.scope_title, file.scope_id)
        return scopeName || `流程实例 #${part}`
      }
      if (part === '_' && idx >= 2) return '节点（未绑定）'
      if (
        idx === 2
        && (firstUpper === 'WORKFLOW' || firstUpper === 'PROJECT' || firstUpper === 'REQUIREMENT')
        && hasConversationSegment
      ) {
        const nodeName = String(file.node_name || '').trim()
        return nodeName ? `节点：${nodeName}` : `节点：${part}`
      }
      if (prevUpper === 'CONVERSATION' && /^\d+$/.test(part)) {
        return formatReferenceConversationLabel(file, part)
      }
      return part
    })

    return displayParts.join(' / ')
  }

  function updateReferenceSelectedIds(value: Array<string | number>) {
    referenceSelectedIds.value = value
      .map((item) => Number(item))
      .filter((item) => Number.isFinite(item))
  }

  function setFocusedReferenceFile(fileId: number | null | undefined) {
    if (!fileId) {
      referenceFocusedFileId.value = referenceAllFiles.value[0]?.file_id ?? null
      return
    }
    referenceFocusedFileId.value = fileId
  }

  function syncFocusedReferenceFile(preferredIds: number[] = []) {
    const availableIds = new Set(referenceAllFiles.value.map((file) => file.file_id))
    const candidates = [
      referenceFocusedFileId.value,
      ...preferredIds,
      ...referenceSelectedIds.value,
      referenceAllFiles.value[0]?.file_id ?? null,
    ]

    for (const candidate of candidates) {
      if (candidate && availableIds.has(candidate)) {
        referenceFocusedFileId.value = candidate
        return
      }
    }
    referenceFocusedFileId.value = null
  }

  function toReferenceActionTarget(file: ReferenceFileItem) {
    if (
      file.source_kind === 'SANDBOX_FILE'
      && file.sandbox_file_id
      && file.conversation_id
    ) {
      return {
        label: file.file_name,
        canPreview: true,
        canDownload: true,
        fileId: file.sandbox_file_id,
        conversationId: file.conversation_id,
        fileType: file.mime_type || undefined,
        fileSize: file.file_size ?? undefined,
      }
    }
    return {
      label: file.file_name,
      canPreview: true,
      canDownload: true,
      assetId: file.file_id,
      fileType: file.mime_type || undefined,
      fileSize: file.file_size ?? undefined,
    }
  }

  const referenceFileActions = useSandboxFileActions({
    filePreview: referenceFilePreview,
    onRefresh: async () => undefined,
    getDeleteDialogConfig: (target) => ({
      title: '删除文件',
      subject: target.label,
      detail: '该弹窗不支持删除资料。',
      confirmText: '删除文件',
    }),
  })

  async function handleReferencePreview(file: ReferenceFileItem) {
    setFocusedReferenceFile(file.file_id)
    await referenceFileActions.handlePreview(toReferenceActionTarget(file))
  }

  async function handleReferenceDownload(file: ReferenceFileItem) {
    setFocusedReferenceFile(file.file_id)
    await referenceFileActions.handleDownload(toReferenceActionTarget(file))
  }

  function handleReferenceInspectorAction(actionKey: string) {
    const file = focusedReferenceFile.value
    if (!file) return
    if (actionKey === 'preview') {
      void handleReferencePreview(file)
      return
    }
    if (actionKey === 'download') {
      void handleReferenceDownload(file)
    }
  }

  function extractReferenceFile(raw: unknown): ReferenceFileItem | null {
    if (!raw || typeof raw !== 'object') return null
    const candidate = raw as Partial<ReferenceFileItem>
    if (!candidate.file_id || !candidate.file_name || !candidate.logical_path || !candidate.source_level) {
      return null
    }
    return candidate as ReferenceFileItem
  }

  function handleReferenceTreeItemClick(itemKey: string | number) {
    setFocusedReferenceFile(Number(itemKey))
  }

  function handleReferenceTreeItemDblClick(raw: unknown) {
    const file = extractReferenceFile(raw)
    if (!file) return
    void handleReferencePreview(file)
  }

  function formatReferenceSize(size?: number | null) {
    if (!size) return '未知'
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    return `${(size / 1024 / 1024).toFixed(2)} MB`
  }

  function formatReferenceTime(updatedAt?: string | null) {
    if (!updatedAt) return '未知'
    return new Date(updatedAt).toLocaleString('zh-CN')
  }

  function formatReferenceBindingSummary(binding?: ConversationBindingInfo | null) {
    if (!binding?.is_bound) return '当前对话暂未绑定项目或需求节点。'

    const scopeType = String(binding.scope_type || '').toUpperCase()
    const scopeTitle = String(binding.scope_title || '').trim() || (scopeType === 'PROJECT' ? '未命名项目' : '未命名需求')
    const nodeName = String(binding.node_name || '').trim() || '未命名节点'

    if (scopeType === 'PROJECT') {
      return `当前对话被项目绑定：${scopeTitle} - ${nodeName}`
    }
    if (scopeType === 'REQUIREMENT') {
      return `当前对话被需求绑定：${scopeTitle} - ${nodeName}`
    }
    return `当前对话已绑定：${scopeTitle} - ${nodeName}`
  }

  async function applyReferenceMode(mode: ReferenceMode) {
    const currentConvId = options.getCurrentConversationId()
    if (!currentConvId) return
    const selected = mode === 'persist_selection' ? referenceSelectedIds.value : []
    try {
      await confirmReferenceSelection(currentConvId, selected, mode)
      if (mode === 'turn_only_skip') {
        nextTurnReferenceMode.value = 'turn_only_skip'
      } else {
        nextTurnReferenceMode.value = null
      }
      await loadReferenceState(currentConvId)
      referenceDialogVisible.value = false
      if (referenceDialogResolver) {
        referenceDialogResolver(true)
        referenceDialogResolver = null
      }
    } catch {
      if (referenceDialogResolver) {
        referenceDialogResolver(false)
        referenceDialogResolver = null
      }
    }
  }

  async function handleClearReference() {
    const currentConvId = options.getCurrentConversationId()
    if (!currentConvId) return
    await options.showDangerConfirm({
      title: '清空默认引用',
      subject: '当前对话',
      detail: '清空后后续轮次将不再沿用当前引用集合，你仍可在发送前重新调整。',
      confirmText: '确认清空',
      confirmType: 'primary',
    })
    await clearReferenceSelection(currentConvId)
    await loadReferenceState(currentConvId)
    referenceAllFiles.value = []
    referenceSelectedIds.value = []
    referenceFocusedFileId.value = null
    referenceFilePreview.close()
    ElMessage.success('已清空默认引用')
  }

  async function openReferenceDialog(query?: string) {
    const currentConvId = options.getCurrentConversationId()
    if (!currentConvId) return
    referenceDialogLoading.value = true
    try {
      await loadReferencePanel(currentConvId, query)
      referenceSelectedIds.value = Array.from(
        new Set([
          ...referenceState.value.selected_file_ids,
        ]),
      )
      syncFocusedReferenceFile(referenceSelectedIds.value)
      referenceDialogVisible.value = true
    } finally {
      referenceDialogLoading.value = false
    }
  }

  return {
    nextTurnReferenceMode,
    referenceState,
    referenceAllFiles,
    referenceSelectedIds,
    referenceFocusedFileId,
    referenceDialogVisible,
    referenceDialogLoading,
    referenceFilePreview,
    referenceTreeItems,
    focusedReferenceFile,
    focusedReferenceInspectorTags,
    focusedReferenceInspectorFields,
    focusedReferenceInspectorSummary,
    referenceSelectedCount,
    referenceBindingSummary,
    showReferenceComposerBar,
    resetReferenceStateLocal,
    loadReferenceState,
    openReferenceDialog,
    cancelReferenceDialog,
    updateReferenceSelectedIds,
    handleReferenceTreeItemClick,
    handleReferenceTreeItemDblClick,
    handleReferenceInspectorAction,
    formatReferenceDisplayPath,
    applyReferenceMode,
    handleClearReference,
  }
}
