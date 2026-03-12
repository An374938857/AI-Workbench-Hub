<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import { showDangerConfirm } from '@/composables/useDangerConfirm'

import { getAdminSkillList } from '@/api/admin/skills'
import {
  createWorkflowVersion,
  deleteWorkflowVersion,
  getWorkflowDefinition,
  getWorkflowVersion,
  publishWorkflowVersion,
  updateWorkflowVersionNodes,
} from '@/api/workflows'

interface SkillItem {
  id: number
  name: string
}

type OutputType = 'MARKDOWN' | 'YUQUE_URL'
type VersionStatus = 'DRAFT' | 'PUBLISHED'

interface WorkflowNodeForm {
  _row_id: string
  node_code: string
  node_name: string
  node_order: number
  skill_id?: number
  output_types: OutputType[]
}

interface WorkflowVersionItem {
  id: number
  version_no: number
  status: VersionStatus
}

const route = useRoute()
const router = useRouter()
const definitionId = Number(route.params.definitionId)

const loading = ref(false)
const savingNodes = ref(false)
const publishing = ref(false)
const creatingVersion = ref(false)
const deletingVersion = ref(false)
const branching = ref(false)

const title = ref('流程定义')
const versions = ref<WorkflowVersionItem[]>([])
const selectedVersionId = ref<number | undefined>(undefined)
const skills = ref<SkillItem[]>([])
const nodes = ref<WorkflowNodeForm[]>([])
let ensureDraftPromise: Promise<boolean> | null = null
const tableRef = ref<{ $el: HTMLElement } | null>(null)
let nodeTableSortable: Sortable | null = null
let nodeRowIdSeed = 0

const OUTPUT_TYPE_OPTIONS: Array<{ label: string; value: OutputType }> = [
  { label: 'Markdown 文档', value: 'MARKDOWN' },
  { label: '语雀链接', value: 'YUQUE_URL' },
]

function parseOutputTypes(outputType?: string): OutputType[] {
  const values = (outputType || '')
    .split(',')
    .map((item) => item.trim())
    .filter((item): item is OutputType => item === 'MARKDOWN' || item === 'YUQUE_URL')
  const uniqueValues = Array.from(new Set(values))
  if (!uniqueValues.length) return ['MARKDOWN']
  return uniqueValues.sort((a, b) => (a === 'MARKDOWN' ? -1 : 1))
}

function stringifyOutputTypes(outputTypes: OutputType[]): string {
  const normalized = parseOutputTypes(outputTypes.join(','))
  return normalized.join(',')
}

function createNodeRowId(): string {
  nodeRowIdSeed += 1
  return `workflow-node-${Date.now()}-${nodeRowIdSeed}`
}

const selectedVersion = computed(() => versions.value.find((item) => item.id === selectedVersionId.value))
const isSelectedPublished = computed(() => selectedVersion.value?.status === 'PUBLISHED')
const canEditDraftActions = computed(() => Boolean(selectedVersionId.value) && !isSelectedPublished.value)
const canDeleteDraft = computed(
  () => Boolean(selectedVersionId.value) && !isSelectedPublished.value && versions.value.length > 1,
)

function goBackToList() {
  router.push('/admin/workflows')
}

async function fetchSkills() {
  const res = await getAdminSkillList({ page: 1, page_size: 100 })
  skills.value = res.data.items.map((item: { id: number; name: string }) => ({ id: item.id, name: item.name }))
}

async function fetchDefinition() {
  loading.value = true
  try {
    const res = await getWorkflowDefinition(definitionId)
    title.value = `${res.data.name} (${res.data.code})`
    versions.value = (
      res.data.versions || []
    ).map((item: { id: number | string; version_no: number | string; status?: VersionStatus; is_published?: boolean }) => ({
      id: Number(item.id),
      version_no: Number(item.version_no),
      status: item.status ? (item.status === 'PUBLISHED' ? 'PUBLISHED' : 'DRAFT') : (item.is_published ? 'PUBLISHED' : 'DRAFT'),
    }))

    const hasSelectedVersion = versions.value.some((item) => item.id === selectedVersionId.value)
    if (!hasSelectedVersion && versions.value.length) {
      selectedVersionId.value = versions.value[0]?.id
    }
    if (!versions.value.length) {
      selectedVersionId.value = undefined
    }
  } finally {
    loading.value = false
  }
}

