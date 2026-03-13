<script setup lang="ts">
import { ref, computed, reactive, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ThemeToggle from '@/components/ThemeToggle.vue'
import SearchBar from '@/components/SearchBar.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import { useShortcuts } from '@/composables/useShortcuts'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const { register } = useShortcuts()

const searchBarRef = ref<InstanceType<typeof SearchBar>>()
const commandPaletteRef = ref<InstanceType<typeof CommandPalette>>()
const menuWrapRef = ref<HTMLElement | null>(null)
const pendingActivePath = ref<string | null>(null)
let pendingClearTimer: ReturnType<typeof setTimeout> | null = null
const navItems = computed(() => {
  const items = [
    { path: '/', label: '首页' },
    { path: '/projects', label: '项目' },
    { path: '/requirements', label: '需求池' },
    { path: '/skills', label: '能力广场' },
    { path: '/mcps', label: 'MCP' },
    { path: '/prompt-templates', label: '提示词' },
    { path: '/chat', label: '历史对话' },
  ]
  if (authStore.isAdmin) {
    items.push({ path: '/admin/dashboard', label: '数据看板' })
  }
  return items
})
const navIndicatorStyle = reactive({
  transform: 'translateX(0px)',
  width: '0px',
  opacity: '0',
  '--nav-duration': '360ms',
})
const navIndicatorState = reactive({
  x: 0,
  width: 0,
})
const activeMenuPath = computed(() => pendingActivePath.value ?? resolveMenuPath(route.path))
const isMainScrollable = computed(() => route.meta.scrollableMain === true)
const useCompactMainTop = computed(() => route.path.startsWith('/projects') || route.path.startsWith('/requirements'))
const isMainFullBleed = computed(() => route.meta.fullBleedMain === true)
const showGuideEntry = computed(() => route.path === '/')
const shortcutModifierLabel = computed(() => {
  if (typeof navigator === 'undefined') return 'Ctrl'
  return /Mac|iPhone|iPad|iPod/i.test(navigator.platform) ? '⌘' : 'Ctrl'
})
const commandPaletteCommands = computed(() => [
  { key: 'meta+k', label: '打开快捷键面板', description: '查看所有可用快捷键' },
  { key: 'meta+f', label: '搜索对话', description: '搜索历史对话' },
  { key: 'meta+1', label: '首页', description: '回到首页' },
  { key: 'meta+2', label: '项目', description: '进入项目列表' },
  { key: 'meta+3', label: '需求池', description: '进入需求池' },
  { key: 'meta+4', label: '能力广场', description: '浏览所有技能' },
  { key: 'meta+5', label: 'MCP', description: '浏览 MCP 广场' },
  { key: 'meta+6', label: '提示词', description: '进入提示词列表' },
  { key: 'meta+7', label: '历史对话', description: '查看历史对话' },
])
const dialogCommands = [
  { key: '/', label: '快捷指令', description: '输入 / 触发指令补全' },
  { key: 'enter', label: '发送消息', description: '发送当前消息' },
  { key: 'shift+enter', label: '换行', description: '在消息中换行' },
  { key: 'escape', label: '取消', description: '取消当前操作' },
]

function resolveMenuPath(path: string): string {
  if (path.startsWith('/sandbox-files')) return '/chat'
  if (navItems.value.some(item => item.path === path)) return path
  const matched = navItems.value.find(item => path.startsWith(item.path === '/' ? '/__never__' : item.path))
  return matched?.path || '/'
}

function findMenuItemByPath(path: string): HTMLElement | null {
  const wrap = menuWrapRef.value
  if (!wrap) return null
  const labels = Array.from(wrap.querySelectorAll('.menu-item-label')) as HTMLElement[]
  const label = labels.find(el => el.dataset.navPath === path)
  return (label?.closest('.el-menu-item') as HTMLElement | null) ?? null
}

function setPendingMenuPath(path: string) {
  pendingActivePath.value = resolveMenuPath(path)
  if (pendingClearTimer) clearTimeout(pendingClearTimer)
  // 兜底清理，防止极端情况下 pending 状态停留
  pendingClearTimer = setTimeout(() => {
    pendingActivePath.value = null
    pendingClearTimer = null
    void syncNavIndicator(route.path)
  }, 1200)
}

async function syncNavIndicator(targetPath?: string) {
  await nextTick()
  const wrap = menuWrapRef.value
  if (!wrap) return

  const resolvedPath = resolveMenuPath(targetPath ?? activeMenuPath.value)
  const activeItem = findMenuItemByPath(resolvedPath) ?? (wrap.querySelector('.el-menu-item.is-active') as HTMLElement | null)
  const menu = wrap.querySelector('.el-menu') as HTMLElement | null
  if (!activeItem || !menu) {
    // 找不到目标项时保持当前状态，避免切页过程中闪烁
    return
  }

  const wrapRect = wrap.getBoundingClientRect()
  const itemRect = activeItem.getBoundingClientRect()
  const targetX = itemRect.left - wrapRect.left
  const targetWidth = itemRect.width

  if (navIndicatorStyle.opacity === '0') {
    navIndicatorStyle.transform = `translateX(${targetX}px)`
    navIndicatorStyle.width = `${targetWidth}px`
    navIndicatorStyle.opacity = '1'
    navIndicatorState.x = targetX
    navIndicatorState.width = targetWidth
    return
  }

  const currentX = navIndicatorState.x
  const distance = Math.abs(targetX - currentX)
  const duration = Math.min(480, Math.max(240, 260 + distance * 0.6))
  navIndicatorStyle['--nav-duration'] = `${Math.round(duration)}ms`

  navIndicatorStyle.transform = `translateX(${targetX}px)`
  navIndicatorStyle.width = `${targetWidth}px`
  navIndicatorStyle.opacity = '1'
  navIndicatorState.x = targetX
  navIndicatorState.width = targetWidth
}

function handleWindowResize() {
  void syncNavIndicator(activeMenuPath.value)
}

function handleMenuSelect(path: string) {
  setPendingMenuPath(path)
  void syncNavIndicator(path)
}


function handleLogout() {
  authStore.logout()
  router.push('/login')
}

function openCommandPalette() {
  commandPaletteRef.value?.open()
}

register({ key: 'meta+f', handler: () => searchBarRef.value?.open(), label: '搜索对话', group: '全局' })
register({ key: 'meta+k', handler: openCommandPalette, label: '打开快捷键面板', group: '全局' })
register({ key: 'ctrl+k', handler: openCommandPalette, label: '打开快捷键面板', group: '全局' })
register({ key: 'meta+1', handler: () => router.push('/'), label: '首页', group: '导航' })
register({ key: 'meta+2', handler: () => router.push('/projects'), label: '项目', group: '导航' })
register({ key: 'meta+3', handler: () => router.push('/requirements'), label: '需求池', group: '导航' })
register({ key: 'meta+4', handler: () => router.push('/skills'), label: '能力广场', group: '导航' })
register({ key: 'meta+5', handler: () => router.push('/mcps'), label: 'MCP', group: '导航' })
register({ key: 'meta+6', handler: () => router.push('/prompt-templates'), label: '提示词', group: '导航' })
register({ key: 'meta+7', handler: () => router.push('/chat'), label: '历史对话', group: '导航' })

watch(() => route.path, () => {
  const resolved = resolveMenuPath(route.path)
  if (pendingActivePath.value === resolved) {
    pendingActivePath.value = null
    if (pendingClearTimer) {
      clearTimeout(pendingClearTimer)
      pendingClearTimer = null
    }
  } else {
    // 路由由其他入口触发时，确保不会残留旧 pending
    pendingActivePath.value = null
  }
  void syncNavIndicator(resolved)
})

onMounted(() => {
  void syncNavIndicator()
  window.addEventListener('resize', handleWindowResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleWindowResize)
  if (pendingClearTimer) clearTimeout(pendingClearTimer)
})
</script>

<template>
  <el-container class="layout-container">
    <el-header class="layout-header">
      <div class="header-left">
        <router-link to="/" class="logo">
          <el-icon :size="24"><Promotion /></el-icon>
          <span class="logo-text">AI 能力共享平台</span>
        </router-link>
        <div ref="menuWrapRef" class="header-menu-wrap">
          <el-menu
            mode="horizontal"
            :router="true"
            :default-active="activeMenuPath"
            :ellipsis="false"
            class="header-menu"
            @select="handleMenuSelect"
          >
            <el-menu-item
              v-for="item in navItems"
              :key="item.path"
              :index="item.path"
            >
              <span class="menu-item-label" :data-nav-path="item.path">{{ item.label }}</span>
            </el-menu-item>
          </el-menu>
          <span class="nav-indicator" :style="navIndicatorStyle" />
        </div>
      </div>
      <div class="header-right">
        <button
          v-if="showGuideEntry"
          class="shortcut-hint"
          type="button"
          title="打开快捷键面板"
          aria-label="打开快捷键面板"
          @click="openCommandPalette"
        >
          <span class="shortcut-key">{{ shortcutModifierLabel }}</span>
          <span class="shortcut-key">K</span>
        </button>
        <SearchBar ref="searchBarRef" />
        <ThemeToggle />
        <el-dropdown>
          <span class="user-info">
            <el-icon><User /></el-icon>
            {{ authStore.user?.display_name }}
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-if="authStore.isProvider" @click="router.push('/admin/skills')">
                管理后台
              </el-dropdown-item>
              <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>
    <div
      v-if="showGuideEntry"
      class="guide-entry-btn guide-entry-btn--floating"
      aria-hidden="true"
    >
      <el-icon :size="18"><Opportunity /></el-icon>
    </div>
    <el-main
      :class="[
        'layout-main',
        {
          'layout-main--scrollable': isMainScrollable,
          'layout-main--compact-top': useCompactMainTop,
          'layout-main--full-bleed': isMainFullBleed,
        },
      ]"
    >
      <router-view />
    </el-main>
    <CommandPalette ref="commandPaletteRef" :commands="commandPaletteCommands" :dialog-commands="dialogCommands" />
  </el-container>
