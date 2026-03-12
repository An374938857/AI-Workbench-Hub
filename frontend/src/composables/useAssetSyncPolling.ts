import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'

import { countFailedSyncAssets, isAssetSyncInProgressStatus } from '@/utils/assetSync'

interface UseAssetSyncPollingOptions<T extends { refetch_status?: string }> {
  assets: Readonly<Ref<T[]>>
  isVisible: Readonly<Ref<boolean>>
  refresh: () => void | Promise<void>
  onSettled?: (failedCount: number) => void
  intervalMs?: number
}

export function useAssetSyncPolling<T extends { refetch_status?: string }>(
  options: UseAssetSyncPollingOptions<T>,
) {
  const { assets, isVisible, refresh, onSettled, intervalMs = 3000 } = options
  const timer = ref<number | null>(null)
  const hadRunningTask = ref(false)

  const hasInProgress = computed(() => assets.value.some((asset) => isAssetSyncInProgressStatus(asset.refetch_status)))

  function start() {
    if (timer.value !== null) return
    timer.value = window.setInterval(() => {
      if (!isVisible.value) return
      void refresh()
    }, intervalMs)
  }

  function stop() {
    if (timer.value === null) return
    window.clearInterval(timer.value)
    timer.value = null
  }

  function markTaskSubmitted() {
    hadRunningTask.value = true
    if (isVisible.value) start()
  }

  watch(
    isVisible,
    (visible) => {
      if (!visible) {
        stop()
        return
      }
      if (hasInProgress.value) start()
    },
    { immediate: true },
  )

  watch(hasInProgress, (inProgress) => {
    if (inProgress) {
      hadRunningTask.value = true
      if (isVisible.value) start()
      return
    }
    stop()
    if (!hadRunningTask.value) return
    onSettled?.(countFailedSyncAssets(assets.value))
    hadRunningTask.value = false
  })

  onBeforeUnmount(() => {
    stop()
  })

  return {
    hasInProgress,
    markTaskSubmitted,
    stop,
  }
}
