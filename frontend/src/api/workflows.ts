import request from './request'

export function listWorkflowDefinitions(params?: { scope?: 'PROJECT' | 'REQUIREMENT' }) {
  return request.get('/admin/workflows/definitions', { params })
}

export function getWorkflowDefinition(id: number) {
  return request.get(`/admin/workflows/definitions/${id}`)
}

export function createWorkflowDefinition(data: {
  name: string
  code: string
  scope: 'PROJECT' | 'REQUIREMENT'
  description?: string
}) {
  return request.post('/admin/workflows/definitions', data)
}

export function createWorkflowVersion(definitionId: number, data?: { version_label?: string; source_version_id?: number }) {
  return request.post(`/admin/workflows/definitions/${definitionId}/versions`, data || {})
}

export function getWorkflowVersion(versionId: number) {
  return request.get(`/admin/workflows/versions/${versionId}`)
}

export function updateWorkflowVersionNodes(versionId: number, data: { nodes: Array<Record<string, unknown>> }) {
  return request.put(`/admin/workflows/versions/${versionId}/nodes`, data)
}

export function publishWorkflowVersion(versionId: number) {
  return request.post(`/admin/workflows/versions/${versionId}/publish`)
}

export function deleteWorkflowVersion(versionId: number) {
  return request.delete(`/admin/workflows/versions/${versionId}`)
}

export function deprecateWorkflowVersion(versionId: number) {
  return request.post(`/admin/workflows/versions/${versionId}/deprecate`)
}

export function activateWorkflowDefinition(definitionId: number) {
  return request.post(`/admin/workflows/definitions/${definitionId}/activate`)
}

export function deprecateWorkflowDefinition(definitionId: number) {
  return request.post(`/admin/workflows/definitions/${definitionId}/deprecate`)
}
