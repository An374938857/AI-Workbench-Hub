<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { showDangerConfirm } from '@/composables/useDangerConfirm'

import {
  bindRequirementWorkflow,
  createRequirement,
  deleteRequirement,
  listRequirementOwnerOptions,
  listRequirements,
  updateRequirement,
} from '@/api/requirements'
import { getRequirementSandboxView, type RelatedSandboxView } from '@/api/sandboxViews'
import { listProjects } from '@/api/projects'
import { listPublishedWorkflowDefinitions } from '@/api/workflowDefinitions'
import { createConversation, getConversationList } from '@/api/conversations'
import { searchConversations } from '@/api/search'
import {
  advanceNode,
  bindNodeConversations,
  createWorkflowInstance,
  listNodeConversations,
  unbindNodeConversation,
  type WorkflowNodeConversationItem,
} from '@/api/workflowInstances'
import { createAsset, deleteAsset, downloadAssetFile, listAssets, refetchAsset, uploadAssetFile } from '@/api/assets'
import { useAuthStore } from '@/stores/auth'
import RequirementFileSandboxDrawer from '@/components/requirement/RequirementFileSandboxDrawer.vue'
import AssetUploadEditor from '@/components/common/AssetUploadEditor.vue'
import UnifiedFilePreviewDialog from '@/components/common/UnifiedFilePreviewDialog.vue'
import ElegantPagination from '@/components/common/ElegantPagination.vue'
import { useAssetSyncPolling } from '@/composables/useAssetSyncPolling'
import { useFilePreview } from '@/composables/useFilePreview'
import { getAssetSyncLabel, getAssetSyncTagType, isAssetSyncInProgressStatus, isYuqueUrl, normalizeAssetSyncStatus } from '@/utils/assetSync'

interface RequirementItem {
  id: number
  project_id: number
  title: string
  owner_user_id: number
  owner_name: string
  priority: 'P0' | 'P1' | 'P2' | 'P3'
  status: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELED'
  workflow_definition_id?: number
  workflow_instance_id?: number
  workflow_status?: 'UNBOUND' | 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELED'
  workflow_nodes?: WorkflowNodeItem[]
  due_date?: string
  description?: string
  created_at?: string
  updated_at?: string
}

interface WorkflowNodeItem {
  id: number | null
  node_code: string
  node_name: string
  node_order: number
  skill_id?: number | null
  status: 'NOT_STARTED' | 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'SKIPPED' | 'BLOCKED' | 'CANCELED'
}

interface ConversationOptionItem {
  conversation_id: number
  title: string
  skill_name: string
}

interface AssetItem {
  id: number
  node_code?: string
  asset_type: string
  title?: string
  source_url?: string
  file_ref?: string
  refetch_status: string
  created_at?: string
}

interface ProjectItem {
  id: number
  name: string
}

interface WorkflowItem {
  id: number
  name: string
  published_version_no: number
}

