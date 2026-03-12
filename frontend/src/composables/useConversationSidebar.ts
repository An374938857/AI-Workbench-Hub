import { ref } from 'vue'

interface SortPreferencePayload {
  target_id: number
  sort_order: number
}

interface SidebarBaseConversation {
  id: number
  updated_at: string
  active_skills?: unknown[]
}

interface UseConversationSidebarOptions<T extends SidebarBaseConversation> {
  getActiveTagFilter: () => number | null
  getCurrentConversationId: () => number | null
  onCurrentConversationActiveSkills?: (skills: NonNullable<T['active_skills']>) => void
  areConversationListsRenderEqual?: (left: T[], right: T[]) => boolean
  fetchConversationList: (
    params: Record<string, unknown>,
    options?: Record<string, unknown>,
  ) => Promise<{ data?: { items?: T[] } }>
  fetchSortPreferences: () => Promise<{ data?: SortPreferencePayload[] }>
  saveSortPreferences: (items: Array<{ id: number; sort_order: number }>) => Promise<unknown>
}

export function useConversationSidebar<T extends SidebarBaseConversation>(
  options: UseConversationSidebarOptions<T>,
) {
  const conversations = ref<T[]>([])
  const conversationSortOrderMap = ref<Map<number, number>>(new Map())
  const conversationSortPreferencesLoaded = ref(false)
  const currentPage = ref(1)
  const hasMoreConversations = ref(true)
  const loadingMoreConversations = ref(false)
  let autoRefreshTimer: number | null = null
  let autoRefreshInFlight = false

  function sortConversationItems(items: T[]) {
    const next = [...items]
    const orderMap = conversationSortOrderMap.value
    const canApplyCustomOrder = conversationSortPreferencesLoaded.value
    return next.sort((a, b) => {
      const aOrder = canApplyCustomOrder ? orderMap.get(a.id) : undefined
      const bOrder = canApplyCustomOrder ? orderMap.get(b.id) : undefined
      const bothOrdered = aOrder != null && bOrder != null
      if (bothOrdered) {
        const orderDiff = aOrder - bOrder
        if (orderDiff !== 0) {
          return orderDiff
        }
      }
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    })
  }

  function resetPagination() {
    currentPage.value = 1
    hasMoreConversations.value = true
  }

  async function ensureConversationSortPreferencesLoaded(force = false) {
    if (conversationSortPreferencesLoaded.value && !force) {
      return
    }

    try {
      const prefsRes = await options.fetchSortPreferences()
      const prefs = Array.isArray(prefsRes?.data) ? prefsRes.data : []
      conversationSortOrderMap.value = new Map(
        prefs.map((item) => [item.target_id, item.sort_order]),
      )
    } catch {
      conversationSortOrderMap.value = new Map()
    } finally {
      conversationSortPreferencesLoaded.value = true
    }
  }

  async function loadConversationList(
    append = false,
    loadOptions: { silent?: boolean } = {},
  ) {
    try {
      const { silent = false } = loadOptions
      if (!append) {
        resetPagination()
        await ensureConversationSortPreferencesLoaded()
      }

      const params: Record<string, unknown> = { page: currentPage.value, page_size: 50 }
      const activeTagFilter = options.getActiveTagFilter()
      if (activeTagFilter) params.tag_id = activeTagFilter

      const res = await options.fetchConversationList(
        params,
        silent ? { _silent: true } : undefined,
      )
      const items = Array.isArray(res?.data?.items) ? res.data.items : []
      const mergedItems = (append ? [...conversations.value, ...items] : items) as T[]
      const nextConversations = sortConversationItems(mergedItems)

      if (
        !append
        && silent
        && options.areConversationListsRenderEqual
        && options.areConversationListsRenderEqual(conversations.value as T[], nextConversations)
      ) {
        return
      }

      conversations.value = nextConversations
      hasMoreConversations.value = items.length === 50

      const currentConversationId = options.getCurrentConversationId()
      if (currentConversationId && options.onCurrentConversationActiveSkills) {
        const current = conversations.value.find((conv) => conv.id === currentConversationId)
        if (current?.active_skills) {
          options.onCurrentConversationActiveSkills(current.active_skills as NonNullable<T['active_skills']>)
        }
      }
    } catch {
      // ignore
    }
  }

  async function loadMoreConversations() {
    if (loadingMoreConversations.value || !hasMoreConversations.value) return
    loadingMoreConversations.value = true
    try {
      currentPage.value += 1
      await loadConversationList(true)
    } finally {
      loadingMoreConversations.value = false
    }
  }

  function handleConvListScroll(e: Event) {
    const target = e.target as HTMLElement
    const scrollBottom = target.scrollHeight - target.scrollTop - target.clientHeight
    if (scrollBottom < 100 && hasMoreConversations.value && !loadingMoreConversations.value) {
      void loadMoreConversations()
    }
  }

  async function handleConvDragEnd() {
    const items = conversations.value.map((conversation, index) => ({
      id: conversation.id,
      sort_order: index,
    }))
    try {
      await options.saveSortPreferences(items)
      conversationSortOrderMap.value = new Map(items.map((item) => [item.id, item.sort_order]))
      conversationSortPreferencesLoaded.value = true
    } catch {
      // ignore
    }
  }

  async function refreshConversationStatuses() {
    await loadConversationList(false, { silent: true })
  }

  function stopAutoRefresh() {
    if (autoRefreshTimer == null) return
    window.clearInterval(autoRefreshTimer)
    autoRefreshTimer = null
  }

  function startAutoRefresh(intervalMs = 1000) {
    if (autoRefreshTimer != null) return
    autoRefreshTimer = window.setInterval(async () => {
      if (autoRefreshInFlight || loadingMoreConversations.value) return
      autoRefreshInFlight = true
      try {
        await refreshConversationStatuses()
      } finally {
        autoRefreshInFlight = false
      }
    }, intervalMs)
  }

  return {
    conversations,
    currentPage,
    hasMoreConversations,
    loadingMoreConversations,
    loadConversationList,
    loadMoreConversations,
    handleConvListScroll,
    handleConvDragEnd,
    resetPagination,
    refreshConversationStatuses,
    startAutoRefresh,
    stopAutoRefresh,
  }
}
