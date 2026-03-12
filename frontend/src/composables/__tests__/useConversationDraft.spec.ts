import { describe, expect, it } from 'vitest'
import { useConversationDraft } from '@/composables/useConversationDraft'

describe('useConversationDraft', () => {
  it('restores snapshot exactly after optimistic updates fail', () => {
    const draft = useConversationDraft()

    draft.inputText.value = '原始输入'
    draft.fileIds.value = [1, 2]
    draft.quotedMessages.value = [
      { id: 10, role: 'user', content: 'quoted', created_at: '2026-03-10 10:00:00' },
    ]
    draft.forkFromMessageId.value = 99
    draft.messagesBeforeFork.value = [
      { id: 1, role: 'assistant', content: 'history' } as any,
    ]

    const snapshot = draft.snapshotDraft()

    draft.clearDraft()
    draft.restoreDraft(snapshot)

    expect(draft.inputText.value).toBe('原始输入')
    expect(draft.fileIds.value).toEqual([1, 2])
    expect(draft.quotedMessages.value.map((item) => item.id)).toEqual([10])
    expect(draft.forkFromMessageId.value).toBe(99)
    expect(draft.messagesBeforeFork.value?.length).toBe(1)
  })

  it('clearDraft preserves fork state when preserveForkState=true', () => {
    const draft = useConversationDraft()

    draft.inputText.value = 'temp'
    draft.fileIds.value = [3]
    draft.quotedMessages.value = [
      { id: 11, role: 'assistant', content: 'q', created_at: '2026-03-10 10:01:00' },
    ]
    draft.forkFromMessageId.value = 101
    draft.messagesBeforeFork.value = [
      { id: 2, role: 'user', content: 'branch' } as any,
    ]

    draft.clearDraft({ preserveForkState: true })

    expect(draft.inputText.value).toBe('')
    expect(draft.fileIds.value).toEqual([])
    expect(draft.quotedMessages.value).toEqual([])
    expect(draft.forkFromMessageId.value).toBe(101)
    expect(draft.messagesBeforeFork.value?.length).toBe(1)
  })
})
