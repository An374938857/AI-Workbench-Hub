import request from '../request'

export function getEmbeddingConfig() {
  return request.get('/admin/embedding/config')
}

export function updateEmbeddingConfig(data: {
  global_default_text_embedding_model_id?: number | null
  global_default_multimodal_embedding_model_id?: number | null
  rebuild_index: boolean
}) {
  return request.post('/admin/embedding/config', data)
}

export function getEmbeddingRebuildTasks(limit = 20) {
  return request.get('/admin/embedding/rebuild/tasks', { params: { limit } })
}

export function getEmbeddingRebuildTaskItems(taskId: number, limit = 100) {
  return request.get(`/admin/embedding/rebuild/tasks/${taskId}/items`, { params: { limit } })
}

export function startEmbeddingRebuildTask(taskId: number) {
  return request.post(`/admin/embedding/rebuild/tasks/${taskId}/start`)
}

export function retryFailedEmbeddingRebuildTask(taskId: number) {
  return request.post(`/admin/embedding/rebuild/tasks/${taskId}/retry-failed`)
}

export function cancelEmbeddingRebuildTask(taskId: number) {
  return request.post(`/admin/embedding/rebuild/tasks/${taskId}/cancel`)
}

export function getEmbeddingFiles(params: {
  keyword?: string
  status?: 'all' | 'embedded' | 'not_embedded' | 'failed'
  page?: number
  page_size?: number
}) {
  return request.get('/admin/embedding/files', { params })
}

export function getEmbeddingFileDetail(fileId: number, params?: { chunk_size?: number; chunk_overlap?: number }) {
  return request.get(`/admin/embedding/files/${fileId}/detail`, { params })
}

export function getRecallMetrics(params?: {
  range?: '24h' | '7d' | '30d' | 'custom'
  start_time?: string
  end_time?: string
  top_n?: number
}) {
  return request.get('/admin/embedding/recall/metrics', { params })
}
