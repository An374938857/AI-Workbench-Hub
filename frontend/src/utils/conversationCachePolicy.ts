import type { Msg } from '@/types/chat'

export function isEmptyAssistantPlaceholder(message: Msg | undefined): boolean {
  if (!message || message.role !== 'assistant') return false
  if (typeof message.id === 'number') return false
  if ((message.content || '').trim()) return false
  const timeline = Array.isArray(message.timeline) ? message.timeline : []
  if (!timeline.length) return true

  return timeline.every((item) => {
    if (item.type === 'tool_call') return false
    if (item.type === 'thinking') {
      return !(item.content || '').trim()
    }
    return true
  })
}

export function shouldForceRefreshConversationDetailFromCache(payload: {
  cachedMessages: Msg[]
  isConversationGenerating: boolean
  isStreamOwnedByView: boolean
  hasSidebarSignal?: boolean
}): boolean {
  const {
    cachedMessages,
    isConversationGenerating,
    isStreamOwnedByView,
    hasSidebarSignal = false,
  } = payload
  if (!Array.isArray(cachedMessages) || cachedMessages.length === 0) {
    return false
  }
  if (hasSidebarSignal) {
    return true
  }
  if (isConversationGenerating && !isStreamOwnedByView) {
    return true
  }
  if (isStreamOwnedByView) {
    return false
  }

  const lastMessage = cachedMessages[cachedMessages.length - 1]
  return isEmptyAssistantPlaceholder(lastMessage)
}
