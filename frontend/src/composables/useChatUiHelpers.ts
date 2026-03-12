import type { TagInfo } from '@/types/chat'

export { showDangerConfirm } from '@/composables/useDangerConfirm'

function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex?.trim().replace('#', '')
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return `rgba(64, 158, 255, ${alpha})`
  }
  const r = Number.parseInt(normalized.slice(0, 2), 16)
  const g = Number.parseInt(normalized.slice(2, 4), 16)
  const b = Number.parseInt(normalized.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export function getTagFilterItemStyle(tag: TagInfo, active: boolean): Record<string, string> {
  const color = tag.color || '#409eff'
  const bg = hexToRgba(color, active ? 0.14 : 0.1)
  if (active) {
    return {
      '--tag-color': color,
      '--tag-bg': bg,
      color,
      borderColor: color,
      background: bg,
    }
  }
  return {
    '--tag-color': color,
    '--tag-bg': bg,
  }
}
