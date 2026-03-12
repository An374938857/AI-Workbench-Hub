import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChatComposer from '@/components/chat/ChatComposer.vue'

const baseProps = {
  setChatInputAreaRef: () => {},
  setFileUploaderRef: () => {},
  setSkillManagerRef: () => {},
  currentConvId: 1,
  quotedMessages: [],
  showReferenceComposerBar: false,
  referenceEmptyMode: 'none' as const,
  referenceSelectedCount: 0,
  clearReferenceDisabled: false,
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
  getTemplatePreview: () => '',
  isForkMode: false,
  isMessageEditMode: false,
  isDragging: false,
  isGenerating: false,
  optimizing: false,
  inputText: 'hello',
  inputKey: 1,
  inputExpanded: false,
  isComposing: false,
  templatePopoverVisible: false,
  currentTemplateLabel: '自由对话',
  currentTemplateId: null,
  visibleTemplateList: [],
  loadingTemplate: false,
  autoRouteEnabled: false,
  compareMode: false,
  selectedProviderId: null,
  selectedModelName: null,
  compareModelBProviderId: null,
  compareModelBName: null,
  currentProviderId: null,
  currentModelName: null,
}

const globalStubs = {
  FileUploader: { template: '<div class="file-uploader" />' },
  MessageQuote: true,
  SkillManager: { template: '<div class="skill-manager" />' },
  ModelSelector: true,
  PromptTemplateSelector: true,
  ConversationCommandPalette: true,
  ReferenceComposerBar: true,
  ElInput: { template: '<textarea class="mock-el-input" />' },
  ElButton: { template: '<button class="mock-el-button" @click="$emit(\'click\')"><slot /></button>' },
  ElSwitch: { template: '<input type="checkbox" class="mock-switch" />' },
  ElTooltip: { template: '<div><slot /></div>' },
  ElIcon: { template: '<span><slot /></span>' },
  Share: true,
  Edit: true,
  Paperclip: true,
  MagicStick: true,
  Plus: true,
  ArrowUp: true,
  ArrowDown: true,
}

describe('ChatComposer', () => {
  it('shows send action and emits send when idle', async () => {
    const wrapper = mount(ChatComposer, {
      props: {
        ...baseProps,
        isGenerating: false,
        inputText: 'hello',
      },
      global: {
        stubs: globalStubs,
      },
    })

    expect(wrapper.text()).toContain('发送')
    await wrapper.find('.send-btn').trigger('click')
    expect(wrapper.emitted('send')).toBeTruthy()
  })

  it('shows stop action and emits stop when generating', async () => {
    const wrapper = mount(ChatComposer, {
      props: {
        ...baseProps,
        isGenerating: true,
      },
      global: {
        stubs: globalStubs,
      },
    })

    expect(wrapper.text()).toContain('停止')
    await wrapper.find('.stop-btn').trigger('click')
    expect(wrapper.emitted('stop')).toBeTruthy()
  })

  it('shows edit banner and emits cancel-message-edit in message edit mode', async () => {
    const wrapper = mount(ChatComposer, {
      props: {
        ...baseProps,
        isMessageEditMode: true,
      },
      global: {
        stubs: globalStubs,
      },
    })

    expect(wrapper.text()).toContain('编辑消息')
    expect(wrapper.text()).toContain('保存并重新生成')

    const cancelButtons = wrapper.findAll('.mock-el-button')
    const target = cancelButtons.find((button) => button.text().includes('取消'))
    expect(target).toBeTruthy()
    await target!.trigger('click')
    expect(wrapper.emitted('cancel-message-edit')).toBeTruthy()
  })
})