interface UserOptionItem {
  id: number
  display_name: string
  username: string
}

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const loading = ref(false)
const creating = ref(false)
const updatingRequirementStatusId = ref<number | null>(null)
const updatingRequirementPriorityId = ref<number | null>(null)
const updatingRequirementOwnerId = ref<number | null>(null)
const formMode = ref<'create' | 'edit'>('create')
const editingRequirementId = ref<number | null>(null)
const formPanelExpanded = ref(false)
const items = ref<RequirementItem[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const autoMinPageSize = ref(20)
const PAGE_SIZE_CANDIDATES = [20, 50, 100]
const tableRef = ref<{ $el?: HTMLElement } | null>(null)
let paginationResizeTimer: number | null = null
const projects = ref<ProjectItem[]>([])
const workflows = ref<WorkflowItem[]>([])
const ownerOptions = ref<UserOptionItem[]>([])
const ownerOptionsLoading = ref(false)
const nodeAssetDialogVisible = ref(false)
const nodeAssetLoading = ref(false)
const nodeAssetSubmitting = ref(false)
const currentNodeAssetRequirement = ref<RequirementItem | null>(null)
const currentNodeAsset = ref<WorkflowNodeItem | null>(null)
const currentNodeAssets = ref<AssetItem[]>([])
const nodeAssetPreview = useFilePreview()
const nodeAssetRefetchingId = ref<number | null>(null)
const nodeConversationDialogVisible = ref(false)
const nodeConversationLoading = ref(false)
const nodeConversationSearching = ref(false)
const nodeConversationBinding = ref(false)
const nodeConversationCreating = ref(false)
const currentNodeConversationRequirement = ref<RequirementItem | null>(null)
const currentNodeConversationNode = ref<WorkflowNodeItem | null>(null)
const currentNodeConversationItems = ref<WorkflowNodeConversationItem[]>([])
const nodeConversationSearchKeyword = ref('')
const nodeConversationSearchResults = ref<ConversationOptionItem[]>([])
const requirementSandboxVisible = ref(false)
const requirementSandboxLoading = ref(false)
const requirementSandboxRequirement = ref<RequirementItem | null>(null)
const requirementSandboxView = ref<RelatedSandboxView | null>(null)
const nodeAssetForm = ref({
  asset_type: 'FILE' as 'URL' | 'FILE' | 'MARKDOWN',
  title: '',
  source_url: '',
  content: '',
  files: [] as File[],
})
const nodeAssetTypeOptions = [
  { label: '文件', value: 'FILE' },
  { label: 'URL', value: 'URL' },
  { label: 'Markdown', value: 'MARKDOWN' },
]

const filters = ref({
  project_id: undefined as number | undefined,
  owner_user_id: undefined as number | undefined,
  priority: undefined as string | undefined,
  status: undefined as string | undefined,
  keyword: '',
  due_date_range: null as [string, string] | null,
})

const form = ref({
  project_id: undefined as number | undefined,
  title: '',
  priority: 'P2' as RequirementItem['priority'],
  workflow_definition_id: undefined as number | undefined,
  due_date: '' as string,
  description: '',
})

function resetForm() {
  form.value.title = ''
  form.value.priority = 'P2'
  form.value.workflow_definition_id = undefined
  form.value.due_date = ''
  form.value.description = ''
  formMode.value = 'create'
  editingRequirementId.value = null
  form.value.project_id = parseRouteProjectId(route.query.project_id)
}

const canEdit = computed(() => authStore.user?.role === 'user' || authStore.user?.role === 'admin')
const hasActiveFilters = computed(
  () =>
    Boolean(
      filters.value.project_id ||
        filters.value.priority ||
        filters.value.status ||
        filters.value.keyword.trim() ||
        filters.value.owner_user_id ||
        Boolean(filters.value.due_date_range?.length),
    ),
)

const statusTypeMap: Record<string, 'info' | 'warning' | 'success' | 'danger' | 'primary'> = {
  UNBOUND: 'info',
  NOT_STARTED: 'info',
  IN_PROGRESS: 'warning',
  COMPLETED: 'success',
  CANCELED: 'danger',
  PENDING: 'info',
  RUNNING: 'warning',
  SUCCEEDED: 'success',
  FAILED: 'danger',
  SKIPPED: 'primary',
  BLOCKED: 'danger',
}

const statusLabelMap: Record<string, string> = {
  UNBOUND: '未绑定流程',
  NOT_STARTED: '未开始',
  IN_PROGRESS: '进行中',
  COMPLETED: '已完成',
  CANCELED: '已取消',
  PENDING: '待处理',
  RUNNING: '进行中',
  SUCCEEDED: '完成',
  FAILED: '失败',
  SKIPPED: '跳过',
  BLOCKED: '阻塞',
}

const priorityTypeMap: Record<RequirementItem['priority'], 'danger' | 'warning' | 'primary' | 'info' | 'success'> = {
  P0: 'danger',
  P1: 'warning',
  P2: 'primary',
  P3: 'success',
}
const editableNodeStatuses: Array<WorkflowNodeItem['status']> = [
  'PENDING',
  'RUNNING',
  'SUCCEEDED',
  'SKIPPED',
  'BLOCKED',
  'CANCELED',
]
const editableRequirementStatuses: Array<RequirementItem['status']> = [
  'NOT_STARTED',
  'IN_PROGRESS',
  'COMPLETED',
  'CANCELED',
]
const editablePriorities: Array<RequirementItem['priority']> = ['P0', 'P1', 'P2', 'P3']

function getPriorityTagType(priority: RequirementItem['priority']) {
  return priorityTypeMap[priority]
}

function getStatusTagType(status?: string) {
  if (!status) return 'info'
  return statusTypeMap[status] || 'info'
}

function getRequirementStatusTagClass(status?: string) {
  return status === 'CANCELED' ? 'status-tag--canceled' : ''
}

function getStatusLabel(status?: string) {
  if (!status) return '-'
  return statusLabelMap[status] || status
}

function getNodeLightClass(status: string) {
  return `node-light--${status.toLowerCase()}`
}

function normalizeNodeStatus(status: WorkflowNodeItem['status']): WorkflowNodeItem['status'] {
  if (status === 'NOT_STARTED') return 'PENDING'
  return status
}

const terminalNodeStatuses = new Set<string>(['SUCCEEDED', 'SKIPPED', 'CANCELED', 'COMPLETED'])

function isTerminalNodeStatus(status?: string): boolean {
  return terminalNodeStatuses.has((status || '').toUpperCase())
}

function getFirstAttentionNodeIndex(nodes?: WorkflowNodeItem[]): number {
  if (!nodes?.length) return -1
  return nodes.findIndex((node) => !isTerminalNodeStatus(node.status))
}

function isPrimaryAttentionNode(row: RequirementItem, index: number): boolean {
  return getFirstAttentionNodeIndex(row.workflow_nodes) === index
}

function autoScrollNodeFlowRows() {
  const wraps = document.querySelectorAll<HTMLElement>('.node-flow-wrap')
  wraps.forEach((wrap) => {
    const nodeItems = Array.from(wrap.querySelectorAll<HTMLElement>('.node-flow-item'))
    if (!nodeItems.length) return
    const firstActiveNode = nodeItems.find((item) => !isTerminalNodeStatus(item.dataset.nodeStatus))
    if (!firstActiveNode) {
      wrap.scrollTo({ left: 0, behavior: 'auto' })
      return
    }
    wrap.scrollTo({
      left: Math.max(firstActiveNode.offsetLeft - 4, 0),
      behavior: 'auto',
    })
  })
}

const stats = computed(() => {
  const current = items.value
  const inProgress = current.filter((item) => item.status === 'IN_PROGRESS').length
  const completed = current.filter((item) => item.status === 'COMPLETED').length
  const urgent = current.filter((item) => item.priority === 'P0' || item.priority === 'P1').length
  return {
    total: total.value,
    inProgress,
    completed,
    urgent,
  }
})

async function fetchProjects() {
  const res = await listProjects({ page: 1, page_size: 100 })
  projects.value = res.data.items.map((item: { id: number; name: string }) => ({
    id: item.id,
    name: item.name,
  }))
}

async function fetchWorkflows() {
  const res = await listPublishedWorkflowDefinitions('REQUIREMENT')
  workflows.value = res.data
}

async function fetchOwnerOptions(keyword = '') {
  if (ownerOptionsLoading.value) return
  ownerOptionsLoading.value = true
  try {
    const res = await listRequirementOwnerOptions({
      keyword: keyword.trim() || undefined,
      page_size: 100,
    })
    ownerOptions.value = res.data as UserOptionItem[]
  } finally {
    ownerOptionsLoading.value = false
  }
}

async function fetchRequirements() {
  if (loading.value) return
  loading.value = true
  try {
    const dueDateStart = filters.value.due_date_range?.[0]
    const dueDateEnd = filters.value.due_date_range?.[1]
    const res = await listRequirements({
      page: currentPage.value,
      page_size: pageSize.value,
      project_id: filters.value.project_id,
      owner_user_id: filters.value.owner_user_id,
      priority: filters.value.priority,
      status: filters.value.status,
      keyword: filters.value.keyword.trim() || undefined,
      due_date_start: dueDateStart,
      due_date_end: dueDateEnd,
    })
    items.value = (res.data.items as RequirementItem[])
      .slice()
      .sort((a, b) => a.id - b.id)
      .map((item) => ({
      ...item,
      workflow_nodes: (item.workflow_nodes || []).map((node) => ({
        ...node,
        status: normalizeNodeStatus(node.status),
      })),
      }))
    total.value = res.data.total
    await nextTick()
    requestAnimationFrame(() => {
      autoScrollNodeFlowRows()
    })
  } finally {
    loading.value = false
  }
}

function computeAdaptivePageSize(): number {
  const tableElement = tableRef.value?.$el
  if (!tableElement) return autoMinPageSize.value

  const tableTop = tableElement.getBoundingClientRect().top
  const firstRow = tableElement.querySelector<HTMLElement>('.el-table__body-wrapper tbody tr')
  const rowHeight = firstRow?.offsetHeight || 56
  const footerReserve = 170
  const availableHeight = Math.max(window.innerHeight - tableTop - footerReserve, rowHeight)
  const visibleRows = Math.max(5, Math.floor(availableHeight / rowHeight))
  return visibleRows
}

const pageSizeOptions = computed(() => {
  const merged = [autoMinPageSize.value, ...PAGE_SIZE_CANDIDATES.filter((size) => size >= autoMinPageSize.value)]
  return Array.from(new Set(merged)).sort((a, b) => a - b)
})

async function recalcAdaptivePageSize(options?: { forceReset?: boolean }) {
  const nextMin = computeAdaptivePageSize()
  autoMinPageSize.value = nextMin
  const shouldReset = pageSize.value < nextMin || (options?.forceReset === true && pageSize.value !== nextMin)
  if (!shouldReset) return

  pageSize.value = nextMin
  currentPage.value = 1
  await fetchRequirements()
}

function handleWindowResize() {
  if (paginationResizeTimer !== null) {
    window.clearTimeout(paginationResizeTimer)
  }
  paginationResizeTimer = window.setTimeout(() => {
    void recalcAdaptivePageSize()
  }, 120)
}

async function handleCreate() {
  if (!form.value.project_id || !form.value.workflow_definition_id || !form.value.title.trim()) {
    ElMessage.warning('请填写项目、标题和流程定义')
    return
  }
  creating.value = true
  try {
    if (formMode.value === 'edit' && editingRequirementId.value) {
      const original = items.value.find((item) => item.id === editingRequirementId.value)
      await updateRequirement(editingRequirementId.value, {
        title: form.value.title.trim(),
        priority: form.value.priority,
        due_date: form.value.due_date || null,
        description: form.value.description || undefined,
      })
      if (form.value.workflow_definition_id && original?.workflow_definition_id !== form.value.workflow_definition_id) {
        await bindRequirementWorkflow(editingRequirementId.value, form.value.workflow_definition_id)
      }
      ElMessage.success('需求更新成功')
    } else {
      await createRequirement({
        project_id: form.value.project_id,
        title: form.value.title.trim(),
        priority: form.value.priority,
        workflow_definition_id: form.value.workflow_definition_id,
        due_date: form.value.due_date || undefined,
        description: form.value.description || undefined,
      })
      ElMessage.success('需求创建成功')
    }
    resetForm()
    formPanelExpanded.value = false
    currentPage.value = 1
    await fetchRequirements()
  } finally {
    creating.value = false
  }
}

function handleEditRequirement(row: RequirementItem) {
  formMode.value = 'edit'
  formPanelExpanded.value = true
  editingRequirementId.value = row.id
  form.value.project_id = row.project_id
  form.value.title = row.title
  form.value.priority = row.priority
  form.value.workflow_definition_id = row.workflow_definition_id
  form.value.due_date = row.due_date || ''
  form.value.description = row.description || ''
}

function handleOpenCreateForm() {
  if (!canEdit.value) return
  resetForm()
  formPanelExpanded.value = true
}

function projectNameById(projectId: number): string {
  const project = projects.value.find((item) => item.id === projectId)
  return project?.name || `项目#${projectId}`
}

async function handleNodeStatusChange(
  row: RequirementItem,
  node: WorkflowNodeItem,
  toStatus: WorkflowNodeItem['status'],
) {
  let skipReason: string | undefined
  if (toStatus === 'SKIPPED') {
    try {
      const promptValue = await ElMessageBox.prompt('请输入跳过原因（必填）', '跳过节点', {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /.+/,
        inputErrorMessage: '请填写跳过原因',
      })
      const rawValue = typeof promptValue === 'string' ? promptValue : String(promptValue.value || '')
      skipReason = rawValue.trim()
      if (!skipReason) {
        ElMessage.warning('请填写跳过原因')
        return
      }
    } catch {
      return
    }
  }

  let instanceId = row.workflow_instance_id
  let nodeId = node.id

  if (!instanceId) {
    if (!row.workflow_definition_id) {
      ElMessage.warning('请先为需求绑定流程，再维护节点状态')
      return
    }
    await createWorkflowInstance({
      scope_type: 'REQUIREMENT',
      scope_id: row.id,
      workflow_definition_id: row.workflow_definition_id,
    })
    await fetchRequirements()
    const refreshedRow = items.value.find((item) => item.id === row.id)
    const refreshedNode = refreshedRow?.workflow_nodes?.find((item) => item.node_code === node.node_code)
    if (!refreshedRow?.workflow_instance_id || !refreshedNode?.id) {
      ElMessage.warning('流程实例初始化成功，但节点未就绪，请重试')
      return
    }
    instanceId = refreshedRow.workflow_instance_id
    nodeId = refreshedNode.id
  }

  if (!nodeId) {
    ElMessage.warning('当前节点未就绪，请稍后重试')
    return
  }
  await advanceNode(instanceId, nodeId, { to_status: toStatus, skip_reason: skipReason })
  ElMessage.success('节点状态已更新')
  await fetchRequirements()
}

async function handleNodeInlineStatusChange(
  row: RequirementItem,
  node: WorkflowNodeItem,
  status: WorkflowNodeItem['status'],
) {
  await handleNodeStatusChange(row, node, status)
}

function handleNodeStatusDropdownCommand(
  row: RequirementItem,
  node: WorkflowNodeItem,
  status: string | number | object,
) {
  handleNodeInlineStatusChange(row, node, status as WorkflowNodeItem['status'])
}

async function handleRequirementStatusChange(
  row: RequirementItem,
  status: RequirementItem['status'],
) {
  if (!canEdit.value || updatingRequirementStatusId.value === row.id || row.status === status) {
    return
  }
  updatingRequirementStatusId.value = row.id
  try {
    await updateRequirement(row.id, { status })
    row.status = status
    ElMessage.success('需求状态已更新')
  } finally {
    updatingRequirementStatusId.value = null
  }
}

function handleRequirementStatusDropdownCommand(
  row: RequirementItem,
  status: string | number | object,
) {
  handleRequirementStatusChange(row, status as RequirementItem['status'])
}

async function handleRequirementPriorityChange(
  row: RequirementItem,
  priority: RequirementItem['priority'],
) {
  if (!canEdit.value || updatingRequirementPriorityId.value === row.id || row.priority === priority) {
    return
  }
  updatingRequirementPriorityId.value = row.id
  try {
    await updateRequirement(row.id, { priority })
    row.priority = priority
    ElMessage.success('需求优先级已更新')
  } finally {
    updatingRequirementPriorityId.value = null
  }
}

function handleRequirementPriorityDropdownCommand(
  row: RequirementItem,
  priority: string | number | object,
) {
  handleRequirementPriorityChange(row, priority as RequirementItem['priority'])
}

async function handleRequirementOwnerChange(row: RequirementItem, ownerUserId: number) {
  if (!canEdit.value || updatingRequirementOwnerId.value === row.id || row.owner_user_id === ownerUserId) {
    return
  }
  updatingRequirementOwnerId.value = row.id
  try {
    await updateRequirement(row.id, { owner_user_id: ownerUserId })
    const owner = ownerOptions.value.find((item) => item.id === ownerUserId)
    row.owner_user_id = ownerUserId
    row.owner_name = owner?.display_name || `用户#${ownerUserId}`
    ElMessage.success('负责人更新成功')
  } finally {
    updatingRequirementOwnerId.value = null
  }
}

function handleRequirementOwnerDropdownCommand(row: RequirementItem, ownerUserId: string | number | object) {
  const parsed = Number(ownerUserId)
  if (!Number.isInteger(parsed) || parsed <= 0) return
  handleRequirementOwnerChange(row, parsed)
}

async function ensureRuntimeNode(
  row: RequirementItem,
  node: WorkflowNodeItem,
): Promise<{ instanceId: number; nodeId: number; skillId?: number | null } | null> {
  let instanceId = row.workflow_instance_id
  let runtimeNode = node
  if (!instanceId || !runtimeNode.id) {
    if (!row.workflow_definition_id) {
      ElMessage.warning('请先为需求绑定流程')
      return null
    }
    await createWorkflowInstance({
      scope_type: 'REQUIREMENT',
      scope_id: row.id,
      workflow_definition_id: row.workflow_definition_id,
    })
    await fetchRequirements()
    const refreshedRow = items.value.find((item) => item.id === row.id)
    const refreshedNode = refreshedRow?.workflow_nodes?.find((item) => item.node_code === node.node_code)
    if (!refreshedRow?.workflow_instance_id || !refreshedNode?.id) {
      ElMessage.warning('流程实例初始化成功，但节点未就绪，请重试')
      return null
    }
    instanceId = refreshedRow.workflow_instance_id
    runtimeNode = refreshedNode
  }
  if (runtimeNode.id == null) {
    ElMessage.warning('当前节点未就绪，请稍后重试')
    return null
  }
  return { instanceId, nodeId: runtimeNode.id, skillId: runtimeNode.skill_id }
}

async function searchConversationOptions() {
  nodeConversationSearching.value = true
  try {
    const keyword = nodeConversationSearchKeyword.value.trim()
    if (!keyword) {
      const res = await getConversationList({ page: 1, page_size: 20 })
      nodeConversationSearchResults.value = (res.data.items || []).map((item: { id: number; title?: string; skill_name?: string }) => ({
        conversation_id: item.id,
        title: item.title || '新对话',
        skill_name: item.skill_name || '自由对话',
      }))
      return
    }
    const res = await searchConversations({ q: keyword, page: 1, page_size: 20 })
    nodeConversationSearchResults.value = (res.data.results || []).map((item: { conversation_id: number; title?: string; skill_name?: string }) => ({
      conversation_id: item.conversation_id,
      title: item.title || '新对话',
      skill_name: item.skill_name || '自由对话',
    }))
  } finally {
    nodeConversationSearching.value = false
  }
}

async function refreshNodeConversationItems() {
  if (!currentNodeConversationRequirement.value || !currentNodeConversationNode.value) return
  const runtime = await ensureRuntimeNode(currentNodeConversationRequirement.value, currentNodeConversationNode.value)
  if (!runtime) return
  nodeConversationLoading.value = true
  try {
    const res = await listNodeConversations(runtime.instanceId, runtime.nodeId)
    currentNodeConversationItems.value = res.data.items || []
    if (currentNodeConversationNode.value) {
      currentNodeConversationNode.value.skill_id = res.data.node?.skill_id
    }
  } finally {
    nodeConversationLoading.value = false
  }
}

function applyBoundConversationNodeStatusToView() {
  const row = currentNodeConversationRequirement.value
  const node = currentNodeConversationNode.value
  if (!row || !node) return
  if (normalizeNodeStatus(node.status) !== 'PENDING') return

  node.status = 'RUNNING'
  const targetNode = row.workflow_nodes?.find((item) => item.node_code === node.node_code)
  if (targetNode && normalizeNodeStatus(targetNode.status) === 'PENDING') {
    targetNode.status = 'RUNNING'
  }
}

async function handleOpenNodeConversations(row: RequirementItem, node: WorkflowNodeItem) {
  currentNodeConversationRequirement.value = row
  currentNodeConversationNode.value = { ...node }
  nodeConversationDialogVisible.value = true
  nodeConversationSearchKeyword.value = ''
  nodeConversationSearchResults.value = []
  await refreshNodeConversationItems()
  await searchConversationOptions()
}

async function handleBindConversationToNode(conversationId: number) {
  if (!currentNodeConversationRequirement.value || !currentNodeConversationNode.value) return
  const runtime = await ensureRuntimeNode(currentNodeConversationRequirement.value, currentNodeConversationNode.value)
  if (!runtime) return
  nodeConversationBinding.value = true
  try {
    await bindNodeConversations(runtime.instanceId, runtime.nodeId, {
      conversation_ids: [conversationId],
      binding_type: 'MANUAL',
    })
    applyBoundConversationNodeStatusToView()
    ElMessage.success('会话绑定成功')
    await refreshNodeConversationItems()
  } finally {
    nodeConversationBinding.value = false
  }
}

async function handleCreateAndBindConversation() {
  if (!currentNodeConversationRequirement.value || !currentNodeConversationNode.value) return
  const runtime = await ensureRuntimeNode(currentNodeConversationRequirement.value, currentNodeConversationNode.value)
  if (!runtime) return
  nodeConversationCreating.value = true
  try {
    const created = await createConversation(runtime.skillId || undefined)
    const conversationId = Number(created.data.conversation_id)
    await bindNodeConversations(runtime.instanceId, runtime.nodeId, {
      conversation_ids: [conversationId],
      binding_type: 'AUTO',
    })
    applyBoundConversationNodeStatusToView()
    ElMessage.success('已创建并绑定会话')
    handleOpenConversationDetail(conversationId)
  } finally {
    nodeConversationCreating.value = false
  }
}

async function handleUnbindConversationFromNode(conversationId: number) {
  if (!currentNodeConversationRequirement.value || !currentNodeConversationNode.value) return
  const runtime = await ensureRuntimeNode(currentNodeConversationRequirement.value, currentNodeConversationNode.value)
  if (!runtime) return
  await showDangerConfirm({
    title: '解绑会话',
    subject: `会话 #${conversationId}`,
    detail: '解绑后该会话将不再出现在当前节点下，但不会删除会话本身。',
    confirmText: '确认解绑',
  })
  await unbindNodeConversation(runtime.instanceId, runtime.nodeId, conversationId)
  ElMessage.success('会话解绑成功')
  await refreshNodeConversationItems()
}

function handleOpenConversationDetail(conversationId: number) {
  router.push(`/chat/${conversationId}`)
}

async function handleOpenNodeAssets(row: RequirementItem, node: WorkflowNodeItem) {
  nodeAssetDialogVisible.value = true
  nodeAssetLoading.value = true
  currentNodeAssetRequirement.value = row
  currentNodeAsset.value = node
  nodeAssetForm.value.asset_type = 'FILE'
  nodeAssetForm.value.title = ''
  nodeAssetForm.value.source_url = ''
  nodeAssetForm.value.content = ''
  nodeAssetForm.value.files = []
  try {
    await refreshNodeAssets()
  } finally {
    nodeAssetLoading.value = false
  }
}

async function refreshNodeAssets() {
  if (!currentNodeAssetRequirement.value || !currentNodeAsset.value) return
  const res = await listAssets({
    scope_type: 'REQUIREMENT',
    scope_id: currentNodeAssetRequirement.value.id,
    node_code: currentNodeAsset.value.node_code,
  })
  currentNodeAssets.value = res.data || []
}

async function handleSubmitNodeAsset() {
  if (!currentNodeAssetRequirement.value || !currentNodeAsset.value) return
  const requirementId = currentNodeAssetRequirement.value.id
  const nodeCode = currentNodeAsset.value.node_code
  const isUrlAsset = nodeAssetForm.value.asset_type === 'URL'
  let urlSyncInProgress = false

  nodeAssetSubmitting.value = true
  try {
    if (nodeAssetForm.value.asset_type === 'FILE') {
      const selectedFiles = nodeAssetForm.value.files
      if (!selectedFiles.length) {
        ElMessage.warning('请先选择上传文件')
        return
      }
      for (const file of selectedFiles) {
        await uploadAssetFile(file, 'REQUIREMENT', requirementId, nodeCode, file.name)
      }
    } else if (nodeAssetForm.value.asset_type === 'MARKDOWN') {
      if (!nodeAssetForm.value.content.trim()) {
        ElMessage.warning('请填写 Markdown 内容')
        return
      }
      await createAsset({
        scope_type: 'REQUIREMENT',
        scope_id: requirementId,
        node_code: nodeCode,
        asset_type: 'MARKDOWN',
        title: nodeAssetForm.value.title || undefined,
        content: nodeAssetForm.value.content.trim(),
      })
    } else {
      if (!nodeAssetForm.value.source_url.trim()) {
        ElMessage.warning('请填写 URL')
        return
      }
      const res = await createAsset({
        scope_type: 'REQUIREMENT',
        scope_id: requirementId,
        node_code: nodeCode,
        asset_type: nodeAssetForm.value.asset_type,
        title: nodeAssetForm.value.title || undefined,
        source_url: nodeAssetForm.value.source_url.trim(),
      })
      const status = normalizeAssetSyncStatus(res.data?.refetch_status)
      if (isAssetSyncInProgressStatus(status)) {
        ElMessage.info('已提交后台下载，稍后自动更新状态')
        urlSyncInProgress = true
        nodeAssetSyncPolling.markTaskSubmitted()
      }
    }

    ElMessage.success(isUrlAsset ? (urlSyncInProgress ? '节点资料已保存，后台正在处理' : '节点资料已保存') : '节点资产保存成功')
    nodeAssetForm.value.files = []
    await refreshNodeAssets()
  } finally {
    nodeAssetSubmitting.value = false
  }
}

function handleNodeFilesChange(files: File[]) {
  nodeAssetForm.value.files = files
}

function getNodeAssetTypeLabel(assetType: string) {
  if (assetType === 'FILE') return '文件'
  if (assetType === 'URL') return 'URL'
  if (assetType === 'YUQUE_URL') return '语雀'
  if (assetType === 'MARKDOWN') return 'Markdown'
  return assetType || '未知'
}

function getNodeAssetSummary(asset: AssetItem) {
  return asset.source_url || asset.file_ref || '无内容摘要'
}

function formatNodeAssetTime(createdAt?: string) {
  if (!createdAt) return '--'
  const normalized = createdAt.replace('T', ' ').replace(/\./g, '-')
  const matched = normalized.match(/^(\d{4}-\d{2}-\d{2})[ ](\d{2}):(\d{2}):(\d{2})/)
  if (matched) {
    return `${matched[1]} ${matched[2]}-${matched[3]}-${matched[4]}`
  }
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return normalized
  const pad = (v: number) => String(v).padStart(2, '0')
  const y = date.getFullYear()
  const m = pad(date.getMonth() + 1)
  const d = pad(date.getDate())
  const hh = pad(date.getHours())
  const mm = pad(date.getMinutes())
  const ss = pad(date.getSeconds())
  return `${y}-${m}-${d} ${hh}-${mm}-${ss}`
}

function isFileNodeAsset(asset: AssetItem) {
  return asset.asset_type === 'FILE' || Boolean(asset.file_ref)
}

function shouldShowNodeAssetDownload(asset: AssetItem) {
  const type = String(asset.asset_type || '').toUpperCase()
  if (type === 'MARKDOWN') return false
  if (type === 'URL' || type === 'YUQUE_URL') return isYuqueUrl(asset.source_url)
  return isFileNodeAsset(asset)
}

function isYuqueSourceUrl(sourceUrl?: string) {
  return isYuqueUrl(sourceUrl)
}

function shouldShowNodeAssetRefetch(asset: AssetItem) {
  return isYuqueSourceUrl(asset.source_url)
}

function openExternalAssetLink(asset: AssetItem) {
  if (!asset.source_url) return
  window.open(asset.source_url, '_blank', 'noopener,noreferrer')
}

async function handlePreviewNodeAsset(asset: AssetItem) {
  if ((asset.asset_type === 'URL' || asset.asset_type === 'YUQUE_URL') && asset.source_url) {
    openExternalAssetLink(asset)
    return
  }
  await nodeAssetPreview.openPreview({
    source: 'asset',
    assetId: asset.id,
    label: asset.title || `资料 #${asset.id}`,
    fileType: asset.file_ref?.split('.').pop(),
    autoOpenExternalUrl: true,
  })
}

function getFilenameFromDisposition(disposition?: string): string {
  if (!disposition) return ''
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1])
  const quotedMatch = disposition.match(/filename=\"([^\"]+)\"/i)
  if (quotedMatch?.[1]) return quotedMatch[1]
  const plainMatch = disposition.match(/filename=([^;]+)/i)
  return plainMatch?.[1]?.trim() || ''
}