</template>

<style scoped>
.layout-container {
  min-height: 100vh;
  background: var(--bg-page, #f5f7fa);
  overflow: hidden; /* 禁用容器滚动 */
  height: 100vh; /* 固定高度 */
}

.layout-header {
  background: var(--bg-card, #fff);
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: var(--shadow-sm, 0 1px 4px rgba(0, 0, 0, 0.08));
  padding: 0 24px;
  z-index: 100;
  position: sticky;
  top: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: #409eff;
  font-weight: 600;
  font-size: 16px;
}

.logo-text {
  white-space: nowrap;
}

.header-menu {
  border-bottom: none !important;
  background: transparent !important;
  position: relative;
}

.header-menu-wrap {
  position: relative;
}

.header-menu :deep(.el-menu-item) {
  color: var(--text-secondary, #606266) !important;
  background: transparent !important;
  width: 100px; /* 固定等宽 */
  text-align: center;
  padding: 0 !important;
}

.header-menu :deep(.el-menu-item:hover),
.header-menu :deep(.el-menu-item.is-active) {
  color: #409eff !important;
  background: transparent !important;
}

.header-menu :deep(.el-menu--horizontal > .el-menu-item::after) {
  display: none !important;
}

.nav-indicator {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(90deg, #4da3ff 0%, #409eff 100%);
  box-shadow: 0 1px 8px rgba(64, 158, 255, 0.35);
  transform-origin: left center;
  transition:
    transform var(--nav-duration, 360ms) cubic-bezier(0.2, 0.9, 0.28, 1),
    width var(--nav-duration, 360ms) cubic-bezier(0.2, 0.9, 0.28, 1),
    opacity 180ms ease;
  will-change: transform, width;
  pointer-events: none;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.guide-entry-btn {
  width: 38px;
  height: 38px;
  border-radius: 999px;
  border: 1px solid rgba(145, 164, 195, 0.35);
  background: linear-gradient(160deg, rgba(255, 255, 255, 0.95) 0%, rgba(236, 244, 255, 0.82) 100%);
  color: #23548a;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 8px 16px rgba(28, 61, 105, 0.12);
}

.guide-entry-btn--floating {
  position: fixed;
  top: 86px;
  right: 28px;
  z-index: 120;
}

html.dark .guide-entry-btn {
  border-color: rgba(145, 170, 214, 0.34);
  background: linear-gradient(160deg, rgba(28, 40, 58, 0.9) 0%, rgba(18, 28, 44, 0.86) 100%);
  color: #93c5fd;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 8px 18px rgba(3, 8, 18, 0.35);
}

@media (max-width: 768px) {
  .guide-entry-btn--floating {
    top: 78px;
    right: 16px;
  }
}

.shortcut-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: transparent;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.shortcut-hint:hover {
  background: rgba(0, 0, 0, 0.04);
  border-color: rgba(0, 0, 0, 0.12);
  transform: translateY(-1px);
}

.shortcut-hint:active {
  transform: translateY(0);
}

html.dark .shortcut-hint {
  border-color: rgba(255, 255, 255, 0.08);
}

html.dark .shortcut-hint:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
}

.shortcut-key {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  font-size: 11px;
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-weight: 500;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.9) 0%, rgba(255, 255, 255, 0.7) 100%);
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-bottom-width: 2px;
  border-radius: 4px;
  color: var(--text-primary, #0f172a);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

html.dark .shortcut-key {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.1) 0%, rgba(255, 255, 255, 0.05) 100%);
  border-color: rgba(255, 255, 255, 0.15);
  color: var(--text-primary, #f1f5f9);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: var(--text-secondary, #606266);
  font-size: 14px;
}

.layout-main {
  padding: 24px;
  padding-top: 84px; /* 导航栏高度(60px) + 间距(24px) */
  overflow: hidden; /* 默认禁用页面滚动，避免影响聊天页等固定布局 */
}

.layout-main--scrollable {
  overflow-y: auto;
  overflow-x: hidden;
}

.layout-main--compact-top {
  padding-top: 24px;
}

.layout-main--full-bleed {
  padding: 0;
}

html.dark .layout-container {
  background: var(--bg-page, #1a1a1a);
}

html.dark .layout-header {
  background: #1a1d22;
  box-shadow: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

html.dark .layout-main {
  background: var(--bg-page, #1a1a1a);
}

html.dark .header-menu :deep(.el-menu-item) {
  color: rgba(229, 231, 235, 0.66) !important;
}

html.dark .header-menu :deep(.el-menu-item:hover),
html.dark .header-menu :deep(.el-menu-item.is-active) {
  color: #f3f4f6 !important;
}

html.dark .user-info {
  color: rgba(229, 231, 235, 0.78);
}
</style>
