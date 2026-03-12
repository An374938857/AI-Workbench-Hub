<template>
  <div :class="['sandbox-files', { 'sandbox-files--embedded': embedded }]">
    <div v-if="!embedded" class="page-header">
      <div>
        <h2 class="page-title">对话沙箱</h2>
        <p class="page-subtitle">
          技能包会按原始目录结构完整挂载到当前对话中，下面展示的是可直接访问的文件目录树。
        </p>
      </div>
      <div class="header-actions">
        <div class="stat-card">
          <div class="stat-label">空间使用</div>
          <div class="stat-value">{{ sandboxSize.toFixed(2) }} / {{ sandboxLimit }} MB</div>
          <el-progress
            :percentage="sandboxPercentage"
            :status="sandboxPercentage > 80 ? 'exception' : undefined"
            :stroke-width="6"
          />
        </div>
        <div class="header-action-buttons">
          <el-button class="cleanup-button archive-button" plain @click="handleArchiveDownload" :loading="archiving">
            <el-icon><Download /></el-icon>
            <span>打包下载</span>
          </el-button>
          <el-button class="cleanup-button" plain @click="handleCleanup" :loading="cleaning">
            <el-icon><Delete /></el-icon>
            <span>清空沙箱</span>
          </el-button>
        </div>
      </div>
    </div>
    <div v-else class="embedded-summary">
      <div class="stat-card">
        <div class="stat-label">空间使用</div>
        <div class="stat-value">{{ sandboxSize.toFixed(2) }} / {{ sandboxLimit }} MB</div>
        <el-progress
          :percentage="sandboxPercentage"
          :status="sandboxPercentage > 80 ? 'exception' : undefined"
          :stroke-width="6"
        />
      </div>
      <div class="header-action-buttons">
        <el-button class="cleanup-button archive-button" plain @click="handleArchiveDownload" :loading="archiving">
          <el-icon><Download /></el-icon>
          <span>打包下载</span>
        </el-button>
        <el-button class="cleanup-button" plain @click="handleCleanup" :loading="cleaning">
          <el-icon><Delete /></el-icon>
          <span>清空沙箱</span>
        </el-button>
      </div>
    </div>

    <div class="browser-shell">
      <div class="browser-workbench">
        <div class="browser-tree-pane">
          <ConversationFileTree
            :items="treeItems"
            :loading="loading"
            :current-key="focusedFileId"
            empty-title="沙箱还是空的"
            empty-text="上传文件、技能引用文件或模型生成结果都会在这里按目录结构展示。"
            search-placeholder="按文件名模糊搜索沙箱文件"
            @file-click="handleTreeItemClick"
            @file-dblclick="handleTreeItemDoubleClick"
          >
            <template #actions="{ node }">
              <el-dropdown
                v-if="node.type === 'directory' || node.item"
                trigger="click"
                placement="bottom-end"
                popper-class="sandbox-node-menu"
                :teleported="true"
                @command="handleNodeCommand($event, node)"
              >
                <button class="action-trigger" type="button" @click.stop>
                  <el-icon><MoreFilled /></el-icon>
                </button>
                <template #dropdown>
                  <SandboxFileActionMenu
                    v-if="node.item"
                    :can-preview="true"
                    :can-download="true"
                    :can-rename="true"
                    :can-edit="isMarkdownFile(node.item.raw as SandboxFile)"
                    :can-delete="true"
                    delete-label="删除"
                  />
                  <el-dropdown-menu v-else>
                    <el-dropdown-item command="delete" class="danger-item">
                      <el-icon><Delete /></el-icon>
                      <span>删除目录</span>
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </ConversationFileTree>
        </div>
        <SandboxFileInspectorCard
          badge=""
          title="文件详情"
          overline=""
          :file-name="focusedFile?.original_name || ''"
          :file-path="focusedFile?.sandbox_path || focusedFile?.original_name || ''"
          :tags="[]"
          :fields="focusedFileFields"
          :summary="focusedFileSummary"
          :compact-actions="true"
          summary-title="文件说明"
          empty-text="从左侧树中选择一个文件，这里会显示更完整的资料信息和快捷操作。"
          :actions="focusedFileActions"
          @action="handleInspectorAction"
        />
      </div>
    </div>

    <UnifiedFilePreviewDialog
      v-model="filePreview.visible.value"
      :loading="filePreview.loading.value"
      :title="filePreview.title.value"
      :file-type="filePreview.fileType.value"
      :file-size="filePreview.fileSize.value"
      :mode="filePreview.mode.value"
      :can-edit="filePreview.canEdit.value"
      :enter-edit-token="filePreview.enterEditToken.value"
      :saving="filePreview.saving.value"
      :can-download="filePreview.canDownload.value"
      :content="filePreview.content.value"
      :preview-notice="filePreview.previewNotice.value"
      :preview-url="filePreview.previewUrl.value"
      :sheets="filePreview.sheets.value"
      :active-sheet-name="filePreview.activeSheetName.value"
      @update:active-sheet-name="(name) => (filePreview.activeSheetName.value = name)"
      @open-external="filePreview.openCurrentInNewWindow"
      @download="filePreview.downloadCurrent"
      @save-edit="filePreview.saveMarkdownEdit"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { Delete, MoreFilled, Download, View, Edit } from "@element-plus/icons-vue";
