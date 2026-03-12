import type { useChatStore } from '@/stores/chat'
import {
  continueFromMessageSSE,
  editMessageSSE,
  forkConversationSSE,
  regenerateMessageSSE,
  sendMessageSSE,
} from '@/utils/sse'
import type { SSECallbacks } from '@/utils/sse'
import type { LiveExecutionState } from '@/types/chat'
import type {
  ActionTerminalReason,
  ActionTerminalResult,
  ConversationActionType,
  ConversationExecutionState,
  ConversationStreamAction,
} from '@/types/chatExecution'

interface UseConversationExecutionOptions {
  chatStore: ReturnType<typeof useChatStore>
  ownerPrefix: string
}

interface ReleaseConversationStreamOptions {
  clearGenerating?: boolean
  terminalReason?: ActionTerminalReason
  errorMessage?: string | null
}

interface CancelConversationActionOptions {
  reason: 'user_stop' | 'route_switch' | 'resume_replace' | 'unmount'
  requestRemoteCancel?: (conversationId: number) => Promise<unknown>
  suppressRemoteError?: boolean
}

function isErrorTerminalReason(reason: ActionTerminalReason) {
  return reason === 'error' || reason === 'throw' || reason === 'stream_disconnected'
}

function mapTerminalState(reason: ActionTerminalReason): ConversationExecutionState {
  if (reason === 'done') return 'completed'
  if (reason === 'cancelled' || reason === 'user_stop' || reason === 'route_switch' || reason === 'unmount' || reason === 'resume_replace') {
    return 'idle'
  }
  return 'failed'
}

function logExecution(event: string, payload: Record<string, unknown>) {
  if (!import.meta.env.DEV || import.meta.env.MODE === 'test') return
  console.info(`chat.execution.${event}`, payload)
}

interface SendMessageRequest {
  conversationId: number
  content: string
  fileIds: number[]
  callbacks: SSECallbacks
  abortSignal?: AbortSignal
  referencedMessageIds?: number[]
  providerId?: number | null
  modelName?: string | null
  referenceMode?: string | null
}

interface EditMessageRequest {
  conversationId: number
  messageId: number
  content: string
  fileIds: number[]
  referencedMessageIds: number[]
  callbacks: SSECallbacks
  abortSignal?: AbortSignal
}

interface RegenerateMessageRequest {
  conversationId: number
  messageId: number
  callbacks: SSECallbacks
  abortSignal?: AbortSignal
}

interface ContinueFromMessageRequest {
  conversationId: number
  messageId: number
  callbacks: SSECallbacks
  abortSignal?: AbortSignal
}

interface ForkConversationRequest {
  conversationId: number
  fromMessageId: number
  content: string
  fileIds: number[]
  callbacks: SSECallbacks
  abortSignal?: AbortSignal
}

