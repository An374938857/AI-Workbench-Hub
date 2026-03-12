import type { Ref } from 'vue'
import { getAutoRoute, toggleAutoRoute } from '@/api/userPreferences'

interface UseAutoRoutePreferenceOptions {
  autoRouteEnabled: Ref<boolean>
  onEnable?: () => void
}

export function useAutoRoutePreference(options: UseAutoRoutePreferenceOptions) {
  const { autoRouteEnabled, onEnable } = options

  async function initAutoRoutePreference() {
    try {
      const response: any = await getAutoRoute()
      autoRouteEnabled.value = response?.data?.auto_route_enabled ?? true
    } catch {
      // ignore init failures and keep current value
    }
  }

  async function setAutoRouteEnabled(value: boolean) {
    if (value && onEnable) {
      onEnable()
    }
    try {
      await toggleAutoRoute(value)
      autoRouteEnabled.value = value
    } catch {
      autoRouteEnabled.value = !value
    }
  }

  async function disableAutoRoute() {
    if (!autoRouteEnabled.value) return
    autoRouteEnabled.value = false
    try {
      await toggleAutoRoute(false)
    } catch {
      // keep local disabled to respect explicit user choice
    }
  }

  return {
    initAutoRoutePreference,
    setAutoRouteEnabled,
    disableAutoRoute,
  }
}