import ConversationFileTree from "@/components/common/ConversationFileTree.vue";
import SandboxFileInspectorCard from "@/components/common/SandboxFileInspectorCard.vue";
import SandboxFileActionMenu from "@/components/common/SandboxFileActionMenu.vue";
import UnifiedFilePreviewDialog from "@/components/common/UnifiedFilePreviewDialog.vue";
import { showDangerConfirm } from "@/composables/useDangerConfirm";
import { useFilePreview } from "@/composables/useFilePreview";
import { useSandboxFileActions, type SandboxFileActionTarget } from "@/composables/useSandboxFileActions";
import type { ConversationFileTreeItem, ConversationFileTreeNode } from "@/utils/conversationFileTree";
import {
  getSandboxFiles,
  deleteSandboxDirectory,
  cleanupSandbox,
  downloadSandboxArchive,
} from "../api/sandbox";
import type { SandboxFile } from "../api/sandbox";

const props = defineProps<{
  conversationId?: number;
  embedded?: boolean;
}>();
const route = useRoute();
const embedded = computed(() => props.embedded === true);

const loading = ref(false);
const cleaning = ref(false);
const archiving = ref(false);
const files = ref<SandboxFile[]>([]);
const sandboxSize = ref(0);
const sandboxLimit = ref(100);
const filePreview = useFilePreview();
type NodeCommand = "preview" | "download" | "rename" | "delete";

const sandboxPercentage = computed(() => {
  return Math.round((sandboxSize.value / sandboxLimit.value) * 100);
});
const focusedFileId = ref<number | null>(null);
const focusedFile = computed(() => files.value.find((file) => file.file_id === focusedFileId.value) || null);
const focusedFileFields = computed(() => {
  if (!focusedFile.value) return [];
  return [
    { label: "文件类型", value: (focusedFile.value.file_type || "未知").toUpperCase() },
    { label: "文件大小", value: formatBytes(focusedFile.value.file_size) },
    { label: "更新时间", value: formatTime(focusedFile.value.created_at) },
  ];
});
const focusedFileSummary = computed(() => {
  if (!focusedFile.value) return "";
  if (focusedFile.value.source === "upload") return "该文件来自手动上传。";
  if (focusedFile.value.source === "reference") return "该文件来自技能引用，保留原始目录结构。";
  return "该文件由模型生成并保存到当前对话沙箱。";
});
const focusedFileActions = computed(() => {
  const actions = [
    { key: "preview", label: "预览", icon: View, variant: "primary" as const },
    { key: "download", label: "下载", icon: Download, variant: "secondary" as const },
    { key: "rename", label: "重命名", icon: Edit, variant: "secondary" as const },
  ];
  if (focusedFile.value && isMarkdownFile(focusedFile.value)) {
    actions.push({ key: "edit", label: "编辑", icon: Edit, variant: "secondary" as const });
  }
  actions.push({ key: "delete", label: "删除", icon: Delete, variant: "secondary" as const });
  return actions;
});

const treeItems = computed<ConversationFileTreeItem[]>(() =>
  files.value.map((file) => ({
    key: file.file_id,
    label: file.original_name,
    path: file.sandbox_path || file.original_name,
    fileType: file.file_type,
    fileSize: file.file_size,
    updatedAt: file.created_at,
    sourceLabel: sourceText(file.source),
    sourceTagType: sourceTagType(file.source),
    searchableText: `${file.original_name} ${file.sandbox_path || ""} ${file.file_type}`.toLowerCase(),
    raw: file,
  })),
);

const conversationIdValue = computed<number | null>(() => {
  if (typeof props.conversationId === "number" && Number.isFinite(props.conversationId)) {
    return props.conversationId;
  }
  const routeId = Number(route.params.conversationId);
  if (Number.isFinite(routeId) && routeId > 0) {
    return routeId;
  }
  return null;
});

function sourceText(source: string) {
  if (source === "upload") return "上传";
  if (source === "reference") return "技能文件";
  return "生成";
}

function sourceTagType(source: string): "primary" | "warning" | "success" {
  if (source === "upload") return "primary";
  if (source === "reference") return "warning";
  return "success";
}

function isMarkdownFile(file: SandboxFile): boolean {
  const fileType = (file.file_type || "").toLowerCase();
  if (fileType === "md" || fileType === "markdown") {
    return true;
  }
  return (file.original_name || "").toLowerCase().endsWith(".md");
}

