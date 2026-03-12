import request from './request'

export function getAutoRoute() {
  return request.get('/users/me/auto-route')
}

export function toggleAutoRoute(enabled: boolean) {
  return request.patch('/users/me/auto-route', { enabled })
}
