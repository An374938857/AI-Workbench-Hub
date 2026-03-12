<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { showDangerConfirm } from '@/composables/useDangerConfirm'
import { useAuthStore } from '@/stores/auth'
import ElegantPagination from '@/components/common/ElegantPagination.vue'
import {
  deleteTemplate,
  duplicateTemplate,
  getTemplates,
  setGlobalDefault,
  toggleFavorite,
  type PromptTemplate,
} from '@/api/promptTemplates'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const templates = ref<PromptTemplate[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const autoMinPageSize = ref(20)
const PAGE_SIZE_CANDIDATES = [20, 50]
const gridRef = ref<HTMLElement | null>(null)
let paginationResizeTimer: number | null = null
const keyword = ref('')
const category = ref('')
const visibility = ref('')
const sortBy = ref<'updated_at' | 'priority'>('updated_at')
const quickFilter = ref<'all' | 'mine' | 'favorite' | 'builtin'>('all')

const previewVisible = ref(false)
const previewTemplate = ref<PromptTemplate | null>(null)

const isAdmin = computed(() => authStore.user?.role === 'admin')
const isProvider = computed(() => authStore.user?.role === 'provider')

function getCardDelay(index: number): string {
  return `${Math.min(index * 0.06, 0.58)}s`
}

const filteredTemplates = computed(() => {
  let items = [...templates.value]
  if (quickFilter.value === 'mine') {
    items = items.filter((t) => t.created_by === authStore.user?.id)
  } else if (quickFilter.value === 'favorite') {
    items = items.filter((t) => t.is_favorited)
  } else if (quickFilter.value === 'builtin') {
    items = items.filter((t) => t.is_builtin)
  }

  if (visibility.value) {
    items = items.filter((t) => t.visibility === visibility.value)
  }

  if (sortBy.value === 'updated_at') {
    items.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
  } else {
    items.sort((a, b) => b.priority - a.priority)
  }
  return items
})

const pageSizeOptions = computed(() => {
  const merged = [autoMinPageSize.value, ...PAGE_SIZE_CANDIDATES.filter((size) => size >= autoMinPageSize.value)]
  return Array.from(new Set(merged)).sort((a, b) => a - b)
})

function categoryLabel(value: string): string {
  const map: Record<string, string> = {
    role: '角色',
    style: '风格',
    domain: '领域',
    personal: '个人',
  }
  return map[value] || value
}

function categoryTagType(value: string): 'primary' | 'success' | 'warning' | 'info' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info'> = {
    role: 'primary',
    style: 'success',
    domain: 'warning',
    personal: 'info',
  }
  return map[value] || 'info'
}

function formatDate(dateText: string): string {
  return new Date(dateText).toLocaleString('zh-CN')
}

function canEdit(template: PromptTemplate): boolean {
  if (template.is_builtin) return false
  if (template.visibility === 'public') return isAdmin.value
  return template.created_by === authStore.user?.id || isAdmin.value
}