async function loadFiles() {
  const conversationId = conversationIdValue.value;
  if (!conversationId) {
    ElMessage.error("无效的会话 ID");
    return;
  }

  loading.value = true;
  try {
    const res = await getSandboxFiles(conversationId);
    if (res.code === 0) {
      files.value = res.data.files || [];
      sandboxSize.value = res.data.sandbox_size_mb || 0;
      sandboxLimit.value = res.data.sandbox_size_limit_mb || 100;
      syncFocusedFile();
    } else {
      ElMessage.error(res.message || "加载文件列表失败");
    }
  } catch (error) {
    ElMessage.error("加载文件列表失败");
  } finally {
    loading.value = false;
  }
}

function syncFocusedFile() {
  if (focusedFileId.value && files.value.some((file) => file.file_id === focusedFileId.value)) {
    return;
  }
  focusedFileId.value = files.value[0]?.file_id ?? null;
}

function toActionTarget(row: SandboxFile): SandboxFileActionTarget | null {
  const conversationId = conversationIdValue.value;
  if (!conversationId) {
    return null;
  }
  return {
    label: row.original_name,
    canPreview: true,
    canDownload: true,
    canRename: true,
    canDelete: true,
    conversationId,
    fileId: row.file_id,
    fileType: row.file_type,
    fileSize: row.file_size,
  };
}

const sandboxFileActions = useSandboxFileActions({
  filePreview,
  onRefresh: loadFiles,
  getDeleteDialogConfig: (target) => ({
    title: "删除文件",
    subject: target.label,
    detail: "删除后将从当前对话沙箱中移除，且不可恢复。",
    confirmText: "删除文件",
  }),
});

function countFilesInNode(node: ConversationFileTreeNode): number {
  if (node.type === "file") return 1;
  return (node.children || []).reduce((total, child) => total + countFilesInNode(child), 0);
}

async function handleDeleteDirectory(node: ConversationFileTreeNode) {
  const conversationId = conversationIdValue.value;
  if (!conversationId) {
    ElMessage.error("无效的会话 ID");
    return;
  }

  const fileCount = countFilesInNode(node);

  try {
    await showDangerConfirm({
      title: "删除目录",
      subject: node.label,
      detail: `该操作会递归删除目录内 ${fileCount} 个文件，且不可恢复。`,
      confirmText: "删除目录",
    });

    const res = await deleteSandboxDirectory(conversationId, node.path);
    if (res.code === 0) {
      ElMessage.success("目录删除成功");
      await loadFiles();
    } else {
      ElMessage.error(res.message || "目录删除失败");
    }
  } catch (error) {
    // 用户取消
  }
}

async function handleNodeCommand(commandValue: string | number | object, node: ConversationFileTreeNode) {
  if (typeof commandValue !== "string") {
    return;
  }

  const command = commandValue as NodeCommand | "edit";
  if (command === "delete") {
    if (node.type === "directory") {
      await handleDeleteDirectory(node);
      return;
    }

    if (node.item?.raw) {
      const target = toActionTarget(node.item.raw as SandboxFile);
      if (!target) {
        ElMessage.error("无效的会话 ID");
        return;
      }
      await sandboxFileActions.handleDelete(target);
    }
    return;
  }

  if (!node.item?.raw) {
    return;
  }

  if (command === "preview") {
    const target = toActionTarget(node.item.raw as SandboxFile);
    if (!target) {
      ElMessage.error("无效的会话 ID");
      return;
    }
    await sandboxFileActions.handlePreview(target);
    return;
  }

  if (command === "download") {
    const target = toActionTarget(node.item.raw as SandboxFile);
    if (!target) {
      ElMessage.error("无效的会话 ID");
      return;
    }
    await sandboxFileActions.handleDownload(target);
    return;
  }

  if (command === "rename") {
    const target = toActionTarget(node.item.raw as SandboxFile);
    if (!target) {
      ElMessage.error("无效的会话 ID");
      return;
    }
    await sandboxFileActions.handleRename(target);
    return;
  }

  if (command === "edit") {
    const target = toActionTarget(node.item.raw as SandboxFile);
    if (!target) {
      ElMessage.error("无效的会话 ID");
      return;
    }
    await sandboxFileActions.handlePreview(target, { startInEdit: true });
  }
}

function handleTreeItemDoubleClick(item: ConversationFileTreeItem) {
  const file = item.raw as SandboxFile | undefined;
  if (!file) {
    return;
  }
  focusedFileId.value = file.file_id;

  const target = toActionTarget(file);
  if (!target) {
    ElMessage.error("无效的会话 ID");
    return;
  }
  void sandboxFileActions.handlePreview(target);
}

function handleTreeItemClick(item: ConversationFileTreeItem) {
  const file = item.raw as SandboxFile | undefined;
  if (!file) return;
  focusedFileId.value = file.file_id;
}

