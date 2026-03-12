<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  cancelEmbeddingRebuildTask,
  getEmbeddingConfig,
  getEmbeddingFileDetail,
  getEmbeddingFiles,
  getEmbeddingRebuildTasks,
  getRecallMetrics,
  retryFailedEmbeddingRebuildTask,
  startEmbeddingRebuildTask,
  updateEmbeddingConfig,
} from '@/api/admin/embedding'
import { streamEventSource } from '@/utils/sse'

interface GroupedSelectOption {
  label: string
  value: string | number
}

interface GroupedSelectItem {
  providerId: number
  providerName: string
  options: GroupedSelectOption[]
}

interface EmbeddingTaskItem {
  id: number
  embedding_type: string
  target_model_id: number
  target_model_name?: string | null
  status: string
  progress: number
  discovered_count: number
  succeeded_count: number
  failed_count: number
  retryable_failed_count: number
  current_batch_no: number
  total_batches: number
  cancel_requested: boolean
  last_error?: string | null
  created_at?: string | null
  started_at?: string | null
  updated_at?: string | null
  last_heartbeat_at?: string | null
  finished_at?: string | null
}

const activeTab = ref('config')

const embeddingConfigLoading = ref(false)
const embeddingSaving = ref(false)
const embeddingAutoSaveQueued = ref(false)
const embeddingRunningTaskId = ref<number | null>(null)
const embeddingTaskStreamAbortController = ref<AbortController | null>(null)
const embeddingTasks = ref<EmbeddingTaskItem[]>([])

const embeddingConfig = reactive({
  global_default_text_embedding_model_id: null as number | null,
  global_default_multimodal_embedding_model_id: null as number | null,
  text_candidates: [] as any[],
  multimodal_candidates: [] as any[],
})
const lastSavedEmbeddingConfig = reactive({
  global_default_text_embedding_model_id: null as number | null,
  global_default_multimodal_embedding_model_id: null as number | null,
})

const fileFilters = reactive({
  keyword: '',
  status: 'all' as 'all' | 'embedded' | 'not_embedded' | 'failed',
  page: 1,
  page_size: 20,
})
const fileLoading = ref(false)
const fileRows = ref<any[]>([])
const fileTotal = ref(0)
const fileSummary = reactive({
  embedded: 0,
  not_embedded: 0,
  failed: 0,
})

const detailDialogVisible = ref(false)
const detailLoading = ref(false)
const currentDetail = ref<any | null>(null)

const recallLoading = ref(false)
const recallRange = ref<'24h' | '7d' | '30d'>('7d')
const recallMetrics = ref<any | null>(null)

const embeddingTypeLabels: Record<string, string> = {
  TEXT: '文本 Embedding',
  MULTIMODAL: '多模态 Embedding',
}

function buildGroupedModelOptions(
  list: Array<{
    provider_id: number
    provider_name: string
    model_name: string
    value: string | number
    is_enabled?: boolean
  }>,
): GroupedSelectItem[] {
  const grouped = new Map<number, GroupedSelectItem>()
  for (const item of list) {
    if (item.is_enabled === false) continue
    const providerId = Number(item.provider_id)
    if (!providerId) continue
    if (!grouped.has(providerId)) {
      grouped.set(providerId, {
        providerId,
        providerName: item.provider_name || 'Provider',
        options: [],
      })
    }
    grouped.get(providerId)!.options.push({
      label: item.model_name,
      value: item.value,
    })
  }
  return Array.from(grouped.values()).filter((item) => item.options.length > 0)
}

const textEmbeddingModelOptions = computed(() =>
  buildGroupedModelOptions(
    embeddingConfig.text_candidates.map((item: any) => ({
      provider_id: item.provider_id,
      provider_name: item.provider_name,
      model_name: item.model_name,
      value: item.id,
      is_enabled: item.is_enabled,
    })),
  ),
)

const multimodalEmbeddingModelOptions = computed(() =>
  buildGroupedModelOptions(
    embeddingConfig.multimodal_candidates.map((item: any) => ({
      provider_id: item.provider_id,
      provider_name: item.provider_name,
      model_name: item.model_name,
      value: item.id,
      is_enabled: item.is_enabled,
    })),
  ),
)

