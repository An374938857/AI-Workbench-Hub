import { afterEach, describe, expect, it, vi } from 'vitest'
import { useConversationSidebar } from '@/composables/useConversationSidebar'

interface TestConversation {
  id: number
  updated_at: string
  active_skills?: unknown[]
}

function createSidebar(fetchSortPreferencesData: Array<{ target_id: number; sort_order: number }>) {
  return useConversationSidebar<TestConversation>({
    getActiveTagFilter: () => null,
    getCurrentConversationId: () => null,
    fetchConversationList: async () => ({
      data: {
        items: [
          { id: 1, updated_at: '2026-03-10T10:00:00Z' },
          { id: 2, updated_at: '2026-03-10T09:00:00Z' },
          { id: 3, updated_at: '2026-03-10T11:00:00Z' },
        ],
      },
    }),
    fetchSortPreferences: async () => ({ data: fetchSortPreferencesData }),
    saveSortPreferences: async () => undefined,
  })
}

describe('useConversationSidebar', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('keeps newest un-ordered conversation at top even when old sort preferences exist', async () => {
    const sidebar = createSidebar([
      { target_id: 1, sort_order: 0 },
      { target_id: 2, sort_order: 1 },
    ])

    await sidebar.loadConversationList()

    expect(sidebar.conversations.value.map((item) => item.id)).toEqual([3, 1, 2])
  })

  it('uses updated_at desc when no sort preferences exist', async () => {
    const sidebar = createSidebar([])

    await sidebar.loadConversationList()

    expect(sidebar.conversations.value.map((item) => item.id)).toEqual([3, 1, 2])
  })

  it('auto refreshes conversation list in silent mode for live status updates', async () => {
    vi.useFakeTimers()
    const fetchConversationList = vi.fn().mockResolvedValue({
      data: {
        items: [{ id: 1, updated_at: '2026-03-10T10:00:00Z' }],
      },
    })
    const sidebar = useConversationSidebar<TestConversation>({
      getActiveTagFilter: () => null,
      getCurrentConversationId: () => null,
      fetchConversationList,
      fetchSortPreferences: async () => ({ data: [] }),
      saveSortPreferences: async () => undefined,
    })

    await sidebar.loadConversationList()
    fetchConversationList.mockClear()

    sidebar.startAutoRefresh(50)
    await vi.advanceTimersByTimeAsync(130)
    sidebar.stopAutoRefresh()

    expect(fetchConversationList).toHaveBeenCalledTimes(2)
    expect(fetchConversationList).toHaveBeenNthCalledWith(
      1,
      { page: 1, page_size: 50 },
      { _silent: true },
    )
  })
})
