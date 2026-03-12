import { ChunkBuffer } from '@/composables/useChunkBuffer'
import type { Msg, GeneratedFile } from '@/types/chat'
import { buildSkillResumeKey, SkillResumeGuard } from '@/utils/skillResumeGuard'

interface UseConversationMessageActionsOptions {
  messages: { value: Msg[] }
  isGenerating: { value: boolean }
  getCurrentConversationId: () => number | null
  getForkFromMessageId: () => number | null
  clearForkState: () => void
  acknowledgeAllExportHints: () => void
  createLocalMessage: (payload: Omit<Msg, 'clientKey'>) => Msg
  bindConversationStream: (
    conversationId: number,
    controller: AbortController,
    actionType: 'edit' | 'regenerate' | 'fork' | 'continue_from_tool' | 'continue_from_assistant',
  ) => string
  releaseConversationStream: (
    conversationId: number,
    streamSessionId?: string,
    options?: {
      clearGenerating?: boolean
      terminalReason?: 'done' | 'cancelled' | 'error' | 'stream_disconnected' | 'throw' | 'user_stop' | 'route_switch' | 'unmount' | 'resume_replace'
    },
  ) => void
  isStreamOwnedBy: (conversationId: number, streamSessionId: string) => boolean
  appendRunningToolCall: (target: Msg[], data: { toolCallId: string; toolName: string; arguments?: string }) => boolean
  updateToolCallTimeline: (
    target: Msg[],
    toolCallId: string,
    patch: {
      status?: 'calling' | 'success' | 'error'
      progressTick?: number
      elapsedMs?: number
      elapsedSeconds?: number
      resultPreview?: string
      errorMessage?: string
      files?: GeneratedFile[]
    },
  ) => boolean
  markStreamDisconnected: (conversationId: number, streamSessionId: string) => void
  onActionError: (conversationId: number, streamSessionId: string, errorMessage: string) => void
  editMessage: (request: {
    conversationId: number
    messageId: number
    content: string
    fileIds: number[]
    referencedMessageIds: number[]
    callbacks: any
    abortSignal: AbortSignal
  }) => Promise<unknown>
  regenerateMessage: (request: {
    conversationId: number
    messageId: number
    callbacks: any
    abortSignal: AbortSignal
  }) => Promise<unknown>
  continueFromMessage: (request: {
    conversationId: number
    messageId: number
    callbacks: any
    abortSignal: AbortSignal
  }) => Promise<unknown>
  forkConversation: (request: {
    conversationId: number
    fromMessageId: number
    content: string
    fileIds: number[]
    callbacks: any
    abortSignal: AbortSignal
  }) => Promise<unknown>
  loadConversation: (conversationId: number) => Promise<unknown> | void
  loadConversationSkipCache: (conversationId: number) => Promise<unknown> | void
  loadConversationList: () => Promise<unknown> | void
  finalizeVisibleConversationStream: (conversationId: number, messageId?: number) => void
  loadActiveSkills: () => void
  markWaitingSkillConfirmation: (conversationId: number, streamSessionId?: string) => void
  onSkillActivationRequest: (payload: any) => Promise<unknown> | void
  scrollToBottom: (force?: boolean) => void
  showWarning: (message: string) => void
  showError: (message: string) => void
}