const embeddingModelNameById = computed(() => {
  const map = new Map<number, string>()
  for (const candidate of [...embeddingConfig.text_candidates, ...embeddingConfig.multimodal_candidates]) {
    if (!candidate || candidate.id == null) continue
    map.set(Number(candidate.id), candidate.display_name || candidate.model_name || `模型 #${candidate.id}`)
  }
  return map
})

const hasActiveEmbeddingTasks = computed(() =>
  embeddingTasks.value.some((task) => isEmbeddingTaskActive(task.status)),
)

const successRateText = computed(() => {
  const value = Number(recallMetrics.value?.overview?.success_rate || 0)
  return `${(value * 100).toFixed(1)}%`
})

async function fetchEmbeddingConfig() {
  embeddingConfigLoading.value = true
  try {
    const res: any = await getEmbeddingConfig()
    const data = res?.data || {}
    embeddingConfig.global_default_text_embedding_model_id = data.global_default_text_embedding_model_id ?? null
    embeddingConfig.global_default_multimodal_embedding_model_id = data.global_default_multimodal_embedding_model_id ?? null
    embeddingConfig.text_candidates = Array.isArray(data.text_candidates) ? data.text_candidates : []
    embeddingConfig.multimodal_candidates = Array.isArray(data.multimodal_candidates) ? data.multimodal_candidates : []

    lastSavedEmbeddingConfig.global_default_text_embedding_model_id = embeddingConfig.global_default_text_embedding_model_id
    lastSavedEmbeddingConfig.global_default_multimodal_embedding_model_id = embeddingConfig.global_default_multimodal_embedding_model_id
  } finally {
    embeddingConfigLoading.value = false
  }
}

async function fetchEmbeddingTasks() {
  const res: any = await getEmbeddingRebuildTasks(20)
  embeddingTasks.value = Array.isArray(res?.data) ? res.data : []
  syncEmbeddingTaskStream()
}

function hasEmbeddingConfigChanged() {
  return embeddingConfig.global_default_text_embedding_model_id !== lastSavedEmbeddingConfig.global_default_text_embedding_model_id
    || embeddingConfig.global_default_multimodal_embedding_model_id !== lastSavedEmbeddingConfig.global_default_multimodal_embedding_model_id
}

async function saveEmbeddingConfig(options: { rebuildIndex: boolean; autoStartCreatedTasks?: boolean; silent?: boolean }) {
  if (!hasEmbeddingConfigChanged() && !options.rebuildIndex) return

  embeddingSaving.value = true
  try {
    const res: any = await updateEmbeddingConfig({
      global_default_text_embedding_model_id: embeddingConfig.global_default_text_embedding_model_id,
      global_default_multimodal_embedding_model_id: embeddingConfig.global_default_multimodal_embedding_model_id,
      rebuild_index: options.rebuildIndex,
    })

    const createdTasks = Array.isArray(res?.data?.created_tasks) ? res.data.created_tasks : []
    if (options.autoStartCreatedTasks && createdTasks.length > 0) {
      await Promise.all(
        createdTasks
          .map((task: any) => Number(task?.task_id))
          .filter((taskId: number) => Number.isFinite(taskId) && taskId > 0)
          .map((taskId: number) => startEmbeddingRebuildTask(taskId)),
      )
    }

    lastSavedEmbeddingConfig.global_default_text_embedding_model_id = embeddingConfig.global_default_text_embedding_model_id
    lastSavedEmbeddingConfig.global_default_multimodal_embedding_model_id = embeddingConfig.global_default_multimodal_embedding_model_id

    if (!options.silent) {
      ElMessage.success('Embedding 配置已保存')
    }

    await fetchEmbeddingConfig()
    await fetchEmbeddingTasks()
    await fetchFileRows()
  } catch (error: any) {
    if (!options.silent) {
      ElMessage.error(error?.response?.data?.message || '保存 Embedding 配置失败')
    }
  } finally {
    embeddingSaving.value = false
    if (embeddingAutoSaveQueued.value) {
      embeddingAutoSaveQueued.value = false
      if (hasEmbeddingConfigChanged()) {
        void saveEmbeddingConfig({ rebuildIndex: false, silent: true })
      }
    }
  }
}

