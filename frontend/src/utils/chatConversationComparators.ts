import type { ActiveSkillLite, TagInfo, LiveExecutionState, SidebarSignal } from '@/types/chat'

interface ConversationComparable {
  id: number
  skill_id: number | null
  skill_name: string
  title: string
  updated_at: string
  active_skills?: ActiveSkillLite[]
  tags?: TagInfo[]
  live_execution?: LiveExecutionState
  sidebar_signal?: SidebarSignal
}

function areLiveExecutionEqual(
  left?: LiveExecutionState | null,
  right?: LiveExecutionState | null,
): boolean {
  const leftValue = left ?? null
  const rightValue = right ?? null
  if (!leftValue && !rightValue) return true
  if (!leftValue || !rightValue) return false
  return leftValue.status === rightValue.status
    && (leftValue.message_id ?? null) === (rightValue.message_id ?? null)
    && (leftValue.error_message ?? null) === (rightValue.error_message ?? null)
    && (leftValue.stage ?? null) === (rightValue.stage ?? null)
    && (leftValue.stage_detail ?? null) === (rightValue.stage_detail ?? null)
    && (leftValue.round_no ?? null) === (rightValue.round_no ?? null)
    && (leftValue.updated_at ?? null) === (rightValue.updated_at ?? null)
}

function areSidebarSignalEqual(
  left?: SidebarSignal | null,
  right?: SidebarSignal | null,
): boolean {
  const leftValue = left ?? null
  const rightValue = right ?? null
  if (!leftValue && !rightValue) return true
  if (!leftValue || !rightValue) return false
  return leftValue.state === rightValue.state
    && (leftValue.updated_at ?? null) === (rightValue.updated_at ?? null)
    && (leftValue.read_at ?? null) === (rightValue.read_at ?? null)
}

export function formatSkillDisplayName(skills: ActiveSkillLite[]): string {
  if (!skills.length) return '自由对话'
  const first = skills[0]?.name || '技能'
  return skills.length === 1 ? first : `${first} +${skills.length - 1}`
}

export function areActiveSkillsEqual(
  left?: ActiveSkillLite[],
  right?: ActiveSkillLite[],
): boolean {
  const leftSkills = Array.isArray(left) ? left : []
  const rightSkills = Array.isArray(right) ? right : []
  if (leftSkills.length !== rightSkills.length) return false

  return leftSkills.every((skill, index) => {
    const nextSkill = rightSkills[index]
    return !!nextSkill && skill.id === nextSkill.id && skill.name === nextSkill.name
  })
}

export function areTagsEqual(
  left?: TagInfo[],
  right?: TagInfo[],
): boolean {
  const leftTags = Array.isArray(left) ? left : []
  const rightTags = Array.isArray(right) ? right : []
  if (leftTags.length !== rightTags.length) return false

  return leftTags.every((tag, index) => {
    const nextTag = rightTags[index]
    return !!nextTag && tag.id === nextTag.id && tag.name === nextTag.name && tag.color === nextTag.color
  })
}

export function areConversationListsRenderEqual<T extends ConversationComparable>(
  left: T[],
  right: T[],
): boolean {
  if (left.length !== right.length) return false

  return left.every((item, index) => {
    const nextItem = right[index]
    return !!nextItem
      && item.id === nextItem.id
      && item.skill_id === nextItem.skill_id
      && item.skill_name === nextItem.skill_name
      && item.title === nextItem.title
      && item.updated_at === nextItem.updated_at
      && areActiveSkillsEqual(item.active_skills, nextItem.active_skills)
      && areTagsEqual(item.tags, nextItem.tags)
      && areLiveExecutionEqual(item.live_execution, nextItem.live_execution)
      && areSidebarSignalEqual(item.sidebar_signal, nextItem.sidebar_signal)
  })
}
