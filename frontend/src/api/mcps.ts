import request from './request'

export function getMcpPublicList(params?: { keyword?: string }) {
  return request.get('/mcps', { params })
}

export function getMcpPublicDetail(id: number) {
  return request.get(`/mcps/${id}`)
}
