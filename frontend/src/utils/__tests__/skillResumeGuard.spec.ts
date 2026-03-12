import { describe, expect, it } from 'vitest'
import { buildSkillResumeKey, SkillResumeGuard } from '@/utils/skillResumeGuard'

describe('buildSkillResumeKey', () => {
  it('returns null when both ids are missing', () => {
    expect(buildSkillResumeKey({ assistantMessageId: null, toolMessageId: null })).toBeNull()
    expect(buildSkillResumeKey({})).toBeNull()
  })

  it('normalizes key using positive numeric ids only', () => {
    expect(buildSkillResumeKey({ assistantMessageId: 12, toolMessageId: 34 }))
      .toBe('assistant:12|tool:34')
    expect(buildSkillResumeKey({ assistantMessageId: 12, toolMessageId: 0 }))
      .toBe('assistant:12|tool:0')
    expect(buildSkillResumeKey({ assistantMessageId: -1, toolMessageId: 99 }))
      .toBe('assistant:0|tool:99')
  })
})

describe('SkillResumeGuard', () => {
  it('rejects duplicate begin calls for same conversation while in flight', () => {
    const guard = new SkillResumeGuard()
    expect(guard.tryBegin(543, 'assistant:3068|tool:0')).toBe(true)
    expect(guard.tryBegin(543, 'assistant:3068|tool:0')).toBe(false)
    expect(guard.tryBegin(543, 'assistant:3070|tool:0')).toBe(false)
  })

  it('allows independent conversations to run in parallel', () => {
    const guard = new SkillResumeGuard()
    expect(guard.tryBegin(543, 'assistant:3068|tool:0')).toBe(true)
    expect(guard.tryBegin(544, 'assistant:3068|tool:0')).toBe(true)
    expect(guard.isInFlight(543)).toBe(true)
    expect(guard.isInFlight(544)).toBe(true)
  })

  it('releases only matched in-flight key when specified', () => {
    const guard = new SkillResumeGuard()
    expect(guard.tryBegin(543, 'assistant:3068|tool:0')).toBe(true)
    guard.end(543, 'assistant:9999|tool:0')
    expect(guard.isInFlight(543)).toBe(true)
    guard.end(543, 'assistant:3068|tool:0')
    expect(guard.isInFlight(543)).toBe(false)
    expect(guard.tryBegin(543, 'assistant:3070|tool:0')).toBe(true)
  })
})
