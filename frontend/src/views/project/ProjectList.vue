<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { showDangerConfirm } from '@/composables/useDangerConfirm'

import {
  bindProjectWorkflow,
  createProject,
  deleteProject,
  listProjects,
  updateProject,
  updateProjectOwners,
} from '@/api/projects'
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
import { createAsset, deleteAsset, downloadAssetFile, listAssets, refetchAsset, uploadProjectAssetFile } from '@/api/assets'
import { getProjectSandboxView } from '@/api/sandboxViews'
import type { RelatedSandboxView } from '@/api/sandboxViews'
import { getUserList } from '@/api/admin/users'
import { useAuthStore } from '@/stores/auth'
import ProjectFileSandboxDrawer from '@/components/project/ProjectFileSandboxDrawer.vue'
import AssetUploadEditor from '@/components/common/AssetUploadEditor.vue'
import UnifiedFilePreviewDialog from '@/components/common/UnifiedFilePreviewDialog.vue'
import ElegantPagination from '@/components/common/ElegantPagination.vue'
import { useAssetSyncPolling } from '@/composables/useAssetSyncPolling'
import { useFilePreview } from '@/composables/useFilePreview'
import { getAssetSyncLabel, getAssetSyncTagType, isAssetSyncInProgressStatus, isYuqueUrl, normalizeAssetSyncStatus } from '@/utils/assetSync'

