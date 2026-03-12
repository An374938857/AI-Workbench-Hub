import { ref } from 'vue'

interface FeedbackPayload {
  rating: number
  comment?: string
}

interface FeedbackValue {
  rating: number
  comment: string
}

interface UseConversationFeedbackOptions {
  getCurrentConversationId: () => number | null
  fetchFeedback: (conversationId: number) => Promise<{ data?: FeedbackValue | null }>
  submitFeedback: (conversationId: number, rating: number, comment?: string) => Promise<unknown>
  showSuccess: (message: string) => void
}

export function useConversationFeedback(options: UseConversationFeedbackOptions) {
  const feedbackVisible = ref(false)
  const feedbackForm = ref<FeedbackValue>({ rating: 5, comment: '' })
  const feedbackSubmitting = ref(false)
  const currentFeedback = ref<FeedbackValue | null>(null)
  const starHover = ref(0)

  async function loadFeedback(conversationId: number) {
    try {
      const response = await options.fetchFeedback(conversationId)
      currentFeedback.value = response?.data ?? null
      if (currentFeedback.value) {
        feedbackForm.value = {
          rating: currentFeedback.value.rating,
          comment: currentFeedback.value.comment || '',
        }
      }
    } catch {
      // ignore
    }
  }

  function openFeedback() {
    if (!currentFeedback.value) {
      feedbackForm.value = { rating: 5, comment: '' }
    }
    feedbackVisible.value = true
  }

  async function handleFeedback() {
    const conversationId = options.getCurrentConversationId()
    if (!conversationId) return

    feedbackSubmitting.value = true
    try {
      const payload: FeedbackPayload = {
        rating: feedbackForm.value.rating,
        comment: feedbackForm.value.comment || undefined,
      }
      await options.submitFeedback(conversationId, payload.rating, payload.comment)
      currentFeedback.value = { ...feedbackForm.value }
      feedbackVisible.value = false
      options.showSuccess('感谢反馈')
    } finally {
      feedbackSubmitting.value = false
    }
  }

  function clearFeedbackState() {
    currentFeedback.value = null
    feedbackVisible.value = false
    feedbackForm.value = { rating: 5, comment: '' }
    starHover.value = 0
  }

  return {
    feedbackVisible,
    feedbackForm,
    feedbackSubmitting,
    currentFeedback,
    starHover,
    loadFeedback,
    openFeedback,
    handleFeedback,
    clearFeedbackState,
  }
}
