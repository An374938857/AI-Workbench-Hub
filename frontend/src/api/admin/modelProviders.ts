import request from '../request'

export function getModelProviderList() {
  return request.get('/admin/model-providers')
}

export function createModelProvider(data: Record<string, unknown>) {
  return request.post('/admin/model-providers', data)
}

export function updateModelProvider(id: number, data: Record<string, unknown>) {
  return request.put(`/admin/model-providers/${id}`, data)
}

export function deleteModelProvider(id: number) {
  return request.delete(`/admin/model-providers/${id}`)
}

export function toggleModelProvider(id: number, isEnabled: boolean) {
  return request.post(`/admin/model-providers/${id}/toggle`, { is_enabled: isEnabled })
}

export function testModelProvider(id: number) {
  return request.post(`/admin/model-providers/${id}/test`)
}

export function getAvailableModels() {
  return request.get('/admin/model-providers/available-models')
}

export function setDefaultModel(providerId: number, modelName: string) {
  return request.post(`/admin/model-providers/${providerId}/models/${modelName}/set-default`)
}

export function getDefaultModelForAdmin() {
  return request.get('/admin/model-providers/default')
}

export function updateModelTags(
  providerId: number,
  modelName: string,
  data: {
    capability_tags?: string[]
    speed_rating?: string
    cost_rating?: string
    description?: string
    max_output_tokens?: number
  }
) {
  return request.put(`/admin/model-providers/${providerId}/models/${modelName}/tags`, data)
}

export function getEmbeddingConfig() {
  return request.get('/admin/model-providers/embedding-config')
}

export function updateEmbeddingConfig(data: {
  global_default_text_embedding_model_id?: number | null
  global_default_multimodal_embedding_model_id?: number | null
  rebuild_index: boolean
}) {
  return request.post('/admin/model-providers/embedding-config', data)
}

export function getEmbeddingRebuildTasks(limit = 20) {
  return request.get('/admin/model-providers/embedding-rebuild/tasks', { params: { limit } })
}

export function getEmbeddingRebuildTaskItems(taskId: number, limit = 100) {
  return request.get(`/admin/model-providers/embedding-rebuild/tasks/${taskId}/items`, { params: { limit } })
}

export function startEmbeddingRebuildTask(taskId: number) {
  return request.post(`/admin/model-providers/embedding-rebuild/tasks/${taskId}/start`)
}

export function retryFailedEmbeddingRebuildTask(taskId: number) {
  return request.post(`/admin/model-providers/embedding-rebuild/tasks/${taskId}/retry-failed`)
}

export function cancelEmbeddingRebuildTask(taskId: number) {
  return request.post(`/admin/model-providers/embedding-rebuild/tasks/${taskId}/cancel`)
}
