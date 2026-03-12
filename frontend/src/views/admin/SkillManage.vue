<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getAdminSkillList, publishSkill, offlineSkill, onlineSkill, deleteSkill } from '@/api/admin/skills'
import request from '@/api/request'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { showDangerConfirm } from '@/composables/useDangerConfirm'

interface SkillItem {
  id: number
  name: string
  icon_url: string | null
  icon_emoji: string | null
  status: string
  published_version: number | null
  draft_version: number | null
  use_count: number
  tags: { id: number; name: string }[]
  creator_name: string
  updated_at: string
}

const router = useRouter()
const loading = ref(false)
const tableData = ref<SkillItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const statusFilter = ref('')

const publishDialogVisible = ref(false)
const publishSkillId = ref(0)
const publishFormRef = ref<FormInstance>()
const publishForm = ref({ change_log: '' })

const feedbackVisible = ref(false)
const feedbackSkillName = ref('')
const feedbackList = ref<any[]>([])
const feedbackLoading = ref(false)

async function openFeedbacks(row: SkillItem) {
  feedbackSkillName.value = row.name
  feedbackVisible.value = true
  feedbackLoading.value = true
  try {
    const res: any = await request.get(`/admin/skills/${row.id}/feedbacks`, { params: { page: 1, page_size: 50 } })
    feedbackList.value = res.data.items
  } finally {
    feedbackLoading.value = false
  }
}

const statusMap: Record<string, { label: string; type: string }> = {
  draft: { label: '草稿', type: 'info' },
  published: { label: '已发布', type: 'success' },
  offline: { label: '已下架', type: 'warning' },
}

