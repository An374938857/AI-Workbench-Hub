<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getSkillList } from '@/api/skills'
import { getSceneTagList } from '@/api/admin/sceneTags'
import { getSortPreferences, updateSortPreferences } from '@/api/sortPreferences'
import SkillCard from '@/components/SkillCard.vue'
import ElegantPagination from '@/components/common/ElegantPagination.vue'
import draggable from 'vuedraggable'

interface SkillItem {
  id: number
  name: string
  icon_url: string | null
  brief_desc: string
  tags: { id: number; name: string }[]
  use_count: number
  creator_name: string | null
}

const router = useRouter()
const loading = ref(false)
const skills = ref<SkillItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(8)
const autoMinPageSize = ref(8)
const PAGE_SIZE_CANDIDATES = [20, 50]
const gridRef = ref<HTMLElement | { $el?: HTMLElement } | null>(null)
let resizeTimer: number | null = null
const keyword = ref('')
const activeTag = ref<number | null>(null)
const allTags = ref<{ id: number; name: string }[]>([])

async function fetchTags() {
  try {
    const res: any = await getSceneTagList()
    allTags.value = res.data.filter((t: any) => t.is_active)
  } catch { /* ignore */ }
}

async function fetchSkills() {
  loading.value = true
  try {
    const res: any = await getSkillList({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      tag_id: activeTag.value || undefined,
    })
    skills.value = res.data.items
    total.value = res.data.total
    // 应用用户保存的排序偏好
    try {
      const prefsRes: any = await getSortPreferences('skill')
      const prefs = prefsRes?.data
      if (Array.isArray(prefs) && prefs.length > 0) {
        const orderMap = new Map(prefs.map((p: { target_id: number; sort_order: number }) => [p.target_id, p.sort_order]))
        skills.value.sort((a, b) => {
          const orderA = orderMap.get(a.id) ?? 9999
          const orderB = orderMap.get(b.id) ?? 9999
          return orderA - orderB
        })
      }
    } catch { /* 无偏好或未登录时忽略 */ }
  } finally {
    loading.value = false
  }
}

function computeAdaptivePageSize(): number {
  const gridRefValue = gridRef.value
  const grid = gridRefValue instanceof HTMLElement ? gridRefValue : gridRefValue?.$el
  if (!grid) {
    return autoMinPageSize.value
  }

  const gridRect = grid.getBoundingClientRect()
  const style = window.getComputedStyle(grid)
  const rowGap = Number.parseFloat(style.rowGap || style.gap || '0') || 0
  const columnCount = style.gridTemplateColumns.split(' ').filter(Boolean).length || 1
  const firstCard = grid.firstElementChild as HTMLElement | null
  const rowHeight = firstCard?.offsetHeight || 160
  const viewportBottomPadding = 24
  const availableHeight = Math.max(window.innerHeight - gridRect.top - viewportBottomPadding, rowHeight)
  const rowUnit = rowHeight + rowGap
  const visibleRows = Math.max(1, Math.floor((availableHeight + rowGap) / rowUnit))
  return Math.max(columnCount, visibleRows * columnCount)
}

function recalcAdaptivePageSize(options?: { forceReset?: boolean }) {
  const nextMin = computeAdaptivePageSize()
  autoMinPageSize.value = nextMin
  const shouldReset = pageSize.value < nextMin || (options?.forceReset === true && pageSize.value !== nextMin)
  if (shouldReset) {
    pageSize.value = nextMin
    page.value = 1
    fetchSkills()
  }
}

function handleSearch() {
  page.value = 1
  fetchSkills()
}

function handleTagFilter(tagId: number | null) {
  activeTag.value = tagId
  page.value = 1
  fetchSkills()
}

function handlePageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  fetchSkills()
}

function handleWindowResize() {
  if (resizeTimer !== null) {
    window.clearTimeout(resizeTimer)
  }
  resizeTimer = window.setTimeout(() => {
    recalcAdaptivePageSize()
  }, 120)
}

