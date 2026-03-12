<script setup lang="ts">
import { ref, onMounted, reactive, computed } from 'vue'
import {
  getModelProviderList,
  createModelProvider,
  updateModelProvider,
  deleteModelProvider,
  toggleModelProvider,
  testModelProvider,
  getEmbeddingConfig,
  updateEmbeddingConfig,
  getEmbeddingRebuildTasks,
  startEmbeddingRebuildTask,
  retryFailedEmbeddingRebuildTask,
  cancelEmbeddingRebuildTask,
} from '@/api/admin/modelProviders'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { showDangerConfirm } from '@/composables/useDangerConfirm'
import { streamEventSource } from '@/utils/sse'

interface ModelItem {
  id?: number
  model_name: string
  context_window: number
  is_enabled: boolean
  capability_tags?: string[]
  speed_rating?: string
  cost_rating?: string
  description?: string
  max_output_tokens?: number
  is_default?: boolean
}

interface ProviderItem {
  id: number
  provider_name: string
  provider_key: string
  api_base_url: string
  api_key_masked: string
  is_enabled: boolean
  protocol_type: string
  remark: string | null
  last_test_result: string | null
  last_test_time: string | null
  models: ModelItem[]
}

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

const loading = ref(false)
const providers = ref<ProviderItem[]>([])
const embeddingConfigLoading = ref(false)
const embeddingSaving = ref(false)
const embeddingRunningTaskId = ref<number | null>(null)
const embeddingTaskStreamAbortController = ref<AbortController | null>(null)
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
const embeddingAutoSaveQueued = ref(false)
const embeddingTasks = ref<EmbeddingTaskItem[]>([])

// 弹窗
const dialogVisible = ref(false)
const dialogTitle = ref('新增提供商')
const isEdit = ref(false)
const editingId = ref(0)
const formRef = ref<FormInstance>()
const form = reactive({
  provider_name: '',
  provider_key: '',
  api_base_url: '',
  api_key: '',
  protocol_type: 'openai_compatible',
  remark: '',
  models: [] as { model_name: string; context_window: number; is_enabled: boolean }[],
})

const providerPresets: Record<string, { key: string; url: string; models: { name: string; ctx: number }[] }> = {
  DeepSeek: {
    key: 'deepseek',
    url: 'https://api.deepseek.com/v1',
    models: [
      { name: 'deepseek-chat', ctx: 65536 },
      { name: 'deepseek-reasoner', ctx: 65536 },
    ],
  },
}

const rules: FormRules = {
  provider_name: [{ required: true, message: '请输入提供商名称', trigger: 'blur' }],
  api_base_url: [{ required: true, message: '请输入 API Base URL', trigger: 'blur' }],
  api_key: [{
    validator: (_rule: any, value: string, callback: any) => {
      if (!isEdit.value && !value) {
        callback(new Error('请输入 API Key'))
      } else {
        callback()
      }
    },
    trigger: 'blur',
  }],
}

const testingId = ref<number | null>(null)

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

async function fetchData() {
  loading.value = true
  try {
    const res: any = await getModelProviderList()
    providers.value = res.data
  } finally {
    loading.value = false
  }
}