async function fetchData() {
  loading.value = true
  try {
    const res: any = await getAdminSkillList({
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

function openPublishDialog(id: number) {
  publishSkillId.value = id
  publishForm.value = { change_log: '' }
  publishDialogVisible.value = true
}

async function handlePublish() {
  await publishFormRef.value?.validate()
  await publishSkill(publishSkillId.value, publishForm.value.change_log)
  ElMessage.success('发布成功')
  publishDialogVisible.value = false
  fetchData()
}

async function handleOffline(row: SkillItem) {
  await showDangerConfirm({
    title: '下架 Skill',
    subject: row.name,
    detail: '下架后用户将暂时不可见，但不会删除已有数据。',
    confirmText: '确认下架',
  })
  await offlineSkill(row.id)
  ElMessage.success('已下架')
  fetchData()
}

async function handleOnline(row: SkillItem) {
  await onlineSkill(row.id)
  ElMessage.success('已上架')
  fetchData()
}

async function handleDelete(row: SkillItem) {
  await showDangerConfirm({
    title: '删除 Skill',
    subject: row.name,
    detail: '删除后将无法恢复，相关版本和配置也会一起移除。',
    confirmText: '删除 Skill',
  })
  await deleteSkill(row.id)
  ElMessage.success('删除成功')
  fetchData()
}

function formatTime(val: string) {
  if (!val) return '-'
  return val.replace('T', ' ').substring(0, 16)
}

onMounted(fetchData)
</script>

<template>
  <div class="skill-manage">
    <div class="page-header">
      <h2>Skill 管理</h2>
      <el-button type="primary" @click="router.push('/admin/skills/new')">
        <el-icon><Plus /></el-icon> 新建 Skill
      </el-button>
    </div>

    <el-card shadow="never">
      <div class="filter-bar">
        <el-input
          v-model="keyword"
          placeholder="搜索 Skill 名称"
          clearable
          style="width: 240px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button @click="handleSearch">搜索</el-button>
      </div>

      <el-table :data="tableData" v-loading="loading" stripe>
        <el-table-column label="名称" min-width="160">
          <template #default="{ row }">
            <div class="skill-name-cell">
              <img v-if="row.icon_url" :src="row.icon_url" class="skill-icon skill-icon-img" />
              <span v-else-if="row.icon_emoji" class="skill-icon skill-icon-emoji">{{ row.icon_emoji }}</span>
              <span v-else class="skill-icon skill-icon-default">
                <el-icon :size="16"><MagicStick /></el-icon>
              </span>
              <span class="skill-name-text">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="(statusMap[row.status]?.type as any) || 'info'" size="small">
              {{ statusMap[row.status]?.label || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="110">
          <template #default="{ row }">
            <span v-if="row.published_version">v{{ row.published_version }}</span>
            <span v-else style="color: var(--text-muted)">-</span>
            <el-tag v-if="row.draft_version" type="warning" size="small" style="margin-left:4px">
              草稿 v{{ row.draft_version }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="120">
          <template #default="{ row }">
            <el-tag v-for="t in row.tags" :key="t.id" size="small" style="margin-right:4px">
              {{ t.name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="use_count" label="使用次数" width="90" />
        <el-table-column label="默认模型" min-width="160">
          <template #default="{ row }">
            <span v-if="row.model_name" style="white-space: nowrap">{{ row.model_name }}</span>
            <span v-else style="color: #999">未配置</span>
          </template>
        </el-table-column>
        <el-table-column prop="creator_name" label="创建者" width="90" />
        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="router.push(`/admin/skills/${row.id}/edit`)">
              编辑
            </el-button>
            <el-button
              v-if="row.draft_version"
              link type="success" size="small"
              @click="openPublishDialog(row.id)"
            >
              发布
            </el-button>
            <el-button
              v-if="row.status === 'published'"
              link type="warning" size="small"
              @click="handleOffline(row)"
            >
              下架
            </el-button>
            <el-button
              v-if="row.status === 'offline'"
              link type="success" size="small"
              @click="handleOnline(row)"
            >
              上架
            </el-button>
            <el-button link type="info" size="small" @click="openFeedbacks(row)">反馈</el-button>
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
          @current-change="(v: number) => { page = v; fetchData() }"
        />
      </div>
    </el-card>

    <!-- 发布弹窗 -->
    <el-dialog v-model="publishDialogVisible" width="500px" destroy-on-close class="skill-manage-dialog">
      <template #header>
        <div class="dialog-header">
          <div class="dialog-header-badge">发布流程</div>
          <div class="dialog-header-title">发布 Skill</div>
          <div class="dialog-header-desc">发布后草稿版本将替换当前线上版本，用户会自动使用新版本。</div>
        </div>
      </template>
      <el-form ref="publishFormRef" :model="publishForm">
        <el-form-item
          prop="change_log"
          :rules="[{ required: true, message: '请填写更新说明', trigger: 'blur' }]"
        >
          <el-input
            v-model="publishForm.change_log"
            type="textarea"
            :rows="3"
            placeholder="请填写本次更新说明"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button class="dialog-btn dialog-btn-secondary" @click="publishDialogVisible = false">取消</el-button>
          <el-button class="dialog-btn dialog-btn-primary" @click="handlePublish">确认发布</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 反馈弹窗 -->
    <el-dialog v-model="feedbackVisible" width="620px" destroy-on-close class="skill-manage-dialog">
      <template #header>
        <div class="dialog-header">
          <div class="dialog-header-badge">反馈概览</div>
          <div class="dialog-header-title">{{ feedbackSkillName }}</div>
          <div class="dialog-header-desc">查看用户评分与评论，快速判断版本质量。</div>
        </div>
      </template>
      <div v-loading="feedbackLoading" class="feedback-dialog-body">
        <el-table v-if="feedbackList.length > 0" :data="feedbackList" stripe size="small" class="feedback-table">
          <el-table-column label="评分" width="100">
            <template #default="{ row }">
              <span style="color: #f59e0b">{{ '★'.repeat(row.rating) }}</span>
              <span style="color: var(--text-muted)">{{ '★'.repeat(5 - row.rating) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="comment" label="反馈内容" min-width="180">
            <template #default="{ row }">
              {{ row.comment || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="user_name" label="用户" width="90" />
          <el-table-column label="时间" width="140">
            <template #default="{ row }">
              {{ row.created_at ? row.created_at.replace('T', ' ').substring(0, 16) : '-' }}
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无反馈" class="feedback-empty" />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.skill-manage { width: 100% }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px }
.page-header h2 { margin: 0; font-size: 20px; color: var(--text-primary, #303133) }
.filter-bar { display: flex; gap: 12px; margin-bottom: 16px }
.pagination-bar { display: flex; justify-content: flex-end; margin-top: 16px }

.skill-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.skill-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.skill-icon-img {
  object-fit: cover;
}

.skill-icon-emoji {
  font-size: 18px;
  line-height: 1;
  background: #f0f0ff;
}

.skill-icon-default {
  background: linear-gradient(135deg, #e0e7ff, #c7d2fe);
  color: #6366f1;
}

.skill-name-text {
  font-weight: 500;
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

.feedback-dialog-body {
  padding: 6px 0 18px;
}

.feedback-table {
  overflow: hidden;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 18px;
  background: #ffffff;
}

:global(.skill-manage-dialog .feedback-table .el-table__inner-wrapper) {
  border-radius: 18px;
  overflow: hidden;
}

:global(.skill-manage-dialog .feedback-table .el-table__body-wrapper) {
  border-radius: 0 0 18px 18px;
}

.feedback-empty {
  min-height: 244px;
  border: 1px dashed rgba(226, 232, 240, 0.95);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.72);
}

:global(.skill-manage-dialog .el-dialog) {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 32px;
  background: #ffffff;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
  background-clip: padding-box;
}

:global(.skill-manage-dialog .el-dialog__header) {
  margin: 0;
  padding: 24px 24px 0;
  border-radius: 32px 32px 0 0;
  background: inherit;
}

:global(.skill-manage-dialog .el-dialog__body) {
  padding: 18px 24px 0;
  background: inherit;
}

:global(.skill-manage-dialog .el-dialog__footer) {
  padding: 22px 24px 24px;
  border-radius: 0 0 32px 32px;
  background: inherit;
}

:global(.skill-manage-dialog .el-dialog__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.skill-manage-dialog .el-dialog__headerbtn .el-dialog__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.skill-manage-dialog .el-dialog__footer .el-button.dialog-btn) {
  min-width: 108px;
  height: 42px;
  border-radius: 14px;
  font-weight: 600;
}

:global(.skill-manage-dialog .dialog-btn-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.skill-manage-dialog .dialog-btn-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.skill-manage-dialog .dialog-btn-primary) {
  border: none;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #fff;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.2);
}

:global(.skill-manage-dialog .dialog-btn-primary:hover) {
  background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
  color: #fff;
}

:global(.skill-manage-dialog .feedback-table .el-table__inner-wrapper::before) {
  display: none;
}

:global(.skill-manage-dialog .feedback-table th.el-table__cell) {
  background: #f8fafc;
}

:global(.skill-manage-dialog .feedback-table tr:last-child td.el-table__cell) {
  border-bottom: none;
}

:global(.skill-manage-confirm-dialog.el-message-box) {
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

:global(.skill-manage-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.skill-manage-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.skill-manage-confirm-dialog .el-message-box__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.skill-manage-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.skill-manage-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.skill-manage-confirm-dialog .el-message-box__message) {
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

:global(.skill-manage-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.skill-manage-confirm-dialog .el-message-box__btns .el-button) {
  min-width: 108px;
  height: 42px;
  border-radius: 14px;
  font-weight: 600;
}

:global(.skill-manage-confirm-dialog .skill-manage-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.skill-manage-confirm-dialog .skill-manage-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.skill-manage-confirm-dialog .skill-manage-confirm-primary) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.skill-manage-confirm-dialog .skill-manage-confirm-primary:hover) {
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

:global(html.dark) .dialog-header-desc {
  color: #94a3b8;
}

:global(html.dark .skill-manage-dialog .el-dialog) {
  border-color: rgba(148, 163, 184, 0.12);
  background:
    linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .skill-manage-dialog .el-dialog__headerbtn .el-dialog__close) {
  color: #94a3b8;
}

:global(html.dark .skill-manage-dialog .dialog-btn-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .skill-manage-dialog .dialog-btn-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}

:global(html.dark) .feedback-table {
  border-color: rgba(148, 163, 184, 0.12);
  background: rgba(15, 23, 42, 0.4);
}

:global(html.dark) .feedback-empty {
  border-color: rgba(148, 163, 184, 0.14);
  background: rgba(15, 23, 42, 0.22);
}

:global(html.dark .skill-manage-dialog .feedback-table th.el-table__cell) {
  background: rgba(30, 41, 59, 0.72);
}

:global(html.dark .skill-manage-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background:
    linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .skill-manage-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}

:global(html.dark .skill-manage-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: #94a3b8;
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

:global(html.dark .skill-manage-confirm-dialog .skill-manage-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .skill-manage-confirm-dialog .skill-manage-confirm-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}
</style>