async function handleDownloadNodeAsset(asset: AssetItem) {
  if (!isFileNodeAsset(asset)) {
    if (isYuqueSourceUrl(asset.source_url)) {
      await nodeAssetPreview.openPreview({
        source: 'asset',
        assetId: asset.id,
        label: asset.title || `资料 #${asset.id}`,
        fileType: asset.file_ref?.split('.').pop(),
        autoOpenExternalUrl: false,
      })
      await nodeAssetPreview.downloadCurrent()
      return
    }
    if (asset.source_url) {
      openExternalAssetLink(asset)
      return
    }
    ElMessage.warning('当前资料暂不支持下载')
    return
  }
  try {
    const response = await downloadAssetFile(asset.id)
    const disposition = response.headers?.['content-disposition'] as string | undefined
    const fallbackName = asset.file_ref?.split('/').pop() || asset.title || `asset-${asset.id}`
    const filename = getFilenameFromDisposition(disposition) || fallbackName
    const blobUrl = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = blobUrl
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(blobUrl)
  } catch {
    ElMessage.error('下载失败')
  }
}

async function handleDeleteNodeAsset(asset: AssetItem) {
  try {
    await showDangerConfirm({
      title: '删除资料',
      subject: asset.title || `资料 #${asset.id}`,
      detail: '删除后将从当前节点资料中移除，且不可恢复。',
      confirmText: '删除资料',
    })
  } catch {
    return
  }
  await deleteAsset(asset.id)
  ElMessage.success('删除成功')
  await refreshNodeAssets()
}

