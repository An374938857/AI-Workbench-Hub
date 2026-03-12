import { onUnmounted, ref } from 'vue'

type PollingHealth = 'healthy' | 'retrying' | 'degraded'

interface UseConversationLiveStateOptions {
  intervalMs?: number
  shouldSkipPoll?: () => boolean
  poll: () => Promise<void>
}

export function useConversationLiveState(options: UseConversationLiveStateOptions) {
  const intervalMs = options.intervalMs ?? 1000
  const pollingHealth = ref<PollingHealth>('healthy')
  const pollFailureCount = ref(0)
  const lastPollErrorMessage = ref<string | null>(null)

  let pollingTimer: number | null = null
  let pollingInFlight = false

  function resetHealth() {
    pollFailureCount.value = 0
    pollingHealth.value = 'healthy'
    lastPollErrorMessage.value = null
  }

  function markPollSuccess() {
    resetHealth()
  }

  function markPollFailure(error: unknown) {
    pollFailureCount.value += 1
    pollingHealth.value = pollFailureCount.value >= 3 ? 'degraded' : 'retrying'
    const fallback = '同步失败'
    if (error instanceof Error) {
      lastPollErrorMessage.value = error.message || fallback
      if (import.meta.env.DEV && import.meta.env.MODE !== 'test') {
        console.warn('chat.live_state.poll_failed', {
          pollFailureCount: pollFailureCount.value,
          pollingHealth: pollingHealth.value,
          message: lastPollErrorMessage.value,
        })
      }
      return
    }
    if (typeof error === 'string' && error.trim()) {
      lastPollErrorMessage.value = error.trim()
      if (import.meta.env.DEV && import.meta.env.MODE !== 'test') {
        console.warn('chat.live_state.poll_failed', {
          pollFailureCount: pollFailureCount.value,
          pollingHealth: pollingHealth.value,
          message: lastPollErrorMessage.value,
        })
      }
      return
    }
    lastPollErrorMessage.value = fallback
    if (import.meta.env.DEV && import.meta.env.MODE !== 'test') {
      console.warn('chat.live_state.poll_failed', {
        pollFailureCount: pollFailureCount.value,
        pollingHealth: pollingHealth.value,
        message: lastPollErrorMessage.value,
      })
    }
  }

  function stopPolling() {
    if (pollingTimer != null) {
      window.clearInterval(pollingTimer)
      pollingTimer = null
    }
  }

  function startPolling() {
    if (pollingTimer != null) return
    pollingTimer = window.setInterval(async () => {
      if (pollingInFlight) return
      if (options.shouldSkipPoll?.()) return

      pollingInFlight = true
      try {
        await options.poll()
        markPollSuccess()
      } catch (error) {
        markPollFailure(error)
      } finally {
        pollingInFlight = false
      }
    }, intervalMs)
  }

  onUnmounted(() => {
    stopPolling()
  })

  return {
    pollingHealth,
    pollFailureCount,
    lastPollErrorMessage,
    resetHealth,
    markPollSuccess,
    markPollFailure,
    startPolling,
    stopPolling,
  }
}
