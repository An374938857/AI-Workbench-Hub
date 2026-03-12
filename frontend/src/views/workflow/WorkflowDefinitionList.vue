<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  activateWorkflowDefinition,
  createWorkflowDefinition,
  deprecateWorkflowDefinition,
  listWorkflowDefinitions,
} from '@/api/workflows'

interface WorkflowDefinitionItem {
  id: number
  name: string
  code: string
  scope: 'PROJECT' | 'REQUIREMENT'
  status: string
}

const router = useRouter()

const loading = ref(false)
const creating = ref(false)
const updatingStatusIds = ref<number[]>([])
const scopeFilter = ref<string | undefined>(undefined)
const items = ref<WorkflowDefinitionItem[]>([])
const scopeLabelMap: Record<WorkflowDefinitionItem['scope'], string> = {
  PROJECT: '项目流程',
  REQUIREMENT: '需求流程',
}
const statusLabelMap: Record<string, string> = {
  ACTIVE: '启用',
  DEPRECATED: '已废弃',
}

const form = ref({
  name: '',
  code: '',
  scope: 'REQUIREMENT' as 'PROJECT' | 'REQUIREMENT',
  description: '',
})

async function fetchData() {
  loading.value = true
  try {
    const res = await listWorkflowDefinitions({ scope: scopeFilter.value as 'PROJECT' | 'REQUIREMENT' | undefined })
    items.value = res.data
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!form.value.name.trim() || !form.value.code.trim()) {
    ElMessage.warning('请填写流程名称与编码')
    return
  }

  creating.value = true
  try {
    const res = await createWorkflowDefinition({
      name: form.value.name,
      code: form.value.code,
      scope: form.value.scope,
      description: form.value.description || undefined,
    })
    ElMessage.success('流程定义创建成功')
    form.value.name = ''
    form.value.code = ''
    form.value.description = ''
    await fetchData()
    router.push(`/admin/workflows/${res.data.id}`)
  } finally {
    creating.value = false
  }
}

function openEditor(item: WorkflowDefinitionItem) {
  router.push(`/admin/workflows/${item.id}`)
}

function isStatusUpdating(id: number) {
  return updatingStatusIds.value.includes(id)
}

async function handleDeprecate(item: WorkflowDefinitionItem) {
  updatingStatusIds.value.push(item.id)
  try {
    await deprecateWorkflowDefinition(item.id)
    ElMessage.success('流程已废弃')
    await fetchData()
  } finally {
    updatingStatusIds.value = updatingStatusIds.value.filter((id) => id !== item.id)
  }
}

async function handleActivate(item: WorkflowDefinitionItem) {
  updatingStatusIds.value.push(item.id)
  try {
    await activateWorkflowDefinition(item.id)
    ElMessage.success('流程已重新启用')
    await fetchData()
  } finally {
    updatingStatusIds.value = updatingStatusIds.value.filter((id) => id !== item.id)
  }
}

function getScopeLabel(scope: WorkflowDefinitionItem['scope']) {
  return scopeLabelMap[scope] || scope
}

function getStatusLabel(status: string) {
  return statusLabelMap[status] || status
}

onMounted(async () => {
  await fetchData()
})
</script>

<template>
  <div class="workflow-list-page">
    <div class="page-header">
      <h2>流程管理</h2>
    </div>

    <el-card shadow="never">
      <div class="filter-bar">
        <el-select v-model="scopeFilter" clearable placeholder="按作用域筛选" style="width: 180px" @change="fetchData">
          <el-option label="项目流程" value="PROJECT" />
          <el-option label="需求流程" value="REQUIREMENT" />
        </el-select>
      </div>

      <el-form inline>
        <el-form-item label="流程名称">
          <el-input v-model="form.name" style="width: 180px" />
        </el-form-item>
        <el-form-item label="流程编码">
          <el-input v-model="form.code" style="width: 180px" />
        </el-form-item>
        <el-form-item label="作用域">
          <el-select v-model="form.scope" style="width: 140px">
            <el-option label="项目流程" value="PROJECT" />
            <el-option label="需求流程" value="REQUIREMENT" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="creating" @click="handleCreate">创建定义</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="流程名称" min-width="180" />
        <el-table-column prop="code" label="编码" min-width="140" />
        <el-table-column label="作用域" width="140">
          <template #default="{ row }">
            {{ getScopeLabel(row.scope) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            {{ getStatusLabel(row.status) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button type="primary" link @click="openEditor(row)">编辑</el-button>
            <el-button
              v-if="row.status !== 'DEPRECATED'"
              type="warning"
              link
              :loading="isStatusUpdating(row.id)"
              @click="handleDeprecate(row)"
            >
              废弃定义
            </el-button>
            <el-button
              v-else
              type="success"
              link
              :loading="isStatusUpdating(row.id)"
              @click="handleActivate(row)"
            >
              重新启用
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.workflow-list-page {
  width: 100%;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  color: var(--text-primary, #303133);
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