function formatBytes(size?: number): string {
  if (!size || Number.isNaN(size)) return "未知";
  const units = ["B", "KB", "MB", "GB"];
  let index = 0;
  let value = size;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

function formatTime(value?: string | null): string {
  if (!value) return "未知";
  return new Date(value).toLocaleString("zh-CN");
}

function handleInspectorAction(actionKey: string) {
  const file = focusedFile.value;
  if (!file) return;
  const target = toActionTarget(file);
  if (!target) {
    ElMessage.error("无效的会话 ID");
    return;
  }
  if (actionKey === "preview") {
    void sandboxFileActions.handlePreview(target);
    return;
  }
  if (actionKey === "download") {
    void sandboxFileActions.handleDownload(target);
    return;
  }
  if (actionKey === "rename") {
    void sandboxFileActions.handleRename(target);
    return;
  }
  if (actionKey === "edit") {
    void sandboxFileActions.handlePreview(target, { startInEdit: true });
    return;
  }
  if (actionKey === "delete") {
    void sandboxFileActions.handleDelete(target);
  }
}

async function handleCleanup() {
  const conversationId = conversationIdValue.value;
  if (!conversationId) {
    ElMessage.error("无效的会话 ID");
    return;
  }

  try {
    await showDangerConfirm({
      title: "清空沙箱",
      subject: "当前对话沙箱",
      detail: "此操作会删除沙箱中的全部文件与目录，且不可恢复。",
      confirmText: "清空沙箱",
    });

    cleaning.value = true;
    const res = await cleanupSandbox(conversationId);
    if (res.code === 0) {
      ElMessage.success("清理成功");
      loadFiles();
    } else {
      ElMessage.error(res.message || "清理失败");
    }
  } catch (error) {
    // 用户取消
  } finally {
    cleaning.value = false;
  }
}

async function handleArchiveDownload() {
  const conversationId = conversationIdValue.value;
  if (!conversationId) {
    ElMessage.error("无效的会话 ID");
    return;
  }

  archiving.value = true;
  try {
    const res = await downloadSandboxArchive(conversationId);
    const headerFilename =
      (res.headers?.["x-archive-filename"] as string | undefined) ||
      (res.headers?.["X-Archive-Filename"] as string | undefined);
    const disposition =
      (res.headers?.["content-disposition"] as string | undefined) ||
      (res.headers?.["Content-Disposition"] as string | undefined);
    const filename = decodeArchiveFilename(headerFilename) || resolveFilenameFromDisposition(disposition) || `conversation_${conversationId}.zip`;
    const blob = new Blob([res.data], { type: "application/zip" });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (error) {
    ElMessage.error("打包下载失败");
  } finally {
    archiving.value = false;
  }
}

function resolveFilenameFromDisposition(disposition?: string): string {
  if (!disposition) return "";
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const quotedMatch = disposition.match(/filename="([^"]+)"/i);
  if (quotedMatch?.[1]) return quotedMatch[1];
  const plainMatch = disposition.match(/filename=([^;]+)/i);
  return plainMatch?.[1]?.trim() || "";
}

function decodeArchiveFilename(value?: string): string {
  if (!value) return "";
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

onMounted(() => {
  loadFiles();
});

watch(conversationIdValue, (nextConversationId, prevConversationId) => {
  if (!nextConversationId || nextConversationId === prevConversationId) return;
  filePreview.close();
  files.value = [];
  focusedFileId.value = null;
  void loadFiles();
});
// 暴露刷新方法
defineExpose({
  refresh: loadFiles,
});
</script>

<style scoped>
.sandbox-files {
  --sandbox-workbench-max-height: calc(100dvh - 320px);
  max-width: 1400px;
  margin: 0 auto;
  padding: 4px 0 24px;
}

.sandbox-files--embedded {
  --sandbox-workbench-max-height: calc(100dvh - 300px);
  max-width: none;
  padding: 0 0 6px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 18px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary, #1e293b);
}

.page-subtitle {
  margin: 8px 0 0;
  max-width: 760px;
  color: var(--text-muted, #64748b);
  font-size: 14px;
  line-height: 1.6;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-action-buttons {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.embedded-summary {
  display: flex;
  align-items: stretch;
  gap: 12px;
  margin-bottom: 14px;
}

.cleanup-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 42px;
  padding: 0 16px;
  border-color: rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.04);
  color: var(--text-secondary, #475569);
  box-shadow: none;
}

.cleanup-button:hover,
.cleanup-button:focus-visible {
  border-color: rgba(248, 113, 113, 0.26);
  background: rgba(248, 113, 113, 0.08);
  color: #dc2626;
}

.archive-button:hover,
.archive-button:focus-visible {
  border-color: #f5d9a7;
  background: #FDF6EC;
  color: #9a6a19;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 240px;
  padding: 14px 16px;
  border: 1px solid var(--border-primary, #e2e8f0);
  border-radius: 14px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--bg-card, #ffffff) 94%, #ffffff 6%) 0%, color-mix(in srgb, var(--bg-card, #ffffff) 88%, var(--bg-page, #f8fafc) 12%) 100%);
  box-shadow: var(--shadow-sm, 0 8px 24px rgba(15, 23, 42, 0.06));
}

.stat-label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted, #94a3b8);
}

.stat-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
}

.browser-shell {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-primary, #e2e8f0);
  border-radius: 18px;
  overflow: hidden;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--bg-card, #ffffff) 92%, var(--bg-page, #f8fafc) 8%) 0%, color-mix(in srgb, var(--bg-card, #ffffff) 98%, transparent 2%) 100%);
  box-shadow: 0 12px 36px rgba(15, 23, 42, 0.06);
  padding: 14px;
  height: var(--sandbox-workbench-max-height);
  max-height: var(--sandbox-workbench-max-height);
}

.browser-workbench {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.75fr) minmax(320px, 1fr);
  gap: 14px;
  align-items: start;
  min-height: 0;
  overflow: hidden;
}

.browser-tree-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--bg-card, #ffffff) 96%, var(--bg-page, #f8fafc) 4%) 0%,
      color-mix(in srgb, var(--bg-card, #ffffff) 99%, transparent 1%) 100%
    );
  min-height: 180px;
  padding: 8px 10px 10px;
  box-sizing: border-box;
}

.sandbox-files--embedded .browser-shell {
  flex: 1;
  height: 100%;
  max-height: none;
  min-height: 0;
}

.browser-tree-pane :deep(.conversation-file-tree) {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.browser-tree-pane :deep(.conversation-file-tree .tree-wrap) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 4px;
}

.browser-workbench :deep(.sandbox-file-inspector) {
  position: sticky;
  top: 6px;
  max-height: calc(var(--sandbox-workbench-max-height) - 12px);
  overflow-y: auto;
}

.browser-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-primary, #e2e8f0);
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--bg-page, #f8fafc) 68%, var(--bg-card, #ffffff) 32%) 0%, color-mix(in srgb, var(--bg-card, #ffffff) 92%, transparent 8%) 100%);
}

.browser-toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.browser-toolbar-right {
  display: grid;
  grid-template-columns: minmax(220px, 280px) auto;
  align-items: center;
  justify-content: end;
  gap: 18px;
  margin-left: auto;
}

.browser-pill {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: #0f172a;
  color: #f8fafc;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.browser-hint {
  color: var(--text-muted, #64748b);
  font-size: 13px;
  line-height: 1.6;
  text-align: right;
}

.toolbar-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-summary span {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.1);
  color: var(--text-secondary, #64748b);
  font-size: 12px;
  font-weight: 600;
}

.tree-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.04);
  flex-shrink: 0;
}

