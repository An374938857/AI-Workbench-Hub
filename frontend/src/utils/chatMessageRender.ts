import type { Msg } from '@/types/chat'

export function applyMessageUiState(previous: Msg[], next: Msg[]): Msg[] {
  const previousById = new Map<number, Msg>()
  previous.forEach((message) => {
    if (typeof message.id === 'number') {
      previousById.set(message.id, message)
    }
  })

  return next.map((message) => {
    if (typeof message.id !== 'number') return message
    const prev = previousById.get(message.id)
    if (!prev) return message
    return {
      ...message,
      forceToolbarVisible: prev.forceToolbarVisible,
      exportHintActive: prev.exportHintActive,
      exportHintPulse: prev.exportHintPulse,
      exportHintAcknowledged: prev.exportHintAcknowledged,
    }
  })
}

export function isSameTimeline(left?: Msg['timeline'], right?: Msg['timeline']): boolean {
  const l = Array.isArray(left) ? left : []
  const r = Array.isArray(right) ? right : []
  if (l.length !== r.length) return false

  return l.every((item, index) => {
    const next = r[index]
    if (!next) return false
    return item.type === next.type
      && item.isThinking === next.isThinking
      && (item.content || '') === (next.content || '')
      && (item.toolCallId || '') === (next.toolCallId || '')
      && (item.toolName || '') === (next.toolName || '')
      && (item.arguments || '') === (next.arguments || '')
      && (item.status || '') === (next.status || '')
      && Number(item.progressTick || 0) === Number(next.progressTick || 0)
      && Number(item.elapsedMs || 0) === Number(next.elapsedMs || 0)
      && Number(item.elapsedSeconds || 0) === Number(next.elapsedSeconds || 0)
      && (item.resultPreview || '') === (next.resultPreview || '')
      && (item.errorMessage || '') === (next.errorMessage || '')
      && JSON.stringify(item.files || []) === JSON.stringify(next.files || [])
  })
}

export function isSameMessageForRender(left: Msg, right: Msg): boolean {
  return left.id === right.id
    && left.role === right.role
    && left.content === right.content
    && JSON.stringify(left.files || []) === JSON.stringify(right.files || [])
    && left.parentId === right.parentId
    && left.branchIndex === right.branchIndex
    && left.siblingCount === right.siblingCount
    && left.childBranchCount === right.childBranchCount
    && left.activeChildBranchIndex === right.activeChildBranchIndex
    && JSON.stringify(left.referencedMessageIds || []) === JSON.stringify(right.referencedMessageIds || [])
    && isSameTimeline(left.timeline, right.timeline)
}

export function areMessagesRenderEqual(left: Msg[], right: Msg[]): boolean {
  if (left.length !== right.length) return false
  return left.every((message, index) => {
    const next = right[index]
    return !!next && isSameMessageForRender(message, next)
  })
}

export function canPatchLatestAssistantOnly(current: Msg[], next: Msg[]): boolean {
  if (current.length !== next.length || current.length === 0) return false

  const currentLastAssistantIndex = [...current]
    .map((item, index) => ({ item, index }))
    .reverse()
    .find(({ item }) => item.role === 'assistant')?.index
  const nextLastAssistantIndex = [...next]
    .map((item, index) => ({ item, index }))
    .reverse()
    .find(({ item }) => item.role === 'assistant')?.index

  if (currentLastAssistantIndex == null || nextLastAssistantIndex == null) return false
  if (currentLastAssistantIndex !== nextLastAssistantIndex) return false

  for (let i = 0; i < current.length; i += 1) {
    if (i === currentLastAssistantIndex) continue
    if (!isSameMessageForRender(current[i]!, next[i]!)) return false
  }

  const currentLast = current[currentLastAssistantIndex]
  const nextLast = next[nextLastAssistantIndex]
  if (!currentLast || !nextLast) return false
  if (currentLast.id !== nextLast.id || currentLast.role !== 'assistant' || nextLast.role !== 'assistant') return false

  return !isSameMessageForRender(currentLast, nextLast)
}