async function loadTemplates() {
  loading.value = true
  try {
    const res = await getTemplates({
      page: page.value,
      page_size: pageSize.value,
      search: keyword.value || undefined,
      category: category.value || undefined,
    })
    templates.value = res.data?.templates || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

function computeAdaptivePageSize(): number {
  const grid = gridRef.value
  if (!grid) return autoMinPageSize.value

  const gridRect = grid.getBoundingClientRect()
  const style = window.getComputedStyle(grid)
  const rowGap = Number.parseFloat(style.rowGap || style.gap || '0') || 0
  const columnCount = style.gridTemplateColumns.split(' ').filter(Boolean).length || 1
  const firstCard = grid.firstElementChild as HTMLElement | null
  const rowHeight = firstCard?.offsetHeight || 220
  const footerReserve = 140
  const availableHeight = Math.max(window.innerHeight - gridRect.top - footerReserve, rowHeight)
  const rowUnit = rowHeight + rowGap
  const visibleRows = Math.max(1, Math.floor((availableHeight + rowGap) / rowUnit))
  return Math.max(columnCount, visibleRows * columnCount)
}

async function recalcAdaptivePageSize(options?: { forceReset?: boolean }) {
  const nextMin = computeAdaptivePageSize()
  autoMinPageSize.value = nextMin
  const shouldReset = pageSize.value < nextMin || (options?.forceReset === true && pageSize.value !== nextMin)
  if (!shouldReset) return

  pageSize.value = nextMin
  page.value = 1
  await loadTemplates()
}

function handleWindowResize() {
  if (paginationResizeTimer !== null) {
    window.clearTimeout(paginationResizeTimer)
  }
  paginationResizeTimer = window.setTimeout(() => {
    void recalcAdaptivePageSize()
  }, 120)
}

function handleSearch() {
  page.value = 1
  void loadTemplates()
}

function openCreatePage() {
  router.push('/prompt-templates/new')
}

function openDetailPage(id: number) {
  router.push(`/prompt-templates/${id}`)
}

function openPreview(template: PromptTemplate) {
  previewTemplate.value = template
  previewVisible.value = true
}

async function handleToggleFavorite(template: PromptTemplate) {
  const res = await toggleFavorite(template.id)
  template.is_favorited = !!res.data?.is_favorited
  ElMessage.success(template.is_favorited ? '收藏成功' : '已取消收藏')
}

async function handleSetDefault(template: PromptTemplate) {
  await showDangerConfirm({
    title: '设为全局默认',
    subject: template.name,
    detail: '该模板将成为所有新对话的默认提示词模板。',
    confirmText: '确认设置',
    confirmType: 'primary',
  })
  await setGlobalDefault(template.id)
  ElMessage.success('已设置为全局默认模板')
  await loadTemplates()
}

async function handleDuplicate(template: PromptTemplate) {
  await duplicateTemplate(template.id)
  ElMessage.success('复制成功')
  await loadTemplates()
}

async function handleDelete(template: PromptTemplate) {
  await showDangerConfirm({
    title: '删除模板',
    subject: template.name,
    detail: '删除后模板不可恢复，且会从所有视图中移除。',
    confirmText: '删除模板',
  })
  await deleteTemplate(template.id)
  ElMessage.success('删除成功')
  await loadTemplates()
}

onMounted(() => {
  window.addEventListener('resize', handleWindowResize)
  void (async () => {
    await loadTemplates()
    await nextTick()
    await recalcAdaptivePageSize({ forceReset: true })
  })()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleWindowResize)
  if (paginationResizeTimer !== null) {
    window.clearTimeout(paginationResizeTimer)
  }
})
</script>

<template>
  <div class="prompt-square">
    <div class="hero-section">
      <h1>提示词广场</h1>
      <p>统一管理提示词模板，支持收藏、复制、版本化维护与默认模板治理</p>
      <div class="hero-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索模板名称..."
          clearable
          style="width: 360px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button type="primary" @click="openCreatePage">
          <el-icon><Plus /></el-icon>
          新建模板
        </el-button>
      </div>
    </div>

    <div class="filter-bar">
      <div class="quick-tags">
        <el-check-tag :checked="quickFilter === 'all'" @change="quickFilter = 'all'">全部</el-check-tag>
        <el-check-tag :checked="quickFilter === 'mine'" @change="quickFilter = 'mine'">我的</el-check-tag>
        <el-check-tag :checked="quickFilter === 'favorite'" @change="quickFilter = 'favorite'">收藏</el-check-tag>
        <el-check-tag :checked="quickFilter === 'builtin'" @change="quickFilter = 'builtin'">内置</el-check-tag>
      </div>
      <div class="filter-controls">
        <el-select v-model="category" clearable placeholder="分类" style="width: 140px" @change="handleSearch">
          <el-option label="角色" value="role" />
          <el-option label="风格" value="style" />
          <el-option label="领域" value="domain" />
          <el-option label="个人" value="personal" />
        </el-select>
        <el-select v-model="visibility" clearable placeholder="可见性" style="width: 120px">
          <el-option label="公开" value="public" />
          <el-option label="个人" value="personal" />
        </el-select>
        <el-segmented
          v-model="sortBy"
          :options="[
            { label: '最近更新', value: 'updated_at' },
            { label: '优先级', value: 'priority' },
          ]"
        />
      </div>
    </div>

    <div ref="gridRef" v-loading="loading" class="template-grid">
      <article
        v-for="(template, index) in filteredTemplates"
        :key="template.id"
        class="template-card"
        :style="{ '--card-enter-delay': getCardDelay(index) }"
        @click="openDetailPage(template.id)"
      >
        <div class="card-top">
          <h3>{{ template.name }}</h3>
          <span class="priority-pill">P{{ template.priority }}</span>
        </div>

        <div class="card-tags">
          <el-tag size="small" :type="categoryTagType(template.category)">
            {{ categoryLabel(template.category) }}
          </el-tag>
          <el-tag size="small" :type="template.visibility === 'public' ? 'success' : 'info'">
            {{ template.visibility === 'public' ? '公开' : '个人' }}
          </el-tag>
          <el-tag v-if="template.is_global_default" size="small" type="danger">全局默认</el-tag>
          <el-tag v-if="template.is_builtin" size="small">内置</el-tag>
          <el-tag v-if="template.is_favorited" size="small" type="warning">已收藏</el-tag>
        </div>

        <p class="card-content">{{ template.content }}</p>

        <div class="card-meta">
          <span>更新于 {{ formatDate(template.updated_at) }}</span>
        </div>

        <div class="card-actions" @click.stop>
          <el-button text @click="openPreview(template)">预览</el-button>
          <el-button text @click="handleToggleFavorite(template)">
            {{ template.is_favorited ? '取消收藏' : '收藏' }}
          </el-button>
          <el-button text @click="handleDuplicate(template)">复制</el-button>
          <el-button text type="primary" :disabled="!canEdit(template)" @click="openDetailPage(template.id)">编辑</el-button>
          <el-button text type="danger" :disabled="template.is_builtin || template.is_global_default || !canEdit(template)" @click="handleDelete(template)">删除</el-button>
          <el-button
            v-if="isAdmin || isProvider"
            text
            type="warning"
            :disabled="template.is_global_default"
            @click="handleSetDefault(template)"
          >
            设为默认
          </el-button>
        </div>
      </article>
    </div>

    <el-empty v-if="!loading && filteredTemplates.length === 0" description="暂无匹配的提示词模板" />

    <div v-if="total > pageSize" class="pagination-bar">
      <ElegantPagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        :page-sizes="pageSizeOptions"
        layout="total, sizes, prev, pager, next, jumper"
        @update:current-page="page = $event"
        @update:page-size="pageSize = $event"
        @size-change="loadTemplates"
        @current-change="loadTemplates"
      />
    </div>

    <el-dialog v-model="previewVisible" width="760px" destroy-on-close class="prompt-preview-dialog" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <div class="dialog-header-badge">模板预览</div>
          <div class="dialog-header-title">{{ previewTemplate?.name }}</div>
          <div class="dialog-header-desc">查看模板内容与关键属性，便于快速比对与复用。</div>
        </div>
      </template>
      <div v-if="previewTemplate" class="preview-pane">
        <div class="preview-meta">
          <el-tag :type="categoryTagType(previewTemplate.category)">
            {{ categoryLabel(previewTemplate.category) }}
          </el-tag>
          <span>{{ formatDate(previewTemplate.updated_at) }}</span>
        </div>
        <pre>{{ previewTemplate.content }}</pre>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button class="dialog-btn dialog-btn-secondary" @click="previewVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.prompt-square {
  max-width: var(--container-xl);
  margin: 0 auto;
}

