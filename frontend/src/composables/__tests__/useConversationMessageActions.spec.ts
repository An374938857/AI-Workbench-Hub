import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useConversationMessageActions } from '@/composables/useConversationMessageActions'
import type { Msg } from '@/types/chat'

function createLocalMessage(payload: Omit<Msg, 'clientKey'>): Msg {
  return {
    ...payload,
    clientKey: `${payload.role}-${Math.random()}`,
  }
}

describe('useConversationMessageActions', () => {
  it('passes file ids and referenced message ids when editing', async () => {
    const messages = ref<Msg[]>([
      createLocalMessage({ id: 10, role: 'user', content: 'old' }),
      createLocalMessage({ id: 11, role: 'assistant', content: 'old answer' }),
    ])
    const editMessage = vi.fn(async ({ callbacks }) => {
      callbacks.onDone?.({ message_id: 99 })
    })

    const actions = useConversationMessageActions({
      messages,
      isGenerating: ref(false),
      getCurrentConversationId: () => 5,
      getForkFromMessageId: () => null,
      clearForkState: () => {},
      acknowledgeAllExportHints: () => {},
      createLocalMessage,
      bindConversationStream: vi.fn(() => 'stream-edit'),
      releaseConversationStream: vi.fn(),
      isStreamOwnedBy: () => true,
      appendRunningToolCall: () => false,
      updateToolCallTimeline: () => false,
      markStreamDisconnected: () => {},
      onActionError: () => {},
      editMessage,
      regenerateMessage: vi.fn(),
      continueFromMessage: vi.fn(),
      forkConversation: vi.fn(),
      loadConversation: vi.fn(),
      loadConversationSkipCache: vi.fn(),
      loadConversationList: vi.fn(),
      finalizeVisibleConversationStream: vi.fn(),
      loadActiveSkills: vi.fn(),
      markWaitingSkillConfirmation: vi.fn(),
      onSkillActivationRequest: vi.fn(),
      scrollToBottom: () => {},
      showWarning: () => {},
      showError: () => {},
    })

    await actions.handleEdit(10, 'updated', [21, 22], [3, 4])

    expect(editMessage).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: 5,
      messageId: 10,
      content: 'updated',
      fileIds: [21, 22],
      referencedMessageIds: [3, 4],
    }))
  })

  it('continues from tool message and finalizes with done state', async () => {
    const messages = ref<Msg[]>([])
    const finalizeVisibleConversationStream = vi.fn()
    const loadActiveSkills = vi.fn()
    const loadConversationList = vi.fn().mockResolvedValue(undefined)
    const onSkillActivationRequest = vi.fn()
    const markWaitingSkillConfirmation = vi.fn()
    const bindConversationStream = vi.fn(() => 'stream-1')
    const releaseConversationStream = vi.fn()

    const actions = useConversationMessageActions({
      messages,
      isGenerating: ref(false),
      getCurrentConversationId: () => 9,
      getForkFromMessageId: () => null,
      clearForkState: () => {},
      acknowledgeAllExportHints: () => {},
      createLocalMessage,
      bindConversationStream,
      releaseConversationStream,
      isStreamOwnedBy: () => true,
      appendRunningToolCall: () => false,
      updateToolCallTimeline: () => false,
      markStreamDisconnected: () => {},
      onActionError: () => {},
      editMessage: vi.fn(),
      regenerateMessage: vi.fn(),
      continueFromMessage: vi.fn(async ({ callbacks }) => {
        callbacks.onSkillActivationRequest?.({ skill_id: 1 })
        callbacks.onDone?.({ message_id: 77 })
      }),
      forkConversation: vi.fn(),
      loadConversation: vi.fn(),
      loadConversationSkipCache: vi.fn(),
      loadConversationList,
      finalizeVisibleConversationStream,
      loadActiveSkills,
      markWaitingSkillConfirmation,
      onSkillActivationRequest,
      scrollToBottom: () => {},
      showWarning: () => {},
      showError: () => {},
    })

    await actions.handleContinueAfterSkillActivation(12, 34, '技能已激活，继续生成')

    expect(messages.value.at(-2)?.role).toBe('system_notice')
    expect(messages.value.at(-1)?.role).toBe('assistant')
    expect(bindConversationStream).toHaveBeenCalledWith(9, expect.any(AbortController), 'continue_from_tool')
    expect(releaseConversationStream).toHaveBeenCalledWith(9, 'stream-1', { clearGenerating: true })
    expect(markWaitingSkillConfirmation).toHaveBeenCalledWith(9)
    expect(onSkillActivationRequest).toHaveBeenCalledWith({ skill_id: 1 })
    expect(releaseConversationStream).toHaveBeenCalledWith(9, 'stream-1', { terminalReason: 'done' })
    expect(finalizeVisibleConversationStream).toHaveBeenCalledWith(9, 77)
    expect(loadConversationList).toHaveBeenCalled()
    expect(loadActiveSkills).toHaveBeenCalled()
  })

  it('continues from assistant branch and handles cancelled terminal', async () => {
    const messages = ref<Msg[]>([])
    const bindConversationStream = vi.fn(() => 'stream-2')
    const releaseConversationStream = vi.fn()
    const loadConversationSkipCache = vi.fn().mockResolvedValue(undefined)
    const loadConversationList = vi.fn().mockResolvedValue(undefined)
    const regenerateMessage = vi.fn(async ({ callbacks }) => {
      callbacks.onCancelled?.()
    })

    const actions = useConversationMessageActions({
      messages,
      isGenerating: ref(false),
      getCurrentConversationId: () => 15,
      getForkFromMessageId: () => null,
      clearForkState: () => {},
      acknowledgeAllExportHints: () => {},
      createLocalMessage,
      bindConversationStream,
      releaseConversationStream,
      isStreamOwnedBy: () => true,
      appendRunningToolCall: () => false,
      updateToolCallTimeline: () => false,
      markStreamDisconnected: () => {},
      onActionError: () => {},
      editMessage: vi.fn(),
      regenerateMessage,
      continueFromMessage: vi.fn(),
      forkConversation: vi.fn(),
      loadConversation: vi.fn(),
      loadConversationSkipCache,
      loadConversationList,
      finalizeVisibleConversationStream: vi.fn(),
      loadActiveSkills: vi.fn(),
      markWaitingSkillConfirmation: vi.fn(),
      onSkillActivationRequest: vi.fn(),
      scrollToBottom: () => {},
      showWarning: () => {},
      showError: () => {},
    })

    await actions.handleContinueAfterSkillActivation(55, null, '继续上一条回复')

    expect(bindConversationStream).toHaveBeenCalledWith(15, expect.any(AbortController), 'continue_from_assistant')
    expect(regenerateMessage).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: 15,
      messageId: 55,
    }))
    expect(releaseConversationStream).toHaveBeenCalledWith(15, 'stream-2', { terminalReason: 'cancelled' })
    expect(loadConversationSkipCache).toHaveBeenCalledWith(15)
    expect(loadConversationList).toHaveBeenCalled()
  })
})
