<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getSkillDetail } from '@/api/skills'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

interface SkillInfo {
  id: number
  name: string
  icon_url: string | null
  icon_emoji?: string | null
  brief_desc: string
  detail_desc: string
  tags: { id: number; name: string }[]
  usage_example: string | null
  system_prompt: string | null
  use_count: number
  creator_name: string | null
  current_version: number
  version_logs: { version: number; change_log: string; created_at: string }[]
}

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const skill = ref<SkillInfo | null>(null)
const mdHeadings = ref<{ text: string; id: string }[]>([])
const activeSection = ref('section-desc')

async function fetchSkill() {
  loading.value = true
  try {
    const id = Number(route.params.id)
    const res: any = await getSkillDetail(id)
    skill.value = res.data
    // 提取 SKILL.md 中的一级标题并生成 id
    if (res.data.system_prompt) {
      const matches = res.data.system_prompt.match(/^# (.+)$/gm)
      mdHeadings.value = matches ? matches.map((m: string) => {
        const text = m.replace(/^# /, '')
        // 使用相同的 id 生成逻辑
        const id = text.toLowerCase().replace(/[^\w\u4e00-\u9fa5]+/g, '-').replace(/^-|-$/g, '')
        return { text, id }
      }) : []
    }
  } finally {
    loading.value = false
  }
}

function scrollToSection(id: string) {
  activeSection.value = id
  const container = document.querySelector('.detail-bottom')
  const el = document.getElementById(id)
  if (el && container) {
    const containerTop = container.getBoundingClientRect().top
    const elTop = el.getBoundingClientRect().top
    const offset = elTop - containerTop + container.scrollTop - 20
    container.scrollTo({
      top: offset,
      behavior: 'smooth'
    })
  }
}

function startChat() {
  if (!skill.value) return
  router.push({ name: 'Chat', query: { skill_id: skill.value.id } })
}

function formatTime(val: string) {
  if (!val) return ''
  return val.replace('T', ' ').substring(0, 10)
}

onMounted(fetchSkill)

const showBackTop = ref(false)
function handleScroll() {
  const el = document.querySelector('.detail-bottom')
  showBackTop.value = el ? el.scrollTop > 300 : false
}
function scrollToTop() {
  document.querySelector('.detail-bottom')?.scrollTo({ top: 0, behavior: 'smooth' })
}
onMounted(() => {
  setTimeout(() => document.querySelector('.detail-bottom')?.addEventListener('scroll', handleScroll), 100)
})
onUnmounted(() => document.querySelector('.detail-bottom')?.removeEventListener('scroll', handleScroll))
</script>

<template>
  <div class="skill-detail" v-loading="loading">
    <template v-if="skill">
      <div class="detail-top">
      <!-- 返回 -->
      <div class="detail-nav">
        <el-button text @click="router.push('/skills')">
          <el-icon><ArrowLeft /></el-icon> 返回能力广场
        </el-button>
      </div>

      <!-- 顶部 Hero -->
      <div class="hero-card">
        <div class="hero-left">
          <div class="hero-icon">
            <img v-if="skill.icon_url" :src="skill.icon_url" alt="" />
            <span v-else-if="skill.icon_emoji" class="hero-emoji">{{ skill.icon_emoji }}</span>
            <el-icon v-else :size="36" color="#fff"><Promotion /></el-icon>
          </div>
          <div class="hero-info">
            <h1>{{ skill.name }}</h1>
            <p class="hero-desc">{{ skill.brief_desc }}</p>
            <div class="hero-meta">
              <el-tag v-for="t in skill.tags" :key="t.id" size="small" effect="dark" round>{{ t.name }}</el-tag>
              <span class="meta-dot">·</span>
              <span class="meta-item"><el-icon><User /></el-icon> {{ skill.creator_name || '系统' }}</span>
              <span class="meta-dot">·</span>
              <span class="meta-item">v{{ skill.current_version }}</span>
              <span class="meta-dot">·</span>
              <span class="meta-item">{{ skill.use_count }} 次使用</span>
            </div>
          </div>
        </div>
        <el-button type="primary" size="large" round @click="startChat" class="start-btn">
          <el-icon style="margin-right: 6px"><ChatDotRound /></el-icon> 开始使用
        </el-button>
      </div>
      </div>

      <!-- 内容区 -->
      <div class="detail-bottom">
      <div class="content-grid">
        <!-- 功能说明 -->
        <div v-if="skill.detail_desc" id="section-desc" class="content-card">
          <div class="card-header">
            <el-icon color="#6366f1"><Document /></el-icon>
            <h2>功能说明</h2>
          </div>
          <div class="card-body">
            <MarkdownRenderer :content="skill.detail_desc" />
          </div>
        </div>

        <!-- SKILL.md -->
        <div v-if="skill.system_prompt" id="section-skill" class="content-card">
          <div class="card-header">
            <el-icon color="#e86e2c"><Document /></el-icon>
            <h2>SKILL.md</h2>
          </div>
          <div class="card-body">
            <MarkdownRenderer :content="skill.system_prompt" />
          </div>
        </div>

        <!-- 使用示例 -->
        <div v-if="skill.usage_example" class="content-card">
          <div class="card-header">
            <el-icon color="#22c55e"><Compass /></el-icon>
            <h2>使用示例</h2>
          </div>
          <div class="card-body">
            <MarkdownRenderer :content="skill.usage_example" />
          </div>
        </div>
      </div>

      <!-- 更新日志 -->
      <div v-if="skill.version_logs.length > 0" id="section-changelog" class="changelog-section">
        <div class="section-title">
          <el-icon color="#f59e0b"><Clock /></el-icon>
          <h2>更新日志</h2>
        </div>
        <div class="changelog-list">
          <div v-for="log in skill.version_logs" :key="log.version" class="changelog-item">
            <div class="cl-version">v{{ log.version }}</div>
            <div class="cl-date">{{ formatTime(log.created_at) }}</div>
            <div class="cl-text">{{ log.change_log }}</div>
          </div>
        </div>
      </div>
      </div>
      
      <!-- 右侧导航 -->
      <div class="toc-nav">
        <div class="toc-title">目录</div>
        <div class="toc-list">
          <div v-if="skill.detail_desc" class="toc-item" :class="{ active: activeSection === 'section-desc' }" @click="scrollToSection('section-desc')">功能说明</div>
          <div v-if="skill.system_prompt" class="toc-item" :class="{ active: activeSection === 'section-skill' }" @click="scrollToSection('section-skill')">SKILL.md</div>
          <div v-if="skill.version_logs.length > 0" class="toc-item" :class="{ active: activeSection === 'section-changelog' }" @click="scrollToSection('section-changelog')">更新日志</div>
        </div>
      </div>
    </template>

    <Transition name="fade">
      <button v-if="showBackTop" class="back-top-btn" @click="scrollToTop">
        <el-icon :size="20"><Top /></el-icon>
      </button>
    </Transition>
  </div>
</template>

<style scoped>
.skill-detail {
  max-width: 1200px;
  margin: 0 auto;
  height: calc(100vh - 84px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.detail-top {
  flex-shrink: 0;
}

.detail-bottom {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 80px;
}

/* ── TOC Navigation ── */
.toc-nav {
  position: fixed;
  right: 32px;
  top: 280px;
  width: 240px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  border-radius: 16px;
  padding: 20px;
  border: 1px solid rgba(0, 0, 0, 0.04);
  max-height: calc(100vh - 320px);
  overflow-y: auto;
  z-index: 50;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04), 0 1px 3px rgba(0, 0, 0, 0.02);
}

html.dark .toc-nav {
  background: rgba(36, 36, 36, 0.8);
  border-color: rgba(255, 255, 255, 0.04);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2), 0 1px 3px rgba(0, 0, 0, 0.1);
}

.toc-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #64748b);
  margin-bottom: 12px;
  padding-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

html.dark .toc-title {
  border-bottom-color: rgba(255, 255, 255, 0.06);
}

.toc-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  position: relative;
  padding-left: 16px;
}

.toc-list::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: rgba(0, 0, 0, 0.06);
  border-radius: 1px;
}

