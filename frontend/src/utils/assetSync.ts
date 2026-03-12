export type AssetSyncTagType = 'info' | 'warning' | 'danger'

const SYNC_IN_PROGRESS = new Set(['PENDING', 'RUNNING'])

export function normalizeAssetSyncStatus(status?: string): string {
  return String(status || '').toUpperCase()
}

export function isAssetSyncInProgressStatus(status?: string): boolean {
  return SYNC_IN_PROGRESS.has(normalizeAssetSyncStatus(status))
}

export function getAssetSyncLabel(status?: string): string {
  const normalized = normalizeAssetSyncStatus(status)
  if (normalized === 'PENDING') return '等待下载'
  if (normalized === 'RUNNING') return '下载中'
  if (normalized === 'FAILED') return '下载失败'
  return ''
}

export function getAssetSyncTagType(status?: string): AssetSyncTagType {
  const normalized = normalizeAssetSyncStatus(status)
  if (normalized === 'FAILED') return 'danger'
  if (normalized === 'RUNNING') return 'warning'
  return 'info'
}

export function countFailedSyncAssets<T extends { refetch_status?: string }>(items: T[]): number {
  return items.filter((item) => normalizeAssetSyncStatus(item.refetch_status) === 'FAILED').length
}

export function isYuqueUrl(url?: string): boolean {
  if (!url) return false
  try {
    const parsed = new URL(url)
    const host = parsed.hostname.toLowerCase()
    return host === 'yuque.com' || host.endsWith('.yuque.com') || host === 'yuque.cn' || host.endsWith('.yuque.cn')
  } catch {
    return false
  }
}