interface ProjectItem {
  id: number
  name: string
  level: 'S' | 'A' | 'B' | 'C' | 'DEMAND_SET'
  start_date?: string
  end_date?: string
  metis_url?: string
  workflow_definition_id?: number
  workflow_instance_id?: number
  owner_user_ids: number[]
  workflow_status?: 'UNBOUND' | 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELED'
  workflow_nodes?: WorkflowNodeItem[]
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

interface UserItem {
  id: number
  display_name: string
}

interface UserOptionItem {
  id: number
  username: string
  display_name: string
}

interface WorkflowItem {
  id: number
  name: string
  code: string
  published_version_no: number
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

const authStore = useAuthStore()
const router = useRouter()
const loading = ref(false)
const creating = ref(false)
const updatingProjectLevelId = ref<number | null>(null)
const updatingProjectStatusId = ref<number | null>(null)
const updatingProjectOwnerId = ref<number | null>(null)
const formMode = ref<'create' | 'edit'>('create')
const editingProjectId = ref<number | null>(null)
const formPanelExpanded = ref(false)
const items = ref<ProjectItem[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const autoMinPageSize = ref(20)
const PAGE_SIZE_CANDIDATES = [20, 50, 100]
const tableRef = ref<{ $el?: HTMLElement } | null>(null)
let paginationResizeTimer: number | null = null
const users = ref<UserItem[]>([])
const ownerOptions = ref<UserOptionItem[]>([])
const ownerOptionsLoading = ref(false)
const workflows = ref<WorkflowItem[]>([])
const projectSandboxDialogVisible = ref(false)
const projectSandboxLoading = ref(false)
const currentSandboxProject = ref<ProjectItem | null>(null)
const projectSandboxView = ref<RelatedSandboxView | null>(null)
const nodeAssetDialogVisible = ref(false)
const nodeAssetLoading = ref(false)
const nodeAssetSubmitting = ref(false)
const currentNodeAssetProject = ref<ProjectItem | null>(null)
const currentNodeAsset = ref<WorkflowNodeItem | null>(null)
const currentNodeAssets = ref<AssetItem[]>([])
const nodeAssetPreview = useFilePreview()
const nodeAssetRefetchingId = ref<number | null>(null)
const nodeConversationDialogVisible = ref(false)
const nodeConversationLoading = ref(false)
const nodeConversationSearching = ref(false)
const nodeConversationBinding = ref(false)
const nodeConversationCreating = ref(false)
const currentNodeConversationProject = ref<ProjectItem | null>(null)
const currentNodeConversationNode = ref<WorkflowNodeItem | null>(null)
const currentNodeConversationItems = ref<WorkflowNodeConversationItem[]>([])
const nodeConversationSearchKeyword = ref('')
const nodeConversationSearchResults = ref<ConversationOptionItem[]>([])
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
  keyword: '',
  owner_user_id: undefined as number | undefined,
  workflow_status: undefined as Exclude<ProjectItem['workflow_status'], 'UNBOUND'> | undefined,
  end_date_range: null as [string, string] | null,
  level: undefined as ProjectItem['level'] | undefined,
})

const form = ref({
  name: '',
  level: 'B' as ProjectItem['level'],
  start_date: '',
  end_date: '',
  metis_url: '',
  owner_user_ids: [] as number[],
  workflow_definition_id: undefined as number | undefined,
})

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

const statusTagTypeMap: Record<string, 'info' | 'warning' | 'success' | 'danger' | 'primary'> = {
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
const editableNodeStatuses: Array<WorkflowNodeItem['status']> = [
  'PENDING',
  'RUNNING',
  'SUCCEEDED',
  'SKIPPED',
  'BLOCKED',
  'CANCELED',
]
const editableProjectLevels: Array<ProjectItem['level']> = ['S', 'A', 'B', 'C', 'DEMAND_SET']
const editableProjectStatuses: Array<NonNullable<ProjectItem['workflow_status']>> = [
  'NOT_STARTED',
  'IN_PROGRESS',
  'COMPLETED',
  'CANCELED',
]

const canEdit = computed(() => authStore.user?.role === 'user' || authStore.user?.role === 'admin')
const hasActiveFilters = computed(
  () =>
    Boolean(
      filters.value.keyword.trim()
        || filters.value.owner_user_id
        || filters.value.workflow_status
        || Boolean(filters.value.end_date_range?.length)
        || filters.value.level,
    ),
)

const levelTagTypeMap: Record<ProjectItem['level'], 'danger' | 'warning' | 'primary' | 'success' | 'info'> = {
  S: 'danger',
  A: 'warning',
  B: 'primary',
  C: 'info',
  DEMAND_SET: 'success',
}

const levelLabelMap: Record<ProjectItem['level'], string> = {
  S: 'S 级',
  A: 'A 级',
  B: 'B 级',
  C: 'C 级',
  DEMAND_SET: '需求集',
}

function getLevelTagType(level: ProjectItem['level']) {
  return levelTagTypeMap[level]
}

function getLevelLabel(level: ProjectItem['level']) {
  return levelLabelMap[level]
}

function getUserDisplayName(userId: number) {
  const matchedUser = users.value.find((user) => user.id === userId)
  return matchedUser?.display_name || `用户 #${userId}`
}

function getStatusLabel(status?: string) {
  if (!status) return '-'
  return statusLabelMap[status] || status
}

function getStatusTagType(status?: string) {
  if (!status) return 'info'
  return statusTagTypeMap[status] || 'info'
}

function getProjectStatusTagClass(status?: string) {
  return status === 'CANCELED' ? 'status-tag--canceled' : ''
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

function isPrimaryAttentionNode(row: ProjectItem, index: number): boolean {
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

function resetForm() {
  form.value.name = ''
  form.value.level = 'B'
  form.value.start_date = ''
  form.value.end_date = ''
  form.value.metis_url = ''
  form.value.workflow_definition_id = undefined
  formMode.value = 'create'
  editingProjectId.value = null
  if (authStore.user) {
    form.value.owner_user_ids = [authStore.user.id]
    return
  }
  form.value.owner_user_ids = []
}

const stats = computed(() => {
  const current = items.value
  const demandSetCount = current.filter((item) => item.level === 'DEMAND_SET').length
  const keyProjectCount = current.filter((item) => item.level === 'S' || item.level === 'A').length
  const inProgressCount = current.filter((item) => item.workflow_status === 'IN_PROGRESS').length
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const inOneMonth = new Date(today)
  inOneMonth.setMonth(inOneMonth.getMonth() + 1)
  const expiringInOneMonthCount = current.filter((item) => {
    if (!item.end_date) return false
    if (item.workflow_status === 'COMPLETED' || item.workflow_status === 'CANCELED') return false
    const endDate = new Date(`${item.end_date}T00:00:00`)
    if (Number.isNaN(endDate.getTime())) return false
    return endDate >= today && endDate <= inOneMonth
  }).length
  return {
    total: total.value,
    demandSetCount,
    keyProjectCount,
    inProgressCount,
    expiringInOneMonthCount,
  }
})

async function fetchProjects() {
  if (loading.value) return
  loading.value = true
  try {
    const endDateStart = filters.value.end_date_range?.[0]
    const endDateEnd = filters.value.end_date_range?.[1]
    const res = await listProjects({
      page: currentPage.value,
      page_size: pageSize.value,
      keyword: filters.value.keyword.trim() || undefined,
      owner_user_id: filters.value.owner_user_id,
      workflow_status: filters.value.workflow_status,
      end_date_start: endDateStart,
      end_date_end: endDateEnd,
      level: filters.value.level,
    })
    items.value = (res.data.items as ProjectItem[])
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
  await fetchProjects()
}

function handleWindowResize() {
  if (paginationResizeTimer !== null) {
    window.clearTimeout(paginationResizeTimer)
  }
  paginationResizeTimer = window.setTimeout(() => {
    void recalcAdaptivePageSize()
  }, 120)
}

async function fetchUsers() {
  if (!authStore.user) return
  if (authStore.user.role === 'admin') {
    const res = await getUserList({ page: 1, page_size: 100 })
    users.value = res.data.items.map((item: { id: number; display_name: string }) => ({
      id: item.id,
      display_name: item.display_name,
    }))
    if (form.value.owner_user_ids.length === 0) {
      form.value.owner_user_ids = [authStore.user.id]
    }
  } else {
    users.value = [{ id: authStore.user.id, display_name: authStore.user.display_name }]
    form.value.owner_user_ids = [authStore.user.id]
  }
}

async function fetchWorkflows() {
  const res = await listPublishedWorkflowDefinitions('PROJECT')
  workflows.value = res.data
}

async function fetchOwnerOptions(keyword = '') {
  if (!authStore.user) return
  if (authStore.user.role !== 'admin') {
    ownerOptions.value = [{
      id: authStore.user.id,
      username: authStore.user.username,
      display_name: authStore.user.display_name,
    }]
    return
  }
  if (ownerOptionsLoading.value) return
  ownerOptionsLoading.value = true
  try {
    const res = await getUserList({
      page: 1,
      page_size: 100,
      keyword: keyword.trim() || undefined,
    })
    ownerOptions.value = (res.data.items || []).map((item: { id: number; username: string; display_name: string }) => ({
      id: item.id,
      username: item.username,
      display_name: item.display_name,
    }))
  } finally {
    ownerOptionsLoading.value = false
  }
}

async function handleCreate() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入项目名称')
    return
  }
  if (form.value.owner_user_ids.length === 0) {
    ElMessage.warning('至少选择一个负责人')
    return
  }

  if (form.value.owner_user_ids.length > 2) {
    ElMessage.warning('最多选择 2 位负责人')
    return
  }
  if (form.value.start_date && form.value.end_date && form.value.end_date < form.value.start_date) {
    ElMessage.warning('结束时间不能早于开始时间')
    return
  }

  creating.value = true
  try {
    if (formMode.value === 'edit' && editingProjectId.value) {
      await updateProject(editingProjectId.value, {
        name: form.value.name.trim(),
        level: form.value.level,
        start_date: form.value.start_date || undefined,
        end_date: form.value.end_date || undefined,
        metis_url: form.value.metis_url || undefined,
      })
      await updateProjectOwners(editingProjectId.value, form.value.owner_user_ids)
      if (form.value.workflow_definition_id) {
        await bindProjectWorkflow(editingProjectId.value, form.value.workflow_definition_id)
      }
      ElMessage.success('项目更新成功')
    } else {
      await createProject({
        name: form.value.name.trim(),
        level: form.value.level,
        start_date: form.value.start_date || undefined,
        end_date: form.value.end_date || undefined,
        metis_url: form.value.metis_url || undefined,
        owner_user_ids: form.value.owner_user_ids,
        workflow_definition_id: form.value.workflow_definition_id,
      })
      ElMessage.success('项目创建成功')
    }
    resetForm()
    formPanelExpanded.value = false
    currentPage.value = 1
    await fetchProjects()
  } finally {
    creating.value = false
  }
}

async function handleBindWorkflow(row: ProjectItem, workflowDefinitionId?: number) {
  if (!workflowDefinitionId) return
  await bindProjectWorkflow(row.id, workflowDefinitionId)
  ElMessage.success('流程绑定成功')
  await fetchProjects()
}

async function handleProjectOwnersChange(row: ProjectItem, ownerUserIds: number[]) {
  if (!canEdit.value || updatingProjectOwnerId.value === row.id) {
    return
  }
  if (!ownerUserIds.length) {
    ElMessage.warning('负责人不能为空')
    return
  }
  if (ownerUserIds.length > 2) {
    ElMessage.warning('最多选择 2 位负责人')
    return
  }
  updatingProjectOwnerId.value = row.id
  try {
    await updateProjectOwners(row.id, ownerUserIds)
    row.owner_user_ids = ownerUserIds
    ElMessage.success('负责人更新成功')
  } finally {
    updatingProjectOwnerId.value = null
  }
}

function handleProjectOwnerDropdownCommand(row: ProjectItem, command: string | number | object) {
  const ownerUserId = Number(command)
  if (!Number.isInteger(ownerUserId)) return
  const isSelected = row.owner_user_ids.includes(ownerUserId)
  const nextOwnerUserIds = isSelected
    ? row.owner_user_ids.filter((id) => id !== ownerUserId)
    : [...row.owner_user_ids, ownerUserId]
  handleProjectOwnersChange(row, nextOwnerUserIds)
}

async function handleProjectLevelChange(row: ProjectItem, level: ProjectItem['level']) {
  if (!canEdit.value || updatingProjectLevelId.value === row.id || row.level === level) {
    return
  }
  updatingProjectLevelId.value = row.id
  try {
    await updateProject(row.id, {
      name: row.name.trim(),
      level,
      start_date: row.start_date || undefined,
      end_date: row.end_date || undefined,
      metis_url: row.metis_url || undefined,
    })
    row.level = level
    ElMessage.success('项目等级更新成功')
  } finally {
    updatingProjectLevelId.value = null
  }
}

function handleProjectLevelDropdownCommand(row: ProjectItem, level: string | number | object) {
  handleProjectLevelChange(row, level as ProjectItem['level'])
}

function handleEditProject(row: ProjectItem) {
  formMode.value = 'edit'
  formPanelExpanded.value = true
  editingProjectId.value = row.id
  form.value.name = row.name
  form.value.level = row.level
  form.value.start_date = row.start_date || ''
  form.value.end_date = row.end_date || ''
  form.value.metis_url = row.metis_url || ''
  form.value.owner_user_ids = [...row.owner_user_ids]
  form.value.workflow_definition_id = row.workflow_definition_id
}

function handleOpenCreateForm() {
  if (!canEdit.value) return
  resetForm()
  formPanelExpanded.value = true
}

async function handleDeleteProject(row: ProjectItem) {
  try {
    await showDangerConfirm({
      title: '删除项目',
      subject: row.name,
      detail: '删除后将清理项目关联的流程实例与资料记录，且不可恢复。',
      confirmText: '确认删除',
    })
  } catch {
    return
  }

  await deleteProject(row.id)
  ElMessage.success('项目已删除')
  if (items.value.length === 1 && currentPage.value > 1) {
    currentPage.value -= 1
  }
  await fetchProjects()
}

async function handleNodeStatusChange(
  row: ProjectItem,
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
      ElMessage.warning('请先为项目绑定流程，再维护节点状态')
      return
    }
    await createWorkflowInstance({
      scope_type: 'PROJECT',
      scope_id: row.id,
      workflow_definition_id: row.workflow_definition_id,
    })
    await fetchProjects()
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
  await fetchProjects()
}

async function handleNodeInlineStatusChange(
  row: ProjectItem,
  node: WorkflowNodeItem,
  status: WorkflowNodeItem['status'],
) {
  await handleNodeStatusChange(row, node, status)
}

function handleNodeStatusDropdownCommand(
  row: ProjectItem,
  node: WorkflowNodeItem,
  status: string | number | object,
) {
  handleNodeInlineStatusChange(row, node, status as WorkflowNodeItem['status'])
}

async function ensureRuntimeNode(
  row: ProjectItem,
  node: WorkflowNodeItem,
): Promise<{ instanceId: number; nodeId: number; skillId?: number | null } | null> {
  let instanceId = row.workflow_instance_id
  let runtimeNode = node
  if (!instanceId || !runtimeNode.id) {
    if (!row.workflow_definition_id) {
      ElMessage.warning('请先为项目绑定流程')
      return null
    }
    await createWorkflowInstance({
      scope_type: 'PROJECT',
      scope_id: row.id,
      workflow_definition_id: row.workflow_definition_id,
    })
    await fetchProjects()
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
  if (!currentNodeConversationProject.value || !currentNodeConversationNode.value) return
  const runtime = await ensureRuntimeNode(currentNodeConversationProject.value, currentNodeConversationNode.value)
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
  const row = currentNodeConversationProject.value
  const node = currentNodeConversationNode.value
  if (!row || !node) return
  if (normalizeNodeStatus(node.status) !== 'PENDING') return

  node.status = 'RUNNING'
  const targetNode = row.workflow_nodes?.find((item) => item.node_code === node.node_code)
  if (targetNode && normalizeNodeStatus(targetNode.status) === 'PENDING') {
    targetNode.status = 'RUNNING'
  }
}

async function handleOpenNodeConversations(row: ProjectItem, node: WorkflowNodeItem) {
  currentNodeConversationProject.value = row
  currentNodeConversationNode.value = { ...node }
  nodeConversationDialogVisible.value = true
  nodeConversationSearchKeyword.value = ''
  nodeConversationSearchResults.value = []
  await refreshNodeConversationItems()
  await searchConversationOptions()
}

async function handleBindConversationToNode(conversationId: number) {
  if (!currentNodeConversationProject.value || !currentNodeConversationNode.value) return
  const runtime = await ensureRuntimeNode(currentNodeConversationProject.value, currentNodeConversationNode.value)
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
  if (!currentNodeConversationProject.value || !currentNodeConversationNode.value) return
  const runtime = await ensureRuntimeNode(currentNodeConversationProject.value, currentNodeConversationNode.value)
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
  if (!currentNodeConversationProject.value || !currentNodeConversationNode.value) return
  const runtime = await ensureRuntimeNode(currentNodeConversationProject.value, currentNodeConversationNode.value)
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

function handleProjectStatusChange(row: ProjectItem, targetStatus: NonNullable<ProjectItem['workflow_status']>) {
  if (!canEdit.value || updatingProjectStatusId.value === row.id || row.workflow_status === targetStatus) {
    return
  }
  updatingProjectStatusId.value = row.id
  row.workflow_status = targetStatus
  ElMessage.success('项目状态已更新')
  updatingProjectStatusId.value = null
}

function handleProjectStatusDropdownCommand(row: ProjectItem, targetStatus: string | number | object) {
  handleProjectStatusChange(row, targetStatus as NonNullable<ProjectItem['workflow_status']>)
}

async function handleOpenProjectSandbox(row: ProjectItem) {
  projectSandboxLoading.value = true
  projectSandboxDialogVisible.value = true
  currentSandboxProject.value = row
  projectSandboxView.value = null
  try {
    const res = await getProjectSandboxView(row.id)
    projectSandboxView.value = res.data
  } finally {
    projectSandboxLoading.value = false
  }
}

async function handleRefreshProjectSandbox() {
  if (!currentSandboxProject.value) return
  projectSandboxLoading.value = true
  try {
    const res = await getProjectSandboxView(currentSandboxProject.value.id)
    projectSandboxView.value = res.data
  } finally {
    projectSandboxLoading.value = false
  }
}

function handleGoRequirementPool(row: ProjectItem) {
  router.push({ name: 'RequirementPool', query: { project_id: String(row.id) } })
}

function handleGoRequirementPoolFromDrawer() {
  if (!currentSandboxProject.value) return
  handleGoRequirementPool(currentSandboxProject.value)
}

async function handleOpenNodeAssets(row: ProjectItem, node: WorkflowNodeItem) {
  nodeAssetDialogVisible.value = true
  nodeAssetLoading.value = true
  currentNodeAssetProject.value = row
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
  if (!currentNodeAssetProject.value || !currentNodeAsset.value) return
  const res = await listAssets({
    scope_type: 'PROJECT',
    scope_id: currentNodeAssetProject.value.id,
    node_code: currentNodeAsset.value.node_code,
  })
  currentNodeAssets.value = res.data || []
}

async function handleSubmitNodeAsset() {
  if (!currentNodeAssetProject.value || !currentNodeAsset.value) return
  const projectId = currentNodeAssetProject.value.id
  const nodeCode = currentNodeAsset.value.node_code
  const isUrlAsset = nodeAssetForm.value.asset_type === 'URL'

  nodeAssetSubmitting.value = true
  try {
    if (nodeAssetForm.value.asset_type === 'FILE') {
      const selectedFiles = nodeAssetForm.value.files
      if (!selectedFiles.length) {
        ElMessage.warning('请先选择上传文件')
        return
      }
      for (const file of selectedFiles) {
        await uploadProjectAssetFile(file, projectId, nodeCode, file.name)
      }
    } else {
      if (nodeAssetForm.value.asset_type === 'MARKDOWN') {
        if (!nodeAssetForm.value.content.trim()) {
          ElMessage.warning('请填写 Markdown 内容')
          return
        }
        await createAsset({
          scope_type: 'PROJECT',
          scope_id: projectId,
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
          scope_type: 'PROJECT',
          scope_id: projectId,
          node_code: nodeCode,
          asset_type: nodeAssetForm.value.asset_type,
          title: nodeAssetForm.value.title || undefined,
          source_url: nodeAssetForm.value.source_url.trim(),
        })
        const status = normalizeAssetSyncStatus(res.data?.refetch_status)
        if (isAssetSyncInProgressStatus(status)) {
          ElMessage.info('已提交后台下载，稍后自动更新状态')
          nodeAssetSyncPolling.markTaskSubmitted()
        }
      }
    }

    ElMessage.success(isUrlAsset ? '节点资料已保存，后台正在处理' : '节点资产保存成功')
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

async function handleCurrentChange(page: number) {
  currentPage.value = page
  await fetchProjects()
}

async function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  await fetchProjects()
}

async function handleSearch() {
  currentPage.value = 1
  await fetchProjects()
}

async function handleResetSearch() {
  filters.value.keyword = ''
  filters.value.owner_user_id = undefined
  filters.value.workflow_status = undefined
  filters.value.end_date_range = null
  filters.value.level = undefined
  currentPage.value = 1
  await fetchProjects()
}

onMounted(async () => {
  try {
    window.addEventListener('resize', handleWindowResize)
    await Promise.all([fetchUsers(), fetchOwnerOptions(), fetchWorkflows(), fetchProjects()])
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
  <div class="project-page">
    <section class="hero">
      <div class="hero-content">
        <h1>项目管理</h1>
        <p class="hero-desc">统一维护项目分级、负责人和流程绑定，确保从立项到交付的执行链路可追踪。</p>
      </div>
    </section>

    <section class="stat-grid">
      <el-card shadow="never" class="stat-card">
        <div class="stat-icon stat-icon--blue">
          <el-icon><FolderOpened /></el-icon>
        </div>
        <div>
          <div class="stat-label">项目总数</div>
          <div class="stat-value">{{ stats.total }}</div>
        </div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-icon stat-icon--violet">
          <el-icon><Flag /></el-icon>
        </div>
        <div>
          <div class="stat-label">重点项目 (S/A)</div>
          <div class="stat-value">{{ stats.keyProjectCount }}</div>
        </div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-icon stat-icon--orange">
          <el-icon><Loading /></el-icon>
        </div>
        <div>
          <div class="stat-label">进行中项目</div>
          <div class="stat-value">{{ stats.inProgressCount }}</div>
        </div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-icon stat-icon--rose">
          <el-icon><Calendar /></el-icon>
        </div>
        <div>
          <div class="stat-label">一个月内到期</div>
          <div class="stat-value">{{ stats.expiringInOneMonthCount }}</div>
        </div>
      </el-card>
    </section>

    <section class="content-grid" :class="{ 'content-grid--form-expanded': formPanelExpanded }">
      <el-card class="panel-card list-card" shadow="never">
        <template #header>
          <div class="card-header card-header--space-between">
            <div>
              <h3>项目列表</h3>
              <p>支持负责人、流程与状态在列表内直接维护</p>
            </div>
          </div>
        </template>

        <div class="list-filters">
          <el-input
            v-model="filters.keyword"
            clearable
            placeholder="按项目名称搜索"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-select
            v-model="filters.owner_user_id"
            clearable
            filterable
            remote
            reserve-keyword
            placeholder="负责人"
            :remote-method="fetchOwnerOptions"
            :loading="ownerOptionsLoading"
            @change="handleSearch"
            @visible-change="(visible: boolean) => visible && fetchOwnerOptions()"
          >
            <el-option
              v-for="u in ownerOptions"
              :key="u.id"
              :label="`${u.display_name} (${u.username})`"
              :value="u.id"
            />
          </el-select>
          <el-select v-model="filters.workflow_status" clearable placeholder="项目状态" @change="handleSearch">
            <el-option label="未开始" value="NOT_STARTED" />
            <el-option label="进行中" value="IN_PROGRESS" />
            <el-option label="已完成" value="COMPLETED" />
            <el-option label="已取消" value="CANCELED" />
          </el-select>
          <el-date-picker
            v-model="filters.end_date_range"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="结束日期开始"
            end-placeholder="结束日期结束"
            clearable
            class="filters__end-date-range"
            @change="handleSearch"
          />
          <el-select v-model="filters.level" clearable placeholder="项目等级" @change="handleSearch">
            <el-option label="S 级" value="S" />
            <el-option label="A 级" value="A" />
            <el-option label="B 级" value="B" />
            <el-option label="C 级" value="C" />
            <el-option label="需求集" value="DEMAND_SET" />
          </el-select>
          <div class="filter-group filter-group--actions">
            <el-button type="primary" :disabled="!canEdit" @click="handleSearch">查询</el-button>
            <el-button @click="handleResetSearch">重置</el-button>
            <el-button class="filters__create-btn" type="success" plain :disabled="!canEdit" @click="handleOpenCreateForm">新建项目</el-button>
          </div>
        </div>

        <div class="table-scroll-wrap">
          <el-table ref="tableRef" v-loading="loading" :data="items" row-key="id">
            <el-table-column prop="id" label="ID" width="56" align="center" header-align="center" />
            <el-table-column prop="name" label="项目名称" min-width="180" />
            <el-table-column label="项目等级" width="108">
              <template #default="{ row }">
                <el-dropdown
                  class="project-level-trigger"
                  trigger="click"
                  :disabled="!canEdit || updatingProjectLevelId === row.id"
                  @command="handleProjectLevelDropdownCommand(row, $event)"
                >
                  <el-tag :type="getLevelTagType(row.level as ProjectItem['level'])" effect="light">
                    {{ getLevelLabel(row.level as ProjectItem['level']) }}
                  </el-tag>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="level in editableProjectLevels"
                        :key="`${row.id}-${level}`"
                        :command="level"
                      >
                        {{ getLevelLabel(level) }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
            <el-table-column label="负责人" width="120">
              <template #default="{ row }">
                <el-dropdown
                  class="project-owner-trigger"
                  trigger="click"
                  :hide-on-click="false"
                  :disabled="!canEdit || updatingProjectOwnerId === row.id"
                  @command="handleProjectOwnerDropdownCommand(row, $event)"
                >
                  <div class="owner-tag-group">
                    <el-tag v-for="ownerId in row.owner_user_ids" :key="`${row.id}-${ownerId}`" effect="light" type="primary">
                      {{ getUserDisplayName(ownerId) }}
                    </el-tag>
                    <el-tag v-if="!row.owner_user_ids.length" effect="light" type="primary">未设置</el-tag>
                  </div>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="u in users"
                        :key="`${row.id}-${u.id}`"
                        :command="u.id"
                      >
                        <span class="owner-dropdown-option">
                          <span>{{ u.display_name }}</span>
                          <span>{{ row.owner_user_ids.includes(u.id) ? '已选' : '' }}</span>
                        </span>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
            <el-table-column label="项目状态" width="104">
              <template #default="{ row }">
                <el-dropdown
                  class="project-status-trigger"
                  trigger="click"
                  :disabled="!canEdit || updatingProjectStatusId === row.id"
                  @command="handleProjectStatusDropdownCommand(row, $event)"
                >
                  <el-tag :type="getStatusTagType(row.workflow_status)" :class="getProjectStatusTagClass(row.workflow_status)" effect="light">
                    {{ getStatusLabel(row.workflow_status) }}
                  </el-tag>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="status in editableProjectStatuses"
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
            <el-table-column prop="start_date" label="开始时间" width="118" />
            <el-table-column prop="end_date" label="结束时间" width="118" />
            <el-table-column label="流程节点" min-width="420">
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
            <el-table-column label="操作" width="248" fixed="right">
              <template #default="{ row }">
                <div class="action-inline">
                  <el-button class="action-link-btn" type="primary" link @click="handleOpenProjectSandbox(row)">文件沙箱</el-button>
                  <el-button class="action-link-btn" type="primary" link :disabled="!canEdit" @click="handleEditProject(row)">编辑</el-button>
                  <el-button class="action-link-btn" type="danger" link :disabled="!canEdit" @click="handleDeleteProject(row)">删除</el-button>
                </div>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty
                :description="hasActiveFilters ? '当前筛选条件无结果，请调整筛选项' : '暂无项目，可在右侧表单创建第一个项目'"
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
              <h3>{{ formMode === 'edit' ? '编辑项目' : '新建项目' }}</h3>
              <p>{{ formMode === 'edit' ? '复用同一表单修改项目核心信息' : '填写核心字段并立即进入项目列表管理' }}</p>
            </div>
            <div class="create-header-actions">
              <el-button v-if="formMode === 'edit'" text type="primary" @click="resetForm">取消编辑</el-button>
              <el-button text type="primary" @click="formPanelExpanded = false">收起</el-button>
            </div>
          </div>
        </template>

        <el-form label-position="top" class="create-form">
          <el-form-item label="项目名称（必填）" required>
            <el-input v-model="form.name" placeholder="例如：MCP 能力运营平台" :disabled="!canEdit" />
          </el-form-item>

          <el-form-item label="项目等级">
            <el-radio-group v-model="form.level" :disabled="!canEdit" class="level-group">
              <el-radio-button label="S">S</el-radio-button>
              <el-radio-button label="A">A</el-radio-button>
              <el-radio-button label="B">B</el-radio-button>
              <el-radio-button label="C">C</el-radio-button>
              <el-radio-button label="DEMAND_SET">需求集</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="负责人（必填）" required>
            <el-select
              v-model="form.owner_user_ids"
              multiple
              :multiple-limit="2"
              placeholder="选择负责人"
              :disabled="!canEdit"
            >
              <el-option v-for="u in users" :key="u.id" :label="u.display_name" :value="u.id" />
            </el-select>
          </el-form-item>

          <el-form-item label="项目流程">
            <el-select v-model="form.workflow_definition_id" clearable placeholder="可选" :disabled="!canEdit">
              <el-option
                v-for="wf in workflows"
                :key="wf.id"
                :label="`${wf.name} (v${wf.published_version_no})`"
                :value="wf.id"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="开始时间">
            <el-date-picker
              v-model="form.start_date"
              type="date"
              value-format="YYYY-MM-DD"
              format="YYYY-MM-DD"
              placeholder="选择开始时间"
              style="width: 100%"
              :disabled="!canEdit"
            />
          </el-form-item>

          <el-form-item label="结束时间">
            <el-date-picker
              v-model="form.end_date"
              type="date"
              value-format="YYYY-MM-DD"
              format="YYYY-MM-DD"
              placeholder="选择结束时间"
              style="width: 100%"
              :disabled="!canEdit"
            />
          </el-form-item>

          <el-form-item label="Metis 地址">
            <el-input v-model="form.metis_url" placeholder="https://metis.example.com/project/123" :disabled="!canEdit" />
          </el-form-item>

          <el-button type="primary" class="create-btn" :loading="creating" :disabled="!canEdit" @click="handleCreate">
            {{ formMode === 'edit' ? '保存修改' : '创建项目' }}
          </el-button>
        </el-form>
        </el-card>
      </transition>
    </section>

    <ProjectFileSandboxDrawer
      v-model="projectSandboxDialogVisible"
      :loading="projectSandboxLoading"
      :project-id="currentSandboxProject?.id || null"
      :project-name="currentSandboxProject?.name || ''"
      :sandbox-view="projectSandboxView"
      @go-requirement-pool="handleGoRequirementPoolFromDrawer"
      @refresh="handleRefreshProjectSandbox"
    />

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
  </div>
</template>

<style scoped>
.project-page {
  --accent-primary: #2563eb;
  --accent-secondary: #3b82f6;
  --accent-cta: #f97316;
  --surface-bg: #eff6ff;
  --ink-strong: #1e3a8a;

  display: flex;
  flex-direction: column;
  gap: 18px;
  font-family: var(--app-font-sans);
}

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px;
  border-radius: 18px;
  background: #f6f9fd;
  border: 1px solid #d7e3ef;
  box-shadow: 0 8px 22px rgb(71 85 105 / 10%);
}

.hero-kicker {
  margin-bottom: 8px;
  color: #4c647d;
  letter-spacing: 0.08em;
  font-size: 12px;
  text-transform: uppercase;
  font-weight: 700;
}

.hero h1 {
  margin: 0;
  color: #1f3348;
  font-size: 30px;
  line-height: 1.2;
}

.hero-desc {
  margin-top: 10px;
  max-width: 640px;
  color: #5d7287;
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
  border: 1px solid #d8e3ee;
  color: #52677c;
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

.stat-icon--violet {
  color: #6d28d9;
  background: #ede9fe;
}

.stat-icon--green {
  color: #047857;
  background: #d1fae5;
}

.stat-icon--cyan {
  color: #0f766e;
  background: #ccfbf1;
}

.stat-icon--rose {
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
  --form-panel-max-width: 360px;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  position: relative;
  align-items: start;
  transition: grid-template-columns 280ms cubic-bezier(0.22, 0.61, 0.36, 1);
}

.content-grid--form-expanded {
  grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);
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

.level-group {
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

.table-scroll-wrap {
  overflow-x: visible;
}

.list-filters {
  display: grid;
  grid-template-columns:
    minmax(170px, 1.35fr)
    minmax(130px, 0.95fr)
    minmax(115px, 0.85fr)
    minmax(210px, 1.1fr)
    minmax(110px, 0.8fr)
    auto;
  gap: 10px;
  margin-bottom: 12px;
}

.list-filters > * {
  min-width: 0;
}

.table-scroll-wrap :deep(.el-table) {
  min-width: 100%;
}

.filters__end-date-range {
  width: 100% !important;
  max-width: 100%;
}

:deep(.filters__end-date-range.el-date-editor) {
  min-width: 0;
  width: 100% !important;
}

.filter-group {
  display: inline-flex;
  align-items: center;
}

.filter-group--actions {
  justify-content: flex-start;
  gap: 6px;
  white-space: nowrap;
}

.filters__create-btn {
  margin-left: 10px;
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

.node-status-trigger {
  grid-area: status;
  display: inline-flex;
  justify-content: center;
  width: 100%;
}

.node-action-row {
  grid-area: actions;
  display: inline-flex;
  align-items: center;
  gap: 8px;
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

.node-light {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  box-shadow: 0 0 0 1px rgb(15 23 42 / 10%);
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

.workflow-select :deep(.el-select__selected-item) {
  font-size: 12px;
}

.project-level-trigger,
.project-status-trigger,
.project-owner-trigger {
  display: inline-flex;
  cursor: pointer;
}

:deep(.status-tag--canceled.el-tag) {
  --el-tag-text-color: #9f8f80;
  --el-tag-bg-color: #faf7f4;
  --el-tag-border-color: #e8ddd3;
}

.owner-tag-group {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  min-height: 24px;
}

.owner-tag-group :deep(.el-tag) {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.owner-dropdown-option {
  min-width: 132px;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.action-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
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

:deep(.el-button:not(.is-text):not(.el-button--text)),
:deep(.el-select__wrapper),
:deep(.el-input__wrapper) {
  min-height: 40px;
}

:deep(.el-button:not(.is-text):not(.el-button--text)) {
  border-radius: 12px;
  transition: transform 180ms ease, box-shadow 220ms ease, background-color 220ms ease;
}

:deep(.el-button:not(.is-disabled):not(.is-text):not(.el-button--text):hover) {
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

  .list-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .hero {
    flex-direction: column;
  }

  .hero-meta {
    gap: 6px;
  }
}

@media (max-width: 640px) {
  .project-page {
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

  .list-filters {
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
html.dark .project-page {
  --project-dark-surface: #1c2026;
  --project-dark-surface-soft: #1c2026;
  --project-dark-card: #22262d;
  --project-dark-border: rgba(107, 114, 128, 0.22);
  --project-dark-border-strong: rgba(148, 163, 184, 0.2);
  --project-dark-text: #f8fafc;
  --project-dark-muted: #9ca3af;
  --project-dark-soft: #cbd5e1;
  color: var(--project-dark-text);
  background: #14171b;
  border-radius: 24px;
  padding: 18px;
}

html.dark .project-page .hero {
  background: var(--project-dark-surface-soft) !important;
  border-color: var(--project-dark-border-strong) !important;
  box-shadow: 0 16px 32px rgba(0, 0, 0, 0.22) !important;
}

html.dark .project-page .hero-kicker {
  color: #cbd5e1;
}

html.dark .project-page .hero h1,
html.dark .project-page .card-header h3,
html.dark .project-page .stat-value,
html.dark .project-page .node-asset-history__title,
html.dark .project-page .node-asset-card__name {
  color: var(--project-dark-text);
}

html.dark .project-page .hero-desc,
html.dark .project-page .card-header p,
html.dark .project-page .stat-label,
html.dark .project-page .page-size-inline,
html.dark .project-page .node-flow-name,
html.dark .project-page .owner-dropdown-option,
html.dark .project-page .node-asset-history__count,
html.dark .project-page .node-asset-card__summary,
html.dark .project-page .node-asset-card__time,
html.dark .project-page .el-form-item__label,
html.dark .project-page .el-empty__description p {
  color: var(--project-dark-muted);
}

html.dark .project-page .hero-meta span {
  background: rgba(148, 163, 184, 0.08);
  border-color: rgba(148, 163, 184, 0.12);
  color: var(--project-dark-soft);
}

html.dark .project-page .panel-card,
html.dark .project-page .stat-card,
html.dark .project-page .node-asset-history {
  border-color: var(--project-dark-border) !important;
  background: var(--project-dark-card) !important;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18) !important;
}

html.dark .project-page .node-asset-card {
  border-color: rgba(107, 114, 128, 0.22) !important;
  background: #171b21 !important;
  box-shadow: none !important;
}

html.dark .project-page .node-asset-card__action-btn,
html.dark .project-page .node-asset-card__action-btn:hover,
html.dark .project-page .node-asset-card__action-btn:focus-visible,
html.dark .project-page .node-asset-card__action-btn:active {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  transform: none !important;
}

html.dark .project-page .node-asset-card__action-btn.el-button--primary,
html.dark .project-page .node-asset-card__action-btn.el-button--primary:hover {
  color: #60a5fa !important;
}

html.dark .project-page .node-asset-card__action-btn.el-button--danger,
html.dark .project-page .node-asset-card__action-btn.el-button--danger:hover {
  color: #f87171 !important;
}

html.dark .project-page .node-asset-card__action-btn:not(.el-button--primary):not(.el-button--danger),
html.dark .project-page .node-asset-card__action-btn:not(.el-button--primary):not(.el-button--danger):hover {
  color: #94a3b8 !important;
}

html.dark .project-page .node-status-badge {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.08);
  color: var(--project-dark-muted);
}

html.dark .project-page .node-status-badge:hover,
html.dark .project-page .node-status-badge--focus {
  border-color: rgba(96, 165, 250, 0.22);
  background: rgba(96, 165, 250, 0.08);
  color: var(--project-dark-text);
}

html.dark .project-page .node-light {
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.18);
}

html.dark .project-page .node-flow-link {
  background: rgba(148, 163, 184, 0.22);
}

html.dark .project-page .node-asset-btn {
  color: #8dc2ff !important;
}

html.dark .project-page .node-asset-btn:hover {
  color: #dbeafe !important;
}

html.dark .project-page .el-input__wrapper,
html.dark .project-page .el-select__wrapper,
html.dark .project-page .el-date-editor.el-input__wrapper,
html.dark .project-page .el-textarea__inner {
  background: rgba(17, 24, 39, 0.56) !important;
  box-shadow: 0 0 0 1px rgba(107, 114, 128, 0.2) inset !important;
  border-color: transparent !important;
}

html.dark .project-page .el-input__inner,
html.dark .project-page .el-textarea__inner,
html.dark .project-page .el-select__selected-item,
html.dark .project-page .el-range-input {
  color: var(--project-dark-text) !important;
}

html.dark .project-page .el-input__inner::placeholder,
html.dark .project-page .el-textarea__inner::placeholder,
html.dark .project-page .el-select__placeholder,
html.dark .project-page .el-range-input::placeholder {
  color: var(--project-dark-muted) !important;
}

html.dark .project-page .el-button:not(.is-text):not(.el-button--text):not(.el-button--primary):not(.el-button--success) {
  border-color: rgba(107, 114, 128, 0.22);
  background: rgba(255, 255, 255, 0.03);
  color: var(--project-dark-soft);
  box-shadow: none;
}

html.dark .project-page .el-button:not(.is-text):not(.el-button--text):not(.el-button--primary):not(.el-button--success):hover {
  border-color: rgba(96, 165, 250, 0.2);
  background: rgba(96, 165, 250, 0.08);
  color: var(--project-dark-text);
}

html.dark .project-page .el-button--primary {
  border: none;
  background: #3b82f6;
  color: #fff;
  box-shadow: none;
}

html.dark .project-page .el-button--primary:hover {
  background: #60a5fa;
}

html.dark .project-page .el-button--success.is-plain {
  border-color: rgba(74, 222, 128, 0.26);
  background: rgba(34, 197, 94, 0.12);
  color: #86efac;
}

html.dark .project-page .el-button--success.is-plain:hover {
  border-color: rgba(74, 222, 128, 0.34);
  background: rgba(34, 197, 94, 0.18);
  color: #dcfce7;
}

html.dark .project-page .action-link-btn,
html.dark .project-page .action-link-btn:hover,
html.dark .project-page .action-link-btn:focus-visible {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  transform: none !important;
}

html.dark .project-page .node-conversation__header {
  border-color: rgba(96, 165, 250, 0.2);
  background: linear-gradient(120deg, rgba(30, 64, 175, 0.2) 0%, rgba(30, 41, 59, 0.82) 100%);
}

html.dark .project-page .node-conversation__badge {
  border-color: rgba(147, 197, 253, 0.3);
  background: rgba(96, 165, 250, 0.16);
  color: #bfdbfe;
}

html.dark .project-page .node-conversation__title {
  color: var(--project-dark-text);
}

html.dark .project-page .node-conversation__desc,
html.dark .project-page .node-conversation__panel-meta {
  color: var(--project-dark-muted);
}

html.dark .project-page .node-conversation__panel {
  border-color: rgba(107, 114, 128, 0.2);
  background: rgba(17, 24, 39, 0.52);
}

html.dark .project-page .node-conversation__footer {
  border-top-color: rgba(107, 114, 128, 0.24);
}

html.dark .project-page .node-conversation__panel-title {
  color: #e2e8f0;
}

html.dark .project-page .node-conversation__panel .el-button,
html.dark .project-page .node-conversation__panel .el-button:hover,
html.dark .project-page .node-conversation__panel .el-button:focus-visible {
  border-color: transparent !important;
  background: transparent !important;
  box-shadow: none !important;
  transform: none !important;
}

html.dark .project-page .node-conversation__panel .el-button {
  color: #93c5fd;
}

html.dark .project-page .node-conversation__panel .el-button.is-disabled {
  color: #64748b !important;
}

html.dark .project-page .node-conversation__table-action,
html.dark .project-page .node-conversation__table-action:hover {
  color: #60a5fa !important;
}

html.dark .project-page .node-conversation__table-action--danger,
html.dark .project-page .node-conversation__table-action--danger:hover {
  color: #f87171 !important;
}

html.dark .project-page .node-conversation__close-btn {
  border-color: rgba(148, 163, 184, 0.24);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

html.dark .project-page .node-conversation__close-btn:hover {
  border-color: rgba(96, 165, 250, 0.28);
  background: rgba(96, 165, 250, 0.14);
  color: #eff6ff;
}

html.dark .project-page .el-table {
  --el-table-bg-color: rgba(27, 31, 38, 0.82);
  --el-table-tr-bg-color: rgba(27, 31, 38, 0.82);
  --el-table-expanded-cell-bg-color: rgba(27, 31, 38, 0.82);
  --el-table-header-bg-color: rgba(34, 38, 46, 0.96);
  --el-table-row-hover-bg-color: rgba(96, 165, 250, 0.06);
  --el-table-border-color: rgba(107, 114, 128, 0.2);
  --el-table-header-text-color: #cbd5e1;
  --el-table-text-color: #e2e8f0;
}

html.dark .project-page .el-table th.el-table__cell {
  background: rgba(34, 38, 46, 0.96);
}

html.dark .project-page .el-table__row:hover > td.el-table__cell {
  background: rgba(96, 165, 250, 0.06) !important;
}

html.dark .project-page .el-pagination {
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

html.dark .project-page .node-asset-preview__pdf,
html.dark .project-page .node-asset-preview__table-wrap,
html.dark .project-page .node-asset-preview__markdown {
  border-color: rgba(148, 163, 184, 0.14);
  background: rgba(17, 24, 39, 0.48);
}

html.dark .project-page .node-asset-preview__text {
  color: #dbe5f5;
}
</style>
