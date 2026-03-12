<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getMcpPublicDetail } from '@/api/mcps'

interface ToolInfo {
  name: string
  description: string | null
}

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const mcpName = ref('')
const mcpDesc = ref('')
const tools = ref<ToolInfo[]>([])

async function fetchDetail() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    const res: any = await getMcpPublicDetail(id)
    mcpName.value = res.data.name
    mcpDesc.value = res.data.description
    tools.value = res.data.tools || []
  } finally {
    loading.value = false
  }
}

onMounted(fetchDetail)

const showBackTop = ref(false)
function handleScroll() {
  const el = document.querySelector('.tools-list')
  showBackTop.value = el ? el.scrollTop > 300 : false
}
function scrollToTop() {
  document.querySelector('.tools-list')?.scrollTo({ top: 0, behavior: 'smooth' })
}
onMounted(() => {
  setTimeout(() => document.querySelector('.tools-list')?.addEventListener('scroll', handleScroll), 100)
})
onUnmounted(() => document.querySelector('.tools-list')?.removeEventListener('scroll', handleScroll))
</script>

<template>
  <div class="mcp-detail" v-loading="loading">
    <div class="detail-top">
    <div class="detail-header">
      <el-button text @click="router.push('/mcps')">
        <el-icon><Back /></el-icon> 返回 MCP 广场
      </el-button>
    </div>

    <div class="detail-card">
      <div class="detail-icon">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
        </svg>
      </div>
      <div>
        <h1 class="detail-title">{{ mcpName }}</h1>
        <p class="detail-desc">{{ mcpDesc }}</p>
      </div>
    </div>
    </div>

    <div class="detail-bottom">
      <div class="section-title">
        <el-icon color="#64748b"><Tools /></el-icon>
        <h2>提供的工具（{{ tools.length }}）</h2>
      </div>
      <div class="tools-list">
        <div v-for="tool in tools" :key="tool.name" class="tool-item">
          <div class="tool-name">🔧 {{ tool.name }}</div>
          <div class="tool-desc">{{ tool.description || '暂无描述' }}</div>
        </div>
        <el-empty v-if="tools.length === 0" description="暂无工具信息" />
      </div>
    </div>

    <Transition name="fade">
      <button v-if="showBackTop" class="back-top-btn" @click="scrollToTop">
        <el-icon :size="20"><Top /></el-icon>
      </button>
    </Transition>
  </div>
</template>

<style scoped>
.mcp-detail {
  max-width: 900px;
  margin: 0 auto;
  height: calc(100vh - 84px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.detail-top {
  flex-shrink: 0;
  background: var(--bg-page, #f5f7fa);
}

.detail-bottom {
  flex: 1;
  overflow: hidden;
  padding-bottom: 24px;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.detail-header {
  margin-bottom: 16px;
  animation: md-fade-down 0.5s cubic-bezier(0.2, 0.6, 0.35, 1) both;
}

.detail-card {
  display: flex;
  gap: 20px;
  align-items: center;
  background: linear-gradient(135deg, #94a3b8 0%, #64748b 50%, #475569 100%);
  border-radius: 20px;
  padding: 32px 36px;
  margin-bottom: 24px;
  border: none;
  animation: md-fade-down 0.6s cubic-bezier(0.2, 0.6, 0.35, 1) 0.05s both;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.detail-icon {
  width: 68px;
  height: 68px;
  border-radius: 18px;
  background: rgba(255,255,255,0.18);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  backdrop-filter: blur(4px);
  color: #fff;
}

.detail-title {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
  margin: 0 0 6px;
}

.detail-desc {
  font-size: 14px;
  color: rgba(255,255,255,0.85);
  margin: 0;
  line-height: 1.5;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.section-title h2 {
  margin: 0;
  font-size: 17px;
  color: var(--text-primary, #0f172a);
  font-weight: 600;
}

.tools-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.tool-item {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-light, #f1f5f9);
  border-radius: 12px;
  padding: 16px 18px;
  transition: box-shadow 0.2s;
  animation: md-fade-up 0.4s cubic-bezier(0.2, 0.6, 0.35, 1) both;
}
.tool-item:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}
.tool-item:nth-child(1)  { animation-delay: 0.12s }
.tool-item:nth-child(2)  { animation-delay: 0.18s }
.tool-item:nth-child(3)  { animation-delay: 0.24s }
.tool-item:nth-child(4)  { animation-delay: 0.30s }
.tool-item:nth-child(5)  { animation-delay: 0.36s }
.tool-item:nth-child(6)  { animation-delay: 0.42s }
.tool-item:nth-child(7)  { animation-delay: 0.48s }
.tool-item:nth-child(n+8) { animation-delay: 0.52s }

.tool-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
  margin-bottom: 4px;
}

.tool-desc {
  font-size: 13px;
  color: var(--text-secondary, #475569);
  line-height: 1.5;
}

.back-top-btn {
  position: fixed;
  bottom: 32px;
  right: 32px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: var(--bg-card, #fff);
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  color: var(--text-secondary, #606266);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: box-shadow 0.2s, color 0.2s;
  z-index: 100;
}
.back-top-btn:hover {
  box-shadow: 0 4px 14px rgba(0,0,0,0.18);
  color: #64748b;
}
.fade-enter-active, .fade-leave-active { transition: opacity 0.25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

@keyframes md-fade-down {
  from { opacity: 0; transform: translateY(-14px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes md-fade-up {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
