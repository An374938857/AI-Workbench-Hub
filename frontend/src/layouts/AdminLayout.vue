<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ThemeToggle from '@/components/ThemeToggle.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const activeMenuIndex = computed(() => {
  const path = route.path
  if (path.startsWith('/admin/skills')) return '/admin/skills'
  if (path.startsWith('/admin/mcps')) return '/admin/mcps'
  if (path.startsWith('/admin/model-providers') || path.startsWith('/admin/routing-rules')) return '/admin/model-providers'
  if (path.startsWith('/admin/workflows')) return '/admin/workflows'
  if (path.startsWith('/admin/audit')) return '/admin/audit/conversations'
  return path
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <el-container class="admin-layout">
    <el-aside width="230px" class="admin-aside">
      <div class="aside-header">
        <router-link to="/" class="logo">
          <div class="logo-icon">
            <el-icon :size="18" color="#fff"><Promotion /></el-icon>
          </div>
          <span>管理后台</span>
        </router-link>
      </div>
      <el-menu
        :default-active="activeMenuIndex"
        :router="true"
        class="aside-menu"
      >
        <el-menu-item index="/admin/skills">
          <el-icon><Document /></el-icon>
          <span>Skill 管理</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.isAdmin" index="/admin/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.isAdmin" index="/admin/model-providers">
          <el-icon><Setting /></el-icon>
          <span>模型管理</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.isAdmin" index="/admin/mcps">
          <el-icon><Connection /></el-icon>
          <span>MCP 管理</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.isAdmin" index="/admin/embedding">
          <el-icon><DataLine /></el-icon>
          <span>检索管理</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.isAdmin" index="/admin/workflows">
          <el-icon><Operation /></el-icon>
          <span>流程管理</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.isAdmin" index="/admin/audit/conversations">
          <el-icon><Histogram /></el-icon>
          <span>会话管理</span>
        </el-menu-item>
        <el-divider />
        <el-menu-item index="/">
          <el-icon><Back /></el-icon>
          <span>返回前台</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container class="admin-content">
      <el-header class="admin-header">
        <div class="header-title">{{ route.meta.title || '' }}</div>
        <div class="header-right">
        <ThemeToggle />
        <el-dropdown>
          <span class="user-info">
            <el-icon><User /></el-icon>
            {{ authStore.user?.display_name }}
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        </div>
      </el-header>
      <el-main class="admin-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin-layout {
  min-height: 100vh;
  height: 100vh;
  overflow: hidden;
}

.admin-aside {
  background: var(--bg-card, #fff);
  border-right: 1px solid var(--border-primary, #f0f0f0);
  overflow-y: auto;
}

.admin-content {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.aside-header {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  border-bottom: 1px solid var(--border-primary, #f0f0f0);
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: var(--text-primary, #1e293b);
  font-weight: 700;
  font-size: 16px;
}

.logo-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #6366f1, #818cf8);
  display: flex;
  align-items: center;
  justify-content: center;
}

.aside-menu {
  border-right: none;
  padding: 8px;
}

.aside-menu :deep(.el-menu-item) {
  height: 44px;
  line-height: 44px;
  margin-bottom: 2px;
  border-radius: 8px;
  color: var(--text-secondary, #64748b);
  font-size: 14px;
  transition: all 0.2s;
}

.aside-menu :deep(.el-menu-item:hover) {
  color: #6366f1;
  background: var(--bg-hover, #f5f3ff);
}

.aside-menu :deep(.el-menu-item.is-active) {
  color: #6366f1;
  background: var(--bg-hover, #ede9fe);
  font-weight: 600;
}

.aside-menu :deep(.el-menu-item .el-icon) {
  font-size: 18px;
}

.aside-menu :deep(.el-divider) {
  margin: 8px 0;
}

.admin-header {
  background: var(--bg-card, #fff);
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  padding: 0 24px;
  border-bottom: 1px solid var(--border-primary, #f0f0f0);
  flex-shrink: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: var(--text-secondary, #64748b);
  font-size: 14px;
  transition: color 0.2s;
}

.user-info:hover {
  color: #6366f1;
}

.admin-main {
  background: var(--bg-code, #f8fafc);
  padding: 24px;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
}
</style>
