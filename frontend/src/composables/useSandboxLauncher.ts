import { computed, ref } from 'vue'

interface SandboxLauncherOptions {
  getCurrentConversationId: () => number | null
  onOpenPanel?: () => void
  onClosePanel?: () => void
  onNoConversation?: () => void
}

export function useSandboxLauncher(options: SandboxLauncherOptions) {
  const sandboxPanelVisible = ref(false)
  const sandboxLauncherVisible = ref(true)
  const sandboxLauncherTop = ref(228)
  const sandboxLauncherDragging = ref(false)
  const sandboxLauncherMoved = ref(false)
  const sandboxLauncherPointerId = ref<number | null>(null)
  const sandboxLauncherStartY = ref(0)
  const sandboxLauncherOriginTop = ref(0)

  const sandboxLauncherStyle = computed(() => ({
    top: `${sandboxLauncherTop.value}px`,
  }))

  function clampSandboxLauncherTop(nextTop: number) {
    const viewportHeight = window.innerHeight || 0
    const minTop = 132
    const maxTop = Math.max(minTop, viewportHeight - 196)
    return Math.min(Math.max(nextTop, minTop), maxTop)
  }

  function syncSandboxLauncherTop(nextTop: number) {
    sandboxLauncherTop.value = clampSandboxLauncherTop(nextTop)
  }

  function handleSandboxLauncherResize() {
    syncSandboxLauncherTop(sandboxLauncherTop.value)
  }

  function openSandboxPanel() {
    if (!options.getCurrentConversationId()) {
      options.onNoConversation?.()
      return
    }

    sandboxLauncherVisible.value = false
    sandboxPanelVisible.value = true
    options.onOpenPanel?.()
  }

  function closeSandboxPanel() {
    sandboxPanelVisible.value = false
    options.onClosePanel?.()
  }

  function handleSandboxDrawerClosed() {
    sandboxLauncherVisible.value = true
  }

  function handleSandboxLauncherPointerDown(event: PointerEvent) {
    if (!options.getCurrentConversationId()) return

    sandboxLauncherPointerId.value = event.pointerId
    sandboxLauncherStartY.value = event.clientY
    sandboxLauncherOriginTop.value = sandboxLauncherTop.value
    sandboxLauncherDragging.value = true
    sandboxLauncherMoved.value = false

    const target = event.currentTarget as HTMLElement | null
    target?.setPointerCapture?.(event.pointerId)
  }

  function handleSandboxLauncherPointerMove(event: PointerEvent) {
    if (!sandboxLauncherDragging.value || sandboxLauncherPointerId.value !== event.pointerId) return

    const deltaY = event.clientY - sandboxLauncherStartY.value
    if (Math.abs(deltaY) > 4) {
      sandboxLauncherMoved.value = true
    }
    syncSandboxLauncherTop(sandboxLauncherOriginTop.value + deltaY)
  }

  function handleSandboxLauncherPointerUp(event: PointerEvent) {
    if (sandboxLauncherPointerId.value !== event.pointerId) return

    const target = event.currentTarget as HTMLElement | null
    target?.releasePointerCapture?.(event.pointerId)

    const moved = sandboxLauncherMoved.value
    sandboxLauncherDragging.value = false
    sandboxLauncherMoved.value = false
    sandboxLauncherPointerId.value = null

    if (!moved) {
      if (sandboxPanelVisible.value) {
        closeSandboxPanel()
      } else {
        openSandboxPanel()
      }
    }
  }

  function handleSandboxLauncherPointerCancel(event: PointerEvent) {
    if (sandboxLauncherPointerId.value !== event.pointerId) return

    const target = event.currentTarget as HTMLElement | null
    target?.releasePointerCapture?.(event.pointerId)

    sandboxLauncherDragging.value = false
    sandboxLauncherMoved.value = false
    sandboxLauncherPointerId.value = null
  }

  function syncSandboxPanelFromRoute(shouldOpen: boolean) {
    if (sandboxPanelVisible.value !== shouldOpen) {
      if (shouldOpen) {
        sandboxLauncherVisible.value = false
      }
      sandboxPanelVisible.value = shouldOpen
    }
  }

  return {
    sandboxPanelVisible,
    sandboxLauncherVisible,
    sandboxLauncherTop,
    sandboxLauncherDragging,
    sandboxLauncherStyle,
    syncSandboxLauncherTop,
    handleSandboxLauncherResize,
    openSandboxPanel,
    closeSandboxPanel,
    handleSandboxDrawerClosed,
    handleSandboxLauncherPointerDown,
    handleSandboxLauncherPointerMove,
    handleSandboxLauncherPointerUp,
    handleSandboxLauncherPointerCancel,
    syncSandboxPanelFromRoute,
  }
}
