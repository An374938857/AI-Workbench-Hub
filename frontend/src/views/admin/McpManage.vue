<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  getMcpList, createMcp, updateMcp, deleteMcp,
  toggleMcp, testMcp, getMcpTools, toggleMcpTool, refreshMcpTools,
  batchTestMcps, getMcpInspectionConfig, updateMcpInspectionConfig
} from '@/api/admin/mcps'
import { ElMessage } from 'element-plus'
import { showDangerConfirm } from '@/composables/useDangerConfirm'

interface McpItem {
  id: number
  name: string
  description: string
  transport_type: string
  is_enabled: boolean
  timeout_seconds: number
  max_retries: number
  circuit_breaker_threshold: number
  circuit_breaker_recovery: number
  access_role: string
  health_status: string
  tool_count: number
  last_test_result: string | null
  last_test_time: string | null
  creator_name: string
  created_at: string
}

interface ToolItem {
  id: number
  tool_name: string
  tool_description: string | null
  input_schema: object | null
  is_enabled: boolean
}

const loading = ref(false)
const tableData = ref<McpItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')

const dialogVisible = ref(false)
const dialogTitle = ref('新增 MCP')
const isEdit = ref(false)
const editingId = ref(0)
const formLoading = ref(false)
const form = ref({
  name: '',
  description: '',
  config_json_str: '',
  timeout_seconds: 30,
  max_retries: 0,
  circuit_breaker_threshold: 5,
  circuit_breaker_recovery: 300,
  access_role: 'all',
})

const testingId = ref<number | null>(null)
const batchTesting = ref(false)
const inspectionConfigLoading = ref(false)
const inspectionConfigSaving = ref(false)
const inspectionHours = ref(0)
const inspectionMinutes = ref(30)

const toolDrawerVisible = ref(false)
const toolDrawerTitle = ref('')
const toolDrawerMcpId = ref(0)
const toolList = ref<ToolItem[]>([])
const toolLoading = ref(false)

