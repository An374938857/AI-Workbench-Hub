import request from './request'

export function getAvailableModels(conversationId?: number | null) {
  return request.get('/models/available', { params: conversationId ? { conversation_id: conversationId } : {} })
}

export function getDefaultModel() {
  return request.get('/models/default')
}
