import { onUnmounted, ref } from 'vue'
import type { ConversationSyncEvent } from '@/types/chat'

export type EventConnectionState = 'idle' | 'connecting' | 'connected' | 'retrying' | 'degraded'

interface ParsedSseEvent {
  event: string
  payload: ConversationSyncEvent
}

interface UseConversationEventsOptions {
  url?: string
  maxRetryBeforeDegraded?: number
  onEvent: (payload: ConversationSyncEvent) => void
}

export function parseSseEventBlock(block: string): ParsedSseEvent | null {
  const trimmed = block.trim()
  if (!trimmed || trimmed.startsWith(':')) return null

  let event = 'message'
  const dataLines: string[] = []

  const lines = block.split('\n')
  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim() || 'message'
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  if (!dataLines.length) return null

  try {
    const payload = JSON.parse(dataLines.join('\n')) as ConversationSyncEvent
    if (typeof payload?.conversation_id !== 'number') return null
    if (typeof payload?.event_version !== 'number') return null
    if (!payload?.patch || typeof payload.patch !== 'object') return null
    return { event, payload }
  } catch {
    return null
  }
}

export function useConversationEvents(options: UseConversationEventsOptions) {
  const url = options.url || '/api/conversations/events'
  const maxRetryBeforeDegraded = options.maxRetryBeforeDegraded ?? 3

  const connectionState = ref<EventConnectionState>('idle')
  const retryCount = ref(0)

  let disposed = false
  let abortController: AbortController | null = null
  let reconnectTimer: number | null = null

  function clearReconnectTimer() {
    if (reconnectTimer != null) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function stop() {
    disposed = true
    clearReconnectTimer()
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    connectionState.value = 'idle'
  }

  async function connect() {
    if (disposed) return
    clearReconnectTimer()
    connectionState.value = retryCount.value > 0 ? 'retrying' : 'connecting'

    const token = localStorage.getItem('access_token')
    if (!token) {
      connectionState.value = 'degraded'
      return
    }

    const controller = new AbortController()
    abortController = controller

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'text/event-stream',
        },
        signal: controller.signal,
      })

      if (!response.ok || !response.body) {
        throw new Error(`SSE connect failed: ${response.status}`)
      }

      retryCount.value = 0
      connectionState.value = 'connected'

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (!disposed) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        while (true) {
          const delimiterIndex = buffer.indexOf('\n\n')
          if (delimiterIndex < 0) break

          const block = buffer.slice(0, delimiterIndex)
          buffer = buffer.slice(delimiterIndex + 2)

          const parsed = parseSseEventBlock(block)
          if (!parsed) continue
          options.onEvent(parsed.payload)
        }
      }

      if (disposed) return
      throw new Error('SSE stream closed')
    } catch {
      if (disposed) return
      retryCount.value += 1
      connectionState.value = retryCount.value >= maxRetryBeforeDegraded ? 'degraded' : 'retrying'
      const delayMs = Math.min(30000, 1000 * (2 ** Math.min(retryCount.value, 5)))
      reconnectTimer = window.setTimeout(() => {
        void connect()
      }, delayMs)
    }
  }

  function start() {
    if (disposed) {
      disposed = false
    }
    if (connectionState.value === 'connecting' || connectionState.value === 'connected') {
      return
    }
    void connect()
  }

  onUnmounted(() => {
    stop()
  })

  return {
    connectionState,
    retryCount,
    start,
    stop,
  }
}
