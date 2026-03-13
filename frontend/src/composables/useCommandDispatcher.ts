interface CommandDispatcherHandlers {
  openModelList: () => Promise<void>
  openSkillList: () => Promise<void>
  openMcpList: () => Promise<void>
  openTemplateList: () => Promise<void>
  toggleTheme: () => void
  onNewChat?: () => Promise<void> | void
  onExport?: () => Promise<void> | void
  onCompact?: () => Promise<void> | void
  onSandbox?: () => Promise<void> | void
  onSkillCommand?: (skillData: any) => Promise<void> | void
}

export function useCommandDispatcher(handlers: CommandDispatcherHandlers) {
  async function executeCommand(command: any) {
    const name = command?.name

    if (name === '/new') {
      await handlers.onNewChat?.()
      return
    }

    if (name === '/export') {
      await handlers.onExport?.()
      return
    }

    if (name === '/compact') {
      await handlers.onCompact?.()
      return
    }

    if (name === '/sandbox') {
      await handlers.onSandbox?.()
      return
    }

    if (name === '/model') {
      await handlers.openModelList()
      return
    }

    if (name === '/skills') {
      await handlers.openSkillList()
      return
    }

    if (name === '/mcps') {
      await handlers.openMcpList()
      return
    }

    if (name === '/prompt') {
      await handlers.openTemplateList()
      return
    }

    if (name === '/theme') {
      handlers.toggleTheme()
      return
    }

    if (command?.data?.id) {
      await handlers.onSkillCommand?.(command.data)
    }
  }

  return {
    executeCommand,
  }
}