async function fetchList() {
  loading.value = true
  try {
    const res: any = await getMcpList({ page: page.value, page_size: pageSize.value, keyword: keyword.value || undefined })
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  fetchList()
}

function openCreate() {
  dialogTitle.value = '新增 MCP'
  isEdit.value = false
  editingId.value = 0
  form.value = {
    name: '', description: '', config_json_str: '',
    timeout_seconds: 30, max_retries: 0,
    circuit_breaker_threshold: 5, circuit_breaker_recovery: 300, access_role: 'all',
  }
  dialogVisible.value = true
}

function openEdit(row: McpItem) {
  dialogTitle.value = '编辑 MCP'
  isEdit.value = true
  editingId.value = row.id
  form.value = {
    name: row.name,
    description: row.description,
    config_json_str: '',
    timeout_seconds: row.timeout_seconds,
    max_retries: row.max_retries,
    circuit_breaker_threshold: row.circuit_breaker_threshold,
    circuit_breaker_recovery: row.circuit_breaker_recovery,
    access_role: row.access_role,
  }
  // Load detail to get config_json
  getMcpDetail(row.id).then((res: any) => {
    form.value.config_json_str = JSON.stringify(res.data.config_json, null, 2)
  })
  dialogVisible.value = true
}

function getMcpDetail(id: number) {
  return import('@/api/admin/mcps').then(m => m.getMcpDetail(id))
}

function formatJson() {
  try {
    const obj = JSON.parse(form.value.config_json_str)
    form.value.config_json_str = JSON.stringify(obj, null, 2)
  } catch {
    ElMessage.warning('JSON 格式不正确，无法格式化')
  }
}

async function handleSubmit() {
  if (!form.value.name.trim()) return ElMessage.warning('请输入名称')
  if (!form.value.description.trim()) return ElMessage.warning('请输入描述')
  if (!form.value.config_json_str.trim()) return ElMessage.warning('请输入 JSON 配置')

  let configJson: object
  try {
    configJson = JSON.parse(form.value.config_json_str)
  } catch {
    return ElMessage.error('JSON 配置格式不正确')
  }

  formLoading.value = true
  try {
    const payload = {
      name: form.value.name,
      description: form.value.description,
      config_json: configJson,
      timeout_seconds: form.value.timeout_seconds,
      max_retries: form.value.max_retries,
      circuit_breaker_threshold: form.value.circuit_breaker_threshold,
      circuit_breaker_recovery: form.value.circuit_breaker_recovery,
      access_role: form.value.access_role,
    }
    if (isEdit.value) {
      await updateMcp(editingId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await createMcp(payload)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchList()
  } finally {
    formLoading.value = false
  }
}

async function handleToggle(row: McpItem) {
  await toggleMcp(row.id, !row.is_enabled)
  ElMessage.success(row.is_enabled ? '已停用' : '已启用')
  fetchList()
}

async function handleTest(row: McpItem) {
  testingId.value = row.id
  try {
    const res: any = await testMcp(row.id)
    if (res.data.result === 'success') {
      ElMessage.success(`连接成功，发现 ${res.data.tools.length} 个工具（${res.data.response_time_ms}ms）`)
    } else {
      ElMessage.error(`连接失败：${res.data.error_detail}`)
    }
    fetchList()
  } catch {
    fetchList()
  } finally {
    testingId.value = null
  }
}

async function handleDelete(row: McpItem) {
  await showDangerConfirm({
    title: '删除 MCP',
    subject: row.name,
    detail: '删除后将移除 MCP 配置、工具同步数据与相关状态记录，且不可恢复。',
    confirmText: '删除 MCP',
  })
  await deleteMcp(row.id)
  ElMessage.success('已删除')
  fetchList()
}

async function openToolDrawer(row: McpItem) {
  toolDrawerTitle.value = `${row.name} — 工具列表`
  toolDrawerMcpId.value = row.id
  toolDrawerVisible.value = true
  await fetchTools(row.id)
}

async function fetchTools(mcpId: number) {
  toolLoading.value = true
  try {
    const res: any = await getMcpTools(mcpId)
    toolList.value = res.data
  } finally {
    toolLoading.value = false
  }
}

async function handleToggleTool(tool: ToolItem) {
  await toggleMcpTool(toolDrawerMcpId.value, tool.id, !tool.is_enabled)
  ElMessage.success(tool.is_enabled ? '已停用' : '已启用')
  await fetchTools(toolDrawerMcpId.value)
  fetchList()
}

async function handleRefreshTools() {
  toolLoading.value = true
  try {
    const res: any = await refreshMcpTools(toolDrawerMcpId.value)
    const d = res.data
    ElMessage.success(`刷新完成：新增 ${d.added.length}，删除 ${d.removed.length}，未变 ${d.unchanged.length}`)
    await fetchTools(toolDrawerMcpId.value)
    fetchList()
  } finally {
    toolLoading.value = false
  }
}

async function handleBatchTest() {
  batchTesting.value = true
  try {
    const res = await batchTestMcps()
    const data = res.data as { success_count: number; fail_count: number }
    ElMessage.success(`批量测试完成：${data.success_count} 成功，${data.fail_count} 失败`)
    fetchList()
  } finally {
    testingId.value = null
    batchTesting.value = false
  }
}

async function fetchInspectionConfig() {
  inspectionConfigLoading.value = true
  try {
    const res = await getMcpInspectionConfig()
    const data = res.data as { interval_hours: number; interval_minutes: number }
    inspectionHours.value = data.interval_hours
    inspectionMinutes.value = data.interval_minutes
  } finally {
    inspectionConfigLoading.value = false
  }
}

async function saveInspectionConfig() {
  const totalMinutes = inspectionHours.value * 60 + inspectionMinutes.value
  if (totalMinutes <= 0) {
    ElMessage.warning('巡检频次必须大于 0 分钟')
    return
  }

  inspectionConfigSaving.value = true
  try {
    await updateMcpInspectionConfig({
      interval_hours: inspectionHours.value,
      interval_minutes: inspectionMinutes.value,
    })
    ElMessage.success('巡检频次已保存')
    await fetchInspectionConfig()
  } finally {
    inspectionConfigSaving.value = false
  }
}

function healthColor(status: string) {
  const map: Record<string, string> = { healthy: 'success', degraded: 'warning', circuit_open: 'danger', unknown: 'info' }
  return map[status] || 'info'
}

function healthLabel(status: string) {
  const map: Record<string, string> = { healthy: '正常', degraded: '降级', circuit_open: '熔断中', unknown: '未知' }
  return map[status] || status
}

function testResultLabel(r: string | null) {
  if (!r) return '未测试'
  return r === 'success' ? '测试成功' : '测试失败'
}

function accessRoleLabel(r: string) {
  const map: Record<string, string> = { all: '所有用户', provider_admin: '管理角色', admin_only: '仅超级管理员' }
  return map[r] || r
}

onMounted(() => {
  fetchList()
  fetchInspectionConfig()
})
</script>

<template>
  <div class="mcp-manage">
    <div class="page-header">
      <h2>MCP 管理</h2>
    </div>
    <el-card shadow="never">
      <div class="inspection-config-bar" v-loading="inspectionConfigLoading">
        <div class="inspection-config-title">自动巡检频次</div>
        <div class="inspection-config-controls">
          <el-input-number v-model="inspectionHours" :min="0" :max="168" controls-position="right" />
          <span class="inspection-config-unit">小时</span>
          <el-input-number v-model="inspectionMinutes" :min="0" :max="59" controls-position="right" />
          <span class="inspection-config-unit">分钟</span>
          <el-button type="primary" plain :loading="inspectionConfigSaving" @click="saveInspectionConfig">
            保存频次
          </el-button>
        </div>
        <div class="inspection-config-hint">已启用的 MCP 将按此频次自动执行批量连通性测试。</div>
      </div>

      <div class="filter-bar">
        <div class="filter-left">
          <el-input
            v-model="keyword"
            placeholder="搜索名称/描述"
            clearable
            style="width: 250px"
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          />
          <el-button @click="handleSearch">搜索</el-button>
        </div>
        <div class="filter-right">
          <el-button :loading="batchTesting" @click="handleBatchTest">批量测试</el-button>
          <el-button type="primary" @click="openCreate">新增 MCP</el-button>
        </div>
      </div>

      <el-table :data="tableData" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="description" label="描述" min-width="140" show-overflow-tooltip />
        <el-table-column prop="transport_type" label="传输方式" width="120" align="center" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag size="small" :type="row.transport_type === 'sse' ? '' : 'warning'">{{ row.transport_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_enabled ? 'success' : 'info'">{{ row.is_enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="健康状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="healthColor(row.health_status)">{{ healthLabel(row.health_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="tool_count" label="工具数" width="70" align="center" />
        <el-table-column label="最近测试" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.last_test_result === 'success' ? 'success' : row.last_test_result === 'failed' ? 'danger' : 'info'">
              {{ testResultLabel(row.last_test_result) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="可用角色" width="100" align="center">
          <template #default="{ row }">{{ accessRoleLabel(row.access_role) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="360" fixed="right">
          <template #default="{ row }">
            <div class="op-actions">
              <el-button size="small" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" @click="openToolDrawer(row)">工具</el-button>
              <el-button size="small" :loading="testingId === row.id" @click="handleTest(row)" style="min-width:56px">测试</el-button>
              <el-button size="small" :type="row.is_enabled ? 'warning' : 'success'" @click="handleToggle(row)" style="min-width:56px">
                {{ row.is_enabled ? '停用' : '启用' }}
              </el-button>
              <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchList"
        />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" width="700px" destroy-on-close class="mcp-manage-dialog">
      <template #header>
        <div class="dialog-header">
          <div class="dialog-header-badge">{{ isEdit ? '配置调整' : '接入配置' }}</div>
          <div class="dialog-header-title">{{ dialogTitle }}</div>
          <div class="dialog-header-desc">维护 MCP 服务的连接参数、熔断策略与访问权限，确保工具调用稳定可控。</div>
        </div>
      </template>
      <el-form :model="form" label-width="120px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="100" placeholder="如：知识库搜索" />
        </el-form-item>
        <el-form-item label="描述" required>
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="MCP 功能描述" />
        </el-form-item>
        <el-form-item label="JSON 配置" required>
          <div style="width:100%">
            <el-input v-model="form.config_json_str" type="textarea" :rows="8" placeholder='{"url": "http://..."}' style="font-family:monospace;font-size:13px" />
            <el-button size="small" style="margin-top:4px" @click="formatJson">格式化 JSON</el-button>
          </div>
        </el-form-item>
        <el-form-item label="调用超时(秒)">
          <el-input-number v-model="form.timeout_seconds" :min="5" :max="120" />
        </el-form-item>
        <el-form-item label="最大重试次数">
          <el-input-number v-model="form.max_retries" :min="0" :max="3" />
        </el-form-item>
        <el-form-item label="熔断阈值">
          <el-input-number v-model="form.circuit_breaker_threshold" :min="1" :max="100" />
          <span style="margin-left:8px;color: var(--text-muted);font-size:12px">连续失败次数</span>
        </el-form-item>
        <el-form-item label="熔断恢复(秒)">
          <el-input-number v-model="form.circuit_breaker_recovery" :min="10" :max="3600" :step="30" />
        </el-form-item>
        <el-form-item label="可用角色">
          <el-select v-model="form.access_role" style="width:220px">
            <el-option label="所有用户" value="all" />
            <el-option label="管理角色（技能管理员+超级管理员）" value="provider_admin" />
            <el-option label="仅超级管理员" value="admin_only" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button class="dialog-btn dialog-btn-secondary" @click="dialogVisible = false">取消</el-button>
          <el-button class="dialog-btn dialog-btn-primary" :loading="formLoading" @click="handleSubmit">
            {{ isEdit ? '保存配置' : '创建 MCP' }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 工具列表抽屉 -->
    <el-drawer v-model="toolDrawerVisible" size="560px" destroy-on-close class="mcp-manage-drawer">
      <template #header>
        <div class="drawer-header">
          <div class="dialog-header-badge">工具目录</div>
          <div class="drawer-header-title">{{ toolDrawerTitle }}</div>
          <div class="drawer-header-desc">查看当前 MCP 暴露的工具列表，支持启停控制与实时同步。</div>
        </div>
      </template>
      <div class="tool-drawer-toolbar">
        <span class="tool-drawer-summary">共 {{ toolList.length }} 个工具，已启用 {{ toolList.filter(t => t.is_enabled).length }} 个</span>
        <el-button class="dialog-btn dialog-btn-secondary dialog-btn-compact" :loading="toolLoading" @click="handleRefreshTools">
          刷新工具列表
        </el-button>
      </div>
      <div v-loading="toolLoading" class="tool-drawer-list">
        <div v-for="tool in toolList" :key="tool.id" class="tool-drawer-item">
          <div class="tool-drawer-header">
            <div class="tool-drawer-name">{{ tool.tool_name }}</div>
            <el-switch :model-value="tool.is_enabled" size="small" @change="handleToggleTool(tool)" />
          </div>
          <div v-if="tool.tool_description" class="tool-drawer-desc">{{ tool.tool_description }}</div>
          <div v-if="tool.input_schema && Object.keys(tool.input_schema).length > 0" class="tool-drawer-schema">
            <div class="tool-drawer-schema-title">参数定义</div>
            <pre class="tool-drawer-schema-code">{{ JSON.stringify(tool.input_schema, null, 2) }}</pre>
          </div>
        </div>
      </div>
      <el-empty v-if="!toolLoading && toolList.length === 0" description="暂无工具，请先测试连接" class="tool-drawer-empty" />
    </el-drawer>
  </div>
</template>

<style scoped>
.mcp-manage { width: 100% }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px }
.page-header h2 { margin: 0; font-size: 20px; color: var(--text-primary, #303133) }
.filter-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px }
.filter-left { display: flex; gap: 12px }
.filter-right { display: flex; gap: 12px }
.pagination-bar { display: flex; justify-content: flex-end; margin-top: 16px }
.inspection-config-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(59, 130, 246, 0.2);
  background: rgba(239, 246, 255, 0.6);
}

.inspection-config-title { font-size: 14px; font-weight: 600; color: var(--text-primary, #0f172a) }
.inspection-config-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap }
.inspection-config-unit { font-size: 13px; color: var(--text-secondary, #64748b); margin-right: 6px }
.inspection-config-hint { font-size: 12px; color: var(--text-secondary, #64748b) }
.op-actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  align-items: center;
}

.dialog-header,
.drawer-header {
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

.dialog-header-title,
.drawer-header-title {
  font-size: 24px;
  line-height: 1.3;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

.dialog-header-desc,
.drawer-header-desc {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-secondary, #64748b);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.tool-drawer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.tool-drawer-summary {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
}

.tool-drawer-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-bottom: 18px;
}

.tool-drawer-item {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 22px;
  padding: 16px 18px;
  background: #ffffff;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.tool-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.tool-drawer-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
}

.tool-drawer-desc {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  margin-top: 8px;
  line-height: 1.6;
}

.tool-drawer-schema {
  margin-top: 12px;
}

.tool-drawer-schema-title {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
  margin-bottom: 6px;
}

.tool-drawer-schema-code {
  background: #f8fafc;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 16px;
  padding: 12px 14px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 11px;
  color: var(--text-secondary, #475569);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 150px;
  overflow-y: auto;
  margin: 0;
}

.tool-drawer-empty {
  min-height: 220px;
  border: 1px dashed rgba(226, 232, 240, 0.95);
  border-radius: 22px;
  background: rgba(248, 250, 252, 0.72);
}

:global(.mcp-manage-dialog .el-dialog) {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 32px;
  background: #ffffff;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
  background-clip: padding-box;
}

:global(.mcp-manage-dialog .el-dialog__header) {
  margin: 0;
  padding: 24px 24px 0;
  border-radius: 32px 32px 0 0;
  background: inherit;
}

:global(.mcp-manage-dialog .el-dialog__body) {
  padding: 18px 24px 0;
  background: inherit;
}

:global(.mcp-manage-dialog .el-dialog__footer) {
  padding: 22px 24px 24px;
  border-radius: 0 0 32px 32px;
  background: inherit;
}

:global(.mcp-manage-dialog .el-dialog__headerbtn),
:global(.mcp-manage-drawer .el-drawer__headerbtn),
:global(.mcp-manage-confirm-dialog .el-message-box__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.mcp-manage-dialog .el-dialog__headerbtn .el-dialog__close),
:global(.mcp-manage-drawer .el-drawer__close-btn),
:global(.mcp-manage-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.mcp-manage-dialog .el-dialog__footer .el-button.dialog-btn),
:global(.mcp-manage-drawer .el-button.dialog-btn),
:global(.mcp-manage-confirm-dialog .el-message-box__btns .el-button) {
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

:global(.dialog-btn-compact) {
  min-width: 124px;
  height: 38px;
}

:global(.mcp-manage-drawer) {
  border-left: 1px solid rgba(226, 232, 240, 0.95);
  background: #ffffff;
}

:global(.mcp-manage-drawer .el-drawer__header) {
  margin-bottom: 0;
  padding: 24px 24px 0;
}

:global(.mcp-manage-drawer .el-drawer__body) {
  padding: 18px 24px 24px;
}

:global(.mcp-manage-confirm-dialog.el-message-box) {
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

:global(.mcp-manage-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.mcp-manage-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.mcp-manage-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.mcp-manage-confirm-dialog .el-message-box__message) {
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

:global(.mcp-manage-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.mcp-manage-confirm-dialog .mcp-manage-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.mcp-manage-confirm-dialog .mcp-manage-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.mcp-manage-confirm-dialog .mcp-manage-confirm-primary) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.mcp-manage-confirm-dialog .mcp-manage-confirm-primary:hover) {
  border-color: #fca5a5;
  background: #fef2f2;
  color: #b91c1c;
}

:global(html.dark) .dialog-header-badge {
  background: rgba(96, 165, 250, 0.14);
  color: #bfdbfe;
}

:global(html.dark) .dialog-header-title,
:global(html.dark) .drawer-header-title {
  color: #f8fafc;
}

:global(html.dark) .dialog-header-desc,
:global(html.dark) .drawer-header-desc,
:global(html.dark) .tool-drawer-summary,
:global(html.dark) .tool-drawer-desc,
:global(html.dark) .tool-drawer-schema-title,
:global(html.dark) .danger-confirm-detail {
  color: #94a3b8;
}

:global(html.dark .mcp-manage-dialog .el-dialog),
:global(html.dark .mcp-manage-drawer),
:global(html.dark .mcp-manage-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .mcp-manage-dialog .el-dialog__headerbtn .el-dialog__close),
:global(html.dark .mcp-manage-drawer .el-drawer__close-btn),
:global(html.dark .mcp-manage-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: #94a3b8;
}

:global(html.dark .dialog-btn-secondary),
:global(html.dark .mcp-manage-confirm-dialog .mcp-manage-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .dialog-btn-secondary:hover),
:global(html.dark .mcp-manage-confirm-dialog .mcp-manage-confirm-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}

:global(html.dark) .tool-drawer-item {
  border-color: rgba(148, 163, 184, 0.12);
  background: rgba(15, 23, 42, 0.32);
  box-shadow: none;
}

:global(html.dark) .tool-drawer-name,
:global(html.dark) .danger-confirm-subject,
:global(html.dark .mcp-manage-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}

:global(html.dark) .tool-drawer-schema-code {
  border-color: rgba(148, 163, 184, 0.12);
  background: rgba(15, 23, 42, 0.4);
  color: #cbd5e1;
}

:global(html.dark) .tool-drawer-empty {
  border-color: rgba(148, 163, 184, 0.14);
  background: rgba(15, 23, 42, 0.22);
}

:global(html.dark) .danger-confirm-badge {
  background: rgba(248, 113, 113, 0.14);
  color: #fca5a5;
}

:global(html.dark) .inspection-config-bar {
  border-color: rgba(96, 165, 250, 0.28);
  background: rgba(30, 58, 138, 0.12);
}
</style>
