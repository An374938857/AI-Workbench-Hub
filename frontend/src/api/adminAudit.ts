import request from './request'

export interface AuditConversationItem {
  conversation_id: number
  user_id: number
  user_name: string
  conversation_title: string
  latest_message_preview: string
  model_name: string | null
  created_at: string | null
  last_activity_at: string | null
  is_abnormal: boolean
  abnormal_types: string[]
  latest_trace_started_at: string | null
  trace_count: number
  round_count: number
}

export interface AuditConversationsResponse {
  items: AuditConversationItem[]
  total: number
  page: number
  page_size: number
}

export interface AuditRoundSummary {
  round_no: number
  event_count: number
  is_abnormal: boolean
  abnormal_types: string[]
  trace_ids: string[]
  start_time: string | null
  end_time: string | null
  duration_seconds: number
}

export interface AuditTimelineResponse {
  conversation_id: number
  rounds: AuditRoundSummary[]
  trace_count: number
}

export interface AuditEventDetail {
  id: number
  trace_id: string
  event_type: string
  event_time: string | null
  source: string
  payload_raw: string
  payload_sha256: string
  verify_status: 'passed' | 'failed'
  verify_error: string | null
  error_code: string | null
  error_message: string | null
}

export interface AuditRoundDetailResponse {
  conversation_id: number
  round_no: number
  trace_ids: string[]
  request: AuditEventDetail[]
  response: AuditEventDetail[]
  tool_chain: AuditEventDetail[]
  events: AuditEventDetail[]
}

export interface AuditMetricsOverview {
  window: 'day' | 'week' | 'month'
  total_traces: number
  abnormal_traces: number
  abnormal_ratio: number
  traceability_coverage: number
  replay_success_rate: number
  abnormal_distribution: Array<{ type: string; count: number }>
}

export interface AuditReplayResponse {
  trace_id: string
  events: Array<{
    id?: number
    conversation_id: number
    round_no: number
    event_type: string
    event_time: string | null
    source: string
    payload_raw: string
    payload_sha256: string
    verify_status: string
    error_code: string | null
    error_message: string | null
  }>
}

interface AuditExportTaskResponse {
  task_id: string
  status: 'processing' | 'completed' | 'failed' | 'not_found'
  format?: 'ndjson' | 'json_array'
  download_url: string | null
  error?: string | null
}

interface RetryableRequestConfig {
  retries?: number
  delayMs?: number
}

async function withRetry<T>(
  fn: () => Promise<T>,
  options: RetryableRequestConfig = { retries: 1, delayMs: 500 },
): Promise<T> {
  const retries = options.retries ?? 1
  const delayMs = options.delayMs ?? 500

  let lastError: unknown = null
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      return await fn()
    } catch (error) {
      lastError = error
      if (attempt >= retries) {
        break
      }
      await new Promise((resolve) => setTimeout(resolve, delayMs))
    }
  }

  throw lastError
}

export function fetchAuditConversations(params: {
  page?: number
  page_size?: number
  user_id?: number
  start_time?: string
  end_time?: string
  model_name?: string
  is_abnormal?: boolean
  skill_id?: number
  mcp_tool?: string
  conversation_status?: string
  tag_id?: number
}) {
  return withRetry(() => request.get<never, { data: AuditConversationsResponse }>('/admin/audit/conversations', { params }))
}

export function fetchConversationTimeline(conversationId: number, traceId?: string) {
  return withRetry(() => request.get<never, { data: AuditTimelineResponse }>(`/admin/audit/conversations/${conversationId}/timeline`, {
    params: traceId ? { trace_id: traceId } : undefined,
  }))
}

export function fetchRoundDetail(conversationId: number, roundNo: number) {
  return withRetry(() => request.get<never, { data: AuditRoundDetailResponse }>(`/admin/audit/conversations/${conversationId}/rounds/${roundNo}`))
}

export function createAuditExportTask(payload: {
  format: 'ndjson' | 'json_array'
  filters: Record<string, unknown>
}) {
  return request.post<typeof payload, { data: { task_id: string } }>('/admin/audit/export', payload)
}

export function fetchAuditExportTask(taskId: string) {
  return withRetry(() => request.get<never, { data: AuditExportTaskResponse }>(`/admin/audit/export/${taskId}`))
}

export function fetchAuditMetrics(window: 'day' | 'week' | 'month' = 'day') {
  return withRetry(() => request.get<never, { data: AuditMetricsOverview }>('/admin/audit/metrics/overview', {
    params: { window },
  }))
}

export function fetchAuditReplay(traceId: string) {
  return withRetry(() => request.get<never, { data: AuditReplayResponse }>(`/admin/audit/replay/${traceId}`))
}

export function downloadAuditExport(taskId: string) {
  return request.get(`/admin/audit/export/${taskId}/download`, {
    responseType: 'blob',
  })
}
