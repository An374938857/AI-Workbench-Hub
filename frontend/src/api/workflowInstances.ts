import request from './request'

export function createWorkflowInstance(data: {
  scope_type: 'PROJECT' | 'REQUIREMENT'
  scope_id: number
  workflow_definition_id: number
}) {
  return request.post('/v1/workflow-instances', data)
}

export function getWorkflowInstance(id: number) {
  return request.get(`/v1/workflow-instances/${id}`)
}

export function bindNodeConversations(
  instanceId: number,
  nodeId: number,
  data: { conversation_ids: number[]; binding_type?: 'AUTO' | 'MANUAL' },
) {
  return request.post(`/v1/workflow-instances/${instanceId}/nodes/${nodeId}/bind-conversations`, data)
}

export interface WorkflowNodeConversationItem {
  binding_id: number
  conversation_id: number
  title: string
  binding_type: 'AUTO' | 'MANUAL'
  created_at?: string
  skill_name: string
  active_skills?: Array<{ id: number; name: string }>
  can_view: boolean
}

export interface WorkflowNodeConversationListResponse {
  node: {
    id: number
    node_code: string
    node_name: string
    skill_id?: number | null
    skill_name?: string | null
  }
  items: WorkflowNodeConversationItem[]
}

export function listNodeConversations(instanceId: number, nodeId: number) {
  return request.get<WorkflowNodeConversationListResponse>(`/v1/workflow-instances/${instanceId}/nodes/${nodeId}/conversations`)
}

export function unbindNodeConversation(instanceId: number, nodeId: number, conversationId: number) {
  return request.delete(`/v1/workflow-instances/${instanceId}/nodes/${nodeId}/conversations/${conversationId}`)
}

export function advanceNode(
  instanceId: number,
  nodeId: number,
  data: { to_status: string; note?: string; skip_reason?: string },
) {
  return request.post(`/v1/workflow-instances/${instanceId}/nodes/${nodeId}/advance`, data)
}

export function retryConversation(instanceId: number, nodeId: number, conversationId: number) {
  return request.post(`/v1/workflow-instances/${instanceId}/nodes/${nodeId}/retry-conversation`, null, {
    params: { conversation_id: conversationId },
  })
}

export function rollbackRecompute(instanceId: number) {
  return request.post(`/v1/workflow-instances/${instanceId}/rollback-recompute`)
}

export function cancelInstance(instanceId: number, note?: string) {
  return request.post(`/v1/workflow-instances/${instanceId}/cancel`, null, { params: { note } })
}

export function resumeInstance(instanceId: number, note?: string) {
  return request.post(`/v1/workflow-instances/${instanceId}/resume`, null, { params: { note } })
}

export interface WorkflowNodeOutputItem {
  id: number
  workflow_instance_node_id: number
  conversation_id?: number
  output_kind: string
  deliverable_type: string
  version_no: number
  title?: string
  summary?: string
  content_type: string
  content_ref: string
  is_current: boolean
  status: string
  created_at?: string
}

export function listNodeOutputs(instanceId: number, nodeId: number) {
  return request.get(`/v1/workflow-instances/${instanceId}/nodes/${nodeId}/outputs`)
}

export function createNodeOutput(
  instanceId: number,
  nodeId: number,
  data: {
    deliverable_type: string
    output_kind?: string
    content_type: string
    content_ref: string
    conversation_id?: number
    title?: string
    summary?: string
  },
) {
  return request.post(`/v1/workflow-instances/${instanceId}/nodes/${nodeId}/outputs`, data)
}

export function setCurrentNodeOutput(instanceId: number, nodeId: number, outputId: number) {
  return request.post(`/v1/workflow-instances/${instanceId}/nodes/${nodeId}/outputs/${outputId}/set-current`)
}