export function useConversationExecution(options: UseConversationExecutionOptions) {
  const { chatStore, ownerPrefix } = options
  let streamSessionSeq = 0

  function createStreamSessionId() {
    streamSessionSeq += 1
    return `${ownerPrefix}:stream:${streamSessionSeq}`
  }

  function isConversationStreamOwnedByView(conversationId: number | null) {
    return chatStore.isStreamOwnedByPrefix(conversationId, ownerPrefix)
  }

  function finalizeConversationAction(result: ActionTerminalResult) {
    const {
      conversationId,
      streamSessionId,
      reason,
      errorMessage = null,
      clearGenerating = true,
    } = result
    releaseConversationStream(conversationId, streamSessionId, {
      clearGenerating,
      terminalReason: reason,
      errorMessage,
    })
  }

  function releaseConversationStream(
    conversationId: number,
    streamSessionId?: string,
    options: ReleaseConversationStreamOptions = {},
  ) {
    const activeOwner = chatStore.getStreamOwner(conversationId)
    const matchesCurrentStream = !streamSessionId || activeOwner === streamSessionId
    if (options.clearGenerating !== false && matchesCurrentStream) {
      chatStore.clearConversationGenerating(conversationId)
    }
    chatStore.clearAbortController(conversationId, streamSessionId)
    chatStore.clearStreamOwner(conversationId, streamSessionId)

    if (!matchesCurrentStream) {
      return
    }

    if (!options.terminalReason) {
      if (options.clearGenerating !== false) {
        chatStore.patchConversationExecutionState(conversationId, {
          state: 'idle',
          streamSessionId: null,
        })
      }
      return
    }

    const nextState = mapTerminalState(options.terminalReason)
    logExecution('terminal', {
      conversationId,
      streamSessionId: activeOwner ?? streamSessionId ?? null,
      reason: options.terminalReason,
      state: nextState,
      errorMessage: options.errorMessage ?? null,
    })
    chatStore.setConversationExecutionState(conversationId, {
      state: nextState,
      streamSessionId: null,
      lastTerminalReason: options.terminalReason,
      lastErrorMessage: options.errorMessage ?? null,
      lastDisconnectedAt: options.terminalReason === 'stream_disconnected' ? new Date().toISOString() : undefined,
    })
  }

  function runConversationAction(action: ConversationStreamAction) {
    const { conversationId, actionType, abortController } = action

    const existingController = chatStore.getAbortController(conversationId)
    const existingOwner = chatStore.getStreamOwner(conversationId)
    if (existingController && !existingController.signal.aborted) {
      existingController.abort()
    }
    if (existingOwner) {
      releaseConversationStream(conversationId, existingOwner, {
        clearGenerating: true,
        terminalReason: 'cancelled',
      })
    } else if (existingController) {
      chatStore.clearAbortController(conversationId)
    }

    const streamSessionId = createStreamSessionId()
    const startedAt = Date.now()
    chatStore.setConversationExecutionState(conversationId, {
      state: 'preparing',
      actionType,
      streamSessionId,
      startedAt,
      lastTerminalReason: null,
      lastErrorMessage: null,
    })
    chatStore.markConversationGenerating(conversationId)
    chatStore.setAbortController(conversationId, streamSessionId, abortController)
    chatStore.setStreamOwner(conversationId, streamSessionId)
    chatStore.setConversationExecutionState(conversationId, {
      state: 'streaming',
      actionType,
      streamSessionId,
      startedAt,
    })
    logExecution('start', {
      conversationId,
      actionType,
      streamSessionId,
      startedAt,
    })
    return streamSessionId
  }

  function markActionPreparing(conversationId: number, actionType: ConversationActionType) {
    if (chatStore.getStreamOwner(conversationId) || chatStore.isConversationGenerating(conversationId)) {
      return false
    }
    chatStore.setConversationExecutionState(conversationId, {
      state: 'preparing',
      actionType,
      streamSessionId: null,
      startedAt: Date.now(),
      lastTerminalReason: null,
      lastErrorMessage: null,
      lastDisconnectedAt: null,
    })
    return true
  }

  function clearActionPreparing(conversationId: number, actionType?: ConversationActionType) {
    if (chatStore.getStreamOwner(conversationId) || chatStore.isConversationGenerating(conversationId)) {
      return false
    }
    const snapshot = chatStore.getConversationExecutionState(conversationId)
    if (!snapshot || snapshot.state !== 'preparing') return false
    if (actionType && snapshot.actionType && snapshot.actionType !== actionType) return false
    chatStore.setConversationExecutionState(conversationId, {
      state: 'idle',
      actionType: snapshot.actionType,
      streamSessionId: null,
      lastTerminalReason: null,
      lastErrorMessage: null,
      lastDisconnectedAt: null,
    })
    return true
  }

  function markWaitingSkillConfirmation(
    conversationId: number,
    streamSessionId?: string,
  ) {
    const activeOwner = chatStore.getStreamOwner(conversationId)
    if (streamSessionId && activeOwner !== streamSessionId) return
    chatStore.setConversationExecutionState(conversationId, {
      state: 'waiting_skill_confirmation',
      streamSessionId: activeOwner ?? null,
    })
  }

  function clearWaitingSkillConfirmation(
    conversationId: number,
    nextState: 'streaming' | 'idle' = 'idle',
  ) {
    const snapshot = chatStore.getConversationExecutionState(conversationId)
    if (snapshot?.state !== 'waiting_skill_confirmation') return false

    if (nextState === 'streaming') {
      chatStore.markConversationGenerating(conversationId)
      chatStore.setConversationExecutionState(conversationId, {
        state: 'streaming',
        lastTerminalReason: null,
        lastErrorMessage: null,
      })
      return true
    }

    chatStore.clearConversationGenerating(conversationId)
    chatStore.setConversationExecutionState(conversationId, {
      state: 'idle',
      streamSessionId: null,
      lastTerminalReason: null,
      lastErrorMessage: null,
    })
    return true
  }

  async function cancelConversationAction(
    conversationId: number,
    options: CancelConversationActionOptions,
  ) {
    const activeOwner = chatStore.getStreamOwner(conversationId)
    const controller = chatStore.getAbortController(conversationId)
    const hasActiveStream = !!activeOwner || !!controller || chatStore.isConversationGenerating(conversationId)
    if (!hasActiveStream) return false

    chatStore.setConversationExecutionState(conversationId, {
      state: 'cancelling',
      streamSessionId: activeOwner ?? null,
      lastTerminalReason: null,
      lastErrorMessage: null,
    })
    logExecution('cancel', {
      conversationId,
      reason: options.reason,
      streamSessionId: activeOwner ?? null,
      hasController: !!controller,
    })

    if (controller && !controller.signal.aborted) {
      controller.abort()
    }

    if (activeOwner) {
      releaseConversationStream(conversationId, activeOwner, {
        terminalReason: options.reason,
        clearGenerating: true,
      })
    } else {
      chatStore.clearAbortController(conversationId)
      chatStore.clearStreamOwner(conversationId)
      chatStore.clearConversationGenerating(conversationId)
      chatStore.setConversationExecutionState(conversationId, {
        state: 'idle',
        streamSessionId: null,
        lastTerminalReason: options.reason,
      })
    }

    if (options.requestRemoteCancel) {
      try {
        await options.requestRemoteCancel(conversationId)
      } catch (error) {
        if (!options.suppressRemoteError) {
          throw error
        }
      }
    }

    return true
  }

  function handleActionErrorTerminal(
    conversationId: number,
    streamSessionId: string | undefined,
    errorMessage: string,
  ) {
    const reason: ActionTerminalReason = errorMessage.includes('连接已中断')
      ? 'stream_disconnected'
      : 'error'
    finalizeConversationAction({
      conversationId,
      streamSessionId,
      reason,
      errorMessage,
      clearGenerating: true,
    })
  }

  async function cancelAllOwnedActions(reason: 'unmount' | 'route_switch' = 'unmount') {
    const entries = Array.from(chatStore.streamOwners.entries())
    for (const [conversationId, ownerId] of entries) {
      if (!ownerId.startsWith(ownerPrefix)) continue
      const controller = chatStore.getAbortController(conversationId)
      if (controller && !controller.signal.aborted) {
        controller.abort()
      }
      releaseConversationStream(conversationId, ownerId, {
        terminalReason: reason,
        clearGenerating: true,
      })
    }
  }

  function sendMessage(request: SendMessageRequest) {
    return sendMessageSSE(
      request.conversationId,
      request.content,
      request.fileIds,
      request.callbacks,
      request.abortSignal,
      request.referencedMessageIds,
      request.providerId,
      request.modelName,
      request.referenceMode,
    )
  }

  function editMessage(request: EditMessageRequest) {
    return editMessageSSE(
      request.conversationId,
      request.messageId,
      request.content,
      request.fileIds,
      request.referencedMessageIds,
      request.callbacks,
      request.abortSignal,
    )
  }

  function regenerateMessage(request: RegenerateMessageRequest) {
    return regenerateMessageSSE(
      request.conversationId,
      request.messageId,
      request.callbacks,
      request.abortSignal,
    )
  }

  function continueFromMessage(request: ContinueFromMessageRequest) {
    return continueFromMessageSSE(
      request.conversationId,
      request.messageId,
      request.callbacks,
      request.abortSignal,
    )
  }

  function forkConversation(request: ForkConversationRequest) {
    return forkConversationSSE(
      request.conversationId,
      request.fromMessageId,
      request.content,
      request.fileIds,
      request.callbacks,
      request.abortSignal,
    )
  }

  function syncLiveState(conversationId: number, liveExecution?: LiveExecutionState | null) {
    const status = liveExecution?.status || 'idle'
    if (status === 'running') {
      chatStore.markConversationGenerating(conversationId)
      chatStore.setConversationExecutionState(conversationId, {
        state: 'streaming',
        lastErrorMessage: null,
      })
      return
    }
    if (status === 'waiting_skill_confirmation') {
      chatStore.markConversationGenerating(conversationId)
      chatStore.setConversationExecutionState(conversationId, {
        state: 'waiting_skill_confirmation',
        lastErrorMessage: null,
      })
      return
    }

    const snapshot = chatStore.getConversationExecutionState(conversationId)
    const activeOwner = chatStore.getStreamOwner(conversationId)
    const isLocallyExecuting = snapshot != null && (
      snapshot.state === 'preparing'
      || snapshot.state === 'streaming'
      || snapshot.state === 'waiting_skill_confirmation'
    )
    const shouldIgnoreStaleIdle = status === 'idle'
      && Boolean(activeOwner)
      && isLocallyExecuting

    // 轮询偶发会返回延迟的 idle，避免刚发起流式时被覆盖导致状态条闪退。
    if (shouldIgnoreStaleIdle) {
      return
    }

    chatStore.clearConversationGenerating(conversationId)
    if (status === 'error') {
      chatStore.setConversationExecutionState(conversationId, {
        state: 'failed',
        lastTerminalReason: 'error',
        lastErrorMessage: liveExecution?.error_message || null,
      })
      return
    }
    if (status === 'cancelled') {
      chatStore.setConversationExecutionState(conversationId, {
        state: 'idle',
        lastTerminalReason: 'cancelled',
        lastErrorMessage: null,
      })
      return
    }
    chatStore.setConversationExecutionState(conversationId, {
      state: 'idle',
    })
  }

  return {
    createStreamSessionId,
    isConversationStreamOwnedByView,
    runConversationAction,
    markActionPreparing,
    clearActionPreparing,
    finalizeConversationAction,
    releaseConversationStream,
    cancelConversationAction,
    cancelAllOwnedActions,
    markWaitingSkillConfirmation,
    clearWaitingSkillConfirmation,
    handleActionErrorTerminal,
    syncLiveState,
    isErrorTerminalReason,
    sendMessage,
    editMessage,
    regenerateMessage,
    continueFromMessage,
    forkConversation,
  }
}
