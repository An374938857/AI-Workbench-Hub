import { ref } from 'vue'
import type { Msg } from '@/types/chat'

interface DraftMessageQuote {
  id: number
  role: string
  content: string
  created_at: string
  [key: string]: unknown
}

export interface ConversationDraftSnapshot {
  inputText: string
  fileIds: number[]
  quotedMessages: DraftMessageQuote[]
  forkFromMessageId: number | null
  messagesBeforeFork: Msg[] | null
}

export function useConversationDraft() {
  const inputText = ref('')
  const fileIds = ref<number[]>([])
  const quotedMessages = ref<DraftMessageQuote[]>([])
  const forkFromMessageId = ref<number | null>(null)
  const messagesBeforeFork = ref<Msg[] | null>(null)

  function snapshotDraft(): ConversationDraftSnapshot {
    return {
      inputText: inputText.value,
      fileIds: [...fileIds.value],
      quotedMessages: quotedMessages.value.map((item) => ({ ...item })),
      forkFromMessageId: forkFromMessageId.value,
      messagesBeforeFork: messagesBeforeFork.value ? [...messagesBeforeFork.value] : null,
    }
  }

  function restoreDraft(snapshot: ConversationDraftSnapshot) {
    inputText.value = snapshot.inputText
    fileIds.value = [...snapshot.fileIds]
    quotedMessages.value = snapshot.quotedMessages.map((item) => ({ ...item }))
    forkFromMessageId.value = snapshot.forkFromMessageId
    messagesBeforeFork.value = snapshot.messagesBeforeFork ? [...snapshot.messagesBeforeFork] : null
  }

  function clearDraft(options: { preserveForkState?: boolean } = {}) {
    inputText.value = ''
    fileIds.value = []
    quotedMessages.value = []
    if (!options.preserveForkState) {
      forkFromMessageId.value = null
      messagesBeforeFork.value = null
    }
  }

  return {
    inputText,
    fileIds,
    quotedMessages,
    forkFromMessageId,
    messagesBeforeFork,
    snapshotDraft,
    restoreDraft,
    clearDraft,
  }
}
