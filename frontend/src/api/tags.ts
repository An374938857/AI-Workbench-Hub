import request from './request'

export function getTagList() {
  return request.get('/tags')
}

export function createTag(name: string, color: string) {
  return request.post('/tags', { name, color })
}

export function updateTag(id: number, data: { name?: string; color?: string; sort_order?: number }) {
  return request.put(`/tags/${id}`, data)
}

export function deleteTag(id: number) {
  return request.delete(`/tags/${id}`)
}