async function fetchVersionDetail() {
  if (!selectedVersionId.value) {
    nodes.value = []
    await initNodeTableSortable()
    return
  }
  const res = await getWorkflowVersion(selectedVersionId.value)
  nodes.value = (res.data.nodes || []).map(
    (item: { node_code: string; node_name: string; node_order: number; skill_id?: number; output_type?: string }) => ({
      _row_id: createNodeRowId(),
      node_code: item.node_code,
      node_name: item.node_name,
      node_order: item.node_order,
      skill_id: item.skill_id,
      output_types: parseOutputTypes(item.output_type),
    }),
  )
  await initNodeTableSortable()
}

async function createDraftFromSelected(showSuccessMessage: boolean): Promise<boolean> {
  creatingVersion.value = true
  try {
    const sourceVersionNo = selectedVersion.value?.version_no
    const res = selectedVersionId.value
      ? await createWorkflowVersion(definitionId, { source_version_id: selectedVersionId.value })
      : await createWorkflowVersion(definitionId)
    await fetchDefinition()
    selectedVersionId.value = Number(res.data.id)
    await fetchVersionDetail()
    if (showSuccessMessage) {
      if (sourceVersionNo) {
        ElMessage.success(`已基于 v${sourceVersionNo} 创建草稿 v${res.data.version_no}`)
      } else {
        ElMessage.success('草稿版本创建成功')
      }
    }
    return true
  } finally {
    creatingVersion.value = false
  }
}

async function ensureDraftForEditing(): Promise<boolean> {
  if (!selectedVersionId.value) {
    ElMessage.warning('请先选择要编辑的版本')
    return false
  }

  if (!isSelectedPublished.value) {
    return true
  }

  if (ensureDraftPromise) {
    return ensureDraftPromise
  }

  ensureDraftPromise = (async () => {
    branching.value = true
    try {
      return await createDraftFromSelected(true)
    } finally {
      branching.value = false
      ensureDraftPromise = null
    }
  })()

  return ensureDraftPromise
}

async function updateNodeField(index: number, key: 'node_code' | 'node_name', value: string) {
  if (!(await ensureDraftForEditing())) return
  const target = nodes.value[index]
  if (!target) return
  target[key] = value
}

async function updateNodeSkill(index: number, value: number | undefined) {
  if (!(await ensureDraftForEditing())) return
  const target = nodes.value[index]
  if (!target) return
  target.skill_id = value
}

async function updateNodeOutputTypes(index: number, values: OutputType[]) {
  if (!(await ensureDraftForEditing())) return
  const target = nodes.value[index]
  if (!target) return
  target.output_types = values
}

async function addNode() {
  if (!(await ensureDraftForEditing())) return
  nodes.value.push({
    _row_id: createNodeRowId(),
    node_code: `NODE_${nodes.value.length + 1}`,
    node_name: `节点${nodes.value.length + 1}`,
    node_order: nodes.value.length + 1,
    skill_id: skills.value[0]?.id,
    output_types: ['MARKDOWN'],
  })
}

async function removeNode(index: number) {
  if (!(await ensureDraftForEditing())) return
  nodes.value.splice(index, 1)
  normalizeNodeOrder()
}

function normalizeNodeOrder() {
  nodes.value.forEach((item, idx) => {
    item.node_order = idx + 1
  })
}

function destroyNodeTableSortable() {
  nodeTableSortable?.destroy()
  nodeTableSortable = null
}

async function initNodeTableSortable() {
  await nextTick()
  destroyNodeTableSortable()
  const tbody = tableRef.value?.$el.querySelector<HTMLTableSectionElement>('.el-table__body-wrapper tbody')
  if (!tbody) return
  nodeTableSortable = Sortable.create(tbody, {
    animation: 150,
    handle: '.node-drag-handle',
    ghostClass: 'node-drag-ghost',
    chosenClass: 'node-drag-chosen',
    dragClass: 'node-drag-dragging',
    onEnd: async ({ oldIndex, newIndex }) => {
      if (oldIndex == null || newIndex == null || oldIndex === newIndex) return
      if (isSelectedPublished.value) {
        if (!(await ensureDraftForEditing())) {
          await fetchVersionDetail()
          return
        }
      }
      const moved = nodes.value.splice(oldIndex, 1)[0]
      if (!moved) return
      nodes.value.splice(newIndex, 0, moved)
      normalizeNodeOrder()
    },
  })
}

