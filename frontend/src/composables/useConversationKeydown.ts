import { useCommandPanelKeydown, type CommandPanelKeydownOptions } from './useCommandPanelKeydown'

export function useConversationKeydown(options: CommandPanelKeydownOptions) {
  return useCommandPanelKeydown(options)
}
