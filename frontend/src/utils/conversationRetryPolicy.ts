import type { Msg } from '@/types/chat'

export function getLatestRetryableAssistantMessageId(messages: Msg[]): number | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i]
    if (message?.role !== 'assistant') continue
    if (typeof message.id !== 'number') continue
    return message.id
  }
  return null
}
