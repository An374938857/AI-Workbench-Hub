import { ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatStore } from '@/stores/chat'
import { useConversationExecution } from '@/composables/useConversationExecution'
import { useConversationMessageActions } from '@/composables/useConversationMessageActions'
import type { Msg } from '@/types/chat'

vi.mock('@/utils/sse', () => ({
  sendMessageSSE: vi.fn().mockResolvedValue(undefined),
  editMessageSSE: vi.fn().mockResolvedValue(undefined),
  regenerateMessageSSE: vi.fn().mockResolvedValue(undefined),
  continueFromMessageSSE: vi.fn().mockResolvedValue(undefined),
  forkConversationSSE: vi.fn().mockResolvedValue(undefined),
}))

function createLocalMessage(payload: Omit<Msg, 'clientKey'>): Msg {
  return {
    ...payload,
    clientKey: `${payload.role}-${Math.random()}`,
  }
}

function createMessageActionsHarness(params: {
  conversationId: number
  forkFromMessageId?: number | null
  continueFromMessage?: (request: any) => Promise<unknown>
  regenerateMessage?: (request: any) => Promise<unknown>
  forkConversation?: (request: any) => Promise<unknown>
  onSkillActivationRequest?: (payload: any) => void
}) {
  const chatStore = useChatStore()
  const execution = useConversationExecution({ chatStore, ownerPrefix: 'chat-view-test' })
  const messages = ref<Msg[]>([])
  const isGenerating = ref(false)

  const actions = useConversationMessageActions({
    messages,
    isGenerating,
    getCurrentConversationId: () => params.conversationId,
    getForkFromMessageId: () => params.forkFromMessageId ?? null,
    clearForkState: () => {},
    acknowledgeAllExportHints: () => {},
    createLocalMessage,
    bindConversationStream: (conversationId, controller, actionType) =>
      execution.runConversationAction({ conversationId, actionType, abortController: controller }),
    releaseConversationStream: (conversationId, streamSessionId, options) =>
      execution.releaseConversationStream(conversationId, streamSessionId, options),
    isStreamOwnedBy: (conversationId, streamSessionId) =>
      chatStore.isStreamOwnedBy(conversationId, streamSessionId),
    appendRunningToolCall: () => false,
    updateToolCallTimeline: () => false,
    markStreamDisconnected: (conversationId, streamSessionId) => {
      execution.finalizeConversationAction({
        conversationId,
        streamSessionId,
        reason: 'stream_disconnected',
        errorMessage: '连接已中断，请重试',
      })
    },
    onActionError: (conversationId, streamSessionId, errorMessage) =>
      execution.handleActionErrorTerminal(conversationId, streamSessionId, errorMessage),
    editMessage: vi.fn().mockResolvedValue(undefined),
    regenerateMessage: params.regenerateMessage || vi.fn().mockResolvedValue(undefined),
    continueFromMessage: params.continueFromMessage || vi.fn().mockResolvedValue(undefined),
    forkConversation: params.forkConversation || vi.fn().mockResolvedValue(undefined),
    loadConversation: vi.fn().mockResolvedValue(undefined),
    loadConversationSkipCache: vi.fn().mockResolvedValue(undefined),
    loadConversationList: vi.fn().mockResolvedValue(undefined),
    finalizeVisibleConversationStream: () => {},
    loadActiveSkills: () => {},
    markWaitingSkillConfirmation: (conversationId, streamSessionId) =>
      execution.markWaitingSkillConfirmation(conversationId, streamSessionId),
    onSkillActivationRequest: (payload) => params.onSkillActivationRequest?.(payload),
    scrollToBottom: () => {},
    showWarning: () => {},
    showError: () => {},
  })

  return { actions, execution, chatStore, messages }
}

