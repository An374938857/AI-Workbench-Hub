import request from './request'

export function listRequirements(params?: {
  page?: number
  page_size?: number
  project_id?: number
  owner_user_id?: number
  priority?: string
  status?: string
  keyword?: string
  owner_keyword?: string
  due_date_start?: string
  due_date_end?: string
}) {
  return request.get('/v1/requirements', { params })
}

export function listRequirementOwnerOptions(params?: { keyword?: string; page_size?: number }) {
  return request.get('/v1/requirements/owner-options', { params })
}

export function createRequirement(data: {
  project_id: number
  title: string
  priority: 'P0' | 'P1' | 'P2' | 'P3'
  workflow_definition_id: number
  due_date?: string
  description?: string
}) {
  return request.post('/v1/requirements', data)
}

export function getRequirement(id: number) {
  return request.get(`/v1/requirements/${id}`)
}

export function updateRequirement(
  id: number,
  data: {
    title?: string
    owner_user_id?: number
    priority?: 'P0' | 'P1' | 'P2' | 'P3'
    status?: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELED'
    due_date?: string | null
    description?: string | null
  },
) {
  return request.put(`/v1/requirements/${id}`, data)
}

export function bindRequirementWorkflow(id: number, workflowDefinitionId: number) {
  return request.put(`/v1/requirements/${id}/workflow-binding`, { workflow_definition_id: workflowDefinitionId })
}

export function deleteRequirement(id: number) {
  return request.delete(`/v1/requirements/${id}`)
}