html.dark .toc-list::before {
  background: rgba(255, 255, 255, 0.06);
}

.toc-item {
  font-size: 14px;
  color: var(--text-secondary, #64748b);
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  line-height: 1.4;
  font-weight: 500;
  position: relative;
}

.toc-item::before {
  content: '';
  position: absolute;
  left: -16px;
  top: 50%;
  transform: translateY(-50%);
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: transparent;
  border: 2px solid transparent;
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.toc-item:hover {
  background: rgba(59, 130, 246, 0.08);
  color: #3b82f6;
}

.toc-item:hover::before {
  transform: translateY(-50%);
}

.toc-item.active {
  color: #3b82f6;
  font-weight: 600;
}

.toc-item.active::before {
  background: #3b82f6;
  border-color: rgba(255, 255, 255, 0.9);
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.5), 0 0 0 3px rgba(59, 130, 246, 0.1);
}

html.dark .toc-item.active::before {
  border-color: rgba(36, 36, 36, 0.9);
}

.toc-sub {
  margin-top: 4px;
  margin-left: 12px;
  padding-left: 8px;
  border-left: 1px solid var(--border-light, #e2e8f0);
}

.toc-sub-item {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
  padding: 4px 8px;
  cursor: pointer;
  transition: color 0.2s;
}

.toc-sub-item:hover {
  color: var(--text-secondary, #64748b);
}

.detail-nav { margin-bottom: 16px; animation: sd-fade-down 0.5s cubic-bezier(0.2, 0.6, 0.35, 1) both; }

/* ── Hero ── */
.hero-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 50%, #1d4ed8 100%);
  border-radius: 20px;
  padding: 32px 36px;
  margin-bottom: 28px;
  animation: sd-fade-down 0.6s cubic-bezier(0.2, 0.6, 0.35, 1) 0.05s both;
}

.hero-left {
  display: flex;
  align-items: center;
  gap: 20px;
  flex: 1;
  min-width: 0;
}

.hero-icon {
  width: 68px;
  height: 68px;
  border-radius: 18px;
  background: rgba(255,255,255,0.18);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  backdrop-filter: blur(4px);
}

.hero-icon img { width: 40px; height: 40px; object-fit: contain }
.hero-emoji { font-size: 34px; line-height: 1 }

.hero-info h1 {
  margin: 0 0 6px;
  font-size: 24px;
  color: #fff;
  font-weight: 700;
}

.hero-desc {
  margin: 0 0 10px;
  color: rgba(255,255,255,0.85);
  font-size: 14px;
  line-height: 1.5;
}

.hero-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.hero-meta :deep(.el-tag) {
  --el-tag-bg-color: rgba(255,255,255,0.2);
  --el-tag-border-color: transparent;
  --el-tag-text-color: #fff;
}

.meta-dot { color: rgba(255,255,255,0.4) }
.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 13px;
  color: rgba(255,255,255,0.75);
}

.start-btn {
  height: 48px;
  font-size: 16px;
  padding: 0 32px;
  flex-shrink: 0;
  background: var(--bg-card, #fff);
  color: #2563eb;
  border: none;
  font-weight: 600;
}
.start-btn:hover { background: var(--bg-hover, #eff6ff); color: #1d4ed8 }

/* ── 内容卡片 ── */
.content-grid {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-bottom: 28px;
}

.content-card {
  background: var(--bg-card, #fff);
  border-radius: 16px;
  border: 1px solid var(--border-light, #f1f5f9);
  overflow: hidden;
  animation: sd-fade-up 0.5s cubic-bezier(0.2, 0.6, 0.35, 1) both;
}
.content-card:nth-child(1) { animation-delay: 0.1s }
.content-card:nth-child(2) { animation-delay: 0.2s }
.content-card:nth-child(3) { animation-delay: 0.3s }

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-light, #f1f5f9);
}

.card-header h2 {
  margin: 0;
  font-size: 17px;
  color: var(--text-primary, #0f172a);
  font-weight: 600;
}

.card-body {
  padding: 20px 24px;
}

/* ── 更新日志 ── */
.changelog-section {
  margin-bottom: 32px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.section-title h2 {
  margin: 0;
  font-size: 17px;
  color: var(--text-primary, #0f172a);
  font-weight: 600;
}

.changelog-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.changelog-item {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-light, #f1f5f9);
  border-radius: 12px;
  padding: 16px 18px;
  transition: box-shadow 0.2s;
  animation: sd-fade-up 0.4s cubic-bezier(0.2, 0.6, 0.35, 1) both;
}
.changelog-item:nth-child(1) { animation-delay: 0.35s }
.changelog-item:nth-child(2) { animation-delay: 0.42s }
.changelog-item:nth-child(3) { animation-delay: 0.49s }
.changelog-item:nth-child(n+4) { animation-delay: 0.54s }

.changelog-item:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}

.cl-version {
  font-size: 16px;
  font-weight: 700;
  color: #2563eb;
  margin-bottom: 4px;
}

.cl-date {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
  margin-bottom: 8px;
}

.cl-text {
  font-size: 14px;
  color: var(--text-secondary, #475569);
  line-height: 1.5;
}

@media (max-width: 700px) {
  .hero-card { flex-direction: column; text-align: center; padding: 24px }
  .hero-left { flex-direction: column }
  .start-btn { width: 100% }
  .changelog-list { grid-template-columns: 1fr }
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
  color: #2563eb;
}
.fade-enter-active, .fade-leave-active { transition: opacity 0.25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

@keyframes sd-fade-down {
  from { opacity: 0; transform: translateY(-14px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes sd-fade-up {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
