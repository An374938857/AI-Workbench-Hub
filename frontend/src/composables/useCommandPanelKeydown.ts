import { nextTick, type Ref } from 'vue'

interface CommandPanelKeydownOptions {
  showMcpList: Ref<boolean>
  selectedMcpIndex: Ref<number>
  filteredMcpList: Ref<any[]>

  showSkillList: Ref<boolean>
  selectedSkillIndex: Ref<number>
  filteredSkillList: Ref<any[]>
  selectSkill: (skill: any) => void | Promise<void>

  showModelList: Ref<boolean>
  selectedModelIndex: Ref<number>
  filteredModelList: Ref<any[]>
  selectModel: (model: any) => void | Promise<void>

  showTemplateList: Ref<boolean>
  selectedTemplateIndex: Ref<number>
  filteredTemplateList: Ref<any[]>
  selectTemplate: (template: any) => void | Promise<void>

  showCommandSuggestions: Ref<boolean>
  selectedCommandIndex: Ref<number>
  commandSuggestions: Ref<any[]>
  executeCommand: (command: any) => void | Promise<void>

  inputText: Ref<string>
  isForkMode?: Ref<boolean>
  cancelFork?: () => void
  isMessageEditMode?: Ref<boolean>
  cancelMessageEdit?: () => void

  isComposing: Ref<boolean>
  isGenerating: Ref<boolean>
  handleSend: () => void
}

function scrollActiveItem(selector: string) {
  nextTick(() => {
    const item = document.querySelector(selector)
    item?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
}

export function useCommandPanelKeydown(options: CommandPanelKeydownOptions) {
  function handleKeyDown(event: KeyboardEvent) {
    if (options.showMcpList.value) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        options.selectedMcpIndex.value = (options.selectedMcpIndex.value + 1) % options.filteredMcpList.value.length
        scrollActiveItem('.mcp-list .command-suggestion-item.active')
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        options.selectedMcpIndex.value = options.selectedMcpIndex.value === 0
          ? options.filteredMcpList.value.length - 1
          : options.selectedMcpIndex.value - 1
        scrollActiveItem('.mcp-list .command-suggestion-item.active')
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        options.showMcpList.value = false
        return
      }
    }

    if (options.showSkillList.value) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        options.selectedSkillIndex.value = (options.selectedSkillIndex.value + 1) % options.filteredSkillList.value.length
        scrollActiveItem('.skill-list .command-suggestion-item.active')
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        options.selectedSkillIndex.value = options.selectedSkillIndex.value === 0
          ? options.filteredSkillList.value.length - 1
          : options.selectedSkillIndex.value - 1
        scrollActiveItem('.skill-list .command-suggestion-item.active')
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        options.showSkillList.value = false
        return
      }
      if (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey)) {
        event.preventDefault()
        const selected = options.filteredSkillList.value[options.selectedSkillIndex.value]
        if (selected) {
          void options.selectSkill(selected)
        }
        return
      }
    }

    if (options.showModelList.value) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        options.selectedModelIndex.value = (options.selectedModelIndex.value + 1) % options.filteredModelList.value.length
        scrollActiveItem('.model-list .command-suggestion-item.active')
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        options.selectedModelIndex.value = options.selectedModelIndex.value === 0
          ? options.filteredModelList.value.length - 1
          : options.selectedModelIndex.value - 1
        scrollActiveItem('.model-list .command-suggestion-item.active')
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        options.showModelList.value = false
        return
      }
      if (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey)) {
        event.preventDefault()
        const selected = options.filteredModelList.value[options.selectedModelIndex.value]
        if (selected) {
          void options.selectModel(selected)
        }
        return
      }
    }

    if (options.showTemplateList.value) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        options.selectedTemplateIndex.value = (options.selectedTemplateIndex.value + 1) % options.filteredTemplateList.value.length
        scrollActiveItem('.template-list .command-suggestion-item.active')
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        options.selectedTemplateIndex.value = options.selectedTemplateIndex.value === 0
          ? options.filteredTemplateList.value.length - 1
          : options.selectedTemplateIndex.value - 1
        scrollActiveItem('.template-list .command-suggestion-item.active')
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        options.showTemplateList.value = false
        return
      }
      if (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey)) {
        event.preventDefault()
        const selected = options.filteredTemplateList.value[options.selectedTemplateIndex.value]
        if (selected) {
          void options.selectTemplate(selected)
        }
        return
      }
    }

    if (options.showCommandSuggestions.value) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        options.selectedCommandIndex.value = (options.selectedCommandIndex.value + 1) % options.commandSuggestions.value.length
        scrollActiveItem('.command-suggestions .command-suggestion-item.active')
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        options.selectedCommandIndex.value = options.selectedCommandIndex.value === 0
          ? options.commandSuggestions.value.length - 1
          : options.selectedCommandIndex.value - 1
        scrollActiveItem('.command-suggestions .command-suggestion-item.active')
        return
      }
      if (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey)) {
        event.preventDefault()
        const selected = options.commandSuggestions.value[options.selectedCommandIndex.value]
        if (selected) {
          void options.executeCommand(selected)
          options.inputText.value = ''
          options.showCommandSuggestions.value = false
        }
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        options.showCommandSuggestions.value = false
        return
      }
    }

    if (event.key === 'Escape' && options.isForkMode?.value && options.cancelFork) {
      event.preventDefault()
      options.cancelFork()
      return
    }

    if (event.key === 'Escape' && options.isMessageEditMode?.value && options.cancelMessageEdit) {
      event.preventDefault()
      options.cancelMessageEdit()
      return
    }

    if (event.key === 'Enter' && !event.shiftKey && !options.isComposing.value) {
      event.preventDefault()
      if (!options.isGenerating.value) {
        options.handleSend()
      }
    }
  }

  return {
    handleKeyDown,
  }
}

export type { CommandPanelKeydownOptions }