.sandbox-files--embedded .embedded-summary {
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.sandbox-files--embedded .stat-card {
  min-width: 300px;
}

.sandbox-files--embedded .browser-toolbar {
  padding: 16px 20px;
}

.tree-control-button {
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary, #64748b);
  font-size: 13px;
  font-weight: 600;
  transition:
    background 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.tree-control-button:hover,
.tree-control-button:focus-visible {
  background: rgba(59, 130, 246, 0.08);
  color: var(--text-primary, #0f172a);
  outline: none;
}

.tree-control-button.is-active {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.14) 0%, rgba(37, 99, 235, 0.2) 100%);
  color: var(--text-primary, #0f172a);
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.18);
}

.tree-wrap {
  min-height: 160px;
  padding: 12px 14px 16px;
  background: transparent;
}

.tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-height: 42px;
  padding: 4px 6px;
  border-radius: 10px;
}

:deep(.el-tree-node__content) {
  height: auto;
  min-height: 42px;
  border-radius: 10px;
}

:deep(.el-tree-node__content:hover) {
  background: rgba(15, 23, 42, 0.05);
}

:deep(.el-tree) {
  background: transparent;
  color: var(--text-primary, #0f172a);
}

:deep(.el-tree-node) {
  background: transparent;
}

.tree-node-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.tree-node-label {
  word-break: break-all;
}

.node-meta {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.1);
  color: #909399;
  font-size: 12px;
}

.node-tag {
  margin-left: 4px;
}

.tree-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 280px;
  border: 1px dashed rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  background:
    radial-gradient(circle at top, rgba(59, 130, 246, 0.08), transparent 42%),
    rgba(15, 23, 42, 0.02);
  text-align: center;
}

.tree-empty-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 62px;
  height: 62px;
  border-radius: 20px;
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
  font-size: 26px;
}

.tree-empty-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

.tree-empty-text {
  max-width: 520px;
  color: var(--text-secondary, #64748b);
  font-size: 14px;
  line-height: 1.7;
}

.file-icon {
  font-size: 18px;
  color: #409eff;
}

.action-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.04);
  color: var(--text-secondary, #94a3b8);
  opacity: 0;
  pointer-events: none;
  transform: translateX(4px);
  transition:
    opacity 0.18s ease,
    transform 0.18s ease,
    background 0.18s ease,
    color 0.18s ease,
    border-color 0.18s ease;
}