async function handleRefetchNodeAsset(asset: AssetItem) {
  if (nodeAssetRefetchingId.value) return
  nodeAssetRefetchingId.value = asset.id
  try {
    asset.refetch_status = 'RUNNING'
    nodeAssetSyncPolling.markTaskSubmitted()
    const res = await refetchAsset(asset.id)
    const status = normalizeAssetSyncStatus(res.data?.refetch_status)
    if (isAssetSyncInProgressStatus(status)) {
      ElMessage.info('重抓任务已提交，后台执行中')
    } else {
      ElMessage.success('重抓完成')
    }
    await refreshNodeAssets()
  } catch {
    asset.refetch_status = 'FAILED'
    ElMessage.error('重抓失败')
  } finally {
    nodeAssetRefetchingId.value = null
  }
}

async function handleDeleteRequirement(row: RequirementItem) {
  try {
    await showDangerConfirm({
      title: '删除需求',
      subject: row.title,
      detail: '删除后将清理需求关联的流程实例与资料记录，且不可恢复。',
      confirmText: '确认删除',
    })
  } catch {
    return
  }

  await deleteRequirement(row.id)
  ElMessage.success('需求已删除')
  if (items.value.length === 1 && currentPage.value > 1) {
    currentPage.value -= 1
  }
  await fetchRequirements()
}

async function openRequirementSandbox(row: RequirementItem) {
  if (requirementSandboxLoading.value) return
  requirementSandboxRequirement.value = row
  requirementSandboxVisible.value = true
  requirementSandboxLoading.value = true
  try {
    const res = await getRequirementSandboxView(row.id)
    requirementSandboxView.value = (res.data || null) as RelatedSandboxView | null
  } finally {
    requirementSandboxLoading.value = false
  }
}

async function refreshRequirementSandbox() {
  if (!requirementSandboxRequirement.value) return
  await openRequirementSandbox(requirementSandboxRequirement.value)
}

async function handleCurrentChange(page: number) {
  currentPage.value = page
  await fetchRequirements()
}

async function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  await fetchRequirements()
}

async function handleFilterChange() {
  currentPage.value = 1
  await fetchRequirements()
}

async function handleFilterReset() {
  filters.value.project_id = undefined
  filters.value.owner_user_id = undefined
  filters.value.priority = undefined
  filters.value.status = undefined
  filters.value.keyword = ''
  filters.value.due_date_range = null
  currentPage.value = 1
  await fetchRequirements()
}

async function handleQuickPriority(priority?: RequirementItem['priority']) {
  filters.value.priority = priority
  currentPage.value = 1
  await fetchRequirements()
}

function parseRouteProjectId(value: unknown): number | undefined {
  if (typeof value !== 'string' || value.trim() === '') return undefined
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed <= 0) return undefined
  return parsed
}

function syncProjectFilterFromRouteQuery(): void {
  const routeProjectId = parseRouteProjectId(route.query.project_id)
  filters.value.project_id = routeProjectId
  if (formMode.value === 'create') {
    // 新建表单默认归属到当前项目，减少重复选择
    form.value.project_id = routeProjectId
  }
}

watch(
  () => route.query.project_id,
  async (nextValue, prevValue) => {
    if (nextValue === prevValue) return
    syncProjectFilterFromRouteQuery()
    currentPage.value = 1
    await fetchRequirements()
  },
)

onMounted(async () => {
  try {
    syncProjectFilterFromRouteQuery()
    window.addEventListener('resize', handleWindowResize)
    await Promise.all([fetchProjects(), fetchWorkflows(), fetchOwnerOptions(), fetchRequirements()])
    await nextTick()
    await recalcAdaptivePageSize({ forceReset: true })
  } catch (_error) {
    // 请求层已统一弹错，这里阻止未捕获异常打断页面渲染
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleWindowResize)
  if (paginationResizeTimer !== null) {
    window.clearTimeout(paginationResizeTimer)
  }
})

watch(nodeAssetDialogVisible, (visible) => {
  if (visible) return
  nodeAssetSyncPolling.stop()
})

const nodeAssetSyncPolling = useAssetSyncPolling({
  assets: currentNodeAssets,
  isVisible: nodeAssetDialogVisible,
  refresh: refreshNodeAssets,
  onSettled: (failedCount) => {
    if (failedCount > 0) {
      ElMessage.warning(`节点资料后台同步结束：${failedCount} 条失败`)
      return
    }
    ElMessage.success('节点资料后台同步完成')
  },
})

function getNodeAssetSyncLabel(asset: AssetItem): string {
  return getAssetSyncLabel(asset.refetch_status)
}

function getNodeAssetSyncTagType(asset: AssetItem): 'info' | 'warning' | 'danger' {
  return getAssetSyncTagType(asset.refetch_status)
}
</script>

