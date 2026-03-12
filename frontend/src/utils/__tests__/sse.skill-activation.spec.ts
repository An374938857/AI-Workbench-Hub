import { describe, expect, it, vi } from 'vitest'
import { sendMessageSSE } from '@/utils/sse'

describe('SSE skill activation waiting state', () => {
  it('does not treat skill_activation_request as stream disconnection error', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue('mock-token'),
    })

    const streamText = [
      'event: message',
      'data: {"type":"skill_activation_request","skill_id":13,"skill_name":"brainstorming","skill_description":"desc"}',
      '',
    ].join('\n')

    const encoder = new TextEncoder()
    const mockReader = {
      read: vi.fn()
        .mockResolvedValueOnce({ done: false, value: encoder.encode(streamText) })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    }

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => mockReader,
      },
    }))

    const onError = vi.fn()
    const onSkillActivationRequest = vi.fn()

    await sendMessageSSE(
      533,
      'test',
      [],
      {
        onChunk: vi.fn(),
        onDone: vi.fn(),
        onCancelled: vi.fn(),
        onTitleUpdated: vi.fn(),
        onContextWarning: vi.fn(),
        onError,
        onSkillActivationRequest,
      },
    )

    expect(onSkillActivationRequest).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalledWith('连接已中断，请重试')
  })
})
