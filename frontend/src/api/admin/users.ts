import request from '../request'

export function getUserList(params?: { page?: number; page_size?: number; keyword?: string }) {
  return request.get('/users', { params })
}

export function createUser(data: { username: string; password: string; display_name: string; role: string }) {
  return request.post('/users', data)
}

export function updateUser(id: number, data: { display_name?: string; role?: string; is_active?: boolean }) {
  return request.put(`/users/${id}`, data)
}

export function resetUserPassword(id: number, newPassword: string) {
  return request.put(`/users/${id}/reset-password`, { new_password: newPassword })
}

export function approveUser(id: number) {
  return request.put(`/users/${id}/approve`)
}

export function getUserDeleteCheck(id: number) {
  return request.get(`/users/${id}/delete-check`)
}

export function deleteUser(id: number, forceTransfer = false) {
  return request.delete(`/users/${id}`, {
    params: { force_transfer: forceTransfer || undefined },
  })
}
