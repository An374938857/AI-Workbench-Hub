import { describe, expect, it } from 'vitest'
import type { Msg } from '@/types/chat'
import { extractPendingSkillActivationFromMessages } from '@/utils/skillActivationRecovery'

function buildAssistantMessageWithTimeline(
  timeline: NonNullable<Msg['timeline']>,
): Msg {
  return {
    clientKey: 'assistant-1',
    id: 1001,
    role: 'assistant',
    content: 'assistant',
    timeline,
  }
}

describe('extractPendingSkillActivationFromMessages', () => {
  it('extracts pending skill activation payload from tool result preview json', () => {
    const messages: Msg[] = [
      buildAssistantMessageWithTimeline([
        {
          type: 'tool_call',
          toolCallId: 'functions.activate_skill_13:0',
          toolName: 'activate_skill_13',
          status: 'success',
          resultPreview: JSON.stringify({
            type: 'skill_activation_pending',
            skill_id: 13,
            skill_name: 'brainstorming',
            message: '请确认激活技能',
          }),
        },
      ]),
    ]

    const result = extractPendingSkillActivationFromMessages(messages)

    expect(result).toEqual({
      skill_id: 13,
      skill_name: 'brainstorming',
      skill_description: '请确认激活技能',
    })
  })

  it('returns null when no activate_skill tool call is present', () => {
    const messages: Msg[] = [
      buildAssistantMessageWithTimeline([
        {
          type: 'tool_call',
          toolCallId: 'functions.other_tool:0',
          toolName: 'other_tool',
          status: 'success',
          resultPreview: '{"ok":true}',
        },
      ]),
    ]

    expect(extractPendingSkillActivationFromMessages(messages)).toBeNull()
  })
})
