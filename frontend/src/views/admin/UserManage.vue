<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  getUserList,
  createUser,
  updateUser,
  resetUserPassword,
  approveUser,
  deleteUser,
  getUserDeleteCheck,
} from '@/api/admin/users'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { showDangerConfirm } from '@/composables/useDangerConfirm'

interface UserItem {
  id: number
  username: string
  display_name: string
  role: string
  is_active: boolean
  is_approved: boolean
  created_at: string
}

const loading = ref(false)
const tableData = ref<UserItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')

// 新增/编辑弹窗
const dialogVisible = ref(false)
const dialogTitle = ref('新增用户')
const isEdit = ref(false)
const editingId = ref(0)
const formRef = ref<FormInstance>()
const form = ref({
  username: '',
  password: '',
  display_name: '',
  role: 'user',
})

const rules: FormRules = {
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    { min: 2, max: 50, message: '长度 2-50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 50, message: '长度 6-50 个字符', trigger: 'blur' },
  ],
  display_name: [
    { required: true, message: '请输入显示名称', trigger: 'blur' },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

// 重置密码弹窗
const resetPwdVisible = ref(false)
const resetPwdId = ref(0)
const resetPwdName = ref('')
const resetPwdFormRef = ref<FormInstance>()
const resetPwdForm = ref({ new_password: '' })

const roleMap: Record<string, { label: string; type: string }> = {
  user: { label: '普通用户', type: '' },
  provider: { label: '技能管理员', type: 'warning' },
  admin: { label: '超级管理员', type: 'danger' },
}

async function fetchData() {
  loading.value = true
  try {
    const res: any = await getUserList({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    })
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  fetchData()
}

function handlePageChange(val: number) {
  page.value = val
  fetchData()
}

function openCreate() {
  isEdit.value = false
  dialogTitle.value = '新增用户'
  form.value = { username: '', password: '', display_name: '', role: 'user' }
  dialogVisible.value = true
}

function openEdit(row: UserItem) {
  isEdit.value = true
  editingId.value = row.id
  dialogTitle.value = '编辑用户'
  form.value = {
    username: row.username,
    password: '',
    display_name: row.display_name,
    role: row.role,
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value?.validate()
  if (isEdit.value) {
    await updateUser(editingId.value, {
      display_name: form.value.display_name,
      role: form.value.role,
    })
    ElMessage.success('用户更新成功')
  } else {
    await createUser(form.value)
    ElMessage.success('用户创建成功')
  }
  dialogVisible.value = false
  fetchData()
}

async function handleToggleActive(row: UserItem) {
  const action = row.is_active ? '停用' : '启用'
  await showDangerConfirm({
    title: `${action}用户`,
    subject: row.display_name,
    detail: action === '停用'
      ? '停用后该用户将无法登录，但数据不会被删除。'
      : '启用后该用户可重新登录并使用相关功能。',
    confirmText: `确认${action}`,
    confirmType: 'primary',
  })
  await updateUser(row.id, { is_active: !row.is_active })
  ElMessage.success(`${action}成功`)
  fetchData()
}

function openResetPassword(row: UserItem) {
  resetPwdId.value = row.id
  resetPwdName.value = row.display_name
  resetPwdForm.value = { new_password: '' }
  resetPwdVisible.value = true
}

async function handleResetPassword() {
  await resetPwdFormRef.value?.validate()
  await resetUserPassword(resetPwdId.value, resetPwdForm.value.new_password)
  ElMessage.success('密码重置成功')
  resetPwdVisible.value = false
}

async function handleApprove(row: UserItem) {
  await showDangerConfirm({
    title: '审核通过',
    subject: row.display_name,
    detail: '审核通过后该用户将可以正常登录并使用平台能力。',
    confirmText: '确认通过',
    confirmType: 'primary',
  })
  await approveUser(row.id)
  ElMessage.success('审核通过')
  fetchData()
}

async function handleDelete(row: UserItem) {
  await showDangerConfirm({
    title: '删除用户',
    subject: row.display_name,
    detail: '删除后将无法恢复该账号信息，请确认已完成必要的数据备份。',
    confirmText: '删除用户',
  })

  const checkRes: any = await getUserDeleteCheck(row.id)
  const checkData = checkRes?.data || {}
  let forceTransfer = false

  if (checkData.has_related_owner_data) {
    await showDangerConfirm({
      title: '关联数据处理',
      subject: row.display_name,
      detail: `该用户仍有创建者关联数据：Skill ${checkData.skill_count} 个、MCP ${checkData.mcp_count} 个。继续删除将自动把这些归属转移到超级管理员。`,
      confirmText: '继续删除并转移',
    })
    forceTransfer = true
  }

  await deleteUser(row.id, forceTransfer)
  ElMessage.success('用户删除成功')
  fetchData()
}

function formatTime(val: string) {
  if (!val) return '-'
  return val.replace('T', ' ').substring(0, 19)
}

onMounted(fetchData)
</script>

<template>
  <div class="user-manage">
    <div class="page-header">
      <h2>用户管理</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新增用户
      </el-button>
    </div>

    <el-card shadow="never">
      <div class="filter-bar">
        <el-input
          v-model="keyword"
          placeholder="搜索账号/名称"
          clearable
          style="width: 260px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button @click="handleSearch">搜索</el-button>
      </div>

      <el-table :data="tableData" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="账号" width="140" />
        <el-table-column prop="display_name" label="显示名称" width="140" />
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="(roleMap[row.role]?.type as any) || 'info'" size="small">
              {{ roleMap[row.role]?.label || row.role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="!row.is_approved" type="warning" size="small">待审核</el-tag>
            <el-tag v-else :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '正常' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="280" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_approved"
              link
              type="success"
              size="small"
              @click="handleApprove(row)"
            >审核通过</el-button>
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" size="small" @click="openResetPassword(row)">重置密码</el-button>
            <el-button
              link
              :type="row.is_active ? 'info' : 'success'"
              size="small"
              @click="handleToggleActive(row)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" width="520px" destroy-on-close class="user-manage-dialog">
      <template #header>
        <div class="dialog-header">
          <div class="dialog-header-badge">{{ isEdit ? '成员维护' : '成员录入' }}</div>
          <div class="dialog-header-title">{{ dialogTitle }}</div>
          <div class="dialog-header-desc">维护用户基本资料与角色权限，变更后即时生效。</div>
        </div>
      </template>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="账号" prop="username">
          <el-input v-model="form.username" :disabled="isEdit" placeholder="请输入账号" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="初始密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入初始密码" show-password />
        </el-form-item>
        <el-form-item label="显示名称" prop="display_name">
          <el-input v-model="form.display_name" placeholder="请输入显示名称" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="普通用户" value="user" />
            <el-option label="技能管理员" value="provider" />
            <el-option label="超级管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button class="dialog-btn dialog-btn-secondary" @click="dialogVisible = false">取消</el-button>
          <el-button class="dialog-btn dialog-btn-primary" @click="handleSubmit">确认保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗 -->
    <el-dialog v-model="resetPwdVisible" width="440px" destroy-on-close class="user-manage-dialog">
      <template #header>
        <div class="dialog-header">
          <div class="dialog-header-badge">安全操作</div>
          <div class="dialog-header-title">重置密码</div>
          <div class="dialog-header-desc">为该用户设置新的登录密码，提交后立即生效。</div>
        </div>
      </template>
      <p style="margin-bottom: 16px; color: var(--text-secondary)">
        为用户「<strong>{{ resetPwdName }}</strong>」设置新密码：
      </p>
      <el-form ref="resetPwdFormRef" :model="resetPwdForm">
        <el-form-item
          prop="new_password"
          :rules="[
            { required: true, message: '请输入新密码', trigger: 'blur' },
            { min: 6, max: 50, message: '长度 6-50 个字符', trigger: 'blur' },
          ]"
        >
          <el-input
            v-model="resetPwdForm.new_password"
            type="password"
            placeholder="请输入新密码"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button class="dialog-btn dialog-btn-secondary" @click="resetPwdVisible = false">取消</el-button>
          <el-button class="dialog-btn dialog-btn-primary" @click="handleResetPassword">确认重置</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.user-manage {
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

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
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

:global(.user-manage-dialog .el-dialog) {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 32px;
  background: #ffffff;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
  background-clip: padding-box;
}

:global(.user-manage-dialog .el-dialog__header) {
  margin: 0;
  padding: 24px 24px 0;
  border-radius: 32px 32px 0 0;
  background: inherit;
}

:global(.user-manage-dialog .el-dialog__body) {
  padding: 18px 24px 0;
  background: inherit;
}

:global(.user-manage-dialog .el-dialog__footer) {
  padding: 22px 24px 24px;
  border-radius: 0 0 32px 32px;
  background: inherit;
}

:global(.user-manage-dialog .el-dialog__headerbtn),
:global(.user-manage-confirm-dialog .el-message-box__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.user-manage-dialog .el-dialog__headerbtn .el-dialog__close),
:global(.user-manage-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.user-manage-dialog .el-dialog__footer .el-button.dialog-btn),
:global(.user-manage-confirm-dialog .el-message-box__btns .el-button) {
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

:global(.user-manage-confirm-dialog.el-message-box) {
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

:global(.user-manage-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.user-manage-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.user-manage-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.user-manage-confirm-dialog .el-message-box__message) {
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

:global(.user-manage-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.user-manage-confirm-dialog .user-manage-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.user-manage-confirm-dialog .user-manage-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.user-manage-confirm-dialog .user-manage-confirm-primary) {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  color: #2563eb;
  box-shadow: none;
}

:global(.user-manage-confirm-dialog .user-manage-confirm-primary:hover) {
  border-color: #bfdbfe;
  background: #dbeafe;
  color: #1d4ed8;
}

:global(.user-manage-confirm-dialog .user-manage-confirm-danger) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.user-manage-confirm-dialog .user-manage-confirm-danger:hover) {
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

:global(html.dark .user-manage-dialog .el-dialog),
:global(html.dark .user-manage-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .user-manage-dialog .el-dialog__headerbtn .el-dialog__close),
:global(html.dark .user-manage-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: #94a3b8;
}

:global(html.dark .dialog-btn-secondary),
:global(html.dark .user-manage-confirm-dialog .user-manage-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .dialog-btn-secondary:hover),
:global(html.dark .user-manage-confirm-dialog .user-manage-confirm-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}

:global(html.dark) .danger-confirm-badge {
  background: rgba(248, 113, 113, 0.14);
  color: #fca5a5;
}

:global(html.dark) .danger-confirm-subject,
:global(html.dark .user-manage-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}
</style>
