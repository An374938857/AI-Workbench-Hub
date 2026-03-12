<script setup lang="ts">
import ConversationFileTree from '@/components/common/ConversationFileTree.vue'
import SandboxFileInspectorCard from '@/components/common/SandboxFileInspectorCard.vue'
import UnifiedFilePreviewDialog from '@/components/common/UnifiedFilePreviewDialog.vue'
import { Download, View } from '@element-plus/icons-vue'

const props = defineProps<{
  visible: boolean
  loading: boolean
  selectedIds: number[]
  allFiles: any[]
  treeItems: any[]
  focusedFileId: string | number | null
  focusedFile: any | null
  inspectorTags: any[]
  inspectorFields: any[]
  inspectorSummary: string
  bindingSummary: string
  formatReferenceDisplayPath: (file: any, hideRoot: boolean) => string
  referenceFilePreview: any
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  cancel: []
  'update:selectedIds': [ids: number[]]
  'file-click': [key: string | number]
  'file-dblclick': [raw: any]
  'inspector-action': [action: any]
  'apply-mode': [mode: 'turn_only_skip' | 'persist_empty' | 'persist_selection']
}>()
</script>

<template>
  <el-dialog
    :model-value="visible"
    width="min(1360px, 97vw)"
    align-center
    destroy-on-close
    class="styled-dialog reference-dialog"
    :show-close="false"
    @update:model-value="(value: boolean) => emit('update:visible', value)"
    @closed="emit('cancel')"
  >
    <template #header>
      <div class="dialog-header">
        <div class="dialog-header-icon">
          <el-icon :size="20"><FolderOpened /></el-icon>
        </div>
        <div>
          <div class="dialog-header-title">确认本轮引用资料</div>
          <div class="dialog-header-desc">请选择本轮需要引用的文件，确认后会用于后续问答。</div>
        </div>
      </div>
    </template>
    <div v-loading="loading" class="reference-dialog-body">
      <div class="reference-binding-summary">
        {{ bindingSummary }}
      </div>
      <div class="reference-dialog-summary">
        <div class="reference-summary-card">
          <div class="reference-summary-label">当前已选</div>
          <div class="reference-summary-value">{{ selectedIds.length }}</div>
        </div>
        <div class="reference-summary-card">
          <div class="reference-summary-label">范围内文件</div>
          <div class="reference-summary-value">{{ allFiles.length }}</div>
        </div>
        <div class="reference-summary-card reference-summary-card--hint">
          <div class="reference-summary-label">操作方式</div>
          <div class="reference-summary-copy">单击聚焦，双击预览，勾选后作为本轮引用</div>
        </div>
      </div>
      <div class="reference-workbench">
        <div class="reference-workbench-main">
          <ConversationFileTree
            class="reference-dialog-tree"
            :items="treeItems"
            sort-mode="file-first"
            :loading="loading"
            :selectable="true"
            :selected-keys="selectedIds"
            :current-key="focusedFileId"
            :show-summary="false"
            :show-path="false"
            :show-source-tag="false"
            :select-on-row-click="true"
            empty-title="当前范围内没有可引用文件"
            empty-text="请先在文件沙箱、项目资料或需求资料中准备可引用文件。"
            search-placeholder="按文件名模糊搜索可引用资料"
            @update:selected-keys="(keys) => emit('update:selectedIds', keys as number[])"
            @file-click="(item) => emit('file-click', item.key)"
            @file-dblclick="(item) => emit('file-dblclick', item.raw)"
          />
        </div>
        <aside class="reference-inspector">
          <SandboxFileInspectorCard
            badge="引用沙箱"
            title="文件详情"
            overline="当前聚焦文件"
            :file-name="focusedFile?.file_name || ''"
            :file-path="focusedFile ? formatReferenceDisplayPath(focusedFile, false) : ''"
            :tags="inspectorTags"
            :fields="inspectorFields"
            :summary="inspectorSummary"
            summary-title="内容摘要"
            empty-text="从左侧树中选择一个文件，这里会显示更完整的资料信息和快捷操作。"
            :actions="[
              { key: 'preview', label: '预览', icon: View, variant: 'primary' },
              { key: 'download', label: '下载', icon: Download, variant: 'secondary' },
            ]"
            @action="(action) => emit('inspector-action', action)"
          />
        </aside>
      </div>
    </div>
    <template #footer>
      <div class="dialog-footer">
        <button type="button" class="dialog-btn secondary" @click="emit('cancel')">取消发送</button>
        <button type="button" class="dialog-btn secondary" @click="emit('apply-mode', 'turn_only_skip')">本轮不引用</button>
        <button type="button" class="dialog-btn danger" @click="emit('apply-mode', 'persist_empty')">持续不引用</button>
        <button type="button" class="dialog-btn primary" @click="emit('apply-mode', 'persist_selection')">确认引用并发送</button>
      </div>
    </template>
  </el-dialog>

  <UnifiedFilePreviewDialog
    v-model="referenceFilePreview.visible.value"
    :loading="referenceFilePreview.loading.value"
    :title="referenceFilePreview.title.value"
    :file-type="referenceFilePreview.fileType.value"
    :file-size="referenceFilePreview.fileSize.value"
    :mode="referenceFilePreview.mode.value"
    :can-edit="referenceFilePreview.canEdit.value"
    :saving="referenceFilePreview.saving.value"
    :can-download="referenceFilePreview.canDownload.value"
    :content="referenceFilePreview.content.value"
    :preview-notice="referenceFilePreview.previewNotice.value"
    :preview-url="referenceFilePreview.previewUrl.value"
    :sheets="referenceFilePreview.sheets.value"
    :active-sheet-name="referenceFilePreview.activeSheetName.value"
    @update:active-sheet-name="(name) => (referenceFilePreview.activeSheetName.value = name)"
    @open-external="referenceFilePreview.openCurrentInNewWindow"
    @download="referenceFilePreview.downloadCurrent"
    @save-edit="referenceFilePreview.saveMarkdownEdit"
  />