async function fetchEmbeddingConfig() {
  embeddingConfigLoading.value = true
  try {
    const res: any = await getEmbeddingConfig()
    const data = res?.data || {}
    embeddingConfig.global_default_text_embedding_model_id = data.global_default_text_embedding_model_id ?? null
    embeddingConfig.global_default_multimodal_embedding_model_id = data.global_default_multimodal_embedding_model_id ?? null
    embeddingConfig.text_candidates = Array.isArray(data.text_candidates) ? data.text_candidates : []
    embeddingConfig.multimodal_candidates = Array.isArray(data.multimodal_candidates) ? data.multimodal_candidates : []

    const textIds = new Set(
      embeddingConfig.text_candidates
        .map((item: any) => Number(item?.id))
        .filter((id: number) => Number.isInteger(id) && id > 0),
    )
    const multimodalIds = new Set(
      embeddingConfig.multimodal_candidates
        .map((item: any) => Number(item?.id))
        .filter((id: number) => Number.isInteger(id) && id > 0),
    )

    const selectedTextId = embeddingConfig.global_default_text_embedding_model_id
    if (selectedTextId != null && !textIds.has(Number(selectedTextId))) {
      embeddingConfig.global_default_text_embedding_model_id = null
    }
    const selectedMultimodalId = embeddingConfig.global_default_multimodal_embedding_model_id
    if (selectedMultimodalId != null && !multimodalIds.has(Number(selectedMultimodalId))) {
      embeddingConfig.global_default_multimodal_embedding_model_id = null
    }
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

async function saveEmbeddingConfig(options: {
  rebuildIndex: boolean
  silent?: boolean
  autoStartCreatedTasks?: boolean
}) {
  const { rebuildIndex, silent = false, autoStartCreatedTasks = false } = options
  embeddingSaving.value = true
  try {
    const res: any = await updateEmbeddingConfig({
      global_default_text_embedding_model_id: embeddingConfig.global_default_text_embedding_model_id,
      global_default_multimodal_embedding_model_id: embeddingConfig.global_default_multimodal_embedding_model_id,
      rebuild_index: rebuildIndex,
    })
    const createdTasks = Array.isArray(res?.data?.created_rebuild_tasks) ? res.data.created_rebuild_tasks : []
    if (autoStartCreatedTasks && createdTasks.length > 0) {
      await Promise.all(
        createdTasks.map((task: any) => {
          const taskId = Number(task?.task_id)
          if (!Number.isInteger(taskId) || taskId <= 0) return Promise.resolve()
          return startEmbeddingRebuildTask(taskId)
        }),
      )
    }

    lastSavedEmbeddingConfig.global_default_text_embedding_model_id = embeddingConfig.global_default_text_embedding_model_id
    lastSavedEmbeddingConfig.global_default_multimodal_embedding_model_id = embeddingConfig.global_default_multimodal_embedding_model_id

    if (silent) {
      // no-op
    } else if (!rebuildIndex) {
      ElMessage.success('Embedding 配置已保存')
    } else if (createdTasks.length > 0) {
      ElMessage.success(`已创建 ${createdTasks.length} 个索引任务，并自动开始执行`)
    } else {
      ElMessage.warning('未创建索引任务，请先选择可用的 embedding 模型')
    }
    await fetchEmbeddingConfig()
    await fetchEmbeddingTasks()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || e?.message || '保存失败')
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
  if (!hasEmbeddingConfigChanged()) {
    return
  }
  if (embeddingSaving.value) {
    embeddingAutoSaveQueued.value = true
    return
  }
  void saveEmbeddingConfig({ rebuildIndex: false, silent: true })
}

function handleTextEmbeddingModelChange() {
  queueEmbeddingAutoSaveIfNeeded()
}

function handleMultimodalEmbeddingModelChange() {
  queueEmbeddingAutoSaveIfNeeded()
}

function isEmbeddingTaskActive(status: string) {
  return status === 'QUEUED' || status === 'RUNNING'
}

const hasActiveEmbeddingTasks = computed(() => embeddingTasks.value.some((task) => isEmbeddingTaskActive(task.status)))

const embeddingTypeLabels: Record<string, string> = {
  TEXT: '文本向量',
  MULTIMODAL: '多模态向量',
}

const embeddingModelNameById = computed(() => {
  const map = new Map<number, string>()
  for (const provider of providers.value) {
    for (const model of provider.models || []) {
      if (model.id && model.model_name) {
        map.set(Number(model.id), model.model_name)
      }
    }
  }
  for (const candidate of [...embeddingConfig.text_candidates, ...embeddingConfig.multimodal_candidates]) {
    const modelId = Number(candidate?.id)
    const modelName = String(candidate?.model_name || '').trim()
    if (modelId > 0 && modelName) {
      map.set(modelId, modelName)
    }
  }
  return map
})

function embeddingTypeLabel(type: string) {
  return embeddingTypeLabels[type] || type || '-'
}

function resolveTargetModelName(task: EmbeddingTaskItem) {
  const explicitName = String(task.target_model_name || '').trim()
  if (explicitName) return explicitName
  const modelId = Number(task.target_model_id)
  return embeddingModelNameById.value.get(modelId) || `模型 #${modelId}`
}

function taskProgressPercent(task: EmbeddingTaskItem) {
  if (Number(task.discovered_count || 0) <= 0) {
    return 100
  }
  const raw = Number(task.progress || 0)
  if (!Number.isFinite(raw)) return 0
  return Math.max(0, Math.min(100, Math.round(raw * 100)))
}

function upsertEmbeddingTask(task: EmbeddingTaskItem) {
  const next = [...embeddingTasks.value]
  const index = next.findIndex((item) => item.id === task.id)
  if (index >= 0) {
    next[index] = { ...next[index], ...task }
  } else {
    next.unshift(task)
  }
  next.sort((a, b) => b.id - a.id)
  embeddingTasks.value = next
}

function syncEmbeddingTaskStream() {
  if (!hasActiveEmbeddingTasks.value) {
    embeddingTaskStreamAbortController.value?.abort()
    embeddingTaskStreamAbortController.value = null
    return
  }
  if (embeddingTaskStreamAbortController.value) {
    return
  }

  const controller = new AbortController()
  embeddingTaskStreamAbortController.value = controller
  streamEventSource(
    '/api/admin/model-providers/embedding-rebuild/tasks/stream',
    {
      onEvent: (eventType, data) => {
        if (eventType === 'task_update') {
          upsertEmbeddingTask(data as EmbeddingTaskItem)
          if (!hasActiveEmbeddingTasks.value) {
            embeddingTaskStreamAbortController.value?.abort()
            embeddingTaskStreamAbortController.value = null
          }
        } else if (eventType === 'task_error') {
          ElMessage.error(data?.message || '重建任务流异常')
        }
      },
      onError: (message) => {
        if (!controller.signal.aborted) {
          ElMessage.error(message)
        }
      },
    },
    controller.signal,
  ).finally(() => {
    if (embeddingTaskStreamAbortController.value === controller) {
      embeddingTaskStreamAbortController.value = null
    }
    if (hasActiveEmbeddingTasks.value && !controller.signal.aborted) {
      window.setTimeout(() => {
        syncEmbeddingTaskStream()
      }, 1000)
    }
  })
}

function taskStatusLabel(status: string) {
  const map: Record<string, string> = {
    PENDING: '待执行',
    QUEUED: '排队中',
    RUNNING: '执行中',
    PARTIAL_FAILED: '部分失败',
    FAILED: '失败',
    SUCCEEDED: '完成',
    CANCELLED: '已取消',
  }
  return map[status] || status
}

function taskStatusType(status: string) {
  if (status === 'SUCCEEDED') return 'success'
  if (status === 'FAILED' || status === 'PARTIAL_FAILED') return 'danger'
  if (status === 'RUNNING' || status === 'QUEUED') return 'warning'
  return 'info'
}

async function handleStartEmbeddingTask(taskId: number) {
  embeddingRunningTaskId.value = taskId
  try {
    await startEmbeddingRebuildTask(taskId)
    ElMessage.success('重建任务已启动，后台会自动按批次处理')
    await fetchEmbeddingTasks()
    window.setTimeout(() => {
      void fetchEmbeddingTasks()
    }, 1500)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '任务启动失败')
  } finally {
    embeddingRunningTaskId.value = null
  }
}

async function handleRetryFailedEmbeddingTask(taskId: number) {
  embeddingRunningTaskId.value = taskId
  try {
    await retryFailedEmbeddingRebuildTask(taskId)
    ElMessage.success('失败项已重新入队，后台会自动重试')
    await fetchEmbeddingTasks()
    window.setTimeout(() => {
      void fetchEmbeddingTasks()
    }, 1500)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '重试失败项失败')
  } finally {
    embeddingRunningTaskId.value = null
  }
}

