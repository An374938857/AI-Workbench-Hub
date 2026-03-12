<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSceneTagList, createSceneTag, updateSceneTag, deleteSceneTag } from '@/api/admin/sceneTags'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { showDangerConfirm } from '@/composables/useDangerConfirm'

interface TagItem {
  id: number
  name: string
  sort_order: number
  is_active: boolean
}

const loading = ref(false)
const tags = ref<TagItem[]>([])

const dialogVisible = ref(false)
const dialogTitle = ref('新增标签')
const isEdit = ref(false)
const editingId = ref(0)
const formRef = ref<FormInstance>()
const form = ref({ name: '', sort_order: 0 })

const rules: FormRules = {
  name: [
    { required: true, message: '请输入标签名称', trigger: 'blur' },
    { max: 50, message: '最多 50 个字符', trigger: 'blur' },
  ],
}

async function fetchData() {
  loading.value = true
  try {
    const res: any = await getSceneTagList()
    tags.value = res.data
  } finally {
    loading.value = false
  }
}

function openCreate() {
  isEdit.value = false
  dialogTitle.value = '新增标签'
  form.value = { name: '', sort_order: 0 }
  dialogVisible.value = true
}

function openEdit(row: TagItem) {
  isEdit.value = true
  editingId.value = row.id
  dialogTitle.value = '编辑标签'
  form.value = { name: row.name, sort_order: row.sort_order }
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value?.validate()
  if (isEdit.value) {
    await updateSceneTag(editingId.value, form.value)
    ElMessage.success('标签更新成功')
  } else {
    await createSceneTag(form.value)
    ElMessage.success('标签创建成功')
  }
  dialogVisible.value = false
  fetchData()
}

async function handleToggle(row: TagItem) {
  const action = row.is_active ? '停用' : '启用'
  await updateSceneTag(row.id, { is_active: !row.is_active })
  ElMessage.success(`${action}成功`)
  fetchData()
}

async function handleDelete(row: TagItem) {
  await showDangerConfirm({
    title: '删除标签',
    subject: row.name,
    detail: '删除后该场景标签将无法再被使用，且不可恢复。',
    confirmText: '删除标签',
  })
  await deleteSceneTag(row.id)
  ElMessage.success('标签删除成功')
  fetchData()
}

onMounted(fetchData)
</script>

<template>
  <div class="scene-tag-manage">
    <div class="page-header">
      <h2>场景标签管理</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新增标签
      </el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="tags" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="标签名称" />
        <el-table-column prop="sort_order" label="排序权重" width="120">
          <template #default="{ row }">
            <el-tag type="info" size="small">{{ row.sort_order }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              link
              :type="row.is_active ? 'info' : 'success'"
              size="small"
              @click="handleToggle(row)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" width="460px" destroy-on-close class="scene-tag-dialog">
      <template #header>
        <div class="dialog-header">
          <div class="dialog-header-badge">{{ isEdit ? '标签维护' : '新建标签' }}</div>
          <div class="dialog-header-title">{{ dialogTitle }}</div>
          <div class="dialog-header-desc">维护场景标签名称与排序权重，前端展示与筛选都会生效。</div>
        </div>
      </template>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="标签名称" prop="name">
          <el-input v-model="form.name" placeholder="如：需求文档、会议管理" />
        </el-form-item>
        <el-form-item label="排序权重">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
          <span style="margin-left: 8px; color: var(--text-muted); font-size: 12px">数值越大排序越靠前</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button class="dialog-btn dialog-btn-secondary" @click="dialogVisible = false">取消</el-button>
          <el-button class="dialog-btn dialog-btn-primary" @click="handleSubmit">保存标签</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.scene-tag-manage {
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

:global(.scene-tag-dialog .el-dialog) {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 32px;
  background: #ffffff;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
  background-clip: padding-box;
}

:global(.scene-tag-dialog .el-dialog__header) {
  margin: 0;
  padding: 24px 24px 0;
  border-radius: 32px 32px 0 0;
  background: inherit;
}

:global(.scene-tag-dialog .el-dialog__body) {
  padding: 18px 24px 0;
  background: inherit;
}

:global(.scene-tag-dialog .el-dialog__footer) {
  padding: 22px 24px 24px;
  border-radius: 0 0 32px 32px;
  background: inherit;
}

:global(.scene-tag-dialog .el-dialog__headerbtn),
:global(.scene-tag-confirm-dialog .el-message-box__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.scene-tag-dialog .el-dialog__headerbtn .el-dialog__close),
:global(.scene-tag-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.scene-tag-dialog .el-dialog__footer .el-button.dialog-btn),
:global(.scene-tag-confirm-dialog .el-message-box__btns .el-button) {
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

:global(.scene-tag-confirm-dialog.el-message-box) {
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

:global(.scene-tag-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.scene-tag-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.scene-tag-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.scene-tag-confirm-dialog .el-message-box__message) {
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

:global(.scene-tag-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.scene-tag-confirm-dialog .scene-tag-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.scene-tag-confirm-dialog .scene-tag-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.scene-tag-confirm-dialog .scene-tag-confirm-danger) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.scene-tag-confirm-dialog .scene-tag-confirm-danger:hover) {
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

:global(html.dark .scene-tag-dialog .el-dialog),
:global(html.dark .scene-tag-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .scene-tag-dialog .el-dialog__headerbtn .el-dialog__close),
:global(html.dark .scene-tag-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: #94a3b8;
}

:global(html.dark .dialog-btn-secondary),
:global(html.dark .scene-tag-confirm-dialog .scene-tag-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .dialog-btn-secondary:hover),
:global(html.dark .scene-tag-confirm-dialog .scene-tag-confirm-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}

:global(html.dark) .danger-confirm-badge {
  background: rgba(248, 113, 113, 0.14);
  color: #fca5a5;
}

:global(html.dark) .danger-confirm-subject,
:global(html.dark .scene-tag-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}
</style>