function queueEmbeddingAutoSaveIfNeeded() {
  if (!hasEmbeddingConfigChanged()) return
  if (embeddingSaving.value) {
    embeddingAutoSaveQueued.value = true
    return
  }
  void saveEmbeddingConfig({ rebuildIndex: false, silent: true })
}

function isEmbeddingTaskActive(status: string) {
  return ['QUEUED', 'RUNNING'].includes((status || '').toUpperCase())
}

function embeddingTypeLabel(type: string) {
  return embeddingTypeLabels[type] || type || '-'
}

function resolveTargetModelName(task: EmbeddingTaskItem) {
  const modelId = Number(task.target_model_id)
  if (!Number.isFinite(modelId)) return '-'
  return embeddingModelNameById.value.get(modelId) || `模型 #${modelId}`
}

function taskProgressPercent(task: EmbeddingTaskItem) {
  const total = Number(task.discovered_count || 0)
  const succeeded = Number(task.succeeded_count || 0)
  const failed = Number(task.failed_count || 0)
  if (total <= 0) return 100
  const value = ((succeeded + failed) / total) * 100
  return Math.min(100, Math.max(0, Math.round(value)))
}

function upsertEmbeddingTask(task: EmbeddingTaskItem) {
  const next = [...embeddingTasks.value]
  const index = next.findIndex((item) => item.id === task.id)
  if (index >= 0) {
    next[index] = { ...next[index], ...task }
  } else {
    next.unshift(task)
  }
  embeddingTasks.value = next
}

function syncEmbeddingTaskStream() {
  if (!hasActiveEmbeddingTasks.value) {
    embeddingTaskStreamAbortController.value?.abort()
    embeddingTaskStreamAbortController.value = null
    return
  }
  if (embeddingTaskStreamAbortController.value) return

  const controller = new AbortController()
  embeddingTaskStreamAbortController.value = controller
  streamEventSource(
    '/api/admin/embedding/rebuild/tasks/stream',
    {
      onEvent: (eventType: string, data: any) => {
        if (eventType === 'task_update' && data) {
          upsertEmbeddingTask(data as EmbeddingTaskItem)
          if (!hasActiveEmbeddingTasks.value) {
            embeddingTaskStreamAbortController.value?.abort()
            embeddingTaskStreamAbortController.value = null
          }
        }
      },
      onError: () => {
        if (embeddingTaskStreamAbortController.value === controller) {
          embeddingTaskStreamAbortController.value = null
        }
        if (hasActiveEmbeddingTasks.value && !controller.signal.aborted) {
          setTimeout(() => {
            syncEmbeddingTaskStream()
          }, 1500)
        }
      },
    },
    controller.signal,
  )
}

async function handleStartEmbeddingTask(taskId: number) {
  embeddingRunningTaskId.value = taskId
  try {
    await startEmbeddingRebuildTask(taskId)
    ElMessage.success('任务已启动')
    await fetchEmbeddingTasks()
  } finally {
    embeddingRunningTaskId.value = null
  }
}

async function handleRetryFailedEmbeddingTask(taskId: number) {
  embeddingRunningTaskId.value = taskId
  try {
    await retryFailedEmbeddingRebuildTask(taskId)
    ElMessage.success('失败项重试任务已启动')
    await fetchEmbeddingTasks()
  } finally {
    embeddingRunningTaskId.value = null
  }
}

async function handleCancelEmbeddingTask(taskId: number) {
  embeddingRunningTaskId.value = taskId
  try {
    await cancelEmbeddingRebuildTask(taskId)
    ElMessage.success('任务取消请求已提交')
    await fetchEmbeddingTasks()
  } finally {
    embeddingRunningTaskId.value = null
  }
}

