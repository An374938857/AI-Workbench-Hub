import { nextTick, ref } from 'vue'
import type { TagInfo } from '@/types/chat'
import type { DangerConfirmOptions } from '@/composables/useDangerConfirm'

interface ConversationLite {
  id: number
}

interface UseConversationBatchActionsOptions {
  getConversations: () => ConversationLite[]
  getAllTags: () => TagInfo[]
  showDangerConfirm: (payload: DangerConfirmOptions) => Promise<unknown>
  showSuccess: (message: string) => void
  showError: (message: string) => void
  showInfo: (message: string) => void
  reloadConversationList: () => Promise<void>
  onDeletedConversations?: (ids: number[]) => void
  batchDeleteConversations: (ids: number[]) => Promise<unknown>
  batchExportConversations: (ids: number[], format: 'md') => Promise<{ data: unknown }>
  batchTagConversations: (ids: number[], tagId: number) => Promise<unknown>
}

export function useConversationBatchActions(options: UseConversationBatchActionsOptions) {
  const isSelectMode = ref(false)
  const selectedConvIds = ref<Set<number>>(new Set())
  const batchTagVisible = ref(false)
  const batchTagFloatingStyle = ref<Record<string, string>>({})

  function toggleSelectMode() {
    isSelectMode.value = !isSelectMode.value
    if (!isSelectMode.value) {
      selectedConvIds.value.clear()
      selectedConvIds.value = new Set(selectedConvIds.value)
    }
  }

  function toggleSelect(id: number) {
    if (selectedConvIds.value.has(id)) {
      selectedConvIds.value.delete(id)
    } else {
      selectedConvIds.value.add(id)
    }
    selectedConvIds.value = new Set(selectedConvIds.value)
  }

  function selectAll() {
    const conversations = options.getConversations()
    if (selectedConvIds.value.size === conversations.length) {
      selectedConvIds.value.clear()
    } else {
      selectedConvIds.value = new Set(conversations.map((conversation) => conversation.id))
    }
    selectedConvIds.value = new Set(selectedConvIds.value)
  }

  async function handleBatchDelete() {
    const ids = [...selectedConvIds.value]
    if (!ids.length) return

    await options.showDangerConfirm({
      title: '批量删除对话',
      subject: `${ids.length} 条对话`,
      detail: '删除后这些对话将无法恢复，请确认已完成必要备份。',
      confirmText: '确认删除',
    })

    await options.batchDeleteConversations(ids)
    options.showSuccess(`已删除 ${ids.length} 条对话`)

    selectedConvIds.value.clear()
    selectedConvIds.value = new Set(selectedConvIds.value)
    isSelectMode.value = false
    options.onDeletedConversations?.(ids)
    await options.reloadConversationList()
  }

  async function handleBatchExport() {
    const ids = [...selectedConvIds.value]
    if (!ids.length) return

    try {
      const res = await options.batchExportConversations(ids, 'md')
      const blobPart: BlobPart = res.data instanceof Blob
        ? res.data
        : (typeof res.data === 'string' ? res.data : JSON.stringify(res.data ?? ''))
      const blob = new Blob([blobPart], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `对话导出_${ids.length}条.md`
      anchor.click()
      URL.revokeObjectURL(url)
      options.showSuccess('导出成功')
    } catch {
      options.showError('导出失败')
    }
  }

  function updateBatchTagFloatingPosition(targetEl?: HTMLElement | null) {
    const tagButton = targetEl || (document.querySelector('.batch-toolbar .bt-tag-btn') as HTMLElement | null)
    if (!tagButton) return

    const rect = tagButton.getBoundingClientRect()
    batchTagFloatingStyle.value = {
      left: `${rect.left + rect.width / 2}px`,
      top: `${rect.top - 8}px`,
    }
  }

  async function handleBatchTag(event?: MouseEvent) {
    if (!options.getAllTags().length) {
      options.showInfo('请先创建标签')
      return
    }

    const nextVisible = !batchTagVisible.value
    if (nextVisible) {
      updateBatchTagFloatingPosition((event?.currentTarget as HTMLElement | null) || null)
      await nextTick()
    }
    batchTagVisible.value = nextVisible
  }

  async function confirmBatchTag(tagId: number) {
    const ids = [...selectedConvIds.value]
    if (!ids.length) return

    try {
      await options.batchTagConversations(ids, tagId)
      batchTagVisible.value = false
      options.showSuccess('标签已添加')
      await options.reloadConversationList()
    } catch (error: any) {
      options.showError(error?.response?.data?.message || '操作失败')
    }
  }

  function handleBatchTagOutsideClick(event: MouseEvent) {
    if (!batchTagVisible.value) return

    const target = event.target as HTMLElement | null
    if (!target) return
    if (target.closest('.batch-tag-floating') || target.closest('.batch-toolbar')) return
    batchTagVisible.value = false
  }

  function handleBatchTagWindowResize() {
    if (batchTagVisible.value) {
      updateBatchTagFloatingPosition()
    }
  }

  function handleBatchTagWindowScroll() {
    if (batchTagVisible.value) {
      updateBatchTagFloatingPosition()
    }
  }

  return {
    isSelectMode,
    selectedConvIds,
    batchTagVisible,
    batchTagFloatingStyle,
    toggleSelectMode,
    toggleSelect,
    selectAll,
    handleBatchDelete,
    handleBatchExport,
    handleBatchTag,
    confirmBatchTag,
    handleBatchTagOutsideClick,
    handleBatchTagWindowResize,
    handleBatchTagWindowScroll,
  }
}
