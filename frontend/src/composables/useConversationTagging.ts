import { ref } from 'vue'
import type { Ref } from 'vue'
import type { TagInfo } from '@/types/chat'

interface TaggableConversation {
  id: number
  tags?: TagInfo[]
}

interface UseConversationTaggingOptions<T extends TaggableConversation> {
  conversations: Ref<T[]>
  activeTagFilter: Ref<number | null>
  fetchTagList: () => Promise<{ data?: TagInfo[] }>
  addConversationTag: (conversationId: number, tagId: number) => Promise<unknown>
  removeConversationTag: (conversationId: number, tagId: number) => Promise<unknown>
  resetPagination: () => void
  reloadConversationList: (append?: boolean) => Promise<void>
  showError: (message: string) => void
}

export function useConversationTagging<T extends TaggableConversation>(
  options: UseConversationTaggingOptions<T>,
) {
  const allTags = ref<TagInfo[]>([])

  async function loadTags() {
    try {
      const response = await options.fetchTagList()
      allTags.value = Array.isArray(response?.data) ? response.data : []
    } catch {
      // ignore
    }
  }

  async function handleTagFilter(tagId: number | null) {
    options.activeTagFilter.value = tagId
    options.resetPagination()
    await options.reloadConversationList(false)
  }

  function convHasTag(conversation: T, tagId: number): boolean {
    return conversation.tags?.some((tag) => tag.id === tagId) ?? false
  }

  async function handleTagCommand(command: string) {
    const [conversationIdRaw, tagIdRaw] = command.split(':')
    const conversationId = Number(conversationIdRaw)
    const tagId = Number(tagIdRaw)
    if (!conversationId || !tagId) return

    const conversation = options.conversations.value.find((item) => item.id === conversationId)
    if (!conversation) return

    try {
      if (convHasTag(conversation, tagId)) {
        await options.removeConversationTag(conversationId, tagId)
      } else {
        await options.addConversationTag(conversationId, tagId)
      }
      await options.reloadConversationList()
    } catch (error: any) {
      options.showError(error?.response?.data?.message || '操作失败')
    }
  }

  return {
    allTags,
    loadTags,
    handleTagFilter,
    convHasTag,
    handleTagCommand,
  }
}
