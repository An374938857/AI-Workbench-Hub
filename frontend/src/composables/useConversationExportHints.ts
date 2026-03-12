import { ref } from 'vue'
import type { Ref } from 'vue'
import type { Msg } from '@/types/chat'

const EXPORT_HINT_MIN_LENGTH = 800
const EXPORT_HINT_MIN_HEADINGS = 3
const EXPORT_HINT_PULSE_DURATION_MS = 20000
const EXPORT_HINT_ACTIVE_DURATION_MS = 60000

interface UseConversationExportHintsOptions {
  messages: Ref<Msg[]>
  getCurrentConversationId: () => number | null
  cacheConversationMessages: (conversationId: number, messages: Msg[]) => void
}

export function useConversationExportHints(options: UseConversationExportHintsOptions) {
  const exportHintShownMessageIds = ref<Set<number>>(new Set())
  const exportHintPulseTimers = new Map<number, number>()
  const exportHintActiveTimers = new Map<number, number>()

  function countMarkdownHeadings(content: string): number {
    const lines = content.split(/\r?\n/)
    let count = 0
    for (const line of lines) {
      if (/^\s{0,3}#{1,6}\s+/.test(line)) count += 1
    }
    return count
  }

  function shouldShowExportHint(content: string): boolean {
    const normalized = String(content || '').trim()
    if (normalized.length < EXPORT_HINT_MIN_LENGTH) return false
    return countMarkdownHeadings(normalized) >= EXPORT_HINT_MIN_HEADINGS
  }

  function syncMessageCache() {
    const currentConversationId = options.getCurrentConversationId()
    if (!currentConversationId) return
    options.cacheConversationMessages(currentConversationId, [...options.messages.value])
  }

  function clearExportHintPulseTimer(messageId: number) {
    const timer = exportHintPulseTimers.get(messageId)
    if (timer) {
      window.clearTimeout(timer)
      exportHintPulseTimers.delete(messageId)
    }
  }

  function clearExportHintActiveTimer(messageId: number) {
    const timer = exportHintActiveTimers.get(messageId)
    if (timer) {
      window.clearTimeout(timer)
      exportHintActiveTimers.delete(messageId)
    }
  }

  function acknowledgeExportHint(messageId?: number | null) {
    if (!messageId) return

    clearExportHintPulseTimer(messageId)
    clearExportHintActiveTimer(messageId)

    let changed = false
    options.messages.value = options.messages.value.map((message) => {
      if (message.id !== messageId) return message
      if (!message.exportHintActive && !message.exportHintPulse && message.exportHintAcknowledged) return message
      changed = true
      return {
        ...message,
        forceToolbarVisible: false,
        exportHintActive: false,
        exportHintPulse: false,
        exportHintAcknowledged: true,
      }
    })

    if (changed) {
      syncMessageCache()
    }
  }

  function acknowledgeAllExportHints() {
    const activeIds = options.messages.value
      .filter((message) => message.role === 'assistant' && message.exportHintActive && message.id)
      .map((message) => Number(message.id))

    if (!activeIds.length) return
    activeIds.forEach((id) => acknowledgeExportHint(id))
  }

  function activateExportHint(messageId: number) {
    clearExportHintPulseTimer(messageId)
    clearExportHintActiveTimer(messageId)

    options.messages.value = options.messages.value.map((message) => {
      if (message.id !== messageId) {
        if (!message.exportHintActive && !message.forceToolbarVisible && !message.exportHintPulse) return message
        return {
          ...message,
          forceToolbarVisible: false,
          exportHintActive: false,
          exportHintPulse: false,
        }
      }

      return {
        ...message,
        forceToolbarVisible: true,
        exportHintActive: true,
        exportHintPulse: true,
        exportHintAcknowledged: false,
      }
    })
    syncMessageCache()

    const pulseTimer = window.setTimeout(() => {
      options.messages.value = options.messages.value.map((message) => {
        if (message.id !== messageId) return message
        if (!message.exportHintActive || !message.exportHintPulse) return message
        return {
          ...message,
          exportHintPulse: false,
        }
      })
      syncMessageCache()
      exportHintPulseTimers.delete(messageId)
    }, EXPORT_HINT_PULSE_DURATION_MS)
    exportHintPulseTimers.set(messageId, pulseTimer)

    const activeTimer = window.setTimeout(() => {
      acknowledgeExportHint(messageId)
    }, EXPORT_HINT_ACTIVE_DURATION_MS)
    exportHintActiveTimers.set(messageId, activeTimer)
  }

  function maybeActivateExportHintForMessage(messageId: number, content: string): boolean {
    if (exportHintShownMessageIds.value.has(messageId)) return false
    if (!shouldShowExportHint(content)) return false

    exportHintShownMessageIds.value.add(messageId)
    activateExportHint(messageId)
    return true
  }

  function maybeActivateExportHintForLatestAssistant() {
    const latestAssistant = [...options.messages.value]
      .reverse()
      .find((message) => message.role === 'assistant' && typeof message.id === 'number')
    if (!latestAssistant || !latestAssistant.id) return
    if (latestAssistant.exportHintAcknowledged || latestAssistant.exportHintActive) return

    maybeActivateExportHintForMessage(latestAssistant.id, latestAssistant.content || '')
  }

  function resetExportHints() {
    exportHintPulseTimers.forEach((timer) => window.clearTimeout(timer))
    exportHintPulseTimers.clear()
    exportHintActiveTimers.forEach((timer) => window.clearTimeout(timer))
    exportHintActiveTimers.clear()
    exportHintShownMessageIds.value = new Set()
  }

  return {
    maybeActivateExportHintForLatestAssistant,
    maybeActivateExportHintForMessage,
    acknowledgeExportHint,
    acknowledgeAllExportHints,
    resetExportHints,
  }
}