</template>

<style scoped>
.dialog-header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.dialog-header-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.dialog-header-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
}

.dialog-header-desc {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
  margin-top: 1px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.dialog-btn {
  padding: 7px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.dialog-btn:active {
  transform: scale(0.97);
}

.dialog-btn.secondary {
  border: 1px solid var(--border-primary, rgba(0, 0, 0, 0.08));
  background: var(--bg-card, #fff);
  color: var(--text-secondary, #64748b);
}

.dialog-btn.secondary:hover {
  border-color: rgba(0, 0, 0, 0.15);
  background: var(--bg-hover, #f8fafc);
}

.dialog-btn.primary {
  border: none;
  background: #3b82f6;
  color: #fff;
}

.dialog-btn.primary:hover {
  background: #2563eb;
}

.dialog-btn.danger {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
}

.dialog-btn.danger:hover {
  border-color: #fca5a5;
  background: #fef2f2;
}

.dialog-btn.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

html.dark .dialog-btn.primary {
  background: #60a5fa;
  color: #0f172a;
}

html.dark .dialog-btn.primary:hover {
  background: #93bbfd;
}

html.dark .dialog-btn.danger {
  border-color: rgba(248, 113, 113, 0.35);
  background: rgba(127, 29, 29, 0.18);
  color: #fecaca;
}

html.dark .dialog-btn.danger:hover {
  border-color: rgba(252, 165, 165, 0.5);
  background: rgba(127, 29, 29, 0.28);
}

.reference-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.reference-binding-summary {
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid rgba(59, 130, 246, 0.24);
  background: rgba(239, 246, 255, 0.72);
  font-size: 13px;
  color: var(--text-secondary, #334155);
}

.reference-dialog-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.reference-summary-card {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.96) 100%);
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.06);
}

.reference-summary-card--hint {
  background:
    radial-gradient(circle at top right, rgba(96, 165, 250, 0.18), transparent 48%),
    linear-gradient(180deg, rgba(239, 246, 255, 0.96) 0%, rgba(248, 250, 252, 0.96) 100%);
}

.reference-summary-label {
  font-size: 12px;
  color: var(--text-muted, #64748b);
}

.reference-summary-value {
  margin-top: 8px;
  font-size: 30px;
  line-height: 1;
  font-weight: 700;
  color: var(--text-primary, #1e293b);
}

.reference-summary-copy {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary, #475569);
}

.reference-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) minmax(340px, 1fr);
  gap: 16px;
  height: min(62vh, 640px);
  max-height: min(62vh, 640px);
  min-height: 0;
  overflow: hidden;
}

.reference-workbench-main,
.reference-inspector {
  min-height: 0;
}

.reference-workbench-main {
  display: flex;
  flex-direction: column;
  border-radius: 24px;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.96) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.reference-dialog-tree {
  flex: 1;
  min-height: 0;
  max-height: none;
  overflow: hidden;
}

.reference-dialog-tree :deep(.conversation-file-tree) {
  height: 100%;
  min-height: 0;
}

.reference-dialog-tree :deep(.tree-wrap) {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.reference-inspector {
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 0;
  border: none;
  background: transparent;
  box-shadow: none;
}

.styled-dialog :deep(.el-dialog) {
  border-radius: 20px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.12), 0 0 1px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.styled-dialog :deep(.el-dialog__header) {
  padding: 28px 28px 18px;
  margin: 0;
}

.styled-dialog :deep(.el-dialog__body) {
  padding: 10px 28px 24px;
}

.styled-dialog :deep(.el-dialog__footer) {
  padding: 0 28px 28px;
}

.reference-dialog :deep(.el-dialog__body) {
  padding-bottom: 18px;
}

:global(html.dark .reference-dialog .el-dialog) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .reference-dialog .dialog-btn.secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .reference-dialog .dialog-btn.secondary:hover) {
  border-color: rgba(148, 163, 184, 0.24);
  background: rgba(148, 163, 184, 0.12);
  color: #f8fafc;
}

:global(html.dark .reference-dialog .dialog-btn.primary) {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(148, 163, 184, 0.12);
  color: #f8fafc;
}

:global(html.dark .reference-dialog .dialog-btn.primary:hover) {
  background: rgba(148, 163, 184, 0.18);
  border-color: rgba(148, 163, 184, 0.24);
}

:global(html.dark .reference-dialog .reference-binding-summary) {
  border-color: rgba(147, 197, 253, 0.24);
  background: rgba(30, 64, 175, 0.2);
  color: #dbeafe;
}

@media (max-width: 1200px) {
  .reference-workbench {
    grid-template-columns: 1fr;
    height: auto;
    max-height: none;
    overflow: visible;
  }

  .reference-workbench-main,
  .reference-inspector {
    min-height: auto;
    height: auto;
    max-height: none;
    overflow: visible;
  }
}

@media (max-width: 900px) {
  .reference-dialog :deep(.el-dialog__header) {
    padding: 22px 20px 14px;
  }

  .reference-dialog :deep(.el-dialog__body) {
    padding: 8px 20px 14px;
  }

  .reference-dialog :deep(.el-dialog__footer) {
    padding: 0 20px 20px;
  }
}

@media (max-width: 768px) {
  .reference-dialog-summary {
    grid-template-columns: 1fr;
  }

  .dialog-footer {
    flex-wrap: wrap;
  }
}
</style>