describe('Chat execution integration flows', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('send -> done terminal', async () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'chat-view-test' })
    const streamSessionId = execution.runConversationAction({
      conversationId: 1,
      actionType: 'send',
      abortController: new AbortController(),
    })

    execution.finalizeConversationAction({
      conversationId: 1,
      streamSessionId,
      reason: 'done',
    })

    expect(chatStore.isConversationGenerating(1)).toBe(false)
    expect(chatStore.getConversationExecutionState(1)?.state).toBe('completed')
    expect(chatStore.getConversationExecutionState(1)?.lastTerminalReason).toBe('done')
  })

  it('send -> stream_disconnected terminal', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'chat-view-test' })
    const streamSessionId = execution.runConversationAction({
      conversationId: 2,
      actionType: 'send',
      abortController: new AbortController(),
    })

    execution.handleActionErrorTerminal(2, streamSessionId, '连接已中断，请重试')

    expect(chatStore.isConversationGenerating(2)).toBe(false)
    expect(chatStore.getConversationExecutionState(2)?.state).toBe('failed')
    expect(chatStore.getConversationExecutionState(2)?.lastTerminalReason).toBe('stream_disconnected')
  })

  it('send -> stop (user_stop) terminal', async () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'chat-view-test' })
    const controller = new AbortController()
    const abortSpy = vi.spyOn(controller, 'abort')

    execution.runConversationAction({
      conversationId: 3,
      actionType: 'send',
      abortController: controller,
    })
    await execution.cancelConversationAction(3, {
      reason: 'user_stop',
      requestRemoteCancel: vi.fn().mockResolvedValue(undefined),
    })

    expect(abortSpy).toHaveBeenCalledTimes(1)
    expect(chatStore.isConversationGenerating(3)).toBe(false)
    expect(chatStore.getConversationExecutionState(3)?.lastTerminalReason).toBe('user_stop')
  })

  it('send -> skill_activation_request switches to waiting and releases stream owner', async () => {
    const skillActivationSpy = vi.fn()
    const harness = createMessageActionsHarness({
      conversationId: 4,
      continueFromMessage: vi.fn(async ({ callbacks }) => {
        callbacks.onSkillActivationRequest?.({ skill_id: 101, skill_name: 'mock-skill' })
        callbacks.onDone?.({ message_id: 999 })
      }),
      onSkillActivationRequest: (payload) => skillActivationSpy(payload),
    })

    await harness.actions.handleContinueAfterSkillActivation(11, 12, '继续生成')

    expect(skillActivationSpy).toHaveBeenCalledWith({ skill_id: 101, skill_name: 'mock-skill' })
    expect(harness.chatStore.getConversationExecutionState(4)?.state).toBe('waiting_skill_confirmation')
    expect(harness.chatStore.getConversationExecutionState(4)?.lastTerminalReason).toBeNull()
    expect(harness.chatStore.getStreamOwner(4)).toBeUndefined()
    expect(harness.chatStore.isConversationGenerating(4)).toBe(false)
  })

  it('edit -> route_switch terminal', async () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'chat-view-test' })
    execution.runConversationAction({
      conversationId: 5,
      actionType: 'edit',
      abortController: new AbortController(),
    })

    await execution.cancelAllOwnedActions('route_switch')

    expect(chatStore.isConversationGenerating(5)).toBe(false)
    expect(chatStore.getConversationExecutionState(5)?.state).toBe('idle')
    expect(chatStore.getConversationExecutionState(5)?.lastTerminalReason).toBe('route_switch')
  })

  it('fork -> fetch_throw falls back to cancelled terminal', async () => {
    const harness = createMessageActionsHarness({
      conversationId: 6,
      forkFromMessageId: 88,
      forkConversation: vi.fn().mockRejectedValue(new Error('network fail')),
    })

    await harness.actions.handleSendFork('new branch question')

    expect(harness.chatStore.isConversationGenerating(6)).toBe(false)
    expect(harness.chatStore.getConversationExecutionState(6)?.state).toBe('idle')
    expect(harness.chatStore.getConversationExecutionState(6)?.lastTerminalReason).toBe('cancelled')
    expect(harness.messages.value.some((msg) => msg.role === 'assistant')).toBe(true)
  })
})
