<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getMcpPublicList } from '@/api/mcps'
import { testMcp } from '@/api/admin/mcps'
import { getSortPreferences, updateSortPreferences } from '@/api/sortPreferences'
import McpCard from '@/components/McpCard.vue'
import ElegantPagination from '@/components/common/ElegantPagination.vue'
import draggable from 'vuedraggable'
import { ElMessage } from 'element-plus'

interface McpItem {
  id: number
  name: string
  description: string
  tool_count: number
  health_status: string
}

const router = useRouter()
const loading = ref(false)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(9)
const autoMinPageSize = ref(9)
const PAGE_SIZE_CANDIDATES = [20, 50]
const allMcpList = ref<McpItem[]>([])
const gridRef = ref<HTMLElement | { $el?: HTMLElement } | null>(null)
let resizeTimer: number | null = null

const total = computed(() => allMcpList.value.length)
const pageCount = computed(() => Math.ceil(total.value / pageSize.value))
const mcpList = computed<McpItem[]>({
  get() {
    const start = (page.value - 1) * pageSize.value
    return allMcpList.value.slice(start, start + pageSize.value)
  },
  set(newItems) {
    const start = (page.value - 1) * pageSize.value
    const merged = [...allMcpList.value]
    merged.splice(start, newItems.length, ...newItems)
    allMcpList.value = merged
  },
})

const pageSizeOptions = computed(() => {
  const merged = [autoMinPageSize.value, ...PAGE_SIZE_CANDIDATES.filter((size) => size >= autoMinPageSize.value)]
  return Array.from(new Set(merged)).sort((a, b) => a - b)
})

function getCardDelay(index: number): string {
  return `${Math.min(index * 0.06, 0.58)}s`
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
  const rowHeight = firstCard?.offsetHeight || 180
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
  }
}

async function fetchList() {
  loading.value = true
  try {
    const res: any = await getMcpPublicList({ keyword: keyword.value || undefined })
    const items: McpItem[] = Array.isArray(res.data) ? [...res.data] : []
    // 应用用户保存的排序偏好
    try {
      const prefsRes: any = await getSortPreferences('mcp')
      const prefs = prefsRes?.data
      if (Array.isArray(prefs) && prefs.length > 0) {
        const orderMap = new Map(prefs.map((p: { target_id: number; sort_order: number }) => [p.target_id, p.sort_order]))
        items.sort((a, b) => {
          const orderA = orderMap.get(a.id) ?? 9999
          const orderB = orderMap.get(b.id) ?? 9999
          return orderA - orderB
        })
      }
    } catch { /* 无偏好或未登录时忽略 */ }
    allMcpList.value = items
    if (page.value > pageCount.value) {
      page.value = Math.max(pageCount.value, 1)
    }
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  fetchList()
}

function handlePageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
}

function handleWindowResize() {
  if (resizeTimer !== null) {
    window.clearTimeout(resizeTimer)
  }
  resizeTimer = window.setTimeout(() => {
    recalcAdaptivePageSize()
  }, 120)
}

function goDetail(id: number) {
  router.push(`/mcps/${id}`)
}

const testingId = ref<number | null>(null)

async function handleTest(id: number) {
  testingId.value = id
  try {
    const res: any = await testMcp(id)
    if (res.data.result === 'success') {
      ElMessage.success(`连接成功，发现 ${res.data.tools.length} 个工具（${res.data.response_time_ms}ms）`)
    } else {
      ElMessage.error(`连接失败：${res.data.error_detail}`)
    }
  } catch {
    // error handled by interceptor
  } finally {
    testingId.value = null
  }
}

async function handleDragEnd() {
  const items = allMcpList.value.map((m, i) => ({ id: m.id, sort_order: i }))
  try {
    await updateSortPreferences('mcp', items)
  } catch { /* ignore */ }
}

onMounted(async () => {
  window.addEventListener('resize', handleWindowResize)
  await fetchList()
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
  <div class="mcp-square">
    <div class="page-header">
      <h2 class="page-title">MCP 广场</h2>
      <p class="page-subtitle">浏览平台接入的外部工具能力，AI 在对话中会自动调用这些工具</p>
    </div>

    <div class="search-bar">
      <el-input
        v-model="keyword"
        placeholder="搜索 MCP 名称或描述"
        clearable
        style="width: 360px"
        @clear="handleSearch"
        @keyup.enter="handleSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <draggable
      ref="gridRef"
      v-model="mcpList"
      item-key="id"
      class="card-grid"
      ghost-class="drag-ghost"
      animation="200"
      @end="handleDragEnd"
    >
      <template #item="{ element, index }">
        <div class="card-grid-item" :style="{ '--card-enter-delay': getCardDelay(index) }">
          <McpCard
            :mcp="element"
            :testing="testingId === element.id"
            @click="goDetail"
            @test="handleTest(element.id)"
          />
        </div>
      </template>
    </draggable>
    <el-empty v-if="!loading && total === 0" description="暂无可用 MCP" />

    <div v-if="total > pageSize" class="pagination-bar">
      <ElegantPagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        :page-sizes="pageSizeOptions"
        layout="total, sizes, prev, pager, next, jumper"
        @update:current-page="page = $event"
        @update:page-size="pageSize = $event"
        @size-change="handlePageSizeChange"
      />
    </div>
  </div>
</template>

<style scoped>
.mcp-square {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #1e293b);
  margin: 0 0 6px;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-muted, #94a3b8);
  margin: 0;
}

.search-bar {
  margin-bottom: 20px;
}

.pagination-bar {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  min-height: 200px;
}

.card-grid-item {
  animation: card-enter 0.4s cubic-bezier(0.2, 0.6, 0.35, 1) both;
  animation-delay: var(--card-enter-delay, 0s);
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

.drag-ghost {
  opacity: 0.4;
  border: 2px dashed #409eff !important;
  border-radius: 10px;
}

@media (max-width: 1080px) {
  .card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .card-grid {
    grid-template-columns: 1fr;
  }
}
</style>
