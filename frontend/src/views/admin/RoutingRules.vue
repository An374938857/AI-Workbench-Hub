<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getRoutingRules, createRoutingRule, updateRoutingRule, deleteRoutingRule, type RoutingRule } from '@/api/admin/routingRules'
import { getAvailableModels } from '@/api/models'
import { showDangerConfirm } from '@/composables/useDangerConfirm'

const TAG_LABELS: Record<string, string> = {
  reasoning: '推理', creative_writing: '创意写作', coding: '代码', data_analysis: '数据分析',
  fast_response: '快速响应', deep_thinking: '深度思考', multimodal: '多模态', long_context: '超长上下文',
}
const ALL_TAGS = Object.keys(TAG_LABELS)

const loading = ref(false)
const rules = ref<RoutingRule[]>([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref<number | null>(null)
const keywordsInput = ref('')
const modelOptions = ref<{ label: string; value: string }[]>([])

async function loadModels() {
  try {
    const res: any = await getAvailableModels()
    const providers = res.data?.providers || []
    modelOptions.value = providers.flatMap((p: any) =>
      p.models.map((m: any) => ({ label: `${p.provider_name} / ${m.display_name || m.model_name}`, value: `${p.provider_id}:${m.model_name}` }))
    )
  } catch { /* ignore */ }
}

const form = ref({
  intent_category: '',
  display_name: '',
  keywords: [] as string[],
  preferred_tags: [] as string[],
  preferred_model: '',
  priority: 0,
  is_enabled: true,
})

async function loadRules() {
  loading.value = true
  try {
    const res: any = await getRoutingRules()
    rules.value = res.data?.items || []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  isEdit.value = false
  editId.value = null
  form.value = { intent_category: '', display_name: '', keywords: [], preferred_tags: [], preferred_model: '', priority: 0, is_enabled: true }
  keywordsInput.value = ''
  dialogVisible.value = true
}

function openEdit(rule: RoutingRule) {
  isEdit.value = true
  editId.value = rule.id
  form.value = { ...rule, preferred_model: rule.preferred_model || '' }
  keywordsInput.value = (rule.keywords || []).join('、')
  dialogVisible.value = true
}

async function handleSave() {
  form.value.keywords = keywordsInput.value.split(/[,，、\s]+/).filter(Boolean)
  if (!form.value.intent_category || !form.value.display_name || form.value.keywords.length === 0) {
    ElMessage.warning('请填写意图类别、显示名和关键词')
    return
  }
  const data = { ...form.value, preferred_model: form.value.preferred_model || null }
  try {
    if (isEdit.value && editId.value) {
      await updateRoutingRule(editId.value, data)
      ElMessage.success('更新成功')
    } else {
      await createRoutingRule(data)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadRules()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '操作失败')
  }
}

async function handleDelete(rule: RoutingRule) {
  await showDangerConfirm({
    title: '删除路由规则',
    subject: rule.display_name,
    detail: '删除后该路由规则将不再生效，且不可恢复。',
    confirmText: '删除规则',
  })
  await deleteRoutingRule(rule.id)
  ElMessage.success('删除成功')
  await loadRules()
}

onMounted(() => { loadRules(); loadModels() })
</script>

<template>
  <div class="routing-rules" v-loading="loading">
    <el-card shadow="never" class="rules-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">路由规则管理</span>
          <el-button type="primary" size="small" @click="openCreate">新增规则</el-button>
        </div>
      </template>

      <el-table :data="rules" stripe size="small">
        <el-table-column prop="intent_category" label="意图类别" width="120" />
        <el-table-column prop="display_name" label="显示名" width="120" />
        <el-table-column label="关键词" min-width="200">
          <template #default="{ row }">
            <el-tag v-for="kw in (row.keywords || []).slice(0, 8)" :key="kw" size="small" style="margin: 2px">{{ kw }}</el-tag>
            <span v-if="(row.keywords || []).length > 8" style="color:#999;font-size:12px"> +{{ row.keywords.length - 8 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="首选标签" width="160">
          <template #default="{ row }">
            <el-tag v-for="t in row.preferred_tags" :key="t" size="small" type="success" style="margin: 2px">{{ TAG_LABELS[t] || t }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="preferred_model" label="首选模型" width="180">
          <template #default="{ row }">{{ modelOptions.find(o => o.value === row.preferred_model)?.label || row.preferred_model || '-' }}</template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="70" />
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">{{ row.is_enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" width="620px" destroy-on-close class="routing-rules-dialog">
      <template #header>
        <div class="dialog-header">
          <div class="dialog-header-badge">{{ isEdit ? '规则调整' : '新建规则' }}</div>
          <div class="dialog-header-title">{{ isEdit ? '编辑路由规则' : '新增路由规则' }}</div>
          <div class="dialog-header-desc">定义意图关键词和模型偏好，帮助系统准确路由到最合适的模型。</div>
        </div>
      </template>
      <el-form :model="form" label-width="100px">
        <el-form-item label="意图类别">
          <el-input v-model="form.intent_category" placeholder="如 coding、creative_writing" />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="form.display_name" placeholder="如 代码相关问题" />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="keywordsInput" type="textarea" :rows="3" placeholder="用逗号、顿号或空格分隔，如：代码、编程、bug、函数" />
        </el-form-item>
        <el-form-item label="首选标签">
          <el-checkbox-group v-model="form.preferred_tags">
            <el-checkbox v-for="tag in ALL_TAGS" :key="tag" :label="tag">{{ TAG_LABELS[tag] }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="首选模型">
          <el-select v-model="form.preferred_model" placeholder="不指定" clearable style="width: 100%">
            <el-option v-for="opt in modelOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="form.priority" :min="0" :max="100" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button class="dialog-btn dialog-btn-secondary" @click="dialogVisible = false">取消</el-button>
          <el-button class="dialog-btn dialog-btn-primary" @click="handleSave">保存规则</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.routing-rules { width: 100%; }
.rules-card {
  border: 1px solid var(--border-primary, #e5e7eb);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
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

:global(.routing-rules-dialog .el-dialog) {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 32px;
  background: #ffffff;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
  background-clip: padding-box;
}

:global(.routing-rules-dialog .el-dialog__header) {
  margin: 0;
  padding: 24px 24px 0;
  border-radius: 32px 32px 0 0;
  background: inherit;
}

:global(.routing-rules-dialog .el-dialog__body) {
  padding: 18px 24px 0;
  background: inherit;
}

:global(.routing-rules-dialog .el-dialog__footer) {
  padding: 22px 24px 24px;
  border-radius: 0 0 32px 32px;
  background: inherit;
}

:global(.routing-rules-dialog .el-dialog__headerbtn),
:global(.routing-rules-confirm-dialog .el-message-box__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.routing-rules-dialog .el-dialog__headerbtn .el-dialog__close),
:global(.routing-rules-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.routing-rules-dialog .el-dialog__footer .el-button.dialog-btn),
:global(.routing-rules-confirm-dialog .el-message-box__btns .el-button) {
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

:global(.routing-rules-confirm-dialog.el-message-box) {
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

:global(.routing-rules-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.routing-rules-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.routing-rules-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.routing-rules-confirm-dialog .el-message-box__message) {
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

:global(.routing-rules-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.routing-rules-confirm-dialog .routing-rules-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.routing-rules-confirm-dialog .routing-rules-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.routing-rules-confirm-dialog .routing-rules-confirm-danger) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.routing-rules-confirm-dialog .routing-rules-confirm-danger:hover) {
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

:global(html.dark .routing-rules-dialog .el-dialog),
:global(html.dark .routing-rules-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .routing-rules-dialog .el-dialog__headerbtn .el-dialog__close),
:global(html.dark .routing-rules-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: #94a3b8;
}

:global(html.dark .dialog-btn-secondary),
:global(html.dark .routing-rules-confirm-dialog .routing-rules-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .dialog-btn-secondary:hover),
:global(html.dark .routing-rules-confirm-dialog .routing-rules-confirm-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}

:global(html.dark) .danger-confirm-badge {
  background: rgba(248, 113, 113, 0.14);
  color: #fca5a5;
}

:global(html.dark) .danger-confirm-subject,
:global(html.dark .routing-rules-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}
</style>