const pageSizeOptions = computed(() => {
  const merged = [autoMinPageSize.value, ...PAGE_SIZE_CANDIDATES.filter((size) => size >= autoMinPageSize.value)]
  return Array.from(new Set(merged)).sort((a, b) => a - b)
})

function goDetail(id: number) {
  router.push(`/skills/${id}`)
}

async function handleDragEnd() {
  const items = skills.value.map((s, i) => ({ id: s.id, sort_order: i }))
  try {
    await updateSortPreferences('skill', items)
  } catch { /* ignore */ }
}

onMounted(async () => {
  await fetchTags()
  window.addEventListener('resize', handleWindowResize)
  await fetchSkills()
  await nextTick()
  recalcAdaptivePageSize({ forceReset: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleWindowResize)
  if (resizeTimer !== null) {
    window.clearTimeout(resizeTimer)
  }
})
</script>

<template>
  <div class="skill-square">
    <div class="hero-section">
      <h1>AI 能力广场</h1>
      <p>选择一个 AI 能力，通过对话方式完成工作</p>
      <div class="search-bar">
        <el-input
          v-model="keyword"
          placeholder="搜索 AI 能力..."
          size="large"
          clearable
          style="width: 400px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
          <template #append>
            <el-button @click="handleSearch"><el-icon><Search /></el-icon></el-button>
          </template>
        </el-input>
      </div>
    </div>

    <div class="tag-filter">
      <el-check-tag :checked="activeTag === null" @change="handleTagFilter(null)">全部</el-check-tag>
      <el-check-tag
        v-for="t in allTags"
        :key="t.id"
        :checked="activeTag === t.id"
        @change="handleTagFilter(t.id)"
      >
        {{ t.name }}
      </el-check-tag>
    </div>

    <draggable
      ref="gridRef"
      v-model="skills"
      item-key="id"
      class="skill-grid"
      ghost-class="drag-ghost"
      animation="200"
      @end="handleDragEnd"
    >
      <template #item="{ element }">
        <SkillCard :skill="element" @click="goDetail" />
      </template>
    </draggable>

    <el-empty v-if="!loading && skills.length === 0" description="暂无已发布的 AI 能力" />

    <div v-if="total > pageSize" class="pagination-bar">
      <ElegantPagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        :page-sizes="pageSizeOptions"
        layout="total, sizes, prev, pager, next, jumper"
        @update:current-page="page = $event"
        @update:page-size="pageSize = $event"
        @current-change="fetchSkills"
        @size-change="handlePageSizeChange"
      />
    </div>
  </div>
</template>

<style scoped>
.skill-square {
  max-width: var(--container-lg);
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

.hero-section p {
  margin: 0 0 20px;
  color: var(--text-muted, #909399);
  font-size: 15px;
}

.search-bar {
  display: flex;
  justify-content: center;
}

.tag-filter {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 20px;
  padding: 0 4px;
}

.skill-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  min-height: 100px;
}

.skill-grid > * {
  animation: card-enter 0.4s cubic-bezier(0.2, 0.6, 0.35, 1) both;
}
.skill-grid > *:nth-child(1)  { animation-delay: 0s }
.skill-grid > *:nth-child(2)  { animation-delay: 0.06s }
.skill-grid > *:nth-child(3)  { animation-delay: 0.12s }
.skill-grid > *:nth-child(4)  { animation-delay: 0.18s }
.skill-grid > *:nth-child(5)  { animation-delay: 0.24s }
.skill-grid > *:nth-child(6)  { animation-delay: 0.30s }
.skill-grid > *:nth-child(7)  { animation-delay: 0.36s }
.skill-grid > *:nth-child(8)  { animation-delay: 0.42s }
.skill-grid > *:nth-child(9)  { animation-delay: 0.48s }
.skill-grid > *:nth-child(10) { animation-delay: 0.54s }
.skill-grid > *:nth-child(n+11) { animation-delay: 0.58s }

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

@media (max-width: 720px) {
  .skill-grid {
    grid-template-columns: 1fr;
  }
}

.pagination-bar {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

.drag-ghost {
  opacity: 0.4;
  border: 2px dashed #409eff !important;
  border-radius: 10px;
}
</style>
