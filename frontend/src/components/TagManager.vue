<script setup lang="ts">
import { ref, onMounted } from 'vue'
import draggable from 'vuedraggable'
import { ElMessage } from 'element-plus'
import { getTagList, createTag, updateTag, deleteTag } from '@/api/tags'
import { showDangerConfirm } from '@/composables/useDangerConfirm'

interface TagItem {
  id: number
  name: string
  color: string
  sort_order: number
  conversation_count: number
}

const emit = defineEmits<{ updated: [] }>()

const visible = ref(false)
const tags = ref<TagItem[]>([])
const newName = ref('')
const newColor = ref('#409eff')

const editingId = ref<number | null>(null)
const editName = ref('')
const editColor = ref('')
const sorting = ref(false)
const dropPulseTagId = ref<number | null>(null)

const PRESET_COLORS = [
  '#f56c6c', '#e6a23c', '#67c23a', '#409eff',
  '#909399', '#b37feb', '#36cfc9', '#ff85c0',
]

async function loadTags() {
  try {
    const res: any = await getTagList()
    tags.value = res.data
  } catch { /* ignore */ }
}

async function handleCreate() {
  const name = newName.value.trim()
  if (!name) return
  try {
    await createTag(name, newColor.value)
    newName.value = ''
    await loadTags()
    emit('updated')
    ElMessage.success('标签已创建')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '创建失败')
  }
}

function startEdit(tag: TagItem) {
  editingId.value = tag.id
  editName.value = tag.name
  editColor.value = tag.color
}

function cancelEdit() {
  editingId.value = null
}

async function saveEdit(tag: TagItem) {
  const name = editName.value.trim()
  if (!name) return
  if (name === tag.name && editColor.value === tag.color) {
    cancelEdit()
    return
  }
  try {
    await updateTag(tag.id, { name, color: editColor.value })
    editingId.value = null
    await loadTags()
    emit('updated')
    ElMessage.success('标签已更新')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '更新失败')
  }
}

async function handleDelete(tag: TagItem) {
  try {
    await showDangerConfirm({
      title: '删除标签',
      subject: tag.name,
      detail: '删除标签不会影响关联对话内容，但该标签将无法再被使用。',
      confirmText: '删除标签',
    })
    await deleteTag(tag.id)
    await loadTags()
    emit('updated')
    ElMessage.success('标签已删除')
  } catch { /* cancelled */ }
}

async function handleSortEnd(evt?: { newIndex?: number | null }) {
  if (editingId.value !== null) return
  if (evt?.newIndex != null && evt.newIndex >= 0 && evt.newIndex < tags.value.length) {
    const landed = tags.value[evt.newIndex]
    if (landed) {
      dropPulseTagId.value = landed.id
      window.setTimeout(() => {
        if (dropPulseTagId.value === landed.id) dropPulseTagId.value = null
      }, 320)
    }
  }
  const updates = tags.value
    .map((t, idx) => ({ id: t.id, sort_order: idx, old_order: t.sort_order }))
    .filter((x) => x.sort_order !== x.old_order)
  if (!updates.length) return
  sorting.value = true
  try {
    await Promise.all(updates.map((u) => updateTag(u.id, { sort_order: u.sort_order })))
    tags.value.forEach((t, idx) => {
      t.sort_order = idx
    })
    emit('updated')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '排序保存失败')
    await loadTags()
  } finally {
    sorting.value = false
  }
}

function open() {
  visible.value = true
  loadTags()
}

defineExpose({ open })

onMounted(loadTags)
</script>

