import request from './request'

export function listProjects(params?: {
  page?: number
  page_size?: number
  keyword?: string
  level?: 'S' | 'A' | 'B' | 'C' | 'DEMAND_SET'
  owner_user_id?: number
  workflow_status?: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELED'
  end_date_start?: string
  end_date_end?: string
}) {
  return request.get('/v1/projects', { params })
}

export function createProject(data: {
  name: string
  level: 'S' | 'A' | 'B' | 'C' | 'DEMAND_SET'
  start_date?: string
  end_date?: string
  metis_url?: string
  owner_user_ids: number[]
  workflow_definition_id?: number
}) {
  return request.post('/v1/projects', data)
}

export function getProject(id: number) {
  return request.get(`/v1/projects/${id}`)
}

export function updateProject(
  id: number,
  data: { name?: string; level?: string; start_date?: string; end_date?: string; metis_url?: string },
) {
  return request.put(`/v1/projects/${id}`, data)
}

export function updateProjectOwners(id: number, ownerUserIds: number[]) {
  return request.put(`/v1/projects/${id}/owners`, { owner_user_ids: ownerUserIds })
}

export function bindProjectWorkflow(id: number, workflowDefinitionId: number) {
  return request.put(`/v1/projects/${id}/workflow-binding`, { workflow_definition_id: workflowDefinitionId })
}

export function deleteProject(id: number) {
  return request.delete(`/v1/projects/${id}`)
}