.action-trigger:hover,
.action-trigger:focus-visible {
  background: rgba(59, 130, 246, 0.1);
  color: var(--text-primary, #0f172a);
  border-color: rgba(96, 165, 250, 0.35);
  outline: none;
}

.tree-node:hover .action-trigger,
.tree-node:focus-within .action-trigger,
:deep(.el-tree-node__content:hover) .action-trigger,
:deep(.el-tree-node__content:focus-within) .action-trigger {
  opacity: 1;
  pointer-events: auto;
  transform: translateX(0);
}

.preview-content {
  min-height: 300px;
  max-height: 60vh;
  overflow: auto;
}

.preview-dialog-header {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}

.preview-dialog-heading {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  width: 100%;
}

.preview-dialog-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.preview-dialog-title {
  margin: 0;
  font-size: 24px;
  line-height: 1.35;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
  word-break: break-word;
}

.preview-dialog-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  width: 100%;
  color: var(--text-secondary, #64748b);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.preview-dialog-meta span {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.12);
}

.preview-image {
  max-width: 100%;
  max-height: 60vh;
  display: block;
  margin: 0 auto;
}

.preview-pdf {
  width: 100%;
  min-height: 70vh;
  border: 1px solid var(--border-primary, #e4e7ed);
  border-radius: 4px;
}

.preview-text {
  background: var(--bg-code, #f5f5f5);
  padding: 20px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: monospace;
  font-size: 14px;
  color: var(--text-primary, #303133);
  max-height: 60vh;
  overflow: auto;
}

.preview-markdown {
  padding: 8px 4px;
}

.preview-table-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sheet-meta {
  color: var(--text-secondary, #606266);
  font-size: 13px;
}

.xlsx-table {
  width: 100%;
}

.preview-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

:global(.sandbox-preview-dialog .el-dialog) {
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 26px;
  overflow: hidden;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--bg-card, #ffffff) 95%, var(--bg-page, #f8fafc) 5%) 0%, color-mix(in srgb, var(--bg-card, #ffffff) 99%, transparent 1%) 100%);
  box-shadow: 0 28px 80px rgba(15, 23, 42, 0.22);
}

:global(.sandbox-preview-dialog .el-dialog__header) {
  margin: 0;
  padding: 24px 28px 0;
}

:global(.sandbox-preview-dialog .el-dialog__body) {
  padding: 18px 28px 0;
}

:global(.sandbox-preview-dialog .el-dialog__footer) {
  padding: 22px 28px 28px;
}

:global(.sandbox-preview-dialog .el-dialog__footer .el-button) {
  min-width: 108px;
  height: 42px;
  border-radius: 14px;
  font-weight: 600;
}

:global(.sandbox-preview-dialog .el-dialog__footer .preview-dialog-secondary) {
  border-color: rgba(148, 163, 184, 0.2);
  background: rgba(15, 23, 42, 0.04);
  color: var(--text-secondary, #475569);
}

:global(.sandbox-preview-dialog .el-dialog__footer .preview-dialog-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.08);
  color: var(--text-primary, #0f172a);
}

:global(.sandbox-preview-dialog .el-dialog__footer .preview-dialog-primary) {
  border: none;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #fff;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.24);
}

:global(.sandbox-preview-dialog .el-dialog__footer .preview-dialog-primary:hover) {
  background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
  color: #fff;
}

:global(.sandbox-node-menu.el-popper) {
  padding: 0;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  background: #ffffff;
  box-shadow:
    0 12px 28px rgba(15, 23, 42, 0.08),
    0 2px 8px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

:global(.sandbox-node-menu.el-popper .el-popper__arrow),
:global(.sandbox-node-menu.el-popper .el-popper__arrow::before) {
  background: #ffffff;
  border-color: #e5e7eb;
}

:global(.sandbox-node-menu .el-dropdown-menu) {
  padding: 6px;
  border: none;
  border-radius: 16px;
  background: transparent;
  box-shadow: none;
}

:global(.sandbox-node-menu .el-dropdown-menu__item) {
  gap: 8px;
  min-width: 128px;
  padding: 10px 12px;
  border-radius: 10px;
  color: #475569;
}

:global(.sandbox-node-menu .el-dropdown-menu__item:hover) {
  background: #f8fafc;
  color: var(--text-primary, #0f172a);
}

:global(.sandbox-node-menu .el-dropdown-menu__item.danger-item) {
  color: #dc2626;
}

:global(.sandbox-node-menu .el-dropdown-menu__item.danger-item:hover) {
  background: #fef2f2;
  color: #b91c1c;
}

:global(.sandbox-confirm-dialog.el-message-box) {
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

:global(.sandbox-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.sandbox-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.sandbox-confirm-dialog .el-message-box__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.sandbox-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.sandbox-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.sandbox-rename-dialog .el-message-box__content) {
  padding-top: 16px;
}

:global(.sandbox-rename-dialog .el-message-box__input) {
  padding-top: 4px;
}

:global(.sandbox-rename-dialog .el-input__wrapper) {
  border-radius: 12px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.28) inset;
  background: rgba(248, 250, 252, 0.88);
}

:global(.sandbox-rename-dialog .el-input__inner) {
  height: 38px;
}

:global(.sandbox-confirm-dialog .el-message-box__message) {
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

:global(.sandbox-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.sandbox-confirm-dialog .el-message-box__btns .el-button) {
  min-width: 108px;
  height: 42px;
  border-radius: 14px;
  font-weight: 600;
}

:global(.sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-primary) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-primary:hover) {
  border-color: #fca5a5;
  background: #fef2f2;
  color: #b91c1c;
}

:global(html.dark) .stat-card {
  border-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 82%, #6b7280 18%);
  background:
    linear-gradient(180deg, rgba(34, 38, 46, 0.96) 0%, rgba(27, 31, 38, 0.98) 100%);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.28);
}

:global(html.dark) .browser-shell {
  border-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 78%, #4b5563 22%);
  background:
    linear-gradient(180deg, rgba(23, 27, 34, 0.96) 0%, rgba(18, 21, 27, 0.98) 100%);
  box-shadow: 0 20px 44px rgba(0, 0, 0, 0.26);
}

:global(html.dark) .browser-tree-pane {
  border-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 78%, #4b5563 22%);
  background: linear-gradient(180deg, rgba(23, 27, 34, 0.96) 0%, rgba(18, 21, 27, 0.98) 100%);
}

:global(html.dark) .browser-tree-pane :deep(.el-tree),
:global(html.dark) .browser-tree-pane :deep(.el-tree-node),
:global(html.dark) .browser-tree-pane :deep(.el-tree-node__content) {
  background: transparent;
  color: var(--text-primary, #e5e5e5);
}

:global(html.dark) .browser-toolbar {
  border-bottom-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 80%, #4b5563 20%);
  background:
    linear-gradient(90deg, rgba(30, 34, 42, 0.96) 0%, rgba(24, 28, 35, 0.92) 100%);
}

:global(html.dark) .browser-pill {
  background: color-mix(in srgb, #60a5fa 18%, #111827 82%);
  color: #dbeafe;
}

:global(html.dark) .browser-hint,
:global(html.dark) .node-meta {
  color: var(--text-secondary, #b3b3b3);
}

:global(html.dark) .toolbar-summary span,
:global(html.dark) .node-type-chip,
:global(html.dark) .node-meta {
  background: rgba(148, 163, 184, 0.08);
}

:global(html.dark) .file-icon {
  color: #7cb8ff;
}

:global(html.dark) .tree-controls {
  border-color: rgba(148, 163, 184, 0.12);
  background: rgba(148, 163, 184, 0.06);
}

:global(html.dark) .tree-control-button {
  color: #94a3b8;
}

:global(html.dark) .tree-control-button:hover,
:global(html.dark) .tree-control-button:focus-visible {
  background: rgba(96, 165, 250, 0.12);
  color: #f8fafc;
}

:global(html.dark) .tree-control-button.is-active {
  background: linear-gradient(135deg, rgba(96, 165, 250, 0.16) 0%, rgba(37, 99, 235, 0.26) 100%);
  color: #f8fafc;
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.18);
}

:global(html.dark) .cleanup-button {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: var(--text-secondary, #cbd5e1);
}

:global(html.dark) .cleanup-button:hover,
:global(html.dark) .cleanup-button:focus-visible {
  border-color: rgba(248, 113, 113, 0.22);
  background: rgba(248, 113, 113, 0.1);
  color: #fca5a5;
}

:global(html.dark) .archive-button:hover,
:global(html.dark) .archive-button:focus-visible {
  border-color: #f5d9a7;
  background: #FDF6EC;
  color: #9a6a19;
}

:global(html.dark) .action-trigger {
  border-color: rgba(148, 163, 184, 0.18);
  background: rgba(148, 163, 184, 0.08);
  color: var(--text-secondary, #94a3b8);
}

:global(html.dark) .action-trigger:hover,
:global(html.dark) .action-trigger:focus-visible {
  background: rgba(96, 165, 250, 0.14);
  color: #e2e8f0;
  border-color: rgba(96, 165, 250, 0.32);
}

:global(html.dark) :deep(.el-tree-node__content:hover) {
  background: rgba(96, 165, 250, 0.1);
}

:global(html.dark) :deep(.el-tree-node:focus > .el-tree-node__content) {
  background: rgba(96, 165, 250, 0.14);
}

:global(html.dark) :deep(.el-progress-bar__outer) {
  background: rgba(255, 255, 255, 0.08);
}

:global(html.dark) .preview-pdf,
:global(html.dark) .preview-text {
  background: color-mix(in srgb, var(--bg-code, #252525) 92%, #0f172a 8%);
}

:global(html.dark) .preview-dialog-badge {
  background: rgba(96, 165, 250, 0.14);
  color: #bfdbfe;
}

:global(html.dark) .preview-dialog-title {
  color: #f8fafc;
}

:global(html.dark) .preview-dialog-meta {
  color: #94a3b8;
}

:global(html.dark) .preview-dialog-meta span {
  background: rgba(148, 163, 184, 0.1);
}

:global(html.dark) .tree-empty-state {
  border-color: rgba(148, 163, 184, 0.14);
  background:
    radial-gradient(circle at top, rgba(96, 165, 250, 0.12), transparent 42%),
    rgba(15, 23, 42, 0.18);
}

:global(html.dark) .tree-empty-icon {
  background: rgba(96, 165, 250, 0.14);
  color: #bfdbfe;
}

:global(html.dark) .tree-empty-title {
  color: #f8fafc;
}

:global(html.dark) .tree-empty-text {
  color: #94a3b8;
}

:global(html.dark .sandbox-node-menu.el-popper) {
  background: color-mix(in srgb, var(--bg-card, #0f172a) 94%, #020617 6%);
  box-shadow: 0 20px 48px rgba(2, 6, 23, 0.34);
  border: 1px solid rgba(148, 163, 184, 0.08);
}

:global(html.dark .sandbox-node-menu.el-popper .el-popper__arrow),
:global(html.dark .sandbox-node-menu.el-popper .el-popper__arrow::before) {
  background: color-mix(in srgb, var(--bg-card, #0f172a) 94%, #020617 6%);
  border-color: rgba(148, 163, 184, 0.08);
}

:global(html.dark .sandbox-node-menu .el-dropdown-menu) {
  background: transparent;
}

:global(html.dark .sandbox-node-menu .el-dropdown-menu__item) {
  color: var(--text-secondary, #cbd5e1);
}

:global(html.dark .sandbox-node-menu .el-dropdown-menu__item:hover) {
  background: rgba(96, 165, 250, 0.12);
  color: #f8fafc;
}

:global(html.dark .sandbox-node-menu .el-dropdown-menu__item.danger-item) {
  color: #fca5a5;
}

:global(html.dark .sandbox-node-menu .el-dropdown-menu__item.danger-item:hover) {
  background: rgba(248, 113, 113, 0.14);
  color: #fecaca;
}

:global(html.dark .sandbox-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background:
    linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .sandbox-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}

:global(html.dark .sandbox-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: #94a3b8;
}

:global(html.dark .sandbox-rename-dialog .el-input__wrapper) {
  background: rgba(148, 163, 184, 0.08);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.18) inset;
}

:global(html.dark .sandbox-rename-dialog .el-input__inner) {
  color: #e2e8f0;
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

:global(html.dark .sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}

:global(html.dark .sandbox-preview-dialog .el-dialog) {
  border-color: rgba(148, 163, 184, 0.12);
  background:
    linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}


:global(html.dark .sandbox-preview-dialog .el-dialog__footer .preview-dialog-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .sandbox-preview-dialog .el-dialog__footer .preview-dialog-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}

@media (max-width: 900px) {
  .sandbox-files,
  .sandbox-files--embedded {
    --sandbox-workbench-max-height: none;
  }

  .page-header {
    flex-direction: column;
  }

  .embedded-summary,
  .header-actions {
    width: 100%;
    flex-direction: column;
    align-items: stretch;
  }

  .stat-card {
    min-width: auto;
  }

  .cleanup-button {
    width: 100%;
    justify-content: center;
  }

  .browser-toolbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .browser-workbench {
    grid-template-columns: 1fr;
  }

  .browser-tree-pane {
    padding: 8px;
  }

  .browser-tree-pane :deep(.conversation-file-tree .tree-wrap) {
    overflow: visible;
    padding-right: 0;
  }

  .browser-shell {
    height: auto;
    max-height: none;
  }

  .browser-workbench {
    overflow: visible;
  }

  .browser-workbench :deep(.sandbox-file-inspector) {
    position: static;
    max-height: none;
    overflow: visible;
  }

  .browser-toolbar-left,
  .browser-toolbar-right {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    margin-left: 0;
  }

  .browser-hint {
    text-align: left;
  }

  .preview-dialog-header {
    flex-direction: column;
  }

  .tree-controls {
    width: 100%;
    flex-wrap: wrap;
    border-radius: 18px;
  }

  .tree-node {
    align-items: flex-start;
    flex-direction: column;
  }

  .action-trigger {
    opacity: 1;
    pointer-events: auto;
    transform: none;
  }
}
</style>
