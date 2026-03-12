import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Msg } from '@/types/chat'
import type { ConversationActionType, ConversationExecutionSnapshot, ConversationExecutionState, ActionTerminalReason } from '@/types/chatExecution'

export interface ChatMessage {
  id?: number
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at?: string
}

interface AbortControllerEntry {
  ownerId: string
  controller: AbortController
}

export const useChatStore = defineStore('chat', () => {
  const currentConversationId = ref<number | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isGenerating = ref(false)
  const conversationTitle = ref('')
  const highlightConversationId = ref<number | null>(null)
  const pendingFocusConversationId = ref<number | null>(null)
  const messageCache = ref<Map<number, Msg[]>>(new Map())
  const generatingConversationIds = ref<Set<number>>(new Set())
  const completedConversationIds = ref<Set<number>>(new Set())
  const abortControllers = ref<Map<number, AbortControllerEntry>>(new Map())
  const streamOwners = ref<Map<number, string>>(new Map())
  const conversationExecutionStates = ref<Map<number, ConversationExecutionSnapshot>>(new Map())

  function setConversation(id: number, title: string, msgs: ChatMessage[]) {
    currentConversationId.value = id
    conversationTitle.value = title
    messages.value = msgs
  }

  function appendChunk(content: string) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content += content
    } else {
      messages.value.push({ role: 'assistant', content })
    }
  }

  function addUserMessage(content: string) {
    messages.value.push({ role: 'user', content })
  }

  function triggerHighlight(conversationId: number) {
    pendingFocusConversationId.value = conversationId
    highlightConversationId.value = conversationId
    setTimeout(() => {
      if (highlightConversationId.value === conversationId) {
        highlightConversationId.value = null
      }
    }, 2000)
  }

  function clearPendingFocusConversation(conversationId?: number) {
    if (conversationId != null && pendingFocusConversationId.value !== conversationId) return
    pendingFocusConversationId.value = null
  }

  function cacheConversationMessages(conversationId: number, conversationMessages: Msg[]) {
    const next = new Map(messageCache.value)
    next.set(conversationId, conversationMessages)
    messageCache.value = next
  }

  function getCachedConversationMessages(conversationId: number) {
    return messageCache.value.get(conversationId)
  }

  function clearCachedConversationMessages(conversationId: number) {
    if (!messageCache.value.has(conversationId)) return
    const next = new Map(messageCache.value)
    next.delete(conversationId)
    messageCache.value = next
  }

  function markConversationGenerating(conversationId: number) {
    const next = new Set(generatingConversationIds.value)
    next.add(conversationId)
    generatingConversationIds.value = next
    clearConversationCompleted(conversationId)
  }

  function clearConversationGenerating(conversationId: number) {
    if (!generatingConversationIds.value.has(conversationId)) return
    const next = new Set(generatingConversationIds.value)
    next.delete(conversationId)
    generatingConversationIds.value = next
  }

  function isConversationGenerating(conversationId: number | null) {
    return conversationId != null && generatingConversationIds.value.has(conversationId)
  }

  function markConversationCompleted(conversationId: number) {
    const next = new Set(completedConversationIds.value)
    next.add(conversationId)
    completedConversationIds.value = next
  }

  function clearConversationCompleted(conversationId: number) {
    if (!completedConversationIds.value.has(conversationId)) return
    const next = new Set(completedConversationIds.value)
    next.delete(conversationId)
    completedConversationIds.value = next
  }

  function markConversationSeen(conversationId: number | null) {
    if (conversationId == null) return
    clearConversationCompleted(conversationId)
  }

  function setAbortController(conversationId: number, ownerId: string, controller: AbortController) {
    const next = new Map(abortControllers.value)
    next.set(conversationId, { ownerId, controller })
    abortControllers.value = next
  }

  function getAbortController(conversationId: number) {
    return abortControllers.value.get(conversationId)?.controller
  }

  function clearAbortController(conversationId: number, ownerId?: string) {
    const current = abortControllers.value.get(conversationId)
    if (!current) return
    if (ownerId && current.ownerId !== ownerId) return
    const next = new Map(abortControllers.value)
    next.delete(conversationId)
    abortControllers.value = next
  }

  function setStreamOwner(conversationId: number, ownerId: string) {
    const next = new Map(streamOwners.value)
    next.set(conversationId, ownerId)
    streamOwners.value = next
  }

  function isStreamOwnedBy(conversationId: number | null, ownerId: string) {
    return conversationId != null && streamOwners.value.get(conversationId) === ownerId
  }

  function isStreamOwnedByPrefix(conversationId: number | null, ownerPrefix: string) {
    if (conversationId == null) return false
    const ownerId = streamOwners.value.get(conversationId)
    return typeof ownerId === 'string' && ownerId.startsWith(ownerPrefix)
  }

  function getStreamOwner(conversationId: number | null) {
    if (conversationId == null) return undefined
    return streamOwners.value.get(conversationId)
  }

  function clearStreamOwner(conversationId: number, ownerId?: string) {
    const currentOwner = streamOwners.value.get(conversationId)
    if (!currentOwner) return
    if (ownerId && currentOwner !== ownerId) return
    const next = new Map(streamOwners.value)
    next.delete(conversationId)
    streamOwners.value = next
  }

  function clearStreamOwnersByOwner(ownerId: string) {
    let changed = false
    const next = new Map(streamOwners.value)
    for (const [conversationId, currentOwner] of next.entries()) {
      if (currentOwner !== ownerId) continue
      next.delete(conversationId)
      changed = true
    }
    if (changed) {
      streamOwners.value = next
    }
  }

  function clearStreamOwnersByPrefix(ownerPrefix: string) {
    let changed = false
    const next = new Map(streamOwners.value)
    for (const [conversationId, currentOwner] of next.entries()) {
      if (!currentOwner.startsWith(ownerPrefix)) continue
      next.delete(conversationId)
      changed = true
    }
    if (changed) {
      streamOwners.value = next
    }
  }

  function getConversationExecutionState(conversationId: number | null) {
    if (conversationId == null) return undefined
    return conversationExecutionStates.value.get(conversationId)
  }

  function setConversationExecutionState(
    conversationId: number,
    payload: {
      state: ConversationExecutionState
      actionType?: ConversationActionType | null
      streamSessionId?: string | null
      startedAt?: number | null
      lastTerminalReason?: ActionTerminalReason | null
      lastErrorMessage?: string | null
      lastDisconnectedAt?: string | null
      resumeAttemptCount?: number
    },
  ) {
    const now = Date.now()
    const current = conversationExecutionStates.value.get(conversationId)
    const nextValue: ConversationExecutionSnapshot = {
      state: payload.state,
      actionType: payload.actionType ?? current?.actionType ?? null,
      streamSessionId: payload.streamSessionId ?? current?.streamSessionId ?? null,
      startedAt: payload.startedAt ?? current?.startedAt ?? null,
      updatedAt: now,
      lastTerminalReason: payload.lastTerminalReason ?? current?.lastTerminalReason ?? null,
      lastErrorMessage: payload.lastErrorMessage ?? current?.lastErrorMessage ?? null,
      lastDisconnectedAt: payload.lastDisconnectedAt ?? current?.lastDisconnectedAt ?? null,
      resumeAttemptCount: payload.resumeAttemptCount ?? current?.resumeAttemptCount ?? 0,
    }
    const next = new Map(conversationExecutionStates.value)
    next.set(conversationId, nextValue)
    conversationExecutionStates.value = next
  }

  function patchConversationExecutionState(
    conversationId: number,
    payload: Partial<Omit<ConversationExecutionSnapshot, 'updatedAt'>>,
  ) {
    const current = conversationExecutionStates.value.get(conversationId)
    if (!current) {
      return
    }
    const next = new Map(conversationExecutionStates.value)
    next.set(conversationId, {
      ...current,
      ...payload,
      updatedAt: Date.now(),
    })
    conversationExecutionStates.value = next
  }

  function clearConversationExecutionState(conversationId: number) {
    if (!conversationExecutionStates.value.has(conversationId)) return
    const next = new Map(conversationExecutionStates.value)
    next.delete(conversationId)
    conversationExecutionStates.value = next
  }

  function reset() {
    currentConversationId.value = null
    messages.value = []
    isGenerating.value = false
    conversationTitle.value = ''
    highlightConversationId.value = null
    pendingFocusConversationId.value = null
    messageCache.value = new Map()
    generatingConversationIds.value = new Set()
    completedConversationIds.value = new Set()
    abortControllers.value = new Map()
    streamOwners.value = new Map()
    conversationExecutionStates.value = new Map()
  }

  return {
    currentConversationId,
    messages,
    isGenerating,
    conversationTitle,
    highlightConversationId,
    pendingFocusConversationId,
    messageCache,
    generatingConversationIds,
    completedConversationIds,
    abortControllers,
    streamOwners,
    conversationExecutionStates,
    setConversation,
    appendChunk,
    addUserMessage,
    triggerHighlight,
    clearPendingFocusConversation,
    cacheConversationMessages,
    getCachedConversationMessages,
    clearCachedConversationMessages,
    markConversationGenerating,
    clearConversationGenerating,
    isConversationGenerating,
    markConversationCompleted,
    clearConversationCompleted,
    markConversationSeen,
    setAbortController,
    getAbortController,
    clearAbortController,
    setStreamOwner,
    isStreamOwnedBy,
    isStreamOwnedByPrefix,
    getStreamOwner,
    clearStreamOwner,
    clearStreamOwnersByOwner,
    clearStreamOwnersByPrefix,
    getConversationExecutionState,
    setConversationExecutionState,
    patchConversationExecutionState,
    clearConversationExecutionState,
    reset,
  }
})
