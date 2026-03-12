import request from '../request'

export interface RoutingRule {
  id: number
  intent_category: string
  display_name: string
  keywords: string[]
  preferred_tags: string[]
  preferred_model: string | null
  priority: number
  is_enabled: boolean
}

export function getRoutingRules() {
  return request.get('/admin/routing-rules')
}

export function createRoutingRule(data: Omit<RoutingRule, 'id'>) {
  return request.post('/admin/routing-rules', data)
}

export function updateRoutingRule(id: number, data: Omit<RoutingRule, 'id'>) {
  return request.put(`/admin/routing-rules/${id}`, data)
}

export function deleteRoutingRule(id: number) {
  return request.delete(`/admin/routing-rules/${id}`)
}