async function handleSaveDraft() {
  if (!selectedVersionId.value) {
    ElMessage.warning('请先选择要编辑的版本')
    return
  }
  if (isSelectedPublished.value) {
    ElMessage.warning('已发布版本不支持直接保存，请先创建草稿')
    return
  }
  if (!nodes.value.length) {
    ElMessage.warning('请至少保留一个节点')
    return
  }
  if (nodes.value.some((node) => !(node.node_code || '').trim() || !(node.node_name || '').trim())) {
    ElMessage.warning('请填写完整节点信息')
    return
  }
  const normalizedCodes = nodes.value.map((node) => (node.node_code || '').trim())
  if (normalizedCodes.length !== new Set(normalizedCodes).size) {
    ElMessage.warning('节点编码不能重复')
    return
  }
  const nodeOrders = nodes.value.map((node) => node.node_order)
  if (nodeOrders.length !== new Set(nodeOrders).size) {
    ElMessage.warning('节点顺序不能重复')
    return
  }

  savingNodes.value = true
  try {
    await updateWorkflowVersionNodes(selectedVersionId.value, {
      nodes: nodes.value.map((node) => ({
        node_code: node.node_code,
        node_name: node.node_name,
        node_order: node.node_order,
        skill_id: node.skill_id,
        output_type: stringifyOutputTypes(node.output_types),
      })),
    })
    ElMessage.success('草稿保存成功')
    await fetchVersionDetail()
  } finally {
    savingNodes.value = false
  }
}

async function handleCreateVersion() {
  if (selectedVersionId.value && nodes.value.length === 0) {
    ElMessage.warning('当前版本没有任何节点，暂不允许新建草稿版本')
    return
  }
  await createDraftFromSelected(true)
}

async function handlePublish() {
  if (!selectedVersionId.value) {
    ElMessage.warning('请先选择要发布的版本')
    return
  }
  if (isSelectedPublished.value) {
    return
  }

  publishing.value = true
  try {
    const res = await publishWorkflowVersion(selectedVersionId.value)
    ElMessage.success(`发布成功，切换实例数：${res.data.switched_instances}`)
    await fetchDefinition()
    await fetchVersionDetail()
  } finally {
    publishing.value = false
  }
}

async function handleDeleteDraft() {
  if (!selectedVersionId.value || isSelectedPublished.value) {
    return
  }
  try {
    await showDangerConfirm({
      title: '删除草稿',
      subject: `版本 #${selectedVersionId.value}`,
      detail: '删除后无法恢复，当前草稿版本会被永久移除。',
      confirmText: '删除草稿',
    })
  } catch (_error) {
    return
  }

  deletingVersion.value = true
  try {
    await deleteWorkflowVersion(selectedVersionId.value)
    ElMessage.success('草稿删除成功')
    await fetchDefinition()
    await fetchVersionDetail()
  } finally {
    deletingVersion.value = false
  }
}

function getVersionStatusLabel(status: VersionStatus | undefined): string {
  return status === 'PUBLISHED' ? '已发布' : '草稿'
}

function getVersionStatusType(status: VersionStatus | undefined): 'success' | 'warning' {
  return status === 'PUBLISHED' ? 'success' : 'warning'
}

onMounted(async () => {
  try {
    await Promise.all([fetchSkills(), fetchDefinition()])
  } catch (_error) {
    // 技能列表失败不应阻断定义详情展示
  }
  await fetchVersionDetail()
})

onBeforeUnmount(() => {
  destroyNodeTableSortable()
})

watch(
  () => nodes.value.length,
  async () => {
    await initNodeTableSortable()
  },
)
</script>