<template>
  <div class="requirement-page">
    <section class="hero">
      <div class="hero-content">
        <h1>需求池</h1>
        <p class="hero-desc">在一个视图内完成需求创建、优先级筛选和状态追踪，减少跨页面切换成本。</p>
      </div>
    </section>

    <section class="stat-grid">
      <el-card shadow="never" class="stat-card">
        <div class="stat-icon stat-icon--blue">
          <el-icon><Tickets /></el-icon>
        </div>
        <div>
          <div class="stat-label">需求总数</div>
          <div class="stat-value">{{ stats.total }}</div>
        </div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-icon stat-icon--orange">
          <el-icon><Loading /></el-icon>
        </div>
        <div>
          <div class="stat-label">进行中</div>
          <div class="stat-value">{{ stats.inProgress }}</div>
        </div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-icon stat-icon--green">
          <el-icon><CircleCheck /></el-icon>
        </div>
        <div>
          <div class="stat-label">已完成</div>
          <div class="stat-value">{{ stats.completed }}</div>
        </div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-icon stat-icon--red">
          <el-icon><Warning /></el-icon>
        </div>
        <div>
          <div class="stat-label">高优需求</div>
          <div class="stat-value">{{ stats.urgent }}</div>
        </div>
      </el-card>
    </section>

    <section class="content-grid" :class="{ 'content-grid--form-expanded': formPanelExpanded }">
      <el-card class="panel-card list-card" shadow="never">
        <template #header>
          <div class="card-header card-header--space-between">
            <div>
              <h3>需求池列表</h3>
              <p>按项目、优先级、状态、关键词组合筛选</p>
            </div>
          </div>
        </template>

        <div class="filters">
          <el-select v-model="filters.project_id" class="filters__project" clearable placeholder="项目" @change="handleFilterChange">
            <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
          <el-input
            v-model="filters.keyword"
            clearable
            placeholder="搜索需求标题"
            @keyup.enter="handleFilterChange"
            @clear="handleFilterChange"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-select
            v-model="filters.owner_user_id"
            class="filters__owner"
            clearable
            filterable
            remote
            reserve-keyword
            placeholder="负责人"
            :remote-method="fetchOwnerOptions"
            :loading="ownerOptionsLoading"
            @change="handleFilterChange"
            @visible-change="(visible: boolean) => visible && fetchOwnerOptions()"
          >
            <el-option
              v-for="u in ownerOptions"
              :key="u.id"
              :label="`${u.display_name} (${u.username})`"
              :value="u.id"
            />
          </el-select>
          <el-select v-model="filters.status" clearable placeholder="状态" @change="handleFilterChange">
            <el-option label="未开始" value="NOT_STARTED" />
            <el-option label="进行中" value="IN_PROGRESS" />
            <el-option label="已完成" value="COMPLETED" />
            <el-option label="已取消" value="CANCELED" />
          </el-select>
          <div class="filter-group filter-group--meta">
            <el-date-picker
              v-model="filters.due_date_range"
              type="daterange"
              value-format="YYYY-MM-DD"
              start-placeholder="截止日期开始"
              end-placeholder="截止日期结束"
              clearable
              class="filters__due-range"
              @change="handleFilterChange"
            />
            <div class="quick-priority quick-priority--inline">
              <span class="quick-priority__label">优先级</span>
              <el-button size="small" :type="filters.priority ? undefined : 'primary'" :plain="Boolean(filters.priority)" @click="handleQuickPriority(undefined)">
                全部
              </el-button>
              <el-button
                size="small"
                type="danger"
                :plain="filters.priority !== 'P0'"
                @click="handleQuickPriority('P0')"
              >
                P0
              </el-button>
              <el-button
                size="small"
                type="warning"
                :plain="filters.priority !== 'P1'"
                @click="handleQuickPriority('P1')"
              >
                P1
              </el-button>
              <el-button
                size="small"
                type="primary"
                :plain="filters.priority !== 'P2'"
                @click="handleQuickPriority('P2')"
              >
                P2
              </el-button>
              <el-button
                size="small"
                type="success"
                :plain="filters.priority !== 'P3'"
                @click="handleQuickPriority('P3')"
              >
                P3
              </el-button>
            </div>
          </div>
          <div class="filter-group filter-group--actions">
            <el-button type="primary" @click="handleFilterChange">查询</el-button>
            <el-button @click="handleFilterReset">重置</el-button>
            <el-button class="filters__create-btn" type="success" plain :disabled="!canEdit" @click="handleOpenCreateForm">新建需求</el-button>
          </div>
        </div>

        <div class="table-scroll-wrap">
          <el-table ref="tableRef" v-loading="loading" :data="items" row-key="id">
            <el-table-column prop="id" label="ID" width="56" align="center" header-align="center" />
            <el-table-column label="归属项目" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                {{ projectNameById(row.project_id) }}
              </template>
            </el-table-column>
            <el-table-column prop="title" label="需求标题" min-width="260" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip :content="row.description || '暂无需求说明'" placement="top-start">
                  <span>{{ row.title }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="需求状态" width="108">
              <template #default="{ row }">
                <el-dropdown
                  class="requirement-status-trigger"
                  trigger="click"
                  :disabled="!canEdit || updatingRequirementStatusId === row.id"
                  @command="handleRequirementStatusDropdownCommand(row, $event)"
                >
                  <el-tag :type="getStatusTagType(row.status)" :class="getRequirementStatusTagClass(row.status)" effect="light">
                    {{ getStatusLabel(row.status) }}
                  </el-tag>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="status in editableRequirementStatuses"
                        :key="`${row.id}-${status}`"
                        :command="status"
                      >
                        {{ getStatusLabel(status) }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
            <el-table-column label="负责人" width="120" show-overflow-tooltip>
              <template #default="{ row }">
                <el-dropdown
                  class="requirement-owner-trigger"
                  trigger="click"
                  :disabled="!canEdit || updatingRequirementOwnerId === row.id"
                  @visible-change="(visible: boolean) => visible && fetchOwnerOptions()"
                  @command="handleRequirementOwnerDropdownCommand(row, $event)"
                >
                  <div class="owner-tag-group">
                    <el-tag effect="light" type="primary">{{ row.owner_name || `用户#${row.owner_user_id}` }}</el-tag>
                  </div>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="u in ownerOptions"
                        :key="`${row.id}-${u.id}`"
                        :command="u.id"
                      >
                        <span class="owner-dropdown-option">
                          <span>{{ u.display_name }}</span>
                          <span>{{ row.owner_user_id === u.id ? '已选' : '' }}</span>
                        </span>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
            <el-table-column label="流程节点" min-width="600" header-class-name="node-column-header">
              <template #default="{ row }">
                <div v-if="row.workflow_nodes?.length" class="node-flow-wrap">
                  <div
                    v-for="(node, idx) in row.workflow_nodes"
                    :key="`${row.id}-${node.node_code}`"
                    class="node-flow-item"
                    :data-node-status="node.status"
                  >
                    <el-dropdown
                      class="node-status-trigger"
                      trigger="click"
                      :disabled="!canEdit || !row.workflow_definition_id"
                      @command="handleNodeStatusDropdownCommand(row, node, $event)"
                    >
                      <button class="node-status-badge" :class="{ 'node-status-badge--focus': isPrimaryAttentionNode(row, idx) }" type="button">
                        <span class="node-light" :class="getNodeLightClass(node.status)" />
                        <span class="node-status-text">{{ getStatusLabel(node.status) }}</span>
                      </button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item
                            v-for="status in editableNodeStatuses"
                            :key="`${row.id}-${node.node_code}-${status}`"
                            :command="status"
                          >
                            {{ getStatusLabel(status) }}
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                    <div class="node-flow-name">{{ node.node_name }}</div>
                    <div class="node-action-row">
                      <el-button
                        text
                        type="primary"
                        class="node-asset-btn"
                        @click="handleOpenNodeAssets(row, node)"
                      >
                        资料
                      </el-button>
                      <el-button
                        text
                        type="primary"
                        class="node-asset-btn"
                        @click="handleOpenNodeConversations(row, node)"
                      >
                        会话
                      </el-button>
                    </div>
                    <span v-if="idx < row.workflow_nodes.length - 1" class="node-flow-link" />
                  </div>
                </div>
                <el-text v-else type="info">未绑定流程节点</el-text>
              </template>
            </el-table-column>
            <el-table-column label="优先级" width="106">
              <template #default="{ row }">
                <el-dropdown
                  class="requirement-priority-trigger"
                  trigger="click"
                  :disabled="!canEdit || updatingRequirementPriorityId === row.id"
                  @command="handleRequirementPriorityDropdownCommand(row, $event)"
                >
                  <el-tag :type="getPriorityTagType(row.priority as RequirementItem['priority'])" effect="light">
                    {{ row.priority }}
                  </el-tag>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="priority in editablePriorities"
                        :key="`${row.id}-${priority}`"
                        :command="priority"
                      >
                        {{ priority }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
            <el-table-column prop="due_date" label="截止日期" width="160">
              <template #default="{ row }">
                {{ row.due_date || '-' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="230" fixed="right">
              <template #default="{ row }">
                <el-button class="action-link-btn" type="primary" link @click="openRequirementSandbox(row)">文件沙箱</el-button>
                <el-button class="action-link-btn" type="primary" link :disabled="!canEdit" @click="handleEditRequirement(row)">编辑</el-button>
                <el-button class="action-link-btn" type="danger" link :disabled="!canEdit" @click="handleDeleteRequirement(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty
                :description="hasActiveFilters ? '当前筛选条件下无结果，请调整筛选项' : '暂无需求，可在右侧表单创建一条需求'"
              />
            </template>
          </el-table>
        </div>

        <div v-if="total > pageSize" class="pagination-wrap">
          <ElegantPagination
            :current-page="currentPage"
            :page-size="pageSize"
            :page-sizes="pageSizeOptions"
            :hide-when-single-page="true"
            layout="total, sizes, prev, pager, next, jumper"
            :total="total"
            @update:current-page="currentPage = $event"
            @update:page-size="pageSize = $event"
            @current-change="handleCurrentChange"
            @size-change="handleSizeChange"
          />
        </div>
      </el-card>

      <transition name="form-panel-slide">
        <el-card v-if="formPanelExpanded" class="panel-card create-card" shadow="never">
        <template #header>
          <div class="card-header card-header--space-between">
            <div>
              <h3>{{ formMode === 'edit' ? '编辑需求' : '创建需求' }}</h3>
              <p>{{ formMode === 'edit' ? '复用同一表单修改需求信息' : '创建后自动进入对应流程实例' }}</p>
            </div>
            <div class="create-header-actions">
              <el-button v-if="formMode === 'edit'" text type="primary" @click="resetForm">取消编辑</el-button>
              <el-button text type="primary" @click="formPanelExpanded = false">收起</el-button>
            </div>
          </div>
        </template>

        <el-form label-position="top" class="create-form">
          <el-form-item label="归属项目（必填）" required>
            <el-select v-model="form.project_id" placeholder="选择项目" :disabled="!canEdit || formMode === 'edit'">
              <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
            </el-select>
          </el-form-item>

          <el-form-item label="需求标题（必填）" required>
            <el-input v-model="form.title" placeholder="例如：支持技能版本比对" :disabled="!canEdit" />
          </el-form-item>

          <el-form-item label="优先级">
            <el-radio-group v-model="form.priority" :disabled="!canEdit" class="priority-group">
              <el-radio-button label="P0">P0</el-radio-button>
              <el-radio-button label="P1">P1</el-radio-button>
              <el-radio-button label="P2">P2</el-radio-button>
              <el-radio-button label="P3">P3</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="需求流程（必填）" required>
            <el-select v-model="form.workflow_definition_id" placeholder="选择流程" :disabled="!canEdit">
              <el-option
                v-for="wf in workflows"
                :key="wf.id"
                :label="`${wf.name} (v${wf.published_version_no})`"
                :value="wf.id"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="截止日期">
            <el-date-picker
              v-model="form.due_date"
              type="date"
              value-format="YYYY-MM-DD"
              format="YYYY-MM-DD"
              clearable
              placeholder="选择截止日期"
              style="width: 100%"
              :disabled="!canEdit"
            />
          </el-form-item>

          <el-form-item label="需求说明">
            <el-input
              v-model="form.description"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 6 }"
              placeholder="补充业务背景、验收标准或关键约束"
              :disabled="!canEdit"
            />
          </el-form-item>

          <el-button type="primary" class="create-btn" :loading="creating" :disabled="!canEdit" @click="handleCreate">
            {{ formMode === 'edit' ? '保存修改' : '创建需求' }}
          </el-button>
        </el-form>
        </el-card>
      </transition>
    </section>

    <el-dialog
      v-model="nodeAssetDialogVisible"
      class="node-asset-dialog"
      title=""
      width="880px"
      :show-close="false"
    >
      <div v-loading="nodeAssetLoading">
        <div class="node-conversation__header node-asset-dialog__header">
          <div>
            <div class="node-conversation__badge">节点资料管理</div>
            <h3 class="node-conversation__title">{{ currentNodeAsset?.node_name || '未命名节点' }}</h3>
            <p class="node-conversation__desc">上传、维护并管理当前节点的资料文件与内容。</p>
          </div>
        </div>

        <AssetUploadEditor
          :show-hero="false"
          :asset-type="nodeAssetForm.asset_type"
          :title="nodeAssetForm.title"
          :source-url="nodeAssetForm.source_url"
          :content="nodeAssetForm.content"
          :files="nodeAssetForm.files"
          :type-options="nodeAssetTypeOptions"
          :url-types="['URL']"
          upload-hint="支持常见文档格式，上传后将挂载到该节点资料"
          @update:asset-type="(value) => (nodeAssetForm.asset_type = value as typeof nodeAssetForm.asset_type)"
          @update:title="(value) => (nodeAssetForm.title = value)"
          @update:source-url="(value) => (nodeAssetForm.source_url = value)"
          @update:content="(value) => (nodeAssetForm.content = value)"
          @files-change="handleNodeFilesChange"
          @file-clear="() => (nodeAssetForm.files = [])"
        >
          <template #actions>
            <el-button @click="nodeAssetDialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="nodeAssetSubmitting" @click="handleSubmitNodeAsset">保存</el-button>
          </template>
        </AssetUploadEditor>

        <section class="node-asset-history">
          <div class="node-asset-history__head">
            <div class="node-asset-history__title-wrap">
              <h4 class="node-asset-history__title">已上传资料</h4>
              <span class="node-asset-history__count">{{ currentNodeAssets.length }} 条</span>
            </div>
          </div>
          <div v-if="currentNodeAssets.length" class="node-asset-history__list">
            <article
              v-for="asset in currentNodeAssets"
              :key="asset.id"
              class="node-asset-card"
            >
              <div class="node-asset-card__content">
                <div class="node-asset-card__meta">
                  <el-tag size="small" effect="plain">{{ getNodeAssetTypeLabel(asset.asset_type) }}</el-tag>
                  <el-tag
                    v-if="getNodeAssetSyncLabel(asset)"
                    size="small"
                    :type="getNodeAssetSyncTagType(asset)"
                    effect="light"
                  >
                    {{ getNodeAssetSyncLabel(asset) }}
                  </el-tag>
                </div>
                <div class="node-asset-card__name">{{ asset.title || `资料 #${asset.id}` }}</div>
                <div class="node-asset-card__summary" :title="getNodeAssetSummary(asset)">
                  {{ getNodeAssetSummary(asset) }}
                </div>
                <div class="node-asset-card__time">{{ formatNodeAssetTime(asset.created_at) }}</div>
              </div>
              <div class="node-asset-card__side">
                <div class="node-asset-card__actions">
                  <el-button class="node-asset-card__action-btn" link size="small" type="primary" @click="handlePreviewNodeAsset(asset)">预览</el-button>
                  <el-button
                    v-if="shouldShowNodeAssetRefetch(asset)"
                    class="node-asset-card__action-btn"
                    link
                    size="small"
                    type="warning"
                    :loading="nodeAssetRefetchingId === asset.id"
                    @click="handleRefetchNodeAsset(asset)"
                  >
                    重抓
                  </el-button>
                  <el-button
                    v-if="shouldShowNodeAssetDownload(asset)"
                    class="node-asset-card__action-btn"
                    link
                    size="small"
                    type="primary"
                    @click="handleDownloadNodeAsset(asset)"
                  >
                    下载
                  </el-button>
                  <el-button class="node-asset-card__action-btn" link size="small" type="danger" @click="handleDeleteNodeAsset(asset)">删除</el-button>
                </div>
              </div>
            </article>
          </div>
          <el-empty v-else description="当前节点暂无已上传资料" :image-size="88" />
        </section>
      </div>
    </el-dialog>

    <UnifiedFilePreviewDialog
      v-model="nodeAssetPreview.visible.value"
      :loading="nodeAssetPreview.loading.value"
      :title="nodeAssetPreview.title.value"
      :file-type="nodeAssetPreview.fileType.value"
      :file-size="nodeAssetPreview.fileSize.value"
      :mode="nodeAssetPreview.mode.value"
      :can-edit="nodeAssetPreview.canEdit.value"
      :saving="nodeAssetPreview.saving.value"
      :can-download="nodeAssetPreview.canDownload.value"
      :content="nodeAssetPreview.content.value"
      :preview-notice="nodeAssetPreview.previewNotice.value"
      :preview-url="nodeAssetPreview.previewUrl.value"
      :sheets="nodeAssetPreview.sheets.value"
      :active-sheet-name="nodeAssetPreview.activeSheetName.value"
      @update:active-sheet-name="(name) => (nodeAssetPreview.activeSheetName.value = name)"
      @open-external="nodeAssetPreview.openCurrentInNewWindow"
      @download="nodeAssetPreview.downloadCurrent"
      @save-edit="nodeAssetPreview.saveMarkdownEdit"
    />

    <el-dialog
      v-model="nodeConversationDialogVisible"
      title=""
      width="1120px"
      class="node-conversation-dialog"
      :show-close="false"
    >
      <div v-loading="nodeConversationLoading" class="node-conversation">
        <div class="node-conversation__header">
          <div>
            <div class="node-conversation__badge">节点会话管理</div>
            <h3 class="node-conversation__title">{{ currentNodeConversationNode?.node_name || '未命名节点' }}</h3>
            <p class="node-conversation__desc">搜索历史会话或创建新会话并快速绑定到当前节点。</p>
          </div>
        </div>

        <section class="node-conversation__panel">
          <div class="node-conversation__panel-head">
            <div class="node-conversation__panel-title-wrap">
              <h4 class="node-conversation__panel-title">搜索并绑定会话</h4>
              <span class="node-conversation__panel-meta">{{ nodeConversationSearchResults.length }} 条候选</span>
            </div>
          </div>
          <div class="node-conversation__toolbar">
            <el-input
              v-model="nodeConversationSearchKeyword"
              placeholder="输入关键词搜索会话（留空显示最近会话）"
              @keyup.enter="searchConversationOptions"
            />
            <el-button :loading="nodeConversationSearching" class="node-conversation__secondary-btn" @click="searchConversationOptions">搜索</el-button>
            <el-button
              type="primary"
              class="node-conversation__primary-btn"
              :loading="nodeConversationCreating"
              :disabled="!canEdit"
              @click="handleCreateAndBindConversation"
            >
              发起并绑定会话
            </el-button>
          </div>
          <el-table :data="nodeConversationSearchResults" max-height="220" stripe>
            <el-table-column prop="conversation_id" label="会话ID" width="90" />
            <el-table-column prop="title" label="会话标题" min-width="220" show-overflow-tooltip />
            <el-table-column prop="skill_name" label="技能" width="180" />
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  class="node-conversation__table-action"
                  :disabled="nodeConversationBinding || !canEdit"
                  @click="handleBindConversationToNode(row.conversation_id)"
                >
                  绑定
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>

        <section class="node-conversation__panel">
          <div class="node-conversation__panel-head">
            <div class="node-conversation__panel-title-wrap">
              <h4 class="node-conversation__panel-title">已绑定会话</h4>
              <span class="node-conversation__panel-meta">{{ currentNodeConversationItems.length }} 条</span>
            </div>
          </div>
          <el-table :data="currentNodeConversationItems" max-height="280" stripe>
            <el-table-column prop="conversation_id" label="会话ID" width="90" />
            <el-table-column prop="title" label="会话标题" min-width="220" show-overflow-tooltip />
            <el-table-column prop="skill_name" label="技能" width="180" />
            <el-table-column prop="binding_type" label="绑定方式" width="110" />
            <el-table-column prop="created_at" label="绑定时间" width="180" />
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button
                  v-if="row.can_view"
                  link
                  type="primary"
                  class="node-conversation__table-action"
                  @click="handleOpenConversationDetail(row.conversation_id)"
                >
                  查看对话
                </el-button>
                <el-button
                  link
                  type="danger"
                  class="node-conversation__table-action node-conversation__table-action--danger"
                  :disabled="!canEdit"
                  @click="handleUnbindConversationFromNode(row.conversation_id)"
                >
                  解绑
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>

        <div class="node-conversation__footer">
          <el-button class="node-conversation__close-btn" @click="nodeConversationDialogVisible = false">关闭</el-button>
        </div>
      </div>
    </el-dialog>

    <RequirementFileSandboxDrawer
      v-model="requirementSandboxVisible"
      :loading="requirementSandboxLoading"
      :requirement-id="requirementSandboxRequirement?.id ?? null"
      :requirement-title="requirementSandboxRequirement?.title || '需求文件沙箱'"
      :sandbox-view="requirementSandboxView"
      @refresh="refreshRequirementSandbox"
    />

  </div>
</template>

<style scoped>
.requirement-page {
  --accent-primary: #2563eb;
  --surface-bg: #eff6ff;

  display: flex;
  flex-direction: column;
  gap: 18px;
  font-family: var(--app-font-sans);
}

.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px;
  border-radius: 18px;
  background: #f6f9fd;
  border: 1px solid #d3e2e5;
  box-shadow: 0 8px 22px rgb(71 85 105 / 10%);
}

.hero-kicker {
  margin-bottom: 8px;
  color: #4d6577;
  letter-spacing: 0.08em;
  font-size: 12px;
  text-transform: uppercase;
  font-weight: 700;
}

.hero h1 {
  margin: 0;
  color: #23384b;
  font-size: 30px;
  line-height: 1.2;
}

.hero-desc {
  margin-top: 10px;
  max-width: 640px;
  color: #5f7486;
  line-height: 1.65;
  font-size: 14px;
}

.hero-meta {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-meta span {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgb(255 255 255 / 76%);
  border: 1px solid #d7e4e8;
  color: #536a7b;
  font-size: 12px;
  font-weight: 500;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stat-card {
  border-radius: 14px;
  border: 1px solid #dbeafe;
  transition: transform 220ms ease-out, box-shadow 220ms ease-out;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgb(30 64 175 / 12%);
}

.stat-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.stat-icon {
  display: inline-flex;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.stat-icon--blue {
  color: #1d4ed8;
  background: #dbeafe;
}

.stat-icon--orange {
  color: #c2410c;
  background: #ffedd5;
}

.stat-icon--green {
  color: #047857;
  background: #d1fae5;
}

.stat-icon--red {
  color: #b91c1c;
  background: #fee2e2;
}

.stat-label {
  color: #64748b;
  font-size: 13px;
}

.stat-value {
  margin-top: 3px;
  font-size: 24px;
  color: #0f172a;
  font-weight: 700;
}

.content-grid {
  --form-panel-max-width: 370px;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  position: relative;
  align-items: start;
  transition: grid-template-columns 280ms cubic-bezier(0.22, 0.61, 0.36, 1);
}

.content-grid--form-expanded {
  grid-template-columns: minmax(0, 1fr) minmax(300px, 370px);
}

.panel-card {
  border-radius: 16px;
  border: 1px solid #dbeafe;
  box-shadow: 0 6px 20px rgb(15 23 42 / 5%);
}

.card-header {
  display: flex;
  align-items: center;
}

.card-header--space-between {
  justify-content: space-between;
}

.create-header-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.form-panel-slide-enter-active,
.form-panel-slide-leave-active {
  transition: opacity 220ms ease, transform 280ms cubic-bezier(0.22, 0.61, 0.36, 1);
  transform-origin: top right;
}

.form-panel-slide-leave-active {
  position: absolute;
  top: 0;
  right: 0;
  width: min(100%, var(--form-panel-max-width));
  pointer-events: none;
}

.form-panel-slide-enter-from,
.form-panel-slide-leave-to {
  opacity: 0;
  transform: translateX(20px) scale(0.98);
}

.card-header h3 {
  margin: 0;
  color: #1e293b;
  font-size: 18px;
}

.card-header p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}

.create-form {
  display: grid;
  gap: 8px;
}

.create-form :deep(.el-form-item) {
  margin-bottom: 8px;
}

.priority-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.create-btn {
  width: 100%;
  min-height: 44px;
  margin-top: 4px;
  font-weight: 600;
}

.quick-priority {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0;
}

.quick-priority__label {
  color: #64748b;
  font-size: 13px;
  margin-right: 12px;
}

.quick-priority :deep(.el-button + .el-button) {
  margin-left: 4px;
}

.filters {
  display: grid;
  grid-template-columns: 0.5fr 1fr auto 140px auto auto;
  gap: 10px;
  margin-bottom: 12px;
}

.filters__project {
  min-width: 0;
}

.filters__owner {
  width: 180px;
}

.filters__due-range {
  width: 250px;
}

.quick-priority--inline {
  min-width: max-content;
}

.filter-group {
  display: inline-flex;
  align-items: center;
}

.filter-group--meta {
  gap: 12px;
  margin-right: 16px;
}

.filter-group--actions {
  gap: 6px;
  white-space: nowrap;
}

.filters__create-btn {
  margin-left: 10px;
}

.table-scroll-wrap {
  overflow-x: visible;
}

.table-scroll-wrap :deep(.el-table) {
  min-width: 100%;
}

.requirement-status-trigger {
  display: inline-flex;
  cursor: pointer;
}

:deep(.status-tag--canceled.el-tag) {
  --el-tag-text-color: #9f8f80;
  --el-tag-bg-color: #faf7f4;
  --el-tag-border-color: #e8ddd3;
}

.requirement-priority-trigger {
  display: inline-flex;
  cursor: pointer;
}

.requirement-owner-trigger {
  display: inline-flex;
  cursor: pointer;
}

.action-link-btn {
  padding: 0 6px;
}

.action-link-btn:hover,
.action-link-btn:focus-visible {
  background: transparent;
  box-shadow: none;
}

:deep(.action-link-btn.el-button.is-link:hover),
:deep(.action-link-btn.el-button.is-link:focus-visible) {
  background: transparent !important;
  box-shadow: none !important;
  color: var(--el-button-text-color) !important;
}

.owner-tag-group {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.owner-tag-group :deep(.el-tag) {
  border-radius: 999px;
}

.owner-dropdown-option {
  width: 150px;
  display: inline-flex;
  justify-content: space-between;
}

:deep(.node-column-header .cell) {
  padding-left: 24px;
}

.node-flow-wrap {
  display: flex;
  align-items: stretch;
  overflow-x: auto;
  gap: 4px;
  padding: 2px 0 6px;
}

.node-flow-item {
  --node-label-center-y: calc(4px + 20px + (44px / 2));
  position: relative;
  flex: 0 0 auto;
  display: grid;
  grid-template-areas:
    'status'
    'name'
    'actions';
  grid-template-rows: 20px 44px 16px;
  justify-items: center;
  align-items: center;
  min-width: 124px;
  min-height: 88px;
  padding: 4px 18px 2px 0;
}

.node-status-trigger {
  grid-area: status;
  display: inline-flex;
  justify-content: center;
  width: 100%;
}

.node-flow-name {
  grid-area: name;
  width: max-content;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0;
  padding: 0 4px;
  font-size: 12px;
  font-weight: 400;
  color: #64748b;
  text-align: center;
  line-height: 1.3;
  white-space: nowrap;
  word-break: normal;
}

.node-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid #dbe6f5;
  border-radius: 999px;
  background: #f8fbff;
  color: #5b6b7c;
  padding: 1px 8px;
  font-size: 10px;
  line-height: 1.4;
  cursor: pointer;
  transition: all 160ms ease;
}

.node-status-badge:hover {
  border-color: #bcd2ee;
  background: #eef5ff;
}

.node-status-badge--focus {
  border-color: #f59e0b;
  background: #fff7e8;
  color: #a16207;
  animation: focus-pulse 1.8s ease-out infinite;
}

.node-status-text {
  font-size: 10px;
}

@keyframes focus-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.35);
  }
  70% {
    box-shadow: 0 0 0 8px rgba(245, 158, 11, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(245, 158, 11, 0);
  }
}

.node-flow-link {
  position: absolute;
  top: var(--node-label-center-y);
  transform: translateY(-50%);
  left: calc(100% - 16px);
  width: 16px;
  height: 1px;
  background: #cbd5e1;
}

.node-asset-btn {
  margin: 0;
  font-size: 10px;
  line-height: 1.2;
  min-height: auto !important;
  height: auto !important;
  padding: 0 2px;
  border-radius: 2px;
  color: #3b82f6 !important;
  background: transparent !important;
  box-shadow: none !important;
  transform: none !important;
}

.node-action-row {
  grid-area: actions;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

:deep(.node-asset-btn:hover),
:deep(.node-asset-btn:focus),
:deep(.node-asset-btn:active),
:deep(.node-asset-btn.is-text:hover),
:deep(.node-asset-btn.is-text:focus),
:deep(.node-asset-btn.is-text:active) {
  background: transparent !important;
  color: #2563eb !important;
  text-decoration: underline;
  text-underline-offset: 2px;
  box-shadow: none !important;
  transform: none !important;
}

.node-light {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  box-shadow: 0 0 0 1px rgb(15 23 42 / 10%);
}

.node-light--not_started,
.node-light--pending {
  background: #94a3b8;
}

.node-light--running,
.node-light--in_progress {
  background: #f59e0b;
}

.node-light--succeeded,
.node-light--completed {
  background: #10b981;
}

.node-light--failed,
.node-light--blocked,
.node-light--canceled {
  background: #ef4444;
}

.node-light--skipped,
.node-light--unbound {
  background: #6366f1;
}

.node-asset-form {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.node-conversation {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.node-conversation__header {
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid #dbeafe;
  background: linear-gradient(120deg, #f8fbff 0%, #eef5ff 100%);
}

.node-conversation__badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.node-conversation__title {
  margin: 8px 0 0;
  color: #0f172a;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.3;
}

.node-conversation__desc {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.node-conversation__close-btn {
  min-width: 88px;
}

.node-conversation__footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
}

.node-conversation__panel {
  padding: 14px;
  border-radius: 14px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}

.node-conversation__panel + .node-conversation__panel {
  margin-top: 2px;
}

.node-conversation__panel-head {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  margin-bottom: 10px;
}

.node-conversation__panel-title-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.node-conversation__panel-title {
  margin: 0;
  color: #1e293b;
  font-size: 14px;
  font-weight: 700;
}

.node-conversation__panel-meta {
  color: #64748b;
  font-size: 12px;
}

.node-conversation__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.node-conversation__toolbar :deep(.el-input) {
  flex: 1;
  min-width: 240px;
}

.node-conversation__secondary-btn {
  min-width: 84px;
}

.node-conversation__primary-btn {
  min-width: 136px;
}

.node-conversation__table-action,
.node-conversation__table-action:hover,
.node-conversation__table-action:focus-visible {
  box-shadow: none !important;
  transform: none !important;
}

.node-conversation__table-action--danger,
.node-conversation__table-action--danger:hover {
  color: #dc2626;
}

.node-conversation-dialog :deep(.el-dialog__header) {
  display: none;
}

.node-conversation-dialog :deep(.el-dialog__body) {
  padding-top: 18px;
}

.node-conversation-dialog :deep(.el-table th.el-table__cell) {
  font-weight: 600;
}

.node-asset-dialog :deep(.el-dialog__header) {
  display: none;
}

.node-asset-dialog :deep(.el-dialog__body) {
  padding-top: 18px;
}

.node-asset-dialog__header {
  margin-bottom: 12px;
}

.node-asset-history {
  margin-top: 20px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  background: #f8fafc;
}

.node-asset-history__head {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
}

.node-asset-history__title-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.node-asset-history__title {
  margin: 0;
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
}

.node-asset-history__count {
  color: #64748b;
  font-size: 12px;
}

.node-asset-history__list {
  display: grid;
  gap: 10px;
  max-height: 320px;
  overflow: auto;
  overflow-x: hidden;
  padding-right: 0;
  scrollbar-gutter: stable;
}

.node-asset-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  width: 100%;
  box-sizing: border-box;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
}

.node-asset-card__content {
  flex: 1;
  min-width: 0;
  padding-right: 8px;
}

.node-asset-card__meta {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
}

.node-asset-card__side {
  flex-shrink: 0;
  min-width: 150px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  gap: 6px;
}

.node-asset-card__time {
  margin-top: 6px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
}

.node-asset-card__name {
  margin-top: 8px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.45;
}

.node-asset-card__summary {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-asset-card__actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  width: 100%;
}

:deep(.node-asset-card__action-btn),
:deep(.node-asset-card__action-btn:hover),
:deep(.node-asset-card__action-btn:focus),
:deep(.node-asset-card__action-btn:active),
:deep(.node-asset-card__action-btn.is-link:hover),
:deep(.node-asset-card__action-btn.is-link:focus),
:deep(.node-asset-card__action-btn.is-link:active) {
  background: transparent !important;
  box-shadow: none !important;
  text-decoration: none !important;
  transform: none !important;
}

.node-asset-preview {
  min-height: 220px;
}

.node-asset-preview__pdf {
  width: 100%;
  height: 68vh;
  border: none;
  border-radius: 8px;
  background: #f8fafc;
}

.node-asset-preview__table-wrap {
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  overflow: hidden;
}

.node-asset-preview__markdown {
  max-height: 68vh;
  overflow: auto;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #fff;
  padding: 14px;
}

.node-asset-preview__text {
  margin: 0;
  max-height: 68vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: #334155;
  font-size: 13px;
  line-height: 1.7;
}

.pagination-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
  margin-top: 16px;
}

:deep(.el-table__row:hover > td.el-table__cell) {
  background: #eff6ff !important;
}

:deep(.el-select),
:deep(.el-input) {
  width: 100%;
}

:deep(.el-button),
:deep(.el-select__wrapper),
:deep(.el-input__wrapper) {
  min-height: 40px;
}

:deep(.el-button:not(.el-button--text)) {
  border-radius: 12px;
  transition: transform 180ms ease, box-shadow 220ms ease, background-color 220ms ease;
}

:deep(.el-button:not(.is-disabled):not(.el-button--text):hover) {
  transform: translateY(-1px);
  box-shadow: 0 8px 18px rgb(30 64 175 / 24%);
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper) {
  border-radius: 12px;
}

.create-btn {
  border-radius: 14px;
}

@media (max-width: 1200px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .content-grid {
    grid-template-columns: 1fr;
  }

  .filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .hero {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 640px) {
  .requirement-page {
    gap: 14px;
  }

  .hero {
    padding: 16px;
    border-radius: 14px;
  }

  .hero h1 {
    font-size: 24px;
  }

  .hero-desc {
    font-size: 13px;
  }

  .stat-grid {
    grid-template-columns: 1fr;
  }

  .filters {
    grid-template-columns: 1fr;
  }

  .pagination-wrap {
    flex-direction: column;
    align-items: flex-end;
  }

  .stat-value {
    font-size: 22px;
  }

  .node-conversation__header {
    flex-direction: column;
  }

  .node-conversation__toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>

<style>
html.dark .requirement-page {
  --requirement-dark-surface: #1c2026;
  --requirement-dark-surface-soft: #1c2026;
  --requirement-dark-card: #22262d;
  --requirement-dark-border: rgba(107, 114, 128, 0.22);
  --requirement-dark-border-strong: rgba(148, 163, 184, 0.2);
  --requirement-dark-text: #f8fafc;
  --requirement-dark-muted: #9ca3af;
  --requirement-dark-soft: #cbd5e1;
  color: var(--requirement-dark-text);
  background: #14171b;
  border-radius: 24px;
  padding: 18px;
}

html.dark .requirement-page .hero {
  background: var(--requirement-dark-surface-soft) !important;
  border-color: var(--requirement-dark-border-strong) !important;
  box-shadow: 0 16px 32px rgba(0, 0, 0, 0.22) !important;
}

html.dark .requirement-page .hero-kicker {
  color: #cbd5e1;
}

html.dark .requirement-page .hero h1,
html.dark .requirement-page .card-header h3,
html.dark .requirement-page .stat-value,
html.dark .requirement-page .node-asset-history__title,
html.dark .requirement-page .node-asset-card__name {
  color: var(--requirement-dark-text);
}

html.dark .requirement-page .hero-desc,
html.dark .requirement-page .card-header p,
html.dark .requirement-page .stat-label,
html.dark .requirement-page .quick-priority__label,
html.dark .requirement-page .page-size-inline,
html.dark .requirement-page .node-flow-name,
html.dark .requirement-page .owner-dropdown-option,
html.dark .requirement-page .node-asset-history__count,
html.dark .requirement-page .node-asset-card__summary,
html.dark .requirement-page .node-asset-card__time,
html.dark .requirement-page .el-form-item__label,
html.dark .requirement-page .el-empty__description p {
  color: var(--requirement-dark-muted);
}

html.dark .requirement-page .hero-meta span {
  background: rgba(148, 163, 184, 0.08);
  border-color: rgba(148, 163, 184, 0.12);
  color: var(--requirement-dark-soft);
}

html.dark .requirement-page .panel-card,
html.dark .requirement-page .stat-card,
html.dark .requirement-page .node-asset-history {
  border-color: var(--requirement-dark-border) !important;
  background: var(--requirement-dark-card) !important;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18) !important;
}

html.dark .requirement-page .node-asset-card {
  border-color: rgba(107, 114, 128, 0.22) !important;
  background: #171b21 !important;
  box-shadow: none !important;
}

html.dark .requirement-page .node-asset-card__action-btn,
html.dark .requirement-page .node-asset-card__action-btn:hover,
html.dark .requirement-page .node-asset-card__action-btn:focus-visible,
html.dark .requirement-page .node-asset-card__action-btn:active {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  transform: none !important;
}

html.dark .requirement-page .node-asset-card__action-btn.el-button--primary,
html.dark .requirement-page .node-asset-card__action-btn.el-button--primary:hover {
  color: #60a5fa !important;
}

html.dark .requirement-page .node-asset-card__action-btn.el-button--danger,
html.dark .requirement-page .node-asset-card__action-btn.el-button--danger:hover {
  color: #f87171 !important;
}

html.dark .requirement-page .node-asset-card__action-btn:not(.el-button--primary):not(.el-button--danger),
html.dark .requirement-page .node-asset-card__action-btn:not(.el-button--primary):not(.el-button--danger):hover {
  color: #94a3b8 !important;
}

html.dark .requirement-page .node-status-badge {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.08);
  color: var(--requirement-dark-muted);
}

html.dark .requirement-page .node-status-badge:hover,
html.dark .requirement-page .node-status-badge--focus {
  border-color: rgba(96, 165, 250, 0.22);
  background: rgba(96, 165, 250, 0.08);
  color: var(--requirement-dark-text);
}

html.dark .requirement-page .node-light {
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.18);
}

html.dark .requirement-page .node-flow-link {
  background: rgba(148, 163, 184, 0.22);
}

html.dark .requirement-page .node-asset-btn {
  color: #8dc2ff !important;
}

html.dark .requirement-page .node-asset-btn:hover {
  color: #dbeafe !important;
}

html.dark .requirement-page .el-input__wrapper,
html.dark .requirement-page .el-select__wrapper,
html.dark .requirement-page .el-date-editor.el-input__wrapper,
html.dark .requirement-page .el-textarea__inner {
  background: rgba(17, 24, 39, 0.56) !important;
  box-shadow: 0 0 0 1px rgba(107, 114, 128, 0.2) inset !important;
  border-color: transparent !important;
}

html.dark .requirement-page .el-input__inner,
html.dark .requirement-page .el-textarea__inner,
html.dark .requirement-page .el-select__selected-item,
html.dark .requirement-page .el-range-input {
  color: var(--requirement-dark-text) !important;
}

html.dark .requirement-page .el-input__inner::placeholder,
html.dark .requirement-page .el-textarea__inner::placeholder,
html.dark .requirement-page .el-select__placeholder,
html.dark .requirement-page .el-range-input::placeholder {
  color: var(--requirement-dark-muted) !important;
}

html.dark .requirement-page .el-button:not(.is-text):not(.el-button--text):not(.el-button--primary):not(.el-button--success) {
  border-color: rgba(107, 114, 128, 0.22);
  background: rgba(255, 255, 255, 0.03);
  color: var(--requirement-dark-soft);
  box-shadow: none;
}

html.dark .requirement-page .el-button:not(.is-text):not(.el-button--text):not(.el-button--primary):not(.el-button--success):hover {
  border-color: rgba(96, 165, 250, 0.2);
  background: rgba(96, 165, 250, 0.08);
  color: var(--requirement-dark-text);
}

html.dark .requirement-page .el-button--primary {
  border: none;
  background: #3b82f6;
  color: #fff;
  box-shadow: none;
}

html.dark .requirement-page .el-button--primary:hover {
  background: #60a5fa;
}

html.dark .requirement-page .el-button--success.is-plain {
  border-color: rgba(74, 222, 128, 0.26);
  background: rgba(34, 197, 94, 0.12);
  color: #86efac;
}

html.dark .requirement-page .el-button--success.is-plain:hover {
  border-color: rgba(74, 222, 128, 0.34);
  background: rgba(34, 197, 94, 0.18);
  color: #dcfce7;
}

html.dark .requirement-page .quick-priority .el-button {
  border-color: rgba(107, 114, 128, 0.22);
  background: rgba(255, 255, 255, 0.03);
  color: var(--requirement-dark-soft);
}

html.dark .requirement-page .quick-priority .el-button:hover,
html.dark .requirement-page .quick-priority .el-button.is-active {
  border-color: rgba(96, 165, 250, 0.2);
  background: rgba(96, 165, 250, 0.08);
  color: var(--requirement-dark-text);
}

html.dark .requirement-page .action-link-btn,
html.dark .requirement-page .action-link-btn:hover,
html.dark .requirement-page .action-link-btn:focus-visible {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  transform: none !important;
}

html.dark .requirement-page .node-conversation__header {
  border-color: rgba(96, 165, 250, 0.2);
  background: linear-gradient(120deg, rgba(30, 64, 175, 0.2) 0%, rgba(30, 41, 59, 0.82) 100%);
}

html.dark .requirement-page .node-conversation__badge {
  border-color: rgba(147, 197, 253, 0.3);
  background: rgba(96, 165, 250, 0.16);
  color: #bfdbfe;
}

html.dark .requirement-page .node-conversation__title {
  color: var(--requirement-dark-text);
}

html.dark .requirement-page .node-conversation__desc,
html.dark .requirement-page .node-conversation__panel-meta {
  color: var(--requirement-dark-muted);
}

html.dark .requirement-page .node-conversation__panel {
  border-color: rgba(107, 114, 128, 0.2);
  background: rgba(17, 24, 39, 0.52);
}

html.dark .requirement-page .node-conversation__footer {
  border-top-color: rgba(107, 114, 128, 0.24);
}

html.dark .requirement-page .node-conversation__panel-title {
  color: #e2e8f0;
}

html.dark .requirement-page .node-conversation__panel .el-button,
html.dark .requirement-page .node-conversation__panel .el-button:hover,
html.dark .requirement-page .node-conversation__panel .el-button:focus-visible {
  border-color: transparent !important;
  background: transparent !important;
  box-shadow: none !important;
  transform: none !important;
}

html.dark .requirement-page .node-conversation__panel .el-button {
  color: #93c5fd;
}

html.dark .requirement-page .node-conversation__panel .el-button.is-disabled {
  color: #64748b !important;
}

html.dark .requirement-page .node-conversation__table-action,
html.dark .requirement-page .node-conversation__table-action:hover {
  color: #60a5fa !important;
}

html.dark .requirement-page .node-conversation__table-action--danger,
html.dark .requirement-page .node-conversation__table-action--danger:hover {
  color: #f87171 !important;
}

html.dark .requirement-page .node-conversation__close-btn {
  border-color: rgba(148, 163, 184, 0.24);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

html.dark .requirement-page .node-conversation__close-btn:hover {
  border-color: rgba(96, 165, 250, 0.28);
  background: rgba(96, 165, 250, 0.14);
  color: #eff6ff;
}

html.dark .requirement-page .el-table {
  --el-table-bg-color: rgba(27, 31, 38, 0.82);
  --el-table-tr-bg-color: rgba(27, 31, 38, 0.82);
  --el-table-expanded-cell-bg-color: rgba(27, 31, 38, 0.82);
  --el-table-header-bg-color: rgba(34, 38, 46, 0.96);
  --el-table-row-hover-bg-color: rgba(96, 165, 250, 0.06);
  --el-table-border-color: rgba(107, 114, 128, 0.2);
  --el-table-header-text-color: #cbd5e1;
  --el-table-text-color: #e2e8f0;
}

html.dark .requirement-page .el-table th.el-table__cell {
  background: rgba(34, 38, 46, 0.96);
}

html.dark .requirement-page .el-table__row:hover > td.el-table__cell {
  background: rgba(96, 165, 250, 0.06) !important;
}

html.dark .requirement-page .el-pagination {
  --el-pagination-bg-color: transparent;
  --el-pagination-text-color: #cbd5e1;
  --el-pagination-button-color: #cbd5e1;
  --el-pagination-button-bg-color: rgba(148, 163, 184, 0.08);
  --el-pagination-button-disabled-color: #64748b;
  --el-pagination-button-disabled-bg-color: rgba(15, 23, 42, 0.4);
  --el-pagination-hover-color: #bfdbfe;
}

html.dark .node-asset-dialog .el-dialog {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(30, 34, 42, 0.98) 0%, rgba(21, 24, 30, 1) 100%);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.3);
}

html.dark .requirement-page .node-asset-preview__pdf,
html.dark .requirement-page .node-asset-preview__table-wrap,
html.dark .requirement-page .node-asset-preview__markdown {
  border-color: rgba(148, 163, 184, 0.14);
  background: rgba(17, 24, 39, 0.48);
}

html.dark .requirement-page .node-asset-preview__text {
  color: #dbe5f5;
}
</style>
