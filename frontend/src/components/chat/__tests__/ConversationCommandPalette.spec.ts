import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConversationCommandPalette from '@/components/chat/ConversationCommandPalette.vue'

const baseProps = {
  showCommandSuggestions: false,
  commandSuggestions: [],
  selectedCommandIndex: 0,
  showTemplateList: false,
  filteredTemplateList: [],
  selectedTemplateIndex: 0,
  isFreeTemplateGlobalDefault: false,
  globalDefaultTemplateId: null,
  showMcpList: false,
  filteredMcpList: [],
  selectedMcpIndex: 0,
  showSkillList: false,
  filteredSkillList: [],
  selectedSkillIndex: 0,
  showModelList: false,
  filteredModelList: [],
  selectedModelIndex: 0,
  listSearchQuery: '',
  getTemplatePreview: (template: any) => template?.description || '',
}

describe('ConversationCommandPalette', () => {
  it('emits command-select when command suggestion is clicked', async () => {
    const command = { name: '/new', description: 'new chat' }
    const wrapper = mount(ConversationCommandPalette, {
      props: {
        ...baseProps,
        showCommandSuggestions: true,
        commandSuggestions: [command],
      },
      global: {
        stubs: {
          ElTag: true,
        },
      },
    })

    await wrapper.find('.command-suggestion-item').trigger('click')
    expect(wrapper.emitted('command-select')?.[0]?.[0]).toEqual(command)
  })

  it('emits list search update and keydown events in template mode', async () => {
    const wrapper = mount(ConversationCommandPalette, {
      props: {
        ...baseProps,
        showTemplateList: true,
        filteredTemplateList: [{ id: 1, name: '模板A', description: 'desc', is_favorited: false }],
      },
      global: {
        stubs: {
          ElTag: true,
        },
      },
    })

    const input = wrapper.find('.list-search-input')
    await input.setValue('模板')
    expect(wrapper.emitted('update:listSearchQuery')?.[0]?.[0]).toBe('模板')

    await input.trigger('keydown', { key: 'ArrowDown' })
    const keydownEvent = wrapper.emitted('list-keydown')?.[0]?.[0]
    expect((keydownEvent as KeyboardEvent).key).toBe('ArrowDown')
  })
})