async function fetchFileRows() {
  fileLoading.value = true
  try {
    const res: any = await getEmbeddingFiles({
      keyword: fileFilters.keyword || undefined,
      status: fileFilters.status,
      page: fileFilters.page,
      page_size: fileFilters.page_size,
    })
    const data = res?.data || {}
    fileRows.value = Array.isArray(data.list) ? data.list : []
    fileTotal.value = Number(data.pagination?.total || 0)
    fileSummary.embedded = Number(data.summary?.embedded || 0)
    fileSummary.not_embedded = Number(data.summary?.not_embedded || 0)
    fileSummary.failed = Number(data.summary?.failed || 0)
  } finally {
    fileLoading.value = false
  }
}

function handleFileSearch() {
  fileFilters.page = 1
  void fetchFileRows()
}

function handleFilePageChange(page: number) {
  fileFilters.page = page
  void fetchFileRows()
}

function handleFilePageSizeChange(size: number) {
  fileFilters.page_size = size
  fileFilters.page = 1
  void fetchFileRows()
}

async function openFileDetail(row: any) {
  detailDialogVisible.value = true
  detailLoading.value = true
  currentDetail.value = null
  try {
    const res: any = await getEmbeddingFileDetail(Number(row.file_id))
    currentDetail.value = res?.data || null
  } finally {
    detailLoading.value = false
  }
}

async function fetchRecallMetrics() {
  recallLoading.value = true
  try {
    const res: any = await getRecallMetrics({ range: recallRange.value })
    recallMetrics.value = res?.data || null
  } finally {
    recallLoading.value = false
  }
}

function formatTime(val: string | null | undefined) {
  if (!val) return '-'
  return val.replace('T', ' ').substring(0, 19)
}

function taskStatusType(status: string) {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    QUEUED: 'warning',
    RUNNING: 'warning',
    PENDING: 'info',
    SUCCEEDED: 'success',
    FAILED: 'danger',
    PARTIAL_FAILED: 'warning',
    CANCELLED: 'info',
  }
  return map[(status || '').toUpperCase()] || 'info'
}

function taskStatusLabel(status: string) {
  const map: Record<string, string> = {
    QUEUED: '排队中',
    RUNNING: '执行中',
    PENDING: '待执行',
    SUCCEEDED: '成功',
    FAILED: '失败',
    PARTIAL_FAILED: '部分失败',
    CANCELLED: '已取消',
  }
  return map[(status || '').toUpperCase()] || status || '-'
}

onMounted(async () => {
  await fetchEmbeddingConfig()
  await fetchEmbeddingTasks()
  await fetchFileRows()
  await fetchRecallMetrics()
})

onBeforeUnmount(() => {
  embeddingTaskStreamAbortController.value?.abort()
  embeddingTaskStreamAbortController.value = null
})
</script>