async function handleCancelEmbeddingTask(taskId: number) {
  await showDangerConfirm({
    title: '取消重建任务',
    subject: `任务 #${taskId}`,
    detail: '取消后将停止后续批次处理，未完成项会保留为已取消状态。确认继续？',
    confirmText: '确认取消',
  })
  embeddingRunningTaskId.value = taskId
  try {
    await cancelEmbeddingRebuildTask(taskId)
    ElMessage.success('已请求取消重建任务')
    await fetchEmbeddingTasks()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '取消任务失败')
  } finally {
    embeddingRunningTaskId.value = null
  }
}

function generateProviderKey(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
}

function onProviderNameChange(name: string) {
  if (isEdit.value) return
  const preset = providerPresets[name]
  if (preset) {
    form.provider_key = preset.key
    form.api_base_url = preset.url
    form.models = preset.models.map((m) => ({
      model_name: m.name,
      context_window: m.ctx,
      is_enabled: true,
    }))
  } else {
    form.provider_key = generateProviderKey(name)
  }
}

function openCreate() {
  isEdit.value = false
  dialogTitle.value = '新增提供商'
  Object.assign(form, {
    provider_name: '',
    provider_key: '',
    api_base_url: '',
    api_key: '',
    protocol_type: 'openai_compatible',
    remark: '',
    models: [],
  })
  dialogVisible.value = true
}

