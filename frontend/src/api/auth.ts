import request from './request'

export function login(username: string, password: string) {
  return request.post('/auth/login', { username, password })
}

export function getMe() {
  return request.get('/auth/me')
}

export function changePassword(oldPassword: string, newPassword: string) {
  return request.put('/auth/me/password', {
    old_password: oldPassword,
    new_password: newPassword,
  })
}

export function changePasswordOnLogin(username: string, oldPassword: string, newPassword: string) {
  return request.post('/auth/change-password', {
    username,
    old_password: oldPassword,
    new_password: newPassword,
  })
}

export function register(data: { username: string; password: string; display_name: string; role: string }) {
  return request.post('/auth/register', data)
}
