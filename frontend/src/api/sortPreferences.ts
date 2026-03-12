import request from './request'

export function getSortPreferences(targetType: 'skill' | 'mcp' | 'conversation') {
  return request.get(`/sort-preferences/${targetType}`)
}

export function updateSortPreferences(
  targetType: 'skill' | 'mcp' | 'conversation',
  items: { id: number; sort_order: number }[],
) {
  return request.put('/sort-preferences', { target_type: targetType, items })
}