<template>
  <div v-loading="loading || branching" class="workflow-editor-page">
    <div class="page-header">
      <el-button class="back-btn" text @click="goBackToList">
        <el-icon><ArrowLeft /></el-icon>
        返回流程管理
      </el-button>
      <div class="title-row">
        <h2>{{ title }}</h2>
        <div class="actions">
          <el-button @click="handleCreateVersion" :loading="creatingVersion" :disabled="!selectedVersionId">新建草稿版本</el-button>
          <el-button type="primary" :loading="savingNodes" :disabled="!canEditDraftActions" @click="handleSaveDraft">保存草稿</el-button>
          <el-button type="success" :loading="publishing" :disabled="!canEditDraftActions" @click="handlePublish">发布版本</el-button>
          <el-button type="danger" :loading="deletingVersion" :disabled="!canDeleteDraft" @click="handleDeleteDraft">删除草稿</el-button>
        </div>
      </div>
    </div>

    <el-card shadow="never">
      <el-form inline>
        <el-form-item label="编辑版本">
          <div class="version-select-wrap">
            <el-select v-model="selectedVersionId" style="width: 280px" @change="fetchVersionDetail">
              <el-option
                v-for="version in versions"
                :key="version.id"
                :label="`v${version.version_no}`"
                :value="version.id"
              />
            </el-select>
            <el-tag :type="getVersionStatusType(selectedVersion?.status)">{{ getVersionStatusLabel(selectedVersion?.status) }}</el-tag>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button @click="addNode" :disabled="isSelectedPublished || !selectedVersionId">新增节点</el-button>
        </el-form-item>
      </el-form>

      <div class="tip" v-if="isSelectedPublished">当前为已发布版本。修改字段将自动创建新草稿版本，新增节点与发布操作需在草稿中进行。</div>

      <el-table ref="tableRef" :data="nodes" row-key="_row_id" stripe>
        <el-table-column label="" width="48">
          <template #default>
            <span class="node-drag-handle" aria-label="拖拽排序手柄" title="拖拽排序">⋮⋮</span>
          </template>
        </el-table-column>
        <el-table-column prop="node_order" label="顺序" width="80" />
        <el-table-column label="节点编码" min-width="140">
          <template #default="{ row, $index }">
            <el-input :model-value="row.node_code" @update:model-value="(value: string) => updateNodeField($index, 'node_code', value)" />
          </template>
        </el-table-column>
        <el-table-column label="节点名称" min-width="160">
          <template #default="{ row, $index }">
            <el-input :model-value="row.node_name" @update:model-value="(value: string) => updateNodeField($index, 'node_name', value)" />
          </template>
        </el-table-column>
        <el-table-column label="绑定技能（可选）" min-width="220">
          <template #default="{ row, $index }">
            <el-select
              :model-value="row.skill_id"
              clearable
              placeholder="不绑定技能（自由节点）"
              style="width: 100%"
              @update:model-value="(value: number | undefined) => updateNodeSkill($index, value)"
            >
              <el-option v-for="skill in skills" :key="skill.id" :label="skill.name" :value="skill.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="输出类型" min-width="140">
          <template #default="{ row, $index }">
            <el-select
              :model-value="row.output_types"
              multiple
              collapse-tags
              collapse-tags-tooltip
              style="width: 100%"
              @update:model-value="(value: OutputType[]) => updateNodeOutputTypes($index, value)"
            >
              <el-option v-for="option in OUTPUT_TYPE_OPTIONS" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ $index }">
            <el-button type="danger" link @click="removeNode($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.workflow-editor-page {
  width: 100%;
}

.page-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
}

.title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.back-btn {
  width: fit-content;
  padding-left: 0;
}

.title-row h2 {
  margin: 0;
  font-size: 20px;
  color: var(--text-primary, #303133);
}

.actions {
  display: flex;
  gap: 8px;
}

.version-select-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tip {
  margin-bottom: 12px;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 8px 10px;
}

:deep(.node-drag-handle) {
  cursor: grab;
  color: #9ca3af;
}

:deep(.node-drag-handle:active) {
  cursor: grabbing;
}

:deep(.node-drag-ghost > td) {
  background: #eff6ff !important;
}

:deep(.node-drag-chosen > td) {
  background: #f8fafc;
}
</style>
