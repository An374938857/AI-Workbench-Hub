import request from './request'

export function getSkillList(params?: { keyword?: string; tag_id?: number; page?: number; page_size?: number }) {
  return request.get('/skills', { params })
}

export function getSkillDetail(id: number) {
  return request.get(`/skills/${id}`)
}
