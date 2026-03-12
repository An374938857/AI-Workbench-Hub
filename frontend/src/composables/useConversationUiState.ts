import { computed, ref } from 'vue'

function buildTemplatePreview(content: string): string {
  const normalized = content.replace(/\s+/g, ' ').trim()
  const maxLen = 60
  return normalized.length > maxLen ? `${normalized.slice(0, maxLen)}...` : normalized
}

export function useConversationUiState() {
  const showCommandSuggestions = ref(false)
  const commandSuggestions = ref<any[]>([])
  const selectedCommandIndex = ref(0)
  const allCommands = ref<any[]>([])
  const chatInputAreaRef = ref<HTMLElement | null>(null)

  const showTemplateList = ref(false)
  const selectedTemplateIndex = ref(0)

  const showModelList = ref(false)
  const selectedModelIndex = ref(0)

  const showSkillList = ref(false)
  const selectedSkillIndex = ref(0)

  const showMcpList = ref(false)
  const selectedMcpIndex = ref(0)

  const listSearchQuery = ref('')

  const modelList = ref<any[]>([])
  const skillList = ref<any[]>([])
  const mcpList = ref<any[]>([])
  const templateList = ref<any[]>([])
  const currentTemplateId = ref<number | null>(null)
  const loadingTemplate = ref(false)
  const templatePopoverVisible = ref(false)

  const currentTemplateLabel = computed(() => {
    if (!currentTemplateId.value) {
      const globalDefault = templateList.value.find((tpl: any) => tpl.is_global_default || tpl.is_default)
      return globalDefault?.name || '选择模板'
    }
    const current = templateList.value.find((tpl: any) => tpl.id === currentTemplateId.value)
    return current?.name || '选择模板'
  })

  const isCurrentTemplateFavorited = computed(() => {
    if (!currentTemplateId.value) return false
    const current = templateList.value.find((tpl: any) => tpl.id === currentTemplateId.value)
    return Boolean(current?.is_favorited)
  })

  const globalDefaultTemplateId = computed<number | null>(() => {
    const globalDefault = templateList.value.find((tpl: any) => tpl.is_global_default || tpl.is_default)
    return globalDefault?.id ?? null
  })

  const isFreeTemplateGlobalDefault = computed(() => {
    if (globalDefaultTemplateId.value == null) return true
    const globalDefault = templateList.value.find((tpl: any) => tpl.id === globalDefaultTemplateId.value)
    return (globalDefault?.name || '').trim() === '自由对话'
  })

  const isCurrentTemplateDefault = computed(() => {
    if (!currentTemplateId.value) return isFreeTemplateGlobalDefault.value
    return currentTemplateId.value === globalDefaultTemplateId.value
  })

  const visibleTemplateList = computed(() => {
    return templateList.value.filter((tpl: any) => tpl.name !== '自由对话')
  })

  const templateCommandList = computed(() => visibleTemplateList.value)

  function getTemplatePreview(template: any): string {
    const raw = typeof template?.content === 'string' ? template.content : ''
    const preview = buildTemplatePreview(raw)
    if (!preview) {
      return template?.is_favorited
        ? '收藏模板'
        : template?.id === globalDefaultTemplateId.value
          ? '默认模板'
          : '提示词模板'
    }
    return preview
  }

  const filteredModelList = computed(() => {
    const q = listSearchQuery.value.toLowerCase()
    return q
      ? modelList.value.filter(
        (item) => (item.display_name || '').toLowerCase().includes(q) || (item.provider_name || '').toLowerCase().includes(q),
      )
      : modelList.value
  })

  const filteredSkillList = computed(() => {
    const q = listSearchQuery.value.toLowerCase()
    return q
      ? skillList.value.filter(
        (item) => (item.name || '').toLowerCase().includes(q) || (item.description || '').toLowerCase().includes(q),
      )
      : skillList.value
  })

  const filteredMcpList = computed(() => {
    const q = listSearchQuery.value.toLowerCase()
    return q
      ? mcpList.value.filter(
        (item) => (item.name || '').toLowerCase().includes(q) || (item.description || '').toLowerCase().includes(q),
      )
      : mcpList.value
  })

  const filteredTemplateList = computed(() => {
    const q = listSearchQuery.value.toLowerCase()
    return q
      ? templateCommandList.value.filter(
        (item) =>
          (item.name || '').toLowerCase().includes(q)
          || (item.description || '').toLowerCase().includes(q)
          || getTemplatePreview(item).toLowerCase().includes(q),
      )
      : templateCommandList.value
  })

  const optimizing = ref(false)
  const showOptimizedDialog = ref(false)
  const optimizedPrompt = ref('')
  const optimizeAbortController = ref<AbortController | null>(null)
  const optimizedPromptContainerRef = ref<HTMLElement | null>(null)
  const shouldAutoScrollOptimizedPrompt = ref(true)

  const editingSidebarTitleConvId = ref<number | null>(null)
  const editingSidebarTitleText = ref('')
  const editingHeaderTitle = ref(false)
  const editingHeaderTitleText = ref('')
  const headerTitleInputRef = ref<HTMLInputElement | null>(null)
  const sidebarTitleInputRefs = new Map<number, HTMLInputElement>()

  function setSidebarTitleInputRef(convId: number, el: HTMLInputElement | null) {
    if (!el) {
      sidebarTitleInputRefs.delete(convId)
      return
    }
    sidebarTitleInputRefs.set(convId, el)
  }

  function updateOptimizedPromptAutoScroll() {
    const el = optimizedPromptContainerRef.value
    if (!el) return
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    shouldAutoScrollOptimizedPrompt.value = distanceToBottom <= 24
  }

  function scrollOptimizedPromptToBottom() {
    const el = optimizedPromptContainerRef.value
    if (!el) return
    el.scrollTop = el.scrollHeight
    shouldAutoScrollOptimizedPrompt.value = true
  }

  function resetListSelectionIndices() {
    selectedTemplateIndex.value = 0
    selectedModelIndex.value = 0
    selectedSkillIndex.value = 0
    selectedMcpIndex.value = 0
  }

  function closeCommandPanels() {
    showCommandSuggestions.value = false
    showTemplateList.value = false
    showSkillList.value = false
    showMcpList.value = false
    showModelList.value = false
  }

  function updateCommandSuggestionsByInput(inputValue: string) {
    if (!inputValue.startsWith('/')) {
      showCommandSuggestions.value = false
      return
    }

    const query = inputValue.slice(1).toLowerCase()
    if (query === '') {
      commandSuggestions.value = allCommands.value.slice(0, 8)
    } else {
      commandSuggestions.value = allCommands.value.filter((command) =>
        command.name.toLowerCase().includes(query)
        || command.label.toLowerCase().includes(query)
        || command.description.toLowerCase().includes(query),
      ).slice(0, 8)
    }
    showCommandSuggestions.value = commandSuggestions.value.length > 0
    selectedCommandIndex.value = 0
  }

  return {
    showCommandSuggestions,
    commandSuggestions,
    selectedCommandIndex,
    allCommands,
    chatInputAreaRef,
    showTemplateList,
    selectedTemplateIndex,
    showModelList,
    selectedModelIndex,
    showSkillList,
    selectedSkillIndex,
    showMcpList,
    selectedMcpIndex,
    listSearchQuery,
    modelList,
    skillList,
    mcpList,
    templateList,
    currentTemplateId,
    loadingTemplate,
    templatePopoverVisible,
    currentTemplateLabel,
    isCurrentTemplateFavorited,
    globalDefaultTemplateId,
    isFreeTemplateGlobalDefault,
    isCurrentTemplateDefault,
    visibleTemplateList,
    getTemplatePreview,
    filteredModelList,
    filteredSkillList,
    filteredMcpList,
    filteredTemplateList,
    optimizing,
    showOptimizedDialog,
    optimizedPrompt,
    optimizeAbortController,
    optimizedPromptContainerRef,
    shouldAutoScrollOptimizedPrompt,
    editingSidebarTitleConvId,
    editingSidebarTitleText,
    editingHeaderTitle,
    editingHeaderTitleText,
    headerTitleInputRef,
    sidebarTitleInputRefs,
    setSidebarTitleInputRef,
    updateOptimizedPromptAutoScroll,
    scrollOptimizedPromptToBottom,
    resetListSelectionIndices,
    closeCommandPanels,
    updateCommandSuggestionsByInput,
  }
}
