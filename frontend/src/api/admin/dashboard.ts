import request from '../request'

export function getDashboardOverview(params?: { start_date?: string; end_date?: string }) {
  return request.get('/admin/dashboard/overview', { params })
}

export function getDashboardSkills(params?: { start_date?: string; end_date?: string }) {
  return request.get('/admin/dashboard/skills', { params })
}

export function getDashboardTokens(params?: { start_date?: string; end_date?: string; group_by?: string }) {
  return request.get('/admin/dashboard/tokens', { params })
}

export function getDashboardTrends(params?: { start_date?: string; end_date?: string; metric?: string }) {
  return request.get('/admin/dashboard/trends', { params })
}

export function getDashboardMcpOverview(params?: { start_date?: string; end_date?: string }) {
  return request.get('/admin/dashboard/mcp-overview', { params })
}

export function getDashboardMcpStats(params?: { start_date?: string; end_date?: string }) {
  return request.get('/admin/dashboard/mcp-stats', { params })
}

export function getDashboardToolRanking(params?: { start_date?: string; end_date?: string; limit?: number }) {
  return request.get('/admin/dashboard/tool-ranking', { params })
}
