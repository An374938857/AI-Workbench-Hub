export interface SkillResumePayloadLike {
  assistantMessageId?: number | null
  toolMessageId?: number | null
}

export function buildSkillResumeKey(payload: SkillResumePayloadLike): string | null {
  const assistantMessageId = Number(payload.assistantMessageId ?? 0)
  const toolMessageId = Number(payload.toolMessageId ?? 0)

  const normalizedAssistantId = Number.isFinite(assistantMessageId) && assistantMessageId > 0
    ? assistantMessageId
    : 0
  const normalizedToolId = Number.isFinite(toolMessageId) && toolMessageId > 0
    ? toolMessageId
    : 0

  if (!normalizedAssistantId && !normalizedToolId) return null
  return `assistant:${normalizedAssistantId}|tool:${normalizedToolId}`
}

export class SkillResumeGuard {
  private readonly inFlightByConversation = new Map<number, string>()

  tryBegin(conversationId: number, resumeKey: string): boolean {
    const existing = this.inFlightByConversation.get(conversationId)
    if (existing) return false
    this.inFlightByConversation.set(conversationId, resumeKey)
    return true
  }

  end(conversationId: number, resumeKey?: string): void {
    const existing = this.inFlightByConversation.get(conversationId)
    if (!existing) return
    if (resumeKey && existing !== resumeKey) return
    this.inFlightByConversation.delete(conversationId)
  }

  isInFlight(conversationId: number, resumeKey?: string): boolean {
    const existing = this.inFlightByConversation.get(conversationId)
    if (!existing) return false
    if (!resumeKey) return true
    return existing === resumeKey
  }
}
