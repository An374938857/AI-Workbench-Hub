import { describe, expect, it } from 'vitest'
import { resolveConversationStatusSignal } from '@/utils/chatConversationStatus'

describe('resolveConversationStatusSignal', () => {
  it('prioritizes danger over success and unread info', () => {
    const result = resolveConversationStatusSignal({
      liveExecutionStatus: 'running',
      isGenerating: true,
      isCompletedUnread: true,
      pollingHealth: 'degraded',
      isCurrentConversation: true,
    })

    expect(result).not.toBeNull()
    expect(result?.tone).toBe('danger')
    expect(result?.variant).toBe('solid')
  })

  it('uses warning for waiting confirmation and neutral for cancelled state', () => {
    const waiting = resolveConversationStatusSignal({
      liveExecutionStatus: 'waiting_skill_confirmation',
    })
    const cancelled = resolveConversationStatusSignal({
      liveExecutionStatus: 'cancelled',
    })

    expect(waiting?.tone).toBe('warning')
    expect(cancelled?.tone).toBe('neutral')
  })

  it('uses info breathing for generating state', () => {
    const result = resolveConversationStatusSignal({
      liveExecutionStatus: 'running',
      isGenerating: true,
    })

    expect(result?.tone).toBe('info')
    expect(result?.variant).toBe('breathing')
  })

  it('prefers live running status over stale terminal error', () => {
    const result = resolveConversationStatusSignal({
      liveExecutionStatus: 'running',
      executionSnapshot: {
        state: 'failed',
        actionType: 'send',
        streamSessionId: null,
        startedAt: null,
        updatedAt: Date.now(),
        lastTerminalReason: 'error',
        lastErrorMessage: 'old error',
        lastDisconnectedAt: null,
        resumeAttemptCount: 0,
      },
      isGenerating: false,
    })

    expect(result?.tone).toBe('info')
    expect(result?.variant).toBe('breathing')
  })

  it('uses success pulse for unread completed conversation', () => {
    const result = resolveConversationStatusSignal({
      isCompletedUnread: true,
    })

    expect(result?.tone).toBe('success')
    expect(result?.variant).toBe('pulse')
    expect(result?.label).toBe('新消息')
  })

  it('prefers unread pulse over stale cancelled terminal when live status is idle', () => {
    const result = resolveConversationStatusSignal({
      liveExecutionStatus: 'idle',
      executionSnapshot: {
        state: 'idle',
        actionType: 'send',
        streamSessionId: null,
        startedAt: null,
        updatedAt: Date.now(),
        lastTerminalReason: 'cancelled',
        lastErrorMessage: null,
        lastDisconnectedAt: null,
        resumeAttemptCount: 0,
      },
      isCompletedUnread: true,
    })

    expect(result?.tone).toBe('success')
    expect(result?.variant).toBe('pulse')
  })

  it('uses backend sidebar signal as source of truth when provided', () => {
    const result = resolveConversationStatusSignal({
      sidebarSignalState: 'error',
      liveExecutionStatus: 'running',
      isGenerating: true,
      isCompletedUnread: true,
    })

    expect(result?.tone).toBe('danger')
    expect(result?.variant).toBe('solid')
  })

  it('falls back to live status when sidebar signal is explicitly none', () => {
    const result = resolveConversationStatusSignal({
      sidebarSignalState: 'none',
      liveExecutionStatus: 'waiting_skill_confirmation',
    })

    expect(result?.tone).toBe('warning')
    expect(result?.label).toBe('待确认')
  })

  it('applies polling warning only for current conversation', () => {
    const current = resolveConversationStatusSignal({
      pollingHealth: 'retrying',
      isCurrentConversation: true,
    })
    const other = resolveConversationStatusSignal({
      pollingHealth: 'retrying',
      isCurrentConversation: false,
    })

    expect(current?.tone).toBe('info')
    expect(other).toBeNull()
  })
})
