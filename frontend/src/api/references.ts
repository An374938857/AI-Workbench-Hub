import request from './request'

export interface ReferenceFileItem {
  file_id: number
  source_kind?: 'ASSET' | 'SANDBOX_FILE'
  sandbox_file_id?: number
  conversation_id?: number
  conversation_title?: string | null
  file_name: string
  logical_path: string
  source_level: string
  source_entity_id: number
  mime_type?: string | null
  file_size?: number | null
  updated_at?: string | null
  summary?: string
  node_code?: string | null
  node_name?: string | null
  scope_type?: string
  scope_id?: number
  scope_title?: string | null
}

export interface ConversationBindingInfo {
  is_bound: boolean
  scope_type?: 'PROJECT' | 'REQUIREMENT' | string
  scope_id?: number
  scope_title?: string | null
  node_id?: number
  node_name?: string | null
}

export function buildReferenceScope(conversationId: number) {
  return request.post('/reference/scope/build', { conversation_id: conversationId })
}

export function getReferenceState(conversationId: number) {
  return request.get('/reference/state', { params: { conversation_id: conversationId } })
}

export function getReferencePanel(conversationId: number, query?: string) {
  return request.get('/reference/panel', { params: { conversation_id: conversationId, query } })
}

export function confirmReferenceSelection(
  conversationId: number,
  selectedFileIds: number[],
  mode: 'persist_selection' | 'persist_empty' | 'turn_only_skip',
) {
  return request.post('/reference/selection/confirm', {
    conversation_id: conversationId,
    selected_file_ids: selectedFileIds,
    mode,
  })
}

export function clearReferenceSelection(conversationId: number) {
  return request.post('/reference/selection/clear', { conversation_id: conversationId })
}