export function useConversationMessageActions(options: UseConversationMessageActionsOptions) {
  const continueResumeGuard = new SkillResumeGuard()

  function appendThinkingDelta(content: string) {
    const last = options.messages.value[options.messages.value.length - 1]
    if (last?.role !== 'assistant') return

    if (!last.timeline) {
      last.timeline = []
    }
    const current = last.timeline[last.timeline.length - 1]
    if (current && current.type === 'thinking' && current.isThinking) {
      current.content += content
    } else {
      last.timeline.push({ type: 'thinking', content, isThinking: true })
    }
    last.timeline = [...last.timeline]
    options.messages.value = [...options.messages.value]
    options.scrollToBottom()
  }

  function completeThinking() {
    const last = options.messages.value[options.messages.value.length - 1]
    if (last?.role !== 'assistant' || !last.timeline?.length) return
    const current = last.timeline[last.timeline.length - 1]
    if (current?.type === 'thinking') {
      current.isThinking = false
    }
    last.timeline = [...last.timeline]
    options.messages.value = [...options.messages.value]
  }

  function createCommonCallbacks(
    conversationId: number,
    streamSessionId: string,
    chunkBuffer: ChunkBuffer,
    onDone: (doneData?: { message_id?: number }) => void,
    onCancelled: () => void,
  ) {
    return {
      onChunk: (content: string) => chunkBuffer.append(content),
      onThinkingDelta: (content: string) => appendThinkingDelta(content),
      onThinkingDone: () => completeThinking(),
      onDone,
      onCancelled,
      onToolCallStart: (data: { toolCallId: string; toolName: string; arguments?: string }) => {
        if (options.appendRunningToolCall(options.messages.value, data)) {
          options.messages.value = [...options.messages.value]
          options.scrollToBottom()
        }
      },
      onToolCallProgress: (data: { toolCallId: string; progressTick: number; elapsedMs: number; elapsedSeconds: number }) => {
        if (options.updateToolCallTimeline(options.messages.value, data.toolCallId, {
          status: 'calling',
          progressTick: data.progressTick,
          elapsedMs: data.elapsedMs,
          elapsedSeconds: data.elapsedSeconds,
        })) {
          options.messages.value = [...options.messages.value]
        }
      },
      onToolCallResult: (data: { toolCallId: string; resultPreview?: string }) => {
        if (options.updateToolCallTimeline(options.messages.value, data.toolCallId, {
          status: 'success',
          progressTick: undefined,
          elapsedMs: undefined,
          elapsedSeconds: undefined,
          resultPreview: data.resultPreview,
          errorMessage: undefined,
        })) {
          options.messages.value = [...options.messages.value]
        }
      },
      onToolCallError: (data: { toolCallId: string; errorMessage: string }) => {
        if (options.updateToolCallTimeline(options.messages.value, data.toolCallId, {
          status: 'error',
          progressTick: undefined,
          elapsedMs: undefined,
          elapsedSeconds: undefined,
          errorMessage: data.errorMessage,
          resultPreview: undefined,
        })) {
          options.messages.value = [...options.messages.value]
        }
      },
      onToolCallFiles: (data: { toolCallId: string; files: Array<{ file_id: number; filename: string; file_size: number }> }) => {
        if (options.updateToolCallTimeline(options.messages.value, data.toolCallId, {
          files: data.files.map((file) => ({
            fileId: file.file_id,
            filename: file.filename,
            fileSize: file.file_size,
          })),
        })) {
          options.messages.value = [...options.messages.value]
        }
      },
      onTitleUpdated: () => {},
      onContextWarning: (message: string) => options.showWarning(message),
      onSkillActivationRequest: (payload: any) => {
        if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
        options.releaseConversationStream(conversationId, streamSessionId, {
          clearGenerating: true,
        })
        options.markWaitingSkillConfirmation(conversationId)
        void options.onSkillActivationRequest(payload)
      },
      onStreamDisconnected: () => {
        options.markStreamDisconnected(conversationId, streamSessionId)
      },
      onError: (message: string) => {
        if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
        chunkBuffer.destroy()
        options.onActionError(conversationId, streamSessionId, message)
        options.showError(message)
      },
    }
  }

  async function handleEdit(
    messageId: number,
    newContent: string,
    fileIds: number[] = [],
    referencedMessageIds: number[] = [],
  ) {
    options.acknowledgeAllExportHints()

    const conversationId = options.getCurrentConversationId()
    if (!conversationId || options.isGenerating.value) return

    const editIndex = options.messages.value.findIndex((message) => message.id === messageId)
    if (editIndex >= 0) {
      options.messages.value = options.messages.value.slice(0, editIndex)
    }

    options.messages.value.push(options.createLocalMessage({ role: 'user', content: newContent }))
    options.messages.value.push(options.createLocalMessage({ role: 'assistant', content: '', timeline: [] }))

    const abortController = new AbortController()
    const streamSessionId = options.bindConversationStream(conversationId, abortController, 'edit')
    const chunkBuffer = new ChunkBuffer((content) => {
      const last = options.messages.value[options.messages.value.length - 1]
      if (last?.role === 'assistant') last.content += content
      options.scrollToBottom()
    })

    const callbacks = createCommonCallbacks(
      conversationId,
      streamSessionId,
      chunkBuffer,
      () => {
        if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
        chunkBuffer.destroy()
        options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'done' })
        void options.loadConversation(conversationId)
        void options.loadConversationList()
      },
      () => {
        if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
        chunkBuffer.destroy()
        options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'cancelled' })
        void options.loadConversation(conversationId)
        void options.loadConversationList()
      },
    )

    await options.editMessage({
      conversationId,
      messageId,
      content: newContent,
      fileIds,
      referencedMessageIds,
      callbacks,
      abortSignal: abortController.signal,
    }).catch(() => {
      if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
      options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'cancelled' })
    })
  }

  async function handleRegenerate(messageId: number) {
    options.acknowledgeAllExportHints()

    const conversationId = options.getCurrentConversationId()
    if (!conversationId || options.isGenerating.value) return

    const regenerateIndex = options.messages.value.findIndex((message) => message.id === messageId)
    if (regenerateIndex >= 0) {
      options.messages.value = options.messages.value.slice(0, regenerateIndex)
    }

    options.messages.value.push(options.createLocalMessage({ role: 'assistant', content: '', timeline: [] }))

    const abortController = new AbortController()
    const streamSessionId = options.bindConversationStream(conversationId, abortController, 'regenerate')
    const chunkBuffer = new ChunkBuffer((content) => {
      const last = options.messages.value[options.messages.value.length - 1]
      if (last?.role === 'assistant') last.content += content
      options.scrollToBottom()
    })

    const callbacks = createCommonCallbacks(
      conversationId,
      streamSessionId,
      chunkBuffer,
      () => {
        if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
        chunkBuffer.destroy()
        options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'done' })
        void options.loadConversation(conversationId)
        void options.loadConversationList()
      },
      () => {
        if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
        chunkBuffer.destroy()
        options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'cancelled' })
        void options.loadConversation(conversationId)
        void options.loadConversationList()
      },
    )

    await options.regenerateMessage({
      conversationId,
      messageId,
      callbacks,
      abortSignal: abortController.signal,
    }).catch(() => {
      if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
      options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'cancelled' })
    })
  }

  async function handleSendFork(content: string) {
    options.acknowledgeAllExportHints()

    const conversationId = options.getCurrentConversationId()
    const fromMessageId = options.getForkFromMessageId()
    if (!conversationId || !fromMessageId || options.isGenerating.value) return

    options.clearForkState()

    options.messages.value.push(options.createLocalMessage({ role: 'user', content }))
    options.messages.value.push(options.createLocalMessage({ role: 'assistant', content: '', timeline: [] }))
    options.scrollToBottom(true)

    const abortController = new AbortController()
    const streamSessionId = options.bindConversationStream(conversationId, abortController, 'fork')
    const chunkBuffer = new ChunkBuffer((chunk) => {
      const last = options.messages.value[options.messages.value.length - 1]
      if (last?.role === 'assistant') last.content += chunk
      options.scrollToBottom()
    })

    const callbacks = createCommonCallbacks(
      conversationId,
      streamSessionId,
      chunkBuffer,
      () => {
        if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
        chunkBuffer.destroy()
        options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'done' })
        void options.loadConversation(conversationId)
        void options.loadConversationList()
      },
      () => {
        if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
        chunkBuffer.destroy()
        options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'cancelled' })
        void options.loadConversation(conversationId)
        void options.loadConversationList()
      },
    )

    await options.forkConversation({
      conversationId,
      fromMessageId,
      content,
      fileIds: [],
      callbacks,
      abortSignal: abortController.signal,
    }).catch(() => {
      if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
      options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'cancelled' })
    })
  }

  async function handleContinueAfterSkillActivation(
    assistantMessageId: number | null,
    toolMessageId: number | null,
    notice: string,
  ) {
    const conversationId = options.getCurrentConversationId()
    if (!conversationId || options.isGenerating.value) return
    const resumeKey = buildSkillResumeKey({
      assistantMessageId,
      toolMessageId,
    })
    if (!resumeKey) return
    if (!continueResumeGuard.tryBegin(conversationId, resumeKey)) return

    try {
      options.messages.value = [
        ...options.messages.value,
        options.createLocalMessage({ role: 'system_notice', content: notice }),
        options.createLocalMessage({ role: 'assistant', content: '', timeline: [] }),
      ]

      const abortController = new AbortController()
      const streamSessionId = options.bindConversationStream(
        conversationId,
        abortController,
        toolMessageId ? 'continue_from_tool' : 'continue_from_assistant',
      )
      const chunkBuffer = new ChunkBuffer((content) => {
        const last = options.messages.value[options.messages.value.length - 1]
        if (last?.role === 'assistant') last.content += content
        options.scrollToBottom()
      })

      const callbacks = createCommonCallbacks(
        conversationId,
        streamSessionId,
        chunkBuffer,
        (doneData?: { message_id?: number }) => {
          if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
          chunkBuffer.destroy()
          options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'done' })
          options.finalizeVisibleConversationStream(conversationId, doneData?.message_id)
          void options.loadConversationList()
          options.loadActiveSkills()
        },
        () => {
          if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
          chunkBuffer.destroy()
          options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'cancelled' })
          void options.loadConversationSkipCache(conversationId)
          void options.loadConversationList()
        },
      )

      const continueSSE = toolMessageId
        ? options.continueFromMessage({
          conversationId,
          messageId: toolMessageId,
          callbacks,
          abortSignal: abortController.signal,
        })
        : options.regenerateMessage({
          conversationId,
          messageId: assistantMessageId!,
          callbacks,
          abortSignal: abortController.signal,
        })

      await continueSSE.catch(() => {
        if (!options.isStreamOwnedBy(conversationId, streamSessionId)) return
        options.releaseConversationStream(conversationId, streamSessionId, { terminalReason: 'cancelled' })
      })
    } finally {
      continueResumeGuard.end(conversationId, resumeKey)
    }
  }

  return {
    handleEdit,
    handleRegenerate,
    handleSendFork,
    handleContinueAfterSkillActivation,
  }
}