<template>
  <div class="embedding-manage">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="全局配置与重建任务" name="config">
        <el-card shadow="never" class="provider-card" v-loading="embeddingConfigLoading">
          <template #header>
            <div class="card-header">
              <div class="card-title">Embedding 全局配置</div>
              <el-button
                size="small"
                type="primary"
                :loading="embeddingSaving"
                @click="saveEmbeddingConfig({ rebuildIndex: true, autoStartCreatedTasks: true })"
              >
                创建索引
              </el-button>
            </div>
          </template>
          <div class="embedding-config-grid">
            <div class="embedding-config-item">
              <div class="config-label">文本 Embedding 模型</div>
              <el-select
                v-model="embeddingConfig.global_default_text_embedding_model_id"
                clearable
                placeholder="选择全局默认文本 embedding 模型"
                filterable
                style="width: 100%"
                @change="queueEmbeddingAutoSaveIfNeeded"
              >
                <el-option-group
                  v-for="provider in textEmbeddingModelOptions"
                  :key="provider.providerId"
                  :label="provider.providerName"
                >
                  <el-option
                    v-for="model in provider.options"
                    :key="model.value"
                    :label="model.label"
                    :value="model.value"
                  />
                </el-option-group>
              </el-select>
            </div>

            <div class="embedding-config-item">
              <div class="config-label">多模态 Embedding 模型</div>
              <el-select
                v-model="embeddingConfig.global_default_multimodal_embedding_model_id"
                clearable
                placeholder="选择全局默认多模态 embedding 模型"
                filterable
                style="width: 100%"
                @change="queueEmbeddingAutoSaveIfNeeded"
              >
                <el-option-group
                  v-for="provider in multimodalEmbeddingModelOptions"
                  :key="provider.providerId"
                  :label="provider.providerName"
                >
                  <el-option
                    v-for="model in provider.options"
                    :key="model.value"
                    :label="model.label"
                    :value="model.value"
                  />
                </el-option-group>
              </el-select>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="provider-card">
          <template #header>
            <div class="card-header">
              <div class="card-title">索引重建任务</div>
            </div>
          </template>
          <el-table :data="embeddingTasks" size="small" stripe>
            <el-table-column prop="id" label="任务ID" width="90" />
            <el-table-column label="类型" width="140">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" type="info">{{ embeddingTypeLabel(row.embedding_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="目标模型名称" min-width="170">
              <template #default="{ row }">
                {{ resolveTargetModelName(row) }}
              </template>
            </el-table-column>
            <el-table-column label="进度" min-width="200">
              <template #default="{ row }">
                <div class="task-progress-cell">
                  <div class="task-progress-head">
                    <span class="task-progress-text">{{ row.succeeded_count || 0 }}/{{ row.discovered_count || 0 }} 完成</span>
                    <span class="task-progress-percent">{{ taskProgressPercent(row) }}%</span>
                  </div>
                  <div
                    class="task-progress-track"
                    role="progressbar"
                    :aria-valuenow="taskProgressPercent(row)"
                    aria-valuemin="0"
                    aria-valuemax="100"
                    :aria-label="`任务 ${row.id} 进度`"
                  >
                    <div class="task-progress-fill" :style="{ width: `${taskProgressPercent(row)}%` }" />
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="retryable_failed_count" label="可重试失败" width="120" />
            <el-table-column prop="failed_count" label="最终失败" width="100" />
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="taskStatusType(row.status)">{{ taskStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="最近心跳" width="180">
              <template #default="{ row }">
                {{ formatTime(row.last_heartbeat_at || row.updated_at) }}
              </template>
            </el-table-column>
            <el-table-column label="错误摘要" min-width="220">
              <template #default="{ row }">
                <span>{{ row.last_error || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  :disabled="embeddingRunningTaskId === row.id || isEmbeddingTaskActive(row.status) || row.status === 'SUCCEEDED' || row.status === 'CANCELLED'"
                  @click="handleStartEmbeddingTask(row.id)"
                >
                  {{ row.status === 'PENDING' ? '开始执行' : '继续执行' }}
                </el-button>
                <el-button
                  v-if="!isEmbeddingTaskActive(row.status) && (row.failed_count > 0 || row.status === 'PARTIAL_FAILED' || row.status === 'FAILED')"
                  link
                  type="warning"
                  :disabled="embeddingRunningTaskId === row.id"
                  @click="handleRetryFailedEmbeddingTask(row.id)"
                >
                  重试失败项
                </el-button>
                <el-button
                  v-if="isEmbeddingTaskActive(row.status) || row.status === 'PENDING'"
                  link
                  type="danger"
                  :disabled="embeddingRunningTaskId === row.id"
                  @click="handleCancelEmbeddingTask(row.id)"
                >
                  取消
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="文件监控与召回监控" name="monitor">
        <div class="metrics-grid">
          <el-card shadow="never" class="metric-card">
            <div class="metric-label">召回请求量</div>
            <div class="metric-value">{{ recallMetrics?.overview?.total_requests ?? 0 }}</div>
          </el-card>
          <el-card shadow="never" class="metric-card">
            <div class="metric-label">召回成功率</div>
            <div class="metric-value">{{ successRateText }}</div>
          </el-card>
          <el-card shadow="never" class="metric-card">
            <div class="metric-label">平均召回耗时(ms)</div>
            <div class="metric-value">{{ recallMetrics?.overview?.avg_recall_latency_ms ?? '-' }}</div>
          </el-card>
          <el-card shadow="never" class="metric-card">
            <div class="metric-label">平均命中文件数</div>
            <div class="metric-value">{{ recallMetrics?.hit_distribution?.avg_hit_count ?? 0 }}</div>
          </el-card>
        </div>

        <el-card shadow="never" class="provider-card" v-loading="recallLoading">
          <template #header>
            <div class="card-header">
              <div class="card-title">召回使用情况</div>
              <el-radio-group v-model="recallRange" size="small" @change="fetchRecallMetrics">
                <el-radio-button label="24h">近24小时</el-radio-button>
                <el-radio-button label="7d">近7天</el-radio-button>
                <el-radio-button label="30d">近30天</el-radio-button>
              </el-radio-group>
            </div>
          </template>

          <div class="recall-panels">
            <div class="recall-panel">
              <h4>命中文件数分布</h4>
              <el-descriptions :column="3" border size="small">
                <el-descriptions-item label="0个">{{ recallMetrics?.hit_distribution?.bins?.['0'] ?? 0 }}</el-descriptions-item>
                <el-descriptions-item label="1个">{{ recallMetrics?.hit_distribution?.bins?.['1'] ?? 0 }}</el-descriptions-item>
                <el-descriptions-item label="2个">{{ recallMetrics?.hit_distribution?.bins?.['2'] ?? 0 }}</el-descriptions-item>
                <el-descriptions-item label="3个">{{ recallMetrics?.hit_distribution?.bins?.['3'] ?? 0 }}</el-descriptions-item>
                <el-descriptions-item label="4个">{{ recallMetrics?.hit_distribution?.bins?.['4'] ?? 0 }}</el-descriptions-item>
                <el-descriptions-item label="5个以上">{{ recallMetrics?.hit_distribution?.bins?.['5+'] ?? 0 }}</el-descriptions-item>
              </el-descriptions>
            </div>
            <div class="recall-panel">
              <h4>命中最多文件 TOP</h4>
              <el-table :data="recallMetrics?.top_files || []" size="small" max-height="260">
                <el-table-column prop="file_id" label="文件ID" width="90" />
                <el-table-column prop="file_name" label="文件名" min-width="240" show-overflow-tooltip />
                <el-table-column prop="hit_count" label="命中次数" width="110" />
              </el-table>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="provider-card" v-loading="fileLoading">
          <template #header>
            <div class="card-header">
              <div class="card-title">文件 Embedding 监控（全平台）</div>
              <div class="card-actions">
                <el-tag type="success">已执行 {{ fileSummary.embedded }}</el-tag>
                <el-tag type="info">未执行 {{ fileSummary.not_embedded }}</el-tag>
                <el-tag type="danger">失败 {{ fileSummary.failed }}</el-tag>
              </div>
            </div>
          </template>

          <div class="file-filters">
            <el-input
              v-model="fileFilters.keyword"
              clearable
              placeholder="按文件名/路径/节点编码搜索"
              style="width: 320px"
              @keyup.enter="handleFileSearch"
              @clear="handleFileSearch"
            />
            <el-select v-model="fileFilters.status" style="width: 180px" @change="handleFileSearch">
              <el-option label="全部状态" value="all" />
              <el-option label="已执行" value="embedded" />
              <el-option label="未执行" value="not_embedded" />
              <el-option label="执行失败" value="failed" />
            </el-select>
            <el-button type="primary" @click="handleFileSearch">查询</el-button>
          </div>

          <el-table :data="fileRows" stripe size="small">
            <el-table-column prop="file_id" label="文件ID" width="90" />
            <el-table-column prop="file_name" label="文件名" min-width="220" show-overflow-tooltip />
            <el-table-column prop="route_type" label="路由类型" width="120" />
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="row.is_embedded ? 'success' : row.index_status === 'FAILED' ? 'danger' : 'info'">
                  {{ row.is_embedded ? '已执行' : row.index_status === 'FAILED' ? '失败' : '未执行' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="embedding_model_name" label="Embedding模型" min-width="160" show-overflow-tooltip />
            <el-table-column prop="embedding_dim" label="维度" width="90" />
            <el-table-column prop="scope_type" label="作用域" width="120" />
            <el-table-column prop="scope_id" label="作用域ID" width="100" />
            <el-table-column prop="node_code" label="节点编码" width="150" show-overflow-tooltip />
            <el-table-column label="最近索引时间" width="180">
              <template #default="{ row }">
                {{ formatTime(row.indexed_at) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openFileDetail(row)">查看详情</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrap">
            <el-pagination
              background
              layout="total, sizes, prev, pager, next"
              :total="fileTotal"
              :page-size="fileFilters.page_size"
              :current-page="fileFilters.page"
              :page-sizes="[10, 20, 50, 100]"
              @current-change="handleFilePageChange"
              @size-change="handleFilePageSizeChange"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="detailDialogVisible" title="文件 Embedding 详情" width="1100px" top="5vh">
      <div v-loading="detailLoading" class="detail-body">
        <template v-if="currentDetail">
          <el-descriptions border :column="2" size="small" class="detail-meta">
            <el-descriptions-item label="文件ID">{{ currentDetail.file.file_id }}</el-descriptions-item>
            <el-descriptions-item label="文件名">{{ currentDetail.file.file_name }}</el-descriptions-item>
            <el-descriptions-item label="路由类型">{{ currentDetail.file.route_type }}</el-descriptions-item>
            <el-descriptions-item label="状态">{{ currentDetail.embedding.index_status }}</el-descriptions-item>
            <el-descriptions-item label="Embedding模型">{{ currentDetail.embedding.embedding_model_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="Embedding维度">{{ currentDetail.embedding.embedding_dim || '-' }}</el-descriptions-item>
            <el-descriptions-item label="内容来源">{{ currentDetail.file.content_source || '-' }}</el-descriptions-item>
            <el-descriptions-item label="分块数量">{{ currentDetail.chunking.chunk_count }}</el-descriptions-item>
          </el-descriptions>

          <h4>分块内容</h4>
          <el-table :data="currentDetail.chunking.chunks" size="small" max-height="420">
            <el-table-column prop="chunk_no" label="块序号" width="80" />
            <el-table-column prop="start" label="起始" width="80" />
            <el-table-column prop="end" label="结束" width="80" />
            <el-table-column prop="chars" label="字符数" width="90" />
            <el-table-column prop="text" label="文本内容" min-width="700" show-overflow-tooltip />
          </el-table>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.embedding-manage {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.page-header p {
  margin: 6px 0 0;
  color: var(--text-secondary);
}

.provider-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.embedding-config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.embedding-config-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.task-progress-cell {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.task-progress-text {
  font-size: 12px;
  color: var(--text-secondary, #5f6472);
  font-weight: 500;
}

.task-progress-percent {
  font-size: 12px;
  color: #397ef2;
  font-weight: 700;
}

.task-progress-track {
  position: relative;
  height: 10px;
  border-radius: 999px;
  overflow: hidden;
  background: linear-gradient(90deg, #e7ecf5 0%, #dde5f2 100%);
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.1);
}

.task-progress-fill {
  position: relative;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #34d399 0%, #4f8cff 58%, #2563eb 100%);
  box-shadow: 0 1px 8px rgba(37, 99, 235, 0.35);
  transition: width 0.35s ease;
}

.task-progress-fill::after {
  content: '';
  position: absolute;
  top: 0;
  right: -20px;
  width: 28px;
  height: 100%;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.35));
  filter: blur(0.2px);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.metric-card {
  border-radius: 10px;
}

.metric-label {
  color: var(--text-secondary);
  font-size: 13px;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 26px;
  font-weight: 700;
}

.recall-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.recall-panel h4 {
  margin: 0 0 10px;
  font-size: 14px;
}

.file-filters {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.detail-body {
  min-height: 200px;
}

.detail-meta {
  margin-bottom: 14px;
}

@media (max-width: 1024px) {
  .recall-panels {
    grid-template-columns: 1fr;
  }

  .file-filters {
    flex-wrap: wrap;
  }
}
</style>
