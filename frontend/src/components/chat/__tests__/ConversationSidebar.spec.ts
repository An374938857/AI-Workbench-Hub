import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConversationSidebar from '@/components/chat/ConversationSidebar.vue'
import type { ConversationExecutionSnapshot } from '@/types/chatExecution'
import type { SidebarSignal } from '@/types/chat'

interface TestConversation {
  id: number
  skill_id: number | null
  skill_name: string
  title: string
  updated_at: string
  live_execution?: {
    status: 'idle' | 'running' | 'waiting_skill_confirmation' | 'cancelled' | 'error'
  }
  sidebar_signal?: SidebarSignal
}

function createProps(overrides: Partial<InstanceType<typeof ConversationSidebar>['$props']> = {}) {
  return {
    conversations: [
      {
        id: 1,
        skill_id: null,
        skill_name: '自由对话',
        title: '会话1',
        updated_at: '2026-03-11T08:00:00Z',
        live_execution: { status: 'idle' },
        sidebar_signal: { state: 'none' },
      },
    ] as TestConversation[],
    allTags: [],
    activeTagFilter: null,
    isSelectMode: false,
    selectedConvIds: new Set<number>(),
    currentConvId: null,
    editingSidebarTitleConvId: null,
    editingSidebarTitleText: '',
    generatingConvIds: new Set<number>(),
    conversationExecutionStates: new Map<number, ConversationExecutionSnapshot>(),
    pollingHealth: 'healthy' as const,
    loadingMoreConversations: false,
    hasMoreConversations: false,
    getTagFilterItemStyle: () => ({}),
    formatTime: () => '刚刚',
    convHasTag: () => false,
    setSidebarTitleInputRef: () => undefined,
    ...overrides,
  }
}

describe('ConversationSidebar status pill', () => {
  it('shows blue breathing status pill for generating conversations', () => {
    const wrapper = mount(ConversationSidebar, {
      props: createProps({
        generatingConvIds: new Set([1]),
        conversations: [{
          id: 1,
          skill_id: null,
          skill_name: '自由对话',
          title: '会话1',
          updated_at: '2026-03-11T08:00:00Z',
          live_execution: { status: 'running' },
          sidebar_signal: { state: 'running' },
        }],
      }),
    })

    const pill = wrapper.find('.conv-status-pill')
    expect(pill.exists()).toBe(true)
    expect(pill.classes()).toContain('is-info')
    expect(pill.classes()).toContain('is-breathing')
    expect(wrapper.find('.conv-generating-icon').exists()).toBe(false)
  })

  it('shows warning status pill for waiting skill confirmation', () => {
    const wrapper = mount(ConversationSidebar, {
      props: createProps({
        conversations: [{
          id: 1,
          skill_id: null,
          skill_name: '自由对话',
          title: '会话1',
          updated_at: '2026-03-11T08:00:00Z',
          live_execution: { status: 'waiting_skill_confirmation' },
          sidebar_signal: { state: 'waiting_skill_confirmation' },
        }],
      }),
    })

    const pill = wrapper.find('.conv-status-pill')
    expect(pill.classes()).toContain('is-warning')
  })

  it('shows danger status pill for error status', () => {
    const wrapper = mount(ConversationSidebar, {
      props: createProps({
        conversations: [{
          id: 1,
          skill_id: null,
          skill_name: '自由对话',
          title: '会话1',
          updated_at: '2026-03-11T08:00:00Z',
          live_execution: { status: 'error' },
          sidebar_signal: { state: 'error' },
        }],
      }),
    })

    const pill = wrapper.find('.conv-status-pill')
    expect(pill.classes()).toContain('is-danger')
  })

  it('shows success pulse status pill for unread completed reply', () => {
    const wrapper = mount(ConversationSidebar, {
      props: createProps({
        conversations: [{
          id: 1,
          skill_id: null,
          skill_name: '自由对话',
          title: '会话1',
          updated_at: '2026-03-11T08:00:00Z',
          live_execution: { status: 'idle' },
          sidebar_signal: { state: 'unread_reply' },
        }],
      }),
    })

    const pill = wrapper.find('.conv-status-pill')
    expect(pill.classes()).toContain('is-success')
    expect(pill.classes()).toContain('is-pulse')
    expect(pill.attributes('title')).toContain('新消息')
  })
})

describe('ConversationSidebar info hierarchy', () => {
  it('shows only 2 visible tags with +N overflow summary', () => {
    const wrapper = mount(ConversationSidebar, {
      props: createProps({
        conversations: [{
          id: 1,
          skill_id: null,
          skill_name: '自由对话',
          title: '会话1',
          updated_at: '2026-03-11T08:00:00Z',
          live_execution: { status: 'idle' },
          sidebar_signal: { state: 'none' },
          tags: [
            { id: 1, name: '项目需求', color: '#9B87F5' },
            { id: 2, name: '测试', color: '#F59E0B' },
            { id: 3, name: '收藏', color: '#22C55E' },
          ],
        }],
      }),
    })

    expect(wrapper.findAll('.conv-tags > .tag-badge')).toHaveLength(2)
  })

  it('renders collapsed skill summary and expands skill names on toggle', async () => {
    const wrapper = mount(ConversationSidebar, {
      props: createProps({
        conversations: [{
          id: 1,
          skill_id: null,
          skill_name: '自由对话',
          title: '会话1',
          updated_at: '2026-03-11T08:00:00Z',
          live_execution: { status: 'idle' },
          sidebar_signal: { state: 'none' },
          active_skills: [
            { id: 11, name: 'brainstorming' },
            { id: 12, name: 'prd-generator' },
          ],
        }],
      }),
    })

    const toggle = wrapper.find('[data-test="skill-summary-toggle-1"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toContain('技能 2 个')
    expect(wrapper.find('[data-test="skill-expanded-1"]').exists()).toBe(false)

    await toggle.trigger('click')

    expect(wrapper.find('[data-test="skill-expanded-1"]').text()).toContain('brainstorming')
    expect(wrapper.find('[data-test="skill-expanded-1"]').text()).toContain('prd-generator')
  })

  it('uses single row menu trigger for actions', () => {
    const wrapper = mount(ConversationSidebar, {
      props: createProps(),
    })

    expect(wrapper.find('[data-test="row-action-trigger-1"]').exists()).toBe(true)
    expect(wrapper.findAll('.conv-action-btn')).toHaveLength(1)
  })
})
