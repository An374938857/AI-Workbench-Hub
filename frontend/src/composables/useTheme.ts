import { ref, watch, onMounted } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const theme = ref<ThemeMode>((localStorage.getItem('theme') as ThemeMode) || 'system')

let themeInitialized = false

function applyTheme(t: ThemeMode) {
  const isDark =
    t === 'dark' ||
    (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', isDark)
  themeInitialized = true
}

function shouldReloadChatForMermaid(): boolean {
  const inChatPage = /^\/chat(?:\/|$)/.test(window.location.pathname)
  if (!inChatPage) return false
  return !!document.querySelector('.mermaid-wrapper')
}

function reloadIfChatHasMermaid() {
  if (!shouldReloadChatForMermaid()) return
  window.dispatchEvent(new CustomEvent('chat:rerender-mermaid'))
}

export function useTheme() {
  onMounted(() => {
    applyTheme(theme.value)
    window
      .matchMedia('(prefers-color-scheme: dark)')
      .addEventListener('change', () => {
        if (theme.value === 'system') {
          applyTheme('system')
          reloadIfChatHasMermaid()
        }
      })
  })

  watch(theme, (val) => {
    localStorage.setItem('theme', val)
    applyTheme(val)
    reloadIfChatHasMermaid()
  })

  function setTheme(t: ThemeMode) {
    theme.value = t
  }

  function cycleTheme() {
    const order: ThemeMode[] = ['light', 'dark', 'system']
    const idx = order.indexOf(theme.value)
    const next = order[(idx + 1) % order.length] ?? 'system'
    setTheme(next)
  }

  return { theme, setTheme, cycleTheme }
}
