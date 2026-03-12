import { describe, expect, it } from 'vitest'
import { shouldRequestRemoteCancelOnRouteSwitch } from '@/utils/conversationCancelPolicy'

describe('conversationCancelPolicy', () => {
  it('does not request remote cancel when switching route even if stream is owned by current view', () => {
    expect(shouldRequestRemoteCancelOnRouteSwitch(true)).toBe(false)
  })

  it('does not request remote cancel when stream is not owned by current view', () => {
    expect(shouldRequestRemoteCancelOnRouteSwitch(false)).toBe(false)
  })
})
