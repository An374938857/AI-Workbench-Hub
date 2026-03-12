import request from '../request'

export function getSceneTagList() {
  return request.get('/scene-tags')
}

export function createSceneTag(data: { name: string; sort_order: number }) {
  return request.post('/scene-tags', data)
}

export function updateSceneTag(id: number, data: { name?: string; sort_order?: number; is_active?: boolean }) {
  return request.put(`/scene-tags/${id}`, data)
}

export function deleteSceneTag(id: number) {
  return request.delete(`/scene-tags/${id}`)
}
