import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useConversationLiveState } from '@/composables/useConversationLiveState'

function mountLiveState(poll: () => Promise<void>, intervalMs = 20) {
  const TestComponent = defineComponent({
    setup() {
      const liveState = useConversationLiveState({
        intervalMs,
        poll,
      })
      return { liveState }
    },
    template: '<div />',
  })

  return mount(TestComponent)
}

describe('useConversationLiveState', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('keeps healthy state when polling succeeds', async () => {
    vi.useFakeTimers()
    const poll = vi.fn().mockResolvedValue(undefined)
    const wrapper = mountLiveState(poll)
    const liveState = (wrapper.vm as any).liveState

    liveState.startPolling()
    await vi.advanceTimersByTimeAsync(25)

    expect(poll).toHaveBeenCalledTimes(1)
    expect(liveState.pollingHealth.value).toBe('healthy')
    expect(liveState.pollFailureCount.value).toBe(0)

    wrapper.unmount()
  })

  it('switches to degraded after three consecutive failures', async () => {
    vi.useFakeTimers()
    const poll = vi.fn().mockRejectedValue(new Error('poll failed'))
    const wrapper = mountLiveState(poll)
    const liveState = (wrapper.vm as any).liveState

    liveState.startPolling()
    await vi.advanceTimersByTimeAsync(70)

    expect(poll).toHaveBeenCalledTimes(3)
    expect(liveState.pollingHealth.value).toBe('degraded')
    expect(liveState.pollFailureCount.value).toBe(3)
    expect(liveState.lastPollErrorMessage.value).toBe('poll failed')

    wrapper.unmount()
  })
})
