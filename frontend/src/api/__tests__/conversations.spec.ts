import { describe, expect, it, vi } from 'vitest'
import request from '@/api/request'
import { activateConversationSkill } from '@/api/conversations'

vi.mock('@/api/request', () => ({
  default: {
    post: vi.fn(),
  },
}))

describe('conversations api', () => {
  it('activates conversation skill with query param', async () => {
    await activateConversationSkill(506, 12)

    expect(request.post).toHaveBeenCalledWith(
      '/conversations/506/skills',
      null,
      { params: { skill_id: 12 } },
    )
  })
})
