export interface MsgFile {
  file_id: number
  original_name: string
  file_type: string
  file_size: number
}

export interface GeneratedFile {
  fileId: number
  filename: string
  fileSize: number
}

export interface TimelineItem {
  type: 'thinking' | 'tool_call'
  isThinking?: boolean
  content?: string
  toolCallId?: string
  toolName?: string
  arguments?: string
  status?: 'calling' | 'success' | 'error'
  progressTick?: number
  elapsedMs?: number
  elapsedSeconds?: number
  resultPreview?: string
  errorMessage?: string
  files?: GeneratedFile[]
}

export interface Msg {
  clientKey: string
  id?: number
  role: 'user' | 'assistant' | 'tool' | 'system_notice'
  content: string
  files?: MsgFile[]
  timeline?: TimelineItem[]
  toolCallId?: string
  toolName?: string
  parentId?: number | null
  branchIndex?: number
  siblingCount?: number
  childBranchCount?: number
  activeChildBranchIndex?: number
  referencedMessageIds?: number[]
  forceToolbarVisible?: boolean
  exportHintActive?: boolean
  exportHintPulse?: boolean
  exportHintAcknowledged?: boolean
}

export interface TagInfo {
  id: number
  name: string
  color: string
}

export interface ActiveSkillLite {
  id: number
  name: string
}

export interface LiveExecutionState {
  status: 'idle' | 'running' | 'waiting_skill_confirmation' | 'cancelled' | 'error'
  message_id?: number | null
  error_message?: string | null
  stage?: string | null
  stage_detail?: string | null
  stage_meta?: Record<string, unknown> | null
  round_no?: number | null
  started_at?: string | null
  updated_at?: string | null
}

export type SidebarSignalState =
  | 'none'
  | 'running'
  | 'unread_reply'
  | 'error'
  | 'cancelled'
  | 'waiting_skill_confirmation'

export interface SidebarSignal {
  state: SidebarSignalState
  updated_at?: string | null
  read_at?: string | null
}

export interface ConversationLiveStateSnapshot {
  conversation_id: number
  live_execution: LiveExecutionState
  sidebar_signal?: SidebarSignal
  sandbox_unread_change_count?: number
  detail_version: string
}

export interface ConversationSyncEventPatch {
  title?: string
  live_execution?: LiveExecutionState
  sidebar_signal?: SidebarSignal
  sandbox_unread_change_count?: number
  detail_version?: string
}

export interface ConversationSyncEvent {
  type: string
  conversation_id: number
  event_version: number
  event_ts?: string
  patch: ConversationSyncEventPatch
}

export interface SkillActivationRequestEvent {
  skill_id: number
  skill_name: string
  skill_description: string
}

export interface SkillActivatedEvent {
  id: number
  name: string
  brief_desc: string
  resumeAssistantMessageId?: number | null
  resumeToolMessageId?: number | null
}

export interface SkillRejectedEvent {
  id: number
  name: string
  resumeAssistantMessageId?: number | null
  resumeToolMessageId?: number | null
}

export interface PendingSkillResume {
  assistantMessageId?: number | null
  toolMessageId?: number | null
  notice: string
}

export interface DangerConfirmOptions {
  title: string
  subject: string
  detail: string
  confirmText: string
  confirmType?: 'danger' | 'primary'
}
