import { describe, expect, it } from 'vitest'
import type { Msg } from '@/types/chat'
import { getLatestRetryableAssistantMessageId } from '@/utils/conversationRetryPolicy'

function msg(payload: Partial<Msg> & Pick<Msg, 'role' | 'content'>): Msg {
  return {
    clientKey: `k-${Math.random()}`,
    ...payload,
  }
}

describe('conversationRetryPolicy', () => {
  it('returns latest assistant message id as retry target', () => {
    const messages: Msg[] = [
      msg({ id: 11, role: 'user', content: 'hi' }),
      msg({ id: 12, role: 'assistant', content: 'first' }),
      msg({ id: 13, role: 'assistant', content: 'second' }),
    ]

    expect(getLatestRetryableAssistantMessageId(messages)).toBe(13)
  })

  it('ignores assistant placeholders without persisted id', () => {
    const messages: Msg[] = [
      msg({ id: 21, role: 'user', content: 'q' }),
      msg({ id: 22, role: 'assistant', content: 'partial' }),
      msg({ role: 'assistant', content: '' }),
    ]

    expect(getLatestRetryableAssistantMessageId(messages)).toBe(22)
  })

  it('returns null when no retryable assistant exists', () => {
    const messages: Msg[] = [
      msg({ id: 31, role: 'user', content: 'only user' }),
      msg({ role: 'assistant', content: '' }),
      msg({ role: 'system_notice', content: 'notice' }),
    ]

    expect(getLatestRetryableAssistantMessageId(messages)).toBeNull()
  })
})
