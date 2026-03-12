import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '@/stores/chat'
import { useConversationExecution } from '@/composables/useConversationExecution'
import type { SSECallbacks } from '@/utils/sse'
import {
  continueFromMessageSSE,
  editMessageSSE,
  forkConversationSSE,
  regenerateMessageSSE,
  sendMessageSSE,
} from '@/utils/sse'

vi.mock('@/utils/sse', () => ({
  sendMessageSSE: vi.fn().mockResolvedValue(undefined),
  editMessageSSE: vi.fn().mockResolvedValue(undefined),
  regenerateMessageSSE: vi.fn().mockResolvedValue(undefined),
  continueFromMessageSSE: vi.fn().mockResolvedValue(undefined),
  forkConversationSSE: vi.fn().mockResolvedValue(undefined),
}))

const callbacks: SSECallbacks = {
  onChunk: () => {},
  onDone: () => {},
  onTitleUpdated: () => {},
  onContextWarning: () => {},
  onError: () => {},
}

describe('useConversationExecution', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('aborts previous owner before starting a new action', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    const previousController = new AbortController()
    const previousAbortSpy = vi.spyOn(previousController, 'abort')
    chatStore.setAbortController(1, 'old-owner', previousController)
    chatStore.setStreamOwner(1, 'old-owner')
    chatStore.markConversationGenerating(1)
    chatStore.setConversationExecutionState(1, {
      state: 'streaming',
      streamSessionId: 'old-owner',
      actionType: 'send',
    })

    const nextController = new AbortController()
    const streamSessionId = execution.runConversationAction({
      conversationId: 1,
      actionType: 'send',
      abortController: nextController,
    })

    expect(previousAbortSpy).toHaveBeenCalledTimes(1)
    expect(chatStore.getStreamOwner(1)).toBe(streamSessionId)
    expect(chatStore.getAbortController(1)?.signal).toBe(nextController.signal)
    expect(chatStore.isConversationGenerating(1)).toBe(true)
    expect(chatStore.getConversationExecutionState(1)?.state).toBe('streaming')
  })

  it('marks stream_disconnected on disconnected terminal error', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    const streamSessionId = execution.runConversationAction({
      conversationId: 2,
      actionType: 'send',
      abortController: new AbortController(),
    })

    execution.handleActionErrorTerminal(2, streamSessionId, '连接已中断，请重试')

    expect(chatStore.isConversationGenerating(2)).toBe(false)
    expect(chatStore.getStreamOwner(2)).toBeUndefined()
    expect(chatStore.getConversationExecutionState(2)?.state).toBe('failed')
    expect(chatStore.getConversationExecutionState(2)?.lastTerminalReason).toBe('stream_disconnected')
  })

  it('cancelConversationAction aborts immediately and stores user_stop terminal reason', async () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    const controller = new AbortController()
    const abortSpy = vi.spyOn(controller, 'abort')

    execution.runConversationAction({
      conversationId: 3,
      actionType: 'regenerate',
      abortController: controller,
    })

    const remoteCancel = vi.fn().mockResolvedValue(undefined)
    const stopped = await execution.cancelConversationAction(3, {
      reason: 'user_stop',
      requestRemoteCancel: remoteCancel,
    })

    expect(stopped).toBe(true)
    expect(abortSpy).toHaveBeenCalledTimes(1)
    expect(remoteCancel).toHaveBeenCalledWith(3)
    expect(chatStore.isConversationGenerating(3)).toBe(false)
    expect(chatStore.getConversationExecutionState(3)?.state).toBe('idle')
    expect(chatStore.getConversationExecutionState(3)?.lastTerminalReason).toBe('user_stop')
  })

  it('delegates sse requests through execution layer wrappers', async () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    const abortSignal = new AbortController().signal

    await execution.sendMessage({
      conversationId: 5,
      content: 'hello',
      fileIds: [1],
      callbacks,
      abortSignal,
      referencedMessageIds: [11],
      providerId: 8,
      modelName: 'model-x',
      referenceMode: 'selected',
    })
    await execution.editMessage({
      conversationId: 5,
      messageId: 9,
      content: 'edit',
      fileIds: [],
      referencedMessageIds: [12, 13],
      callbacks,
      abortSignal,
    })
    await execution.regenerateMessage({
      conversationId: 5,
      messageId: 9,
      callbacks,
      abortSignal,
    })
    await execution.continueFromMessage({
      conversationId: 5,
      messageId: 9,
      callbacks,
      abortSignal,
    })
    await execution.forkConversation({
      conversationId: 5,
      fromMessageId: 9,
      content: 'fork',
      fileIds: [],
      callbacks,
      abortSignal,
    })

    expect(sendMessageSSE).toHaveBeenCalledWith(5, 'hello', [1], callbacks, abortSignal, [11], 8, 'model-x', 'selected')
    expect(editMessageSSE).toHaveBeenCalledWith(5, 9, 'edit', [], [12, 13], callbacks, abortSignal)
    expect(regenerateMessageSSE).toHaveBeenCalledWith(5, 9, callbacks, abortSignal)
    expect(continueFromMessageSSE).toHaveBeenCalledWith(5, 9, callbacks, abortSignal)
    expect(forkConversationSSE).toHaveBeenCalledWith(5, 9, 'fork', [], callbacks, abortSignal)
  })

  it('marks waiting skill confirmation only for owned stream', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    const streamSessionId = execution.runConversationAction({
      conversationId: 6,
      actionType: 'send',
      abortController: new AbortController(),
    })

    execution.markWaitingSkillConfirmation(6, 'other-stream')
    expect(chatStore.getConversationExecutionState(6)?.state).toBe('streaming')

    execution.markWaitingSkillConfirmation(6, streamSessionId)
    expect(chatStore.getConversationExecutionState(6)?.state).toBe('waiting_skill_confirmation')
  })

  it('clears waiting skill confirmation to streaming when resume starts', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    const streamSessionId = execution.runConversationAction({
      conversationId: 14,
      actionType: 'send',
      abortController: new AbortController(),
    })
    execution.markWaitingSkillConfirmation(14, streamSessionId)
    const updated = execution.clearWaitingSkillConfirmation(14, 'streaming')

    expect(updated).toBe(true)
    expect(chatStore.isConversationGenerating(14)).toBe(true)
    expect(chatStore.getConversationExecutionState(14)?.state).toBe('streaming')
  })

  it('clears waiting skill confirmation to idle when resume is not available', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    const streamSessionId = execution.runConversationAction({
      conversationId: 15,
      actionType: 'send',
      abortController: new AbortController(),
    })
    execution.markWaitingSkillConfirmation(15, streamSessionId)
    const updated = execution.clearWaitingSkillConfirmation(15, 'idle')

    expect(updated).toBe(true)
    expect(chatStore.isConversationGenerating(15)).toBe(false)
    expect(chatStore.getConversationExecutionState(15)?.state).toBe('idle')
  })

  it('cancels all owned actions on route switch and keeps foreign owners intact', async () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    const ownedController = new AbortController()
    const foreignController = new AbortController()
    const ownedAbortSpy = vi.spyOn(ownedController, 'abort')
    const foreignAbortSpy = vi.spyOn(foreignController, 'abort')

    const ownedSession = execution.runConversationAction({
      conversationId: 7,
      actionType: 'send',
      abortController: ownedController,
    })
    chatStore.setAbortController(8, 'other-view:stream:1', foreignController)
    chatStore.setStreamOwner(8, 'other-view:stream:1')
    chatStore.markConversationGenerating(8)

    await execution.cancelAllOwnedActions('route_switch')

    expect(ownedAbortSpy).toHaveBeenCalledTimes(1)
    expect(foreignAbortSpy).not.toHaveBeenCalled()
    expect(chatStore.getStreamOwner(7)).toBeUndefined()
    expect(chatStore.isConversationGenerating(7)).toBe(false)
    expect(chatStore.getConversationExecutionState(7)?.lastTerminalReason).toBe('route_switch')
    expect(chatStore.getStreamOwner(8)).toBe('other-view:stream:1')
    expect(chatStore.isConversationGenerating(8)).toBe(true)
    expect(ownedSession.startsWith('test-view:stream:')).toBe(true)
  })

  it('stores generic error terminal when message is not disconnected', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    const streamSessionId = execution.runConversationAction({
      conversationId: 9,
      actionType: 'edit',
      abortController: new AbortController(),
    })

    execution.handleActionErrorTerminal(9, streamSessionId, '服务端执行失败')

    expect(chatStore.isConversationGenerating(9)).toBe(false)
    expect(chatStore.getConversationExecutionState(9)?.state).toBe('failed')
    expect(chatStore.getConversationExecutionState(9)?.lastTerminalReason).toBe('error')
    expect(chatStore.getConversationExecutionState(9)?.lastErrorMessage).toBe('服务端执行失败')
  })

  it('ignores release when stream id does not match active owner', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    execution.runConversationAction({
      conversationId: 10,
      actionType: 'send',
      abortController: new AbortController(),
    })

    execution.releaseConversationStream(10, 'stale-stream', {
      terminalReason: 'done',
      clearGenerating: true,
    })

    expect(chatStore.isConversationGenerating(10)).toBe(true)
    expect(chatStore.getConversationExecutionState(10)?.state).toBe('streaming')
  })

  it('keeps local streaming state when stale idle live snapshot arrives right after start', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    execution.runConversationAction({
      conversationId: 11,
      actionType: 'send',
      abortController: new AbortController(),
    })

    execution.syncLiveState(11, { status: 'idle' })

    expect(chatStore.isConversationGenerating(11)).toBe(true)
    expect(chatStore.getConversationExecutionState(11)?.state).toBe('streaming')
  })

  it('applies idle live snapshot when there is no active stream owner', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    execution.runConversationAction({
      conversationId: 12,
      actionType: 'send',
      abortController: new AbortController(),
    })
    chatStore.clearStreamOwner(12)
    chatStore.clearAbortController(12)

    execution.syncLiveState(12, { status: 'idle' })

    expect(chatStore.isConversationGenerating(12)).toBe(false)
    expect(chatStore.getConversationExecutionState(12)?.state).toBe('idle')
  })

  it('can mark and clear local preparing state before stream starts', () => {
    const chatStore = useChatStore()
    const execution = useConversationExecution({ chatStore, ownerPrefix: 'test-view' })

    const marked = execution.markActionPreparing(13, 'send')
    expect(marked).toBe(true)
    expect(chatStore.isConversationGenerating(13)).toBe(false)
    expect(chatStore.getConversationExecutionState(13)?.state).toBe('preparing')
    expect(chatStore.getConversationExecutionState(13)?.actionType).toBe('send')

    const cleared = execution.clearActionPreparing(13, 'send')
    expect(cleared).toBe(true)
    expect(chatStore.getConversationExecutionState(13)?.state).toBe('idle')
  })
})
