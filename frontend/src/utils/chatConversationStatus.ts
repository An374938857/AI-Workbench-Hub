import type { ConversationExecutionSnapshot, ConversationExecutionState } from '@/types/chatExecution'
import type { LiveExecutionState, SidebarSignalState } from '@/types/chat'

export type ConversationStatusTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'
export type ConversationStatusVariant = 'breathing' | 'pulse' | 'solid'

export interface ConversationStatusSignal {
  tone: ConversationStatusTone
  variant: ConversationStatusVariant
  label: string
  priority: number
}

interface ResolveConversationStatusSignalInput {
  sidebarSignalState?: SidebarSignalState | null
  liveExecutionStatus?: LiveExecutionState['status'] | null
  executionState?: ConversationExecutionState | null
  executionSnapshot?: ConversationExecutionSnapshot | null
  isGenerating?: boolean
  isCompletedUnread?: boolean
  pollingHealth?: 'healthy' | 'retrying' | 'degraded'
  isCurrentConversation?: boolean
}

function resolveBySidebarSignalState(
  state: SidebarSignalState | null | undefined,
): ConversationStatusSignal | null {
  if (!state || state === 'none') return null
  if (state === 'running') {
    return {
      tone: 'info',
      variant: 'breathing',
      label: '生成中',
      priority: 200,
    }
  }
  if (state === 'unread_reply') {
    return {
      tone: 'success',
      variant: 'pulse',
      label: '新消息',
      priority: 100,
    }
  }
  if (state === 'error') {
    return {
      tone: 'danger',
      variant: 'solid',
      label: '已失败',
      priority: 400,
    }
  }
  if (state === 'cancelled') {
    return {
      tone: 'neutral',
      variant: 'solid',
      label: '已取消',
      priority: 300,
    }
  }
  if (state === 'waiting_skill_confirmation') {
    return {
      tone: 'warning',
      variant: 'solid',
      label: '待确认',
      priority: 300,
    }
  }
  return null
}

function asTerminalReason(
  input: ResolveConversationStatusSignalInput,
) {
  return input.executionSnapshot?.lastTerminalReason ?? null
}

function shouldUseTerminalReason(input: ResolveConversationStatusSignalInput): boolean {
  return input.liveExecutionStatus == null
}

function resolveDangerSignal(input: ResolveConversationStatusSignalInput): ConversationStatusSignal | null {
  const terminalReason = asTerminalReason(input)
  const degradedForCurrent = input.isCurrentConversation && input.pollingHealth === 'degraded'
  if (degradedForCurrent || input.liveExecutionStatus === 'error') {
    return {
      tone: 'danger',
      variant: 'solid',
      label: '已失败',
      priority: 400,
    }
  }
  if (shouldUseTerminalReason(input) && terminalReason === 'stream_disconnected') {
    return {
      tone: 'danger',
      variant: 'solid',
      label: '连接中断',
      priority: 400,
    }
  }
  if (shouldUseTerminalReason(input) && (terminalReason === 'error' || terminalReason === 'throw')) {
    return {
      tone: 'danger',
      variant: 'solid',
      label: '已失败',
      priority: 400,
    }
  }
  return null
}

function resolveWarningSignal(input: ResolveConversationStatusSignalInput): ConversationStatusSignal | null {
  const terminalReason = asTerminalReason(input)
  const retryingForCurrent = input.isCurrentConversation && input.pollingHealth === 'retrying'
  if (input.liveExecutionStatus === 'waiting_skill_confirmation') {
    return {
      tone: 'warning',
      variant: 'solid',
      label: '待确认',
      priority: 300,
    }
  }
  if (input.executionState === 'cancelling' || input.liveExecutionStatus === 'cancelled') {
    return {
      tone: 'neutral',
      variant: 'solid',
      label: '已取消',
      priority: 300,
    }
  }
  if (shouldUseTerminalReason(input) && (terminalReason === 'cancelled' || terminalReason === 'user_stop')) {
    return {
      tone: 'neutral',
      variant: 'solid',
      label: '已取消',
      priority: 300,
    }
  }
  if (retryingForCurrent) {
    return {
      tone: 'info',
      variant: 'solid',
      label: '重试中',
      priority: 300,
    }
  }
  return null
}

function resolveSuccessSignal(input: ResolveConversationStatusSignalInput): ConversationStatusSignal | null {
  const isRunning = input.liveExecutionStatus === 'running'
  const isPreparing = input.executionState === 'preparing'
  const isStreaming = input.executionState === 'streaming'
  if (input.isGenerating || isRunning || isPreparing || isStreaming) {
    return {
      tone: 'info',
      variant: 'breathing',
      label: '生成中',
      priority: 200,
    }
  }
  return null
}

function resolveUnreadSignal(input: ResolveConversationStatusSignalInput): ConversationStatusSignal | null {
  if (!input.isCompletedUnread) return null
  return {
    tone: 'success',
    variant: 'pulse',
    label: '新消息',
    priority: 100,
  }
}

export function resolveConversationStatusSignal(
  input: ResolveConversationStatusSignalInput,
): ConversationStatusSignal | null {
  if (input.sidebarSignalState !== undefined) {
    const sidebarSignal = resolveBySidebarSignalState(input.sidebarSignalState)
    if (sidebarSignal) return sidebarSignal
  }
  return (
    resolveDangerSignal(input)
    ?? resolveWarningSignal(input)
    ?? resolveSuccessSignal(input)
    ?? resolveUnreadSignal(input)
    ?? null
  )
}