function openEdit(row: ProviderItem) {
  isEdit.value = true
  editingId.value = row.id
  dialogTitle.value = '编辑提供商'
  Object.assign(form, {
    provider_name: row.provider_name,
    provider_key: row.provider_key,
    api_base_url: row.api_base_url,
    api_key: '',
    protocol_type: row.protocol_type,
    remark: row.remark || '',
    models: row.models.map((m) => ({
      model_name: m.model_name,
      context_window: m.context_window,
      is_enabled: m.is_enabled,
    })),
  })
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value?.validate()
  if (form.models.length === 0) {
    ElMessage.warning('请至少添加一个模型')
    return
  }
  if (!isEdit.value && !form.provider_key) {
    form.provider_key = generateProviderKey(form.provider_name)
  }
  if (isEdit.value) {
    await updateModelProvider(editingId.value, {
      provider_name: form.provider_name,
      api_base_url: form.api_base_url,
      api_key: form.api_key || '',
      protocol_type: form.protocol_type,
      remark: form.remark,
      models: form.models,
    })
    ElMessage.success('提供商更新成功')
  } else {
    await createModelProvider(form)
    ElMessage.success('提供商创建成功')
  }
  dialogVisible.value = false
  await fetchData()
}

function addModel() {
  form.models.push({ model_name: '', context_window: 65536, is_enabled: true })
}

function removeModel(index: number) {
  form.models.splice(index, 1)
}

async function handleToggle(row: ProviderItem) {
  const action = row.is_enabled ? '停用' : '启用'
  await showDangerConfirm({
    title: `${action}提供商`,
    subject: row.provider_name,
    detail: action === '停用'
      ? '停用后将暂停所有该提供商的模型调用，但数据不会被删除。'
      : '启用后该提供商模型可恢复调用，请确认配置有效。',
    confirmText: `确认${action}`,
    confirmType: 'primary',
  })
  await toggleModelProvider(row.id, !row.is_enabled)
  ElMessage.success(`${action}成功`)
  await fetchData()
}

async function handleTest(row: ProviderItem) {
  testingId.value = row.id
  try {
    const res: any = await testModelProvider(row.id)
    if (res.data?.result === 'success') {
      ElMessage.success(`连通性测试成功，响应时间 ${res.data.response_time_ms}ms`)
    }
    fetchData()
  } catch {
    fetchData()
  } finally {
    testingId.value = null
  }
}

async function handleDelete(row: ProviderItem) {
  await showDangerConfirm({
    title: '删除提供商',
    subject: row.provider_name,
    detail: '删除后将移除该提供商及关联模型配置，且不可恢复。',
    confirmText: '删除提供商',
  })
  await deleteModelProvider(row.id)
  ElMessage.success('提供商删除成功')
  await fetchData()
}

function formatTime(val: string | null) {
  if (!val) return '-'
  return val.replace('T', ' ').substring(0, 19)
}

// 编辑模型标签
const tagDialogVisible = ref(false)
const tagFormRef = ref<FormInstance>()
const tagForm = reactive({
  provider_id: 0,
  model_name: '',
  capability_tags: [] as string[],
  speed_rating: '',
  cost_rating: '',
  description: '',
  max_output_tokens: null as number | null,
})

const availableTags = [
  'reasoning',
  'creative_writing',
  'coding',
  'data_analysis',
  'fast_response',
  'deep_thinking',
  'multimodal',
  'long_context',
  'embedding',
  'text_embedding',
  'multimodal_embedding',
]
const tagLabels: Record<string, string> = {
  reasoning: '推理', creative_writing: '创意写作', coding: '代码', data_analysis: '数据分析',
  fast_response: '快速响应', deep_thinking: '深度思考', multimodal: '多模态', long_context: '超长上下文',
  embedding: 'Embedding',
  text_embedding: '文本 Embedding',
  multimodal_embedding: '多模态 Embedding',
}
const speedOptions = ['fast', 'medium', 'slow']
const costOptions = ['low', 'medium', 'high']
const speedLabels: Record<string, string> = { fast: '快速', medium: '中等', slow: '较慢' }
const costLabels: Record<string, string> = { low: '低', medium: '中', high: '高' }