<template>
  <el-drawer v-model="visible" size="380px" direction="rtl" class="tag-manager-drawer" :with-header="false">
    <div class="tag-manager-header">
      <div class="tm-title">标签管理</div>
      <div class="tm-subtitle">创建、编辑和维护对话标签</div>
    </div>

    <div class="tag-create-card">
      <el-input
        v-model="newName"
        placeholder="输入新标签名称"
        size="default"
        class="tm-input"
        @keyup.enter="handleCreate"
      />
      <div class="tm-create-actions">
        <el-color-picker v-model="newColor" :predefine="PRESET_COLORS" />
        <el-button type="primary" @click="handleCreate" :disabled="!newName.trim()">添加标签</el-button>
      </div>
    </div>

    <draggable
      v-model="tags"
      item-key="id"
      class="tag-list"
      :disabled="editingId !== null || sorting"
      handle=".tag-drag-handle"
      :animation="220"
      ghost-class="tag-drag-ghost"
      chosen-class="tag-drag-chosen"
      drag-class="tag-drag-active"
      @end="handleSortEnd"
    >
      <template #item="{ element: t }">
      <div class="tag-list-item" :class="{ 'tag-drop-pulse': dropPulseTagId === t.id }">
        <!-- 编辑模式 -->
        <template v-if="editingId === t.id">
          <button type="button" class="tm-icon-btn tag-drag-handle" disabled>
            <el-icon><Rank /></el-icon>
          </button>
          <el-color-picker v-model="editColor" :predefine="PRESET_COLORS" />
          <el-input
            v-model="editName"
            class="tm-edit-input"
            autofocus
            @keyup.enter="saveEdit(t)"
            @keyup.escape="cancelEdit"
          />
          <button type="button" class="tm-icon-btn primary" @click="saveEdit(t)">
            <el-icon><Check /></el-icon>
          </button>
          <button type="button" class="tm-icon-btn" @click="cancelEdit">
            <el-icon><Close /></el-icon>
          </button>
        </template>

        <!-- 展示模式 -->
        <template v-else>
          <button type="button" class="tm-icon-btn tag-drag-handle" title="拖拽调整顺序">
            <el-icon><Rank /></el-icon>
          </button>
          <span class="tag-color-dot" :style="{ background: t.color }" />
          <span class="tag-item-name" @click="startEdit(t)">{{ t.name }}</span>
          <span class="tag-item-count">{{ t.conversation_count }}</span>
          <button type="button" class="tm-icon-btn" @click="startEdit(t)">
            <el-icon><Edit /></el-icon>
          </button>
          <button type="button" class="tm-icon-btn danger" @click="handleDelete(t)">
            <el-icon><Delete /></el-icon>
          </button>
        </template>
      </div>
      </template>
    </draggable>
      <el-empty v-if="tags.length === 0" description="暂无标签" :image-size="68" />
  </el-drawer>
</template>

<style scoped>
:deep(.tag-manager-drawer .el-drawer) {
  border-top-left-radius: 18px;
  border-bottom-left-radius: 18px;
  overflow: hidden;
}

:deep(.tag-manager-drawer .el-drawer__body) {
  padding: 18px 16px 16px;
  background: var(--bg-card, #fff);
}

.tag-manager-header {
  margin-bottom: 14px;
  padding: 0 4px 12px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
}

.tm-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
}

.tm-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary, #64748b);
}

.tag-create-card {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: var(--bg-page, #f8fafc);
  margin-bottom: 14px;
}

.tm-create-actions {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.tm-input :deep(.el-input__wrapper) {
  border-radius: 10px;
}

.tag-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tag-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 10px;
  border-radius: 10px;
  border: 1px solid transparent;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background-color 0.18s ease, border-color 0.18s ease;
}

.tag-drag-handle {
  cursor: grab;
}

.tag-drag-handle:active {
  cursor: grabbing;
}

.tag-drag-handle:hover {
  color: #397ef5;
  background: rgba(57, 126, 245, 0.1);
}

:deep(.tag-drag-chosen) {
  border-color: rgba(57, 126, 245, 0.28);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.14);
  transform: scale(1.01);
}

:deep(.tag-drag-active) {
  cursor: grabbing;
}

:deep(.tag-drag-ghost) {
  opacity: 0.55;
  background: rgba(57, 126, 245, 0.08);
  border: 1px dashed rgba(57, 126, 245, 0.35);
}

