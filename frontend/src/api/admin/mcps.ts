import request from '../request'

export interface McpInspectionConfigPayload {
  interval_hours: number
  interval_minutes: number
}

export function getMcpList(params?: { page?: number; page_size?: number; keyword?: string; is_enabled?: boolean }) {
  return request.get('/admin/mcps', { params })
}

export function getMcpDetail(id: number) {
  return request.get(`/admin/mcps/${id}`)
}

export function createMcp(data: {
  name: string
  description: string
  config_json: object
  timeout_seconds?: number
  max_retries?: number
  circuit_breaker_threshold?: number
  circuit_breaker_recovery?: number
  access_role?: string
}) {
  return request.post('/admin/mcps', data)
}

export function updateMcp(id: number, data: Record<string, any>) {
  return request.put(`/admin/mcps/${id}`, data)
}

export function deleteMcp(id: number) {
  return request.delete(`/admin/mcps/${id}`)
}

export function toggleMcp(id: number, isEnabled: boolean) {
  return request.post(`/admin/mcps/${id}/toggle`, { is_enabled: isEnabled })
}

export function testMcp(id: number) {
  return request.post(`/admin/mcps/${id}/test`, {}, { timeout: 20000 })
}

export function refreshMcpTools(id: number) {
  return request.post(`/admin/mcps/${id}/refresh-tools`, {}, { timeout: 15000 })
}

export function getMcpTools(id: number) {
  return request.get(`/admin/mcps/${id}/tools`)
}

export function toggleMcpTool(mcpId: number, toolId: number, isEnabled: boolean) {
  return request.put(`/admin/mcps/${mcpId}/tools/${toolId}/toggle`, { is_enabled: isEnabled })
}

export function batchTestMcps() {
  return request.post('/admin/mcps/batch-test', {}, { timeout: 120000 })
}

export function getMcpInspectionConfig() {
  return request.get('/admin/mcps/inspection-config')
}

export function updateMcpInspectionConfig(data: McpInspectionConfigPayload) {
  return request.put('/admin/mcps/inspection-config', data)
}