function openEditModelTags(providerId: number, model: ModelItem) {
  tagForm.provider_id = providerId
  tagForm.model_name = model.model_name
  tagForm.capability_tags = model.capability_tags || []
  tagForm.speed_rating = model.speed_rating || ''
  tagForm.cost_rating = model.cost_rating || ''
  tagForm.description = model.description || ''
  tagForm.max_output_tokens = model.max_output_tokens || null
  tagDialogVisible.value = true
}

async function saveModelTags() {
  try {
    const { updateModelTags } = await import('@/api/admin/modelProviders')
    await updateModelTags(tagForm.provider_id, tagForm.model_name, {
      capability_tags: tagForm.capability_tags.length > 0 ? tagForm.capability_tags : undefined,
      speed_rating: tagForm.speed_rating || undefined,
      cost_rating: tagForm.cost_rating || undefined,
      description: tagForm.description || undefined,
      max_output_tokens: tagForm.max_output_tokens || undefined,
    })
    ElMessage.success('模型标签更新成功')
    tagDialogVisible.value = false
    await fetchData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '更新失败')
  }
}

onMounted(async () => {
  await fetchData()
})
</script>

<template>
  <div class="model-provider">
    <div class="page-header">
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新增提供商
      </el-button>
    </div>

    <el-card v-for="p in providers" :key="p.id" shadow="never" class="provider-card">
      <template #header>
        <div class="card-header">
          <div class="card-title">
            <span class="provider-name">{{ p.provider_name }}</span>
            <el-tag :type="p.is_enabled ? 'success' : 'info'" size="small">
              {{ p.is_enabled ? '已启用' : '已停用' }}
            </el-tag>
            <el-tag
              v-if="p.last_test_result"
              :type="p.last_test_result === 'success' ? 'success' : p.last_test_result === 'failed' ? 'danger' : 'info'"
              size="small"
            >
              {{ p.last_test_result === 'success' ? '连通正常' : p.last_test_result === 'failed' ? '连通失败' : '未测试' }}
            </el-tag>
          </div>
          <div class="card-actions">
            <el-button
              size="small"
              :loading="testingId === p.id"
              @click="handleTest(p)"
            >
              测试连通性
            </el-button>
            <el-button size="small" @click="openEdit(p)">编辑</el-button>
            <el-button
              size="small"
              :type="p.is_enabled ? 'info' : 'success'"
              @click="handleToggle(p)"
            >
              {{ p.is_enabled ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" type="danger" @click="handleDelete(p)">删除</el-button>
          </div>
        </div>
      </template>

      <div class="provider-meta">
        <div class="meta-row">
          <div class="meta-label">API Base URL</div>
          <div class="meta-value">{{ p.api_base_url }}</div>
        </div>
        <div class="meta-row">
          <div class="meta-label">API Key</div>
          <div class="meta-value">{{ p.api_key_masked }}</div>
        </div>
        <div class="meta-row">
          <div class="meta-label">协议类型</div>
          <div class="meta-value">{{ p.protocol_type }}</div>
        </div>
        <div class="meta-row">
          <div class="meta-label">最近测试时间</div>
          <div class="meta-value">{{ formatTime(p.last_test_time) }}</div>
        </div>
        <div v-if="p.remark" class="meta-row">
          <div class="meta-label">备注</div>
          <div class="meta-value">{{ p.remark }}</div>
        </div>
      </div>

      <div class="model-list">
        <h4>可用模型 ({{ p.models.length }})</h4>
        <el-table :data="p.models" size="small" stripe>
          <el-table-column prop="model_name" label="模型名称" width="180" />
          <el-table-column label="能力标签" min-width="200">
            <template #default="{ row }">
              <el-tag
                v-for="tag in row.capability_tags || []"
                :key="tag"
                size="small"
                style="margin-right: 4px"
              >
                {{ tagLabels[tag] || tag }}
              </el-tag>
              <span v-if="!row.capability_tags || row.capability_tags.length === 0" style="color: #999">未设置</span>
            </template>
          </el-table-column>
          <el-table-column label="速度" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.speed_rating" size="small" :type="row.speed_rating === 'fast' ? 'success' : row.speed_rating === 'slow' ? 'warning' : ''">
                {{ speedLabels[row.speed_rating] || row.speed_rating }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="成本" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.cost_rating" size="small" :type="row.cost_rating === 'low' ? 'success' : row.cost_rating === 'high' ? 'danger' : ''">
                {{ costLabels[row.cost_rating] || row.cost_rating }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="上下文" width="100">
            <template #default="{ row }">{{ (row.context_window / 1000).toFixed(0) }}K</template>
          </el-table-column>
          <el-table-column label="状态" width="130">
            <template #default="{ row }">
              <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small" style="margin-right: 6px;">
                {{ row.is_enabled ? '启用' : '停用' }}
              </el-tag>
              <el-tag v-if="row.is_default" type="warning" size="small">默认</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openEditModelTags(p.id, row)">
                编辑标签
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-empty v-if="!loading && providers.length === 0" description="暂无模型提供商配置" />

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" width="680px" destroy-on-close class="model-provider-dialog">
      <template #header>
        <div class="dialog-header">
          <div class="dialog-header-badge">{{ isEdit ? '配置调整' : '接入配置' }}</div>
          <div class="dialog-header-title">{{ dialogTitle }}</div>
          <div class="dialog-header-desc">管理模型提供商连接参数、访问协议与可用模型。</div>
        </div>
      </template>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="提供商" prop="provider_name">
          <el-input
            v-model="form.provider_name"
            placeholder="如：DeepSeek、OpenAI、Anthropic"
            @input="onProviderNameChange"
          />
        </el-form-item>
        <el-form-item label="API Base URL" prop="api_base_url">
          <el-input v-model="form.api_base_url" placeholder="https://api.deepseek.com/v1" />
        </el-form-item>
        <el-form-item label="协议类型">
          <el-select v-model="form.protocol_type" style="width: 100%">
            <el-option
              label="OpenAI 兼容"
              value="openai_compatible"
            />
            <el-option
              label="Anthropic Messages"
              value="anthropic"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key" prop="api_key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="isEdit ? '留空表示不修改' : '请输入 API Key'"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="可选，如 Key 来源、到期时间等" />
        </el-form-item>

        <el-divider content-position="left">可用模型</el-divider>

        <div v-for="(m, i) in form.models" :key="i" class="model-row">
          <el-input v-model="m.model_name" placeholder="模型名称" style="flex: 2" />
          <el-input-number v-model="m.context_window" :min="1024" :step="1024" style="flex: 1" />
          <span class="unit">tokens</span>
          <el-switch v-model="m.is_enabled" />
          <el-button link type="danger" @click="removeModel(i)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
        <el-button type="primary" link @click="addModel" style="margin-top: 8px">
          <el-icon><Plus /></el-icon> 添加模型
        </el-button>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button class="dialog-btn dialog-btn-secondary" @click="dialogVisible = false">取消</el-button>
          <el-button class="dialog-btn dialog-btn-primary" @click="handleSubmit">
            {{ isEdit ? '保存配置' : '创建提供商' }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 编辑模型标签对话框 -->
    <el-dialog v-model="tagDialogVisible" width="620px" destroy-on-close class="model-provider-dialog">
      <template #header>
        <div class="dialog-header">
          <div class="dialog-header-badge">能力标注</div>
          <div class="dialog-header-title">编辑模型标签</div>
          <div class="dialog-header-desc">维护模型能力标签、速度成本等级及最大输出规模。</div>
        </div>
      </template>
      <el-form ref="tagFormRef" :model="tagForm" label-width="120px">
        <el-form-item label="模型名称">
          <el-input :value="tagForm.model_name" disabled />
        </el-form-item>
        <el-form-item label="能力标签">
          <el-checkbox-group v-model="tagForm.capability_tags">
            <el-checkbox v-for="tag in availableTags" :key="tag" :label="tag">
              {{ tagLabels[tag] || tag }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="速度等级">
          <el-radio-group v-model="tagForm.speed_rating">
            <el-radio label="">未设置</el-radio>
            <el-radio v-for="opt in speedOptions" :key="opt" :label="opt">
              {{ speedLabels[opt] }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="成本等级">
          <el-radio-group v-model="tagForm.cost_rating">
            <el-radio label="">未设置</el-radio>
            <el-radio v-for="opt in costOptions" :key="opt" :label="opt">
              {{ costLabels[opt] }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="tagForm.description" type="textarea" :rows="3" placeholder="模型描述" />
        </el-form-item>
        <el-form-item label="最大输出 Token">
          <el-input-number v-model="tagForm.max_output_tokens" :min="0" :step="1024" placeholder="留空表示未设置" style="width: 50%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button class="dialog-btn dialog-btn-secondary" @click="tagDialogVisible = false">取消</el-button>
          <el-button class="dialog-btn dialog-btn-primary" @click="saveModelTags">保存</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.model-provider {
  width: 100%;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.provider-card {
  margin-bottom: 16px;
}

.embedding-card {
  margin-bottom: 18px;
}

.embedding-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.embedding-config-item {
  padding: 10px 12px;
  border: 1px solid var(--border-primary, #ebeef5);
  border-radius: 10px;
  background: var(--el-fill-color-light, #f8fafc);
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

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.provider-name {
  font-size: 16px;
  font-weight: 600;
}

.card-actions {
  display: flex;
  gap: 4px;
}

.model-list {
  margin-top: 16px;
}

.model-list h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--text-secondary, #606266);
}

.model-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.unit {
  font-size: 12px;
  color: var(--text-muted, #909399);
  white-space: nowrap;
}

.provider-meta {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--el-fill-color-light, #f5f7fa);
}

.meta-row {
  display: flex;
  align-items: flex-start;
  padding: 4px 0;
  border-top: 1px dashed var(--el-border-color-light, #ebeef5);
}

.meta-row:first-child {
  border-top: none;
}

.meta-label {
  width: 120px;
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-secondary, #606266);
  text-align: right;
  padding-right: 8px;
  font-weight: 500;
}

.meta-value {
  flex: 1;
  font-size: 12px;
  color: var(--text-primary, #303133);
  word-break: break-all;
  line-height: 1.5;
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

:global(.model-provider-dialog .el-dialog) {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 32px;
  background: #ffffff;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
  background-clip: padding-box;
}

:global(.model-provider-dialog .el-dialog__header) {
  margin: 0;
  padding: 24px 24px 0;
  border-radius: 32px 32px 0 0;
  background: inherit;
}

:global(.model-provider-dialog .el-dialog__body) {
  padding: 18px 24px 0;
  background: inherit;
}

:global(.model-provider-dialog .el-dialog__footer) {
  padding: 22px 24px 24px;
  border-radius: 0 0 32px 32px;
  background: inherit;
}

:global(.model-provider-dialog .el-dialog__headerbtn),
:global(.model-provider-confirm-dialog .el-message-box__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.model-provider-dialog .el-dialog__headerbtn .el-dialog__close),
:global(.model-provider-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.model-provider-dialog .el-dialog__footer .el-button.dialog-btn),
:global(.model-provider-confirm-dialog .el-message-box__btns .el-button) {
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

:global(.dialog-btn-primary) {
  border: none;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #fff;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.2);
}

:global(.dialog-btn-primary:hover) {
  background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
  color: #fff;
}

:global(.model-provider-confirm-dialog.el-message-box) {
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

:global(.model-provider-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.model-provider-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.model-provider-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.model-provider-confirm-dialog .el-message-box__message) {
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

:global(.model-provider-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.model-provider-confirm-dialog .model-provider-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.model-provider-confirm-dialog .model-provider-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.model-provider-confirm-dialog .model-provider-confirm-primary) {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  color: #2563eb;
  box-shadow: none;
}

:global(.model-provider-confirm-dialog .model-provider-confirm-primary:hover) {
  border-color: #bfdbfe;
  background: #dbeafe;
  color: #1d4ed8;
}

:global(.model-provider-confirm-dialog .model-provider-confirm-danger) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.model-provider-confirm-dialog .model-provider-confirm-danger:hover) {
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

:global(html.dark .model-provider-dialog .el-dialog),
:global(html.dark .model-provider-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .model-provider-dialog .el-dialog__headerbtn .el-dialog__close),
:global(html.dark .model-provider-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: #94a3b8;
}

:global(html.dark .dialog-btn-secondary),
:global(html.dark .model-provider-confirm-dialog .model-provider-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .dialog-btn-secondary:hover),
:global(html.dark .model-provider-confirm-dialog .model-provider-confirm-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}

:global(html.dark) .danger-confirm-badge {
  background: rgba(248, 113, 113, 0.14);
  color: #fca5a5;
}

:global(html.dark) .danger-confirm-subject,
:global(html.dark .model-provider-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}

@media (max-width: 900px) {
  .embedding-config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
