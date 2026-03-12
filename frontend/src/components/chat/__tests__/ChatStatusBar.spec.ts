import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChatStatusBar from '@/components/chat/ChatStatusBar.vue'

describe('ChatStatusBar', () => {
  it('shows streaming status without recovery actions', () => {
    const wrapper = mount(ChatStatusBar, {
      props: {
        state: 'streaming',
        pollingHealth: 'healthy',
        liveExecution: {
          status: 'running',
          stage: 'tool_running',
          stage_detail: '调用工具中：knowledge_search',
          round_no: 2,
        },
      },
    })

    expect(wrapper.classes()).toContain('is-info')
    expect(wrapper.classes()).toContain('is-generating')
    expect(wrapper.text()).toContain('生成中')
    expect(wrapper.text()).toContain('调用工具中：knowledge_search')
    expect(wrapper.text()).not.toContain('重试本轮')
    expect(wrapper.text()).not.toContain('刷新会话')
  })

  it('shows degraded status with retry and refresh actions', async () => {
    const wrapper = mount(ChatStatusBar, {
      props: {
        pollingHealth: 'degraded',
        lastErrorMessage: '同步失败',
      },
    })

    expect(wrapper.text()).toContain('同步异常，可重试')
    expect(wrapper.text()).toContain('同步失败')

    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toBeTruthy()

    const refreshButton = wrapper.findAll('button').at(1)
    await refreshButton?.trigger('click')
    expect(wrapper.emitted('refresh')).toBeTruthy()

    const detailsButton = wrapper.findAll('button').at(2)
    await detailsButton?.trigger('click')
    expect(wrapper.emitted('details')).toBeTruthy()
  })

  it('shows failed status when terminal reason is error', async () => {
    const wrapper = mount(ChatStatusBar, {
      props: {
        state: 'failed',
        pollingHealth: 'healthy',
        lastTerminalReason: 'error',
        lastErrorMessage: '模型调用超时',
      },
    })

    expect(wrapper.text()).toContain('已失败')
    expect(wrapper.text()).toContain('模型调用超时')
    expect(wrapper.text()).toContain('重试本轮')
    expect(wrapper.text()).toContain('刷新会话')

    const buttons = wrapper.findAll('button')
    await buttons.at(0)?.trigger('click')
    await buttons.at(1)?.trigger('click')
    await buttons.at(2)?.trigger('click')
    expect(wrapper.emitted('retry')).toBeTruthy()
    expect(wrapper.emitted('refresh')).toBeTruthy()
    expect(wrapper.emitted('details')).toBeTruthy()
  })

  it('shows cancelled status text when terminal reason is cancelled', () => {
    const wrapper = mount(ChatStatusBar, {
      props: {
        state: 'idle',
        pollingHealth: 'healthy',
        lastTerminalReason: 'cancelled',
      },
    })

    expect(wrapper.text()).toContain('已取消')
    expect(wrapper.text()).toContain('本轮对话已停止，可重新发送。')
    expect(wrapper.text()).not.toContain('重试本轮')
  })
})
