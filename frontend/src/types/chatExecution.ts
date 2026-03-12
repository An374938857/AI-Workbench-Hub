export type ConversationExecutionState =
  | 'idle'
  | 'preparing'
  | 'streaming'
  | 'waiting_skill_confirmation'
  | 'cancelling'
  | 'failed'
  | 'completed'

export type ConversationActionType =
  | 'send'
  | 'edit'
  | 'regenerate'
  | 'fork'
  | 'continue_from_tool'
  | 'continue_from_assistant'
  | 'landing_send'

export type ActionTerminalReason =
  | 'done'
  | 'cancelled'
  | 'error'
  | 'throw'
  | 'unmount'
  | 'route_switch'
  | 'stream_disconnected'
  | 'user_stop'
  | 'resume_replace'

export interface ConversationExecutionSnapshot {
  state: ConversationExecutionState
  actionType: ConversationActionType | null
  streamSessionId: string | null
  startedAt: number | null
  updatedAt: number
  lastTerminalReason: ActionTerminalReason | null
  lastErrorMessage: string | null
  lastDisconnectedAt: string | null
  resumeAttemptCount: number
}

export interface ConversationStreamAction {
  conversationId: number
  actionType: ConversationActionType
  abortController: AbortController
}

export interface ActionTerminalResult {
  conversationId: number
  streamSessionId?: string
  reason: ActionTerminalReason
  errorMessage?: string | null
  clearGenerating?: boolean
}
