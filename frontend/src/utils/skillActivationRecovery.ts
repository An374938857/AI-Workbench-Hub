import type { Msg, SkillActivationRequestEvent } from '@/types/chat'

interface SkillMeta {
  id: number
  name: string
  description: string
}

function parseToolNameSkillId(toolName?: string): number | null {
  if (!toolName) return null
  const matched = /^activate_skill_(\d+)$/.exec(toolName)
  if (!matched) return null
  const parsed = Number(matched[1])
  return Number.isFinite(parsed) ? parsed : null
}

function parseResultPreview(resultPreview?: string): Partial<SkillMeta> | null {
  if (!resultPreview) return null
  try {
    const parsed = JSON.parse(resultPreview) as Record<string, unknown>
    const skillId = Number(parsed.skill_id)
    const skillName = typeof parsed.skill_name === 'string' ? parsed.skill_name : ''
    const message = typeof parsed.message === 'string' ? parsed.message : ''
    return {
      id: Number.isFinite(skillId) ? skillId : undefined,
      name: skillName || undefined,
      description: message || undefined,
    }
  } catch {
    return null
  }
}

export function extractPendingSkillActivationFromMessages(
  messages: Msg[],
  resolveSkillDescription?: (skillId: number) => string | null | undefined,
): SkillActivationRequestEvent | null {
  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const message = messages[messageIndex]
    if (!message?.timeline?.length) continue

    for (let timelineIndex = message.timeline.length - 1; timelineIndex >= 0; timelineIndex -= 1) {
      const timelineItem = message.timeline[timelineIndex]
      if (!timelineItem || timelineItem.type !== 'tool_call') continue

      const parsedSkillId = parseToolNameSkillId(timelineItem.toolName)
      if (!parsedSkillId) continue
      if (timelineItem.status === 'error') continue

      const previewMeta = parseResultPreview(timelineItem.resultPreview)
      const skillId = previewMeta?.id || parsedSkillId
      const skillName = previewMeta?.name || `技能 ${skillId}`
      const skillDescription = (
        previewMeta?.description
        || resolveSkillDescription?.(skillId)
        || '检测到技能激活请求，请确认是否激活该技能。'
      )

      return {
        skill_id: skillId,
        skill_name: skillName,
        skill_description: skillDescription,
      }
    }
  }
  return null
}
