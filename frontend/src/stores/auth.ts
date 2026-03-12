import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi, getMe } from '@/api/auth'

interface UserInfo {
  id: number
  username: string
  display_name: string
  role: string
  is_active: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('access_token') || '')
  const user = ref<UserInfo | null>(null)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isProvider = computed(() => user.value?.role === 'provider' || user.value?.role === 'admin')

  async function login(username: string, password: string) {
    const res: any = await loginApi(username, password)
    token.value = res.data.access_token
    user.value = res.data.user
    localStorage.setItem('access_token', res.data.access_token)
  }

  async function fetchUser() {
    if (!token.value) return
    try {
      const res: any = await getMe()
      user.value = res.data
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('access_token')
  }

  return { token, user, isLoggedIn, isAdmin, isProvider, login, fetchUser, logout }
})
