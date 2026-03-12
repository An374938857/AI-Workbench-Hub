import { ref } from 'vue'

export interface ShortcutConfig {
  key: string
  handler: () => void
  label: string
  group: string
}

const registeredShortcuts = ref<ShortcutConfig[]>([])
let listenerAttached = false

function normalizeKey(key: string): string[] {
  return key.toLowerCase().split('+').map(p => p.trim())
}

function matchEvent(e: KeyboardEvent, parts: string[]): boolean {
  for (const p of parts) {
    switch (p) {
      case 'meta': case 'cmd': case 'command':
        if (!e.metaKey) return false
        break
      case 'ctrl': case 'control':
        if (!e.ctrlKey) return false
        break
      case 'alt': case 'option':
        if (!e.altKey) return false
        break
      case 'shift':
        if (!e.shiftKey) return false
        break
      default: {
        const eventKey = e.key.toLowerCase()
        if (eventKey !== p && e.code.toLowerCase() !== `key${p}` && e.code.toLowerCase() !== `digit${p}` && e.code.toLowerCase() !== p) {
          return false
        }
      }
    }
  }
  return true
}

function handleKeyDown(e: KeyboardEvent) {
  // 忽略 el-dialog 等弹窗内的输入（除全局快捷键外）
  const active = document.activeElement
  const isInput =
    active?.tagName === 'INPUT' ||
    active?.tagName === 'TEXTAREA' ||
    (active as HTMLElement)?.contentEditable === 'true'

  for (const config of registeredShortcuts.value) {
    const parts = normalizeKey(config.key)
    if (matchEvent(e, parts)) {
      if (isInput && config.group !== '全局' && config.group !== 'global') continue
      e.preventDefault()
      e.stopPropagation()
      config.handler()
      return
    }
  }
}

function ensureListener() {
  if (!listenerAttached) {
    document.addEventListener('keydown', handleKeyDown, true)
    listenerAttached = true
  }
}

export function useShortcuts() {
  function register(config: ShortcutConfig) {
    // 同一作用域下的相同快捷键只保留最新注册，避免 HMR 或页面切换后残留 stale handler
    const idx = registeredShortcuts.value.findIndex(
      s => s.key === config.key && s.group === config.group
    )
    if (idx !== -1) {
      registeredShortcuts.value.splice(idx, 1, config)
    } else {
      registeredShortcuts.value.push(config)
    }
    ensureListener()
  }

  function getAll() {
    return registeredShortcuts.value
  }

  return { register, getAll }
}