.hero-section {
  text-align: center;
  padding: 20px 0 24px;
}

.hero-section h1 {
  margin: 0 0 8px;
  font-size: 26px;
  color: var(--text-primary, #303133);
}

.dialog-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dialog-header-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.08);
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.dialog-header-title {
  font-size: 24px;
  line-height: 1.3;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

.dialog-header-desc {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-secondary, #64748b);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

:global(.prompt-preview-dialog .el-dialog) {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 32px;
  background: #ffffff;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
  background-clip: padding-box;
}

:global(.prompt-preview-dialog .el-dialog__header) {
  margin: 0;
  padding: 24px 24px 0;
  border-radius: 32px 32px 0 0;
  background: inherit;
}

:global(.prompt-preview-dialog .el-dialog__body) {
  padding: 18px 24px 0;
  background: inherit;
}

:global(.prompt-preview-dialog .el-dialog__footer) {
  padding: 22px 24px 24px;
  border-radius: 0 0 32px 32px;
  background: inherit;
}

:global(.prompt-preview-dialog .el-dialog__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.prompt-preview-dialog .el-dialog__headerbtn .el-dialog__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.prompt-preview-dialog .el-dialog__footer .el-button.dialog-btn),
:global(.prompt-templates-confirm-dialog .el-message-box__btns .el-button) {
  min-width: 108px;
  height: 42px;
  border-radius: 14px;
  font-weight: 600;
}

:global(.dialog-btn-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.dialog-btn-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.prompt-templates-confirm-dialog.el-message-box) {
  width: min(460px, calc(100vw - 32px));
  padding: 0;
  border: 1px solid #e5e7eb;
  border-radius: 24px;
  background: #ffffff;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

:global(.prompt-templates-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.prompt-templates-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.prompt-templates-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.prompt-templates-confirm-dialog .el-message-box__message) {
  margin: 0;
}

:global(.danger-confirm-content) {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

:global(.danger-confirm-badge) {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: #fef2f2;
  color: #dc2626;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

:global(.danger-confirm-subject) {
  font-size: 18px;
  line-height: 1.5;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
  word-break: break-word;
}

:global(.danger-confirm-detail) {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-secondary, #64748b);
}

:global(.prompt-templates-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.prompt-templates-confirm-dialog .prompt-templates-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.prompt-templates-confirm-dialog .prompt-templates-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.prompt-templates-confirm-dialog .prompt-templates-confirm-primary) {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  color: #2563eb;
  box-shadow: none;
}

:global(.prompt-templates-confirm-dialog .prompt-templates-confirm-primary:hover) {
  border-color: #bfdbfe;
  background: #dbeafe;
  color: #1d4ed8;
}

:global(.prompt-templates-confirm-dialog .prompt-templates-confirm-danger) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.prompt-templates-confirm-dialog .prompt-templates-confirm-danger:hover) {
  border-color: #fca5a5;
  background: #fef2f2;
  color: #b91c1c;
}

:global(html.dark) .dialog-header-badge {
  background: rgba(96, 165, 250, 0.14);
  color: #bfdbfe;
}

:global(html.dark) .dialog-header-title {
  color: #f8fafc;
}

:global(html.dark) .dialog-header-desc,
:global(html.dark) .danger-confirm-detail {
  color: #94a3b8;
}

:global(html.dark .prompt-preview-dialog .el-dialog),
:global(html.dark .prompt-templates-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .prompt-preview-dialog .el-dialog__headerbtn .el-dialog__close),
:global(html.dark .prompt-templates-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: #94a3b8;
}

:global(html.dark .dialog-btn-secondary),
:global(html.dark .prompt-templates-confirm-dialog .prompt-templates-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .dialog-btn-secondary:hover),
:global(html.dark .prompt-templates-confirm-dialog .prompt-templates-confirm-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}

:global(html.dark) .danger-confirm-badge {
  background: rgba(248, 113, 113, 0.14);
  color: #fca5a5;
}

:global(html.dark) .danger-confirm-subject,
:global(html.dark .prompt-templates-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}

.hero-section p {
  margin: 0 0 20px;
  color: var(--text-muted, #6b7280);
  font-size: 15px;
}

.hero-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}

.quick-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-controls {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.template-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-primary, #ebeef5);
  border-radius: 16px;
  padding: 18px;
  cursor: pointer;
  transition: all 0.25s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 2px 8px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
  gap: 10px;
  animation: card-enter 0.4s cubic-bezier(0.2, 0.6, 0.35, 1) both;
  animation-delay: var(--card-enter-delay, 0s);
}

.template-card:hover {
  border-color: #409eff;
  transform: translateY(-2px);
  box-shadow: 0 6px 24px rgba(64, 158, 255, 0.14), 0 2px 10px rgba(0, 0, 0, 0.03);
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.card-top h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.priority-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 46px;
  height: 24px;
  border-radius: 999px;
  background: rgba(64, 158, 255, 0.1);
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
}

.card-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.card-content {
  margin: 0;
  color: var(--text-secondary, #606266);
  font-size: 13px;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 60px;
}

.card-meta {
  font-size: 12px;
  color: var(--text-muted, #6b7280);
}

.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  padding-top: 2px;
  border-top: 1px dashed var(--border-primary, #ebeef5);
}

.pagination-bar {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

.preview-pane pre {
  background: var(--bg-page, #f5f7fa);
  border: 1px solid var(--border-primary, #ebeef5);
  border-radius: 12px;
  padding: 16px;
  white-space: pre-wrap;
  line-height: 1.65;
  max-height: 50vh;
  overflow: auto;
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-size: 13px;
}

.preview-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
  color: var(--text-muted, #6b7280);
  font-size: 12px;
}

@keyframes card-enter {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 900px) {
  .template-grid {
    grid-template-columns: 1fr;
  }
}
</style>
