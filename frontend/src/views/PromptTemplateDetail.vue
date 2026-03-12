<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { showDangerConfirm } from '@/composables/useDangerConfirm'
import { useAuthStore } from '@/stores/auth'
import {
  createTemplate,
  createTemplateVersion,
  deleteTemplate,
  duplicateTemplate,
  getTemplate,
  getTemplateStats,
  getTemplateVersions,
  restoreTemplateVersion,
  setGlobalDefault,
  toggleFavorite,
  updateTemplate,
  type PromptTemplate,
  type PromptTemplateStats,
  type PromptTemplateVersion,
} from '@/api/promptTemplates'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const templateId = computed(() => Number(route.params.id || 0))
const isCreateMode = computed(() => route.name === 'PromptTemplateNew' || !templateId.value)

const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const savingVersion = ref(false)
const restoringVersionId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const template = ref<PromptTemplate | null>(null)
const stats = ref<PromptTemplateStats | null>(null)
const versions = ref<PromptTemplateVersion[]>([])
const versionNote = ref('')

const form = reactive({
  name: '',
  category: 'role',
  visibility: 'personal',
  priority: 50,
  content: '',
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
  content: [{ required: true, message: '请输入模板内容', trigger: 'blur' }],
}

const isAdmin = computed(() => authStore.user?.role === 'admin')

const canEdit = computed(() => {
  if (isCreateMode.value) return true
  if (!template.value) return false
  if (template.value.is_builtin) return false
  if (template.value.visibility === 'public') return isAdmin.value
  return template.value.created_by === authStore.user?.id || isAdmin.value
})

function formatDate(dateText: string | null | undefined): string {
  if (!dateText) return '-'
  return new Date(dateText).toLocaleString('zh-CN')
}

function categoryLabel(value: string): string {
  const map: Record<string, string> = {
    role: '角色',
    style: '风格',
    domain: '领域',
    personal: '个人',
  }
  return map[value] || value
}

function applyTemplateToForm(item: PromptTemplate) {
  form.name = item.name
  form.category = item.category
  form.visibility = item.visibility
  form.priority = item.priority
  form.content = item.content
}

async function loadDetail() {
  if (isCreateMode.value) return
  loading.value = true
  try {
    const [detailRes, statsRes, versionsRes] = await Promise.all([
      getTemplate(templateId.value),
      getTemplateStats(templateId.value),
      getTemplateVersions(templateId.value),
    ])
    template.value = detailRes.data as PromptTemplate
    stats.value = statsRes.data as PromptTemplateStats
    versions.value = (versionsRes.data as PromptTemplateVersion[]) || []
    applyTemplateToForm(template.value)
  } finally {
    loading.value = false
  }
}

async function saveTemplate() {
  await formRef.value?.validate()
  saving.value = true
  try {
    const payload = {
      name: form.name,
      category: form.category,
      visibility: form.visibility,
      priority: form.priority,
      content: form.content,
    }
    if (isCreateMode.value) {
      const res = await createTemplate(payload)
      ElMessage.success('模板创建成功')
      router.replace(`/prompt-templates/${res.data.id}`)
      return
    }

    await updateTemplate(templateId.value, payload)
    ElMessage.success('模板已保存')
    await loadDetail()
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (isCreateMode.value || !template.value) return
  await showDangerConfirm({
    title: '删除模板',
    subject: template.value.name,
    detail: '删除后模板不可恢复，且会从所有视图中移除。',
    confirmText: '删除模板',
  })
  deleting.value = true
  try {
    await deleteTemplate(template.value.id)
    ElMessage.success('删除成功')
    router.push('/prompt-templates')
  } finally {
    deleting.value = false
  }
}

async function handleDuplicate() {
  if (isCreateMode.value || !template.value) return
  const res = await duplicateTemplate(template.value.id)
  ElMessage.success('模板复制成功')
  router.push(`/prompt-templates/${res.data.id}`)
}

async function handleFavorite() {
  if (isCreateMode.value || !template.value) return
  const res = await toggleFavorite(template.value.id)
  template.value.is_favorited = !!res.data?.is_favorited
  ElMessage.success(template.value.is_favorited ? '收藏成功' : '已取消收藏')
}

async function handleSetDefault() {
  if (isCreateMode.value || !template.value) return
  await showDangerConfirm({
    title: '设为全局默认',
    subject: template.value.name,
    detail: '该模板将成为所有新对话的默认提示词模板。',
    confirmText: '确认设置',
    confirmType: 'primary',
  })
  await setGlobalDefault(template.value.id)
  ElMessage.success('设置成功')
  await loadDetail()
}

async function handleCreateVersion() {
  if (isCreateMode.value || !template.value) return
  savingVersion.value = true
  try {
    await createTemplateVersion(template.value.id, versionNote.value || undefined)
    versionNote.value = ''
    ElMessage.success('版本已保存')
    await loadDetail()
  } finally {
    savingVersion.value = false
  }
}

async function handleRestoreVersion(item: PromptTemplateVersion) {
  if (isCreateMode.value || !template.value) return
  await showDangerConfirm({
    title: '恢复版本',
    subject: `v${item.version_no}`,
    detail: '恢复后当前内容会被覆盖，请确认已保存必要信息。',
    confirmText: '确认恢复',
    confirmType: 'primary',
  })
  restoringVersionId.value = item.id
  try {
    await restoreTemplateVersion(template.value.id, item.id)
    ElMessage.success(`已恢复到版本 v${item.version_no}`)
    await loadDetail()
  } finally {
    restoringVersionId.value = null
  }
}

onMounted(() => {
  void loadDetail()
})
</script>

<template>
  <div class="prompt-detail" v-loading="loading">
    <div class="detail-header">
      <div class="title-wrap">
        <el-button text @click="router.push('/prompt-templates')">
          <el-icon><ArrowLeft /></el-icon>
          返回列表
        </el-button>
        <h1>{{ isCreateMode ? '新建提示词模板' : '提示词详情管理' }}</h1>
        <p>{{ isCreateMode ? '创建可复用的提示词模板' : '高级维护：编辑、复制、版本化与统计分析' }}</p>
      </div>
      <div class="header-actions">
        <el-button v-if="!isCreateMode" @click="handleFavorite">
          {{ template?.is_favorited ? '取消收藏' : '收藏' }}
        </el-button>
        <el-button v-if="!isCreateMode" @click="handleDuplicate">复制模板</el-button>
        <el-button v-if="!isCreateMode && isAdmin && template && !template.is_global_default" type="warning" @click="handleSetDefault">
          设为全局默认
        </el-button>
        <el-button type="primary" :loading="saving" :disabled="!canEdit" @click="saveTemplate">保存</el-button>
        <el-button
          v-if="!isCreateMode"
          type="danger"
          plain
          :loading="deleting"
          :disabled="!canEdit || !!template?.is_builtin || !!template?.is_global_default"
          @click="handleDelete"
        >
          删除
        </el-button>
      </div>
    </div>

    <div class="detail-body">
      <aside class="meta-panel">
        <section class="meta-card">
          <h3>模板信息</h3>
          <div class="meta-item"><label>状态</label><span>{{ template?.is_builtin ? '内置只读' : (canEdit ? '可编辑' : '只读') }}</span></div>
          <div class="meta-item"><label>创建时间</label><span>{{ formatDate(template?.created_at) }}</span></div>
          <div class="meta-item"><label>更新时间</label><span>{{ formatDate(template?.updated_at) }}</span></div>
          <div class="meta-item"><label>分类</label><span>{{ categoryLabel(form.category) }}</span></div>
          <div class="meta-item"><label>可见性</label><span>{{ form.visibility === 'public' ? '公开' : '个人' }}</span></div>
        </section>

        <section class="meta-card">
          <h3>使用统计</h3>
          <div class="stat-grid">
            <div class="stat-box">
              <strong>{{ stats?.conversation_count ?? 0 }}</strong>
              <span>会话引用</span>
            </div>
            <div class="stat-box">
              <strong>{{ stats?.favorite_count ?? 0 }}</strong>
              <span>收藏人数</span>
            </div>
            <div class="stat-box">
              <strong>{{ stats?.version_count ?? 0 }}</strong>
              <span>版本数量</span>
            </div>
            <div class="stat-box">
              <strong>{{ stats?.last_used_at ? formatDate(stats.last_used_at) : '-' }}</strong>
              <span>最近使用</span>
            </div>
          </div>
        </section>
      </aside>

      <main class="editor-panel">
        <section class="editor-card">
          <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
            <div class="form-grid">
              <el-form-item label="模板名称" prop="name">
                <el-input v-model="form.name" :disabled="!canEdit" maxlength="100" show-word-limit />
              </el-form-item>
              <el-form-item label="优先级">
                <el-input-number v-model="form.priority" :disabled="!canEdit" :min="1" :max="100" style="width: 100%" />
              </el-form-item>
            </div>

            <div class="form-grid">
              <el-form-item label="分类" prop="category">
                <el-select v-model="form.category" :disabled="!canEdit">
                  <el-option label="角色" value="role" />
                  <el-option label="风格" value="style" />
                  <el-option label="领域" value="domain" />
                  <el-option label="个人" value="personal" />
                </el-select>
              </el-form-item>
              <el-form-item label="可见性">
                <el-radio-group v-model="form.visibility" :disabled="!canEdit">
                  <el-radio value="personal">个人</el-radio>
                  <el-radio value="public">公开</el-radio>
                </el-radio-group>
              </el-form-item>
            </div>

            <el-form-item label="提示词内容" prop="content">
              <el-input
                v-model="form.content"
                type="textarea"
                :rows="14"
                :disabled="!canEdit"
                placeholder="输入完整提示词模板内容"
              />
            </el-form-item>
          </el-form>
        </section>

        <section v-if="!isCreateMode" class="editor-card">
          <div class="version-head">
            <h3>版本管理</h3>
            <div class="version-actions">
              <el-input
                v-model="versionNote"
                placeholder="版本备注（可选）"
                style="width: 260px"
                clearable
              />
              <el-button type="primary" :disabled="!canEdit" :loading="savingVersion" @click="handleCreateVersion">
                保存快照
              </el-button>
            </div>
          </div>

          <el-table :data="versions" size="small">
            <el-table-column prop="version_no" label="版本号" width="90">
              <template #default="{ row }">v{{ row.version_no }}</template>
            </el-table-column>
            <el-table-column prop="note" label="备注" min-width="240" />
            <el-table-column prop="created_at" label="创建时间" width="180">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button
                  text
                  type="primary"
                  :loading="restoringVersionId === row.id"
                  :disabled="!canEdit"
                  @click="handleRestoreVersion(row)"
                >
                  恢复
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>
      </main>
    </div>
  </div>
</template>

<style scoped>
.prompt-detail {
  max-width: 1280px;
  margin: 0 auto;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 6px 0 18px;
}

.title-wrap h1 {
  margin: 8px 0 6px;
  font-size: 24px;
  color: var(--text-primary, #303133);
}

.title-wrap p {
  margin: 0;
  color: var(--text-muted, #6b7280);
  font-size: 14px;
}

.header-actions {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px;
}

.detail-body {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
}

.meta-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.meta-card,
.editor-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-primary, #ebeef5);
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 2px 8px rgba(0, 0, 0, 0.02);
}

.meta-card h3,
.editor-card h3 {
  margin: 0 0 12px;
  font-size: 15px;
  color: var(--text-primary, #303133);
}

.meta-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 0;
  border-bottom: 1px dashed var(--border-light, #f2f3f5);
  color: var(--text-secondary, #606266);
  font-size: 13px;
}

.meta-item:last-child {
  border-bottom: 0;
}

.meta-item label {
  color: var(--text-muted, #6b7280);
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.stat-box {
  border: 1px solid var(--border-light, #f2f3f5);
  border-radius: 12px;
  padding: 10px;
  background: var(--bg-page, #f5f7fa);
}

.stat-box strong {
  display: block;
  font-size: 14px;
  color: var(--text-primary, #303133);
  margin-bottom: 4px;
}

.stat-box span {
  color: var(--text-muted, #6b7280);
  font-size: 12px;
}

.editor-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 220px;
  gap: 12px;
}

.version-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}

.version-head h3 {
  margin: 0;
}

.version-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 1024px) {
  .detail-body {
    grid-template-columns: 1fr;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}

:global(.prompt-detail-confirm-dialog.el-message-box) {
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

:global(.prompt-detail-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.prompt-detail-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.prompt-detail-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.prompt-detail-confirm-dialog .el-message-box__message) {
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

:global(.prompt-detail-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.prompt-detail-confirm-dialog .prompt-detail-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.prompt-detail-confirm-dialog .prompt-detail-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.prompt-detail-confirm-dialog .prompt-detail-confirm-primary) {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  color: #2563eb;
  box-shadow: none;
}

:global(.prompt-detail-confirm-dialog .prompt-detail-confirm-primary:hover) {
  border-color: #bfdbfe;
  background: #dbeafe;
  color: #1d4ed8;
}

:global(.prompt-detail-confirm-dialog .prompt-detail-confirm-danger) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.prompt-detail-confirm-dialog .prompt-detail-confirm-danger:hover) {
  border-color: #fca5a5;
  background: #fef2f2;
  color: #b91c1c;
}

:global(html.dark .prompt-detail-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .prompt-detail-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}

:global(html.dark .danger-confirm-badge) {
  background: rgba(248, 113, 113, 0.14);
  color: #fca5a5;
}

:global(html.dark .danger-confirm-subject) {
  color: #f8fafc;
}

:global(html.dark .danger-confirm-detail) {
  color: #94a3b8;
}
</style>