.tag-drop-pulse {
  animation: tagDropPulse 0.32s cubic-bezier(0.2, 0.8, 0.2, 1);
}

@keyframes tagDropPulse {
  0% {
    transform: scale(0.985);
    box-shadow: 0 0 0 rgba(57, 126, 245, 0);
  }
  55% {
    transform: scale(1.015);
    box-shadow: 0 10px 20px rgba(57, 126, 245, 0.2);
  }
  100% {
    transform: scale(1);
    box-shadow: 0 0 0 rgba(57, 126, 245, 0);
  }
}

.tag-list-item:hover {
  border-color: rgba(59, 130, 246, 0.2);
  background: rgba(59, 130, 246, 0.06);
}

.tag-color-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tag-item-name {
  flex: 1;
  font-size: 14px;
  color: var(--text-primary, #303133);
  cursor: pointer;
}

.tag-item-name:hover {
  color: #397ef5;
}

.tag-item-count {
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  border-radius: 9px;
  font-size: 11px;
  color: #64748b;
  background: rgba(100, 116, 139, 0.12);
}

.tm-edit-input {
  flex: 1;
}

.tm-icon-btn {
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: var(--text-muted, #94a3b8);
  cursor: pointer;
  transition: all 0.16s ease;
}

.tm-icon-btn:hover {
  background: rgba(15, 23, 42, 0.08);
  color: var(--text-primary, #334155);
}

.tm-icon-btn.primary {
  color: #397ef5;
}

.tm-icon-btn.primary:hover {
  background: rgba(57, 126, 245, 0.12);
}

.tm-icon-btn.danger {
  color: #ed4141;
}

.tm-icon-btn.danger:hover {
  background: rgba(237, 65, 65, 0.12);
}

html.dark :deep(.tag-manager-drawer .el-drawer__body) {
  background: #111827;
}

html.dark .tag-manager-header {
  border-bottom-color: rgba(148, 163, 184, 0.2);
}

html.dark .tag-create-card {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(148, 163, 184, 0.2);
}

html.dark .tag-list-item:hover {
  border-color: rgba(96, 165, 250, 0.3);
  background: rgba(96, 165, 250, 0.12);
}

html.dark :deep(.tag-drag-chosen) {
  border-color: rgba(96, 165, 250, 0.42);
  box-shadow: 0 12px 26px rgba(2, 6, 23, 0.55);
}

html.dark :deep(.tag-drag-ghost) {
  background: rgba(96, 165, 250, 0.15);
  border-color: rgba(96, 165, 250, 0.5);
}

html.dark .tag-drop-pulse {
  animation-name: tagDropPulseDark;
}

@keyframes tagDropPulseDark {
  0% {
    transform: scale(0.985);
    box-shadow: 0 0 0 rgba(96, 165, 250, 0);
  }
  55% {
    transform: scale(1.015);
    box-shadow: 0 12px 24px rgba(2, 6, 23, 0.6);
  }
  100% {
    transform: scale(1);
    box-shadow: 0 0 0 rgba(96, 165, 250, 0);
  }
}

html.dark .tag-item-count {
  color: #cbd5e1;
  background: rgba(148, 163, 184, 0.2);
}

html.dark .tm-icon-btn:hover {
  background: rgba(148, 163, 184, 0.18);
  color: #e2e8f0;
}

:global(.tag-manager-confirm-dialog.el-message-box) {
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

:global(.tag-manager-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.tag-manager-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.tag-manager-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.tag-manager-confirm-dialog .el-message-box__message) {
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

:global(.tag-manager-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.tag-manager-confirm-dialog .tag-manager-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.tag-manager-confirm-dialog .tag-manager-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.tag-manager-confirm-dialog .tag-manager-confirm-danger) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.tag-manager-confirm-dialog .tag-manager-confirm-danger:hover) {
  border-color: #fca5a5;
  background: #fef2f2;
  color: #b91c1c;
}

:global(html.dark .tag-manager-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .tag-manager-confirm-dialog .el-message-box__title) {
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
