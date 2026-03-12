import { describe, expect, it } from 'vitest'
import type { Msg } from '@/types/chat'
import { shouldForceRefreshConversationDetailFromCache } from '@/utils/conversationCachePolicy'

function createMessage(partial: Partial<Msg>): Msg {
  return {
    clientKey: partial.clientKey || `msg-${Math.random().toString(36).slice(2)}`,
    role: partial.role || 'assistant',
    content: partial.content || '',
    ...partial,
  }
}

describe('conversationCachePolicy', () => {
  it('forces detail refresh when cached tail is an empty assistant placeholder and stream is no longer owned', () => {
    const cached = [
      createMessage({ role: 'user', content: 'hello', id: 1 }),
      createMessage({ role: 'assistant', content: '', timeline: [] }),
    ]

    expect(
      shouldForceRefreshConversationDetailFromCache({
        cachedMessages: cached,
        isConversationGenerating: false,
        isStreamOwnedByView: false,
      }),
    ).toBe(true)
  })

  it('does not force refresh for settled assistant content', () => {
    const cached = [
      createMessage({ role: 'user', content: 'hello', id: 1 }),
      createMessage({ role: 'assistant', content: 'done', id: 2 }),
    ]

    expect(
      shouldForceRefreshConversationDetailFromCache({
        cachedMessages: cached,
        isConversationGenerating: false,
        isStreamOwnedByView: false,
      }),
    ).toBe(false)
  })

  it('forces detail refresh when sidebar has unread reply signal even if cached assistant looks settled', () => {
    const cached = [
      createMessage({ role: 'user', content: 'hello', id: 1 }),
      createMessage({ role: 'assistant', content: 'done', id: 2 }),
    ]

    expect(
      shouldForceRefreshConversationDetailFromCache({
        cachedMessages: cached,
        isConversationGenerating: false,
        isStreamOwnedByView: false,
        hasSidebarSignal: true,
      }),
    ).toBe(true)
  })
})
