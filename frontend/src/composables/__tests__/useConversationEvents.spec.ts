import { describe, expect, it } from 'vitest'
import { parseSseEventBlock } from '@/composables/useConversationEvents'

describe('parseSseEventBlock', () => {
  it('parses event + data block into typed payload', () => {
    const block = [
      'event: conversation.updated',
      'data: {"type":"conversation.updated","conversation_id":532,"event_version":11,"patch":{"title":"A"}}',
    ].join('\n')

    const parsed = parseSseEventBlock(block)

    expect(parsed).not.toBeNull()
    expect(parsed?.event).toBe('conversation.updated')
    expect(parsed?.payload.conversation_id).toBe(532)
    expect(parsed?.payload.patch.title).toBe('A')
  })

  it('returns null for heartbeat/comment block', () => {
    const block = ': keep-alive'
    expect(parseSseEventBlock(block)).toBeNull()
  })

  it('returns null for invalid json payload', () => {
    const block = [
      'event: conversation.updated',
      'data: not-json',
    ].join('\n')

    expect(parseSseEventBlock(block)).toBeNull()
  })
})
