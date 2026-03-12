<template>
  <el-drawer
    :model-value="modelValue"
    direction="rtl"
    size="min(1320px, 97vw)"
    class="project-file-sandbox-drawer"
    modal-class="project-file-sandbox-mask"
    destroy-on-close
    append-to-body
    @update:model-value="(val: boolean) => emit('update:modelValue', val)"
  >
    <template #header>
      <div class="sandbox-drawer-header">
        <div class="sandbox-drawer-badge">项目协作工作区</div>
        <h3 class="sandbox-drawer-title">文件沙箱</h3>
        <p class="sandbox-drawer-subtitle">
          汇总项目级节点资料、关联需求资料及需求挂载对话中的沙箱文件，支持按结构快速定位。
        </p>
        <div class="sandbox-drawer-project">{{ projectName }}</div>
      </div>
    </template>

    <section class="file-sandbox-shell" v-loading="loading">
      <div class="file-sandbox-summary">
        <div class="summary-card">
          <div class="summary-label">项目级文件</div>
          <div class="summary-value">{{ projectAssetCount }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">需求级文件</div>
          <div class="summary-value">{{ requirementAssetCount }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">需求关联会话文件</div>
          <div class="summary-value">{{ requirementConversationFileCount }}</div>
        </div>
        <div class="summary-card summary-card--action">
          <div class="action-card-row">
            <button
              type="button"
              class="download-entry-card"
              :disabled="!projectId || archiveDownloading"
              @click="handleArchiveDownload"
            >
              <span class="upload-entry-card__icon">
                <el-icon><Download /></el-icon>
              </span>
              <span class="upload-entry-card__content">
                <span class="upload-entry-card__title">{{ archiveDownloading ? '打包中...' : '打包下载' }}</span>
                <span class="upload-entry-card__hint">按沙箱树导出 ZIP</span>
              </span>
            </button>
            <button
              type="button"
              class="upload-entry-card"
              :disabled="!projectId"
              @click="openProjectAssetUploadDialog"
            >
              <span class="upload-entry-card__icon">
                <el-icon><UploadFilled /></el-icon>
              </span>
              <span class="upload-entry-card__content">
                <span class="upload-entry-card__title">上传资料</span>
                <span class="upload-entry-card__hint">归档到项目文件区</span>
              </span>
            </button>
          </div>
        </div>
      </div>

      <div class="file-sandbox-toolbar">
        <div class="toolbar-left">
          <el-input v-model="keyword" clearable placeholder="搜索文件、节点、需求或会话" class="sandbox-search" />
          <span>{{ directoryCount }} 个目录</span>
          <span>{{ fileCount }} 个文件</span>
        </div>
        <div class="toolbar-right">
          <div class="tree-controls" role="tablist" aria-label="目录树展开控制">
            <button type="button" class="tree-control-button" @click="expandOneLevel">展开一级</button>
            <button type="button" class="tree-control-button" @click="expandAll">全部展开</button>
            <button type="button" class="tree-control-button" @click="collapseAll">全部收起</button>
          </div>
        </div>
      </div>

      <div class="file-sandbox-workbench">
        <div class="tree-wrap" :key="treeRenderSeed">
          <el-tree
            v-if="filteredTree.length"
            :data="filteredTree"
            node-key="key"
            :default-expanded-keys="expandedKeys"
            :expand-on-click-node="false"
          >
            <template #default="{ data }">
              <div class="tree-node">
                <div
                  class="tree-node-main"
                  @click.stop="handleNodeClick(data)"
                  @dblclick.stop="handleNodeLabelDoubleClick(data)"
                >
                  <el-icon class="node-icon" :style="iconStyle(data)"><component :is="iconByNode(data)" /></el-icon>
                  <span class="tree-node-label">{{ data.label }}</span>
                  <el-tag
                    v-if="data.tag"
                    size="small"
                    :effect="data.kind === 'node' ? 'light' : 'plain'"
                    :type="data.tagType"
                    class="node-tag"
                  >
                    {{ data.tag }}
                  </el-tag>
                  <span v-if="data.meta" class="node-meta">{{ data.meta }}</span>
                </div>
                <el-dropdown
                  v-if="isFileNode(data)"
                  trigger="click"
                  placement="bottom-end"
                  popper-class="sandbox-node-menu"
                  :teleported="true"
                  @command="handleNodeCommand($event, data)"
                >
                  <button class="action-trigger" type="button" @click.stop>
                    <el-icon><MoreFilled /></el-icon>
                  </button>
                  <template #dropdown>
                    <SandboxFileActionMenu
                      :can-preview="data.canPreview"
                      :can-download="data.canDownload"
                      :can-rename="data.canRename"
                      :can-refetch="data.canRefetch"
                      :can-delete="data.canDelete"
                      delete-label="删除"
                    />
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-tree>
          <el-empty
            v-else-if="!loading"
            :description="keyword.trim() ? '没有匹配内容，试试更短关键词' : '当前项目暂无可展示的沙箱文件'"
          />
        </div>
        <SandboxFileInspectorCard
          badge="项目沙箱"
          title="文件详情"
          overline="当前聚焦文件"
          :file-name="focusedFileNode?.label || ''"
          :file-path="focusedFileNode?.previewUrl || focusedFileNode?.downloadUrl || focusedFileNode?.meta || ''"
          :tags="focusedInspectorTags"
          :fields="focusedInspectorFields"
          :summary="focusedInspectorSummary"
          summary-title="文件说明"
          empty-text="从左侧树中选择一个文件，这里会显示更完整的资料信息和快捷操作。"
          :actions="focusedInspectorActions"
          @action="handleInspectorAction"
        />
      </div>
    </section>

    <UnifiedFilePreviewDialog
      v-model="filePreview.visible.value"
      :loading="filePreview.loading.value"
      :title="filePreview.title.value"
      :file-type="filePreview.fileType.value"
      :file-size="filePreview.fileSize.value"
      :mode="filePreview.mode.value"
      :can-edit="filePreview.canEdit.value"
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

    <el-dialog
      v-model="projectAssetUploadVisible"
      width="760px"
      class="asset-upload-dialog"
      custom-class="asset-upload-dialog-panel"
      :show-close="false"
      destroy-on-close
    >
      <AssetUploadEditor
        :asset-type="projectAssetForm.asset_type"
        :title="projectAssetForm.title"
        :source-url="projectAssetForm.source_url"
        :content="projectAssetForm.content"
        :files="projectAssetForm.files"
        :type-options="projectAssetTypeOptions"
        upload-hint="上传后将归档到当前项目资料，并在沙箱目录中可追踪"
        @update:asset-type="(value) => (projectAssetForm.asset_type = value as typeof projectAssetForm.asset_type)"
        @update:title="(value) => (projectAssetForm.title = value)"
        @update:source-url="(value) => (projectAssetForm.source_url = value)"
        @update:content="(value) => (projectAssetForm.content = value)"
        @files-change="handleProjectAssetFilesChange"
        @file-clear="() => (projectAssetForm.files = [])"
      >
        <template #actions>
          <el-button @click="projectAssetUploadVisible = false">取消</el-button>
          <el-button type="primary" :loading="projectAssetSubmitting" @click="handleSubmitProjectAsset">
            上传并保存
          </el-button>
        </template>
      </AssetUploadEditor>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Document, Files, FolderOpened, Link, MoreFilled, UploadFilled, View, Download, Edit, RefreshRight, Delete } from '@element-plus/icons-vue'
import AssetUploadEditor from '@/components/common/AssetUploadEditor.vue'
import SandboxFileActionMenu from '@/components/common/SandboxFileActionMenu.vue'
import SandboxFileInspectorCard from '@/components/common/SandboxFileInspectorCard.vue'
import UnifiedFilePreviewDialog from '@/components/common/UnifiedFilePreviewDialog.vue'
import { useAssetSyncPolling } from '@/composables/useAssetSyncPolling'
import { useFilePreview } from '@/composables/useFilePreview'
import { useSandboxFileActions } from '@/composables/useSandboxFileActions'
import { createAsset, uploadProjectAssetFile } from '@/api/assets'
import { downloadProjectSandboxArchive, type RelatedSandboxView } from '@/api/sandboxViews'
import { getAssetSyncLabel, isYuqueUrl } from '@/utils/assetSync'
import {
  collectSandboxDirectoryCount,
  collectSandboxDirectoryKeys,
  collectSandboxFileCount,
  pruneEmptySandboxTree,
} from '@/utils/sandboxTree'

interface SandboxTreeNode {
  key: string
  label: string
  kind: 'scope' | 'requirement' | 'group' | 'node' | 'conversation' | 'asset' | 'file'
  tag?: string
  tagType?: 'info' | 'warning' | 'success' | 'danger' | 'primary'
  meta?: string
  previewUrl?: string
  downloadUrl?: string
  fileId?: number
  assetId?: number
  assetType?: string
  fileType?: string
  fileSize?: number
  conversationId?: number
  canPreview?: boolean
  canDownload?: boolean
  canRename?: boolean
  canRefetch?: boolean
  canDelete?: boolean
  searchableText: string
  children?: SandboxTreeNode[]
}

interface AggregatedConversation {
  conversation_id: number
  conversation_title?: string
  binding_type: string
  sandbox_files: RelatedSandboxView['nodes'][number]['conversations'][number]['sandbox_files']
}

type NodeCommand = 'preview' | 'download' | 'rename' | 'refetch' | 'delete'

interface AggregatedNodeBucket {
  node_id: number
  node_code: string
  node_name: string
  status: string
  instance_id: number
  scope_type: 'PROJECT' | 'REQUIREMENT'
  scope_id: number
  scope_title: string
  conversations: Map<number, AggregatedConversation>
}

const statusLabelMap: Record<string, string> = {
  UNBOUND: '未绑定流程',
  NOT_STARTED: '未开始',
  IN_PROGRESS: '进行中',
  COMPLETED: '已完成',
  CANCELED: '取消',
  PENDING: '待处理',
  RUNNING: '进行中',
  SUCCEEDED: '完成',
  FAILED: '失败',
  SKIPPED: '跳过',
  BLOCKED: '阻塞',
}

const statusTagTypeMap: Record<string, 'info' | 'warning' | 'success' | 'danger' | 'primary'> = {
  UNBOUND: 'info',
  NOT_STARTED: 'info',
  IN_PROGRESS: 'warning',
  COMPLETED: 'success',
  CANCELED: 'danger',
  PENDING: 'info',
  RUNNING: 'warning',
  SUCCEEDED: 'success',
  FAILED: 'danger',
  SKIPPED: 'primary',
  BLOCKED: 'danger',
}

const props = defineProps<{
  modelValue: boolean
  loading: boolean
  projectId: number | null
  projectName: string
  sandboxView: RelatedSandboxView | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'go-requirement-pool'): void
  (e: 'refresh'): void
}>()

const keyword = ref('')
const expandedKeys = ref<string[]>([])
const treeRenderSeed = ref(0)
const sandboxViewData = ref<RelatedSandboxView | null>(null)
const focusedFileKey = ref<string | null>(null)
const filePreview = useFilePreview()
const projectAssetUploadVisible = ref(false)
const projectAssetSubmitting = ref(false)
const archiveDownloading = ref(false)
const projectAssetForm = ref({
  asset_type: 'FILE' as 'URL' | 'FILE' | 'MARKDOWN',
  title: '',
  source_url: '',
  content: '',
  files: [] as File[],
})
const projectAssetTypeOptions = [
  { label: '文件', value: 'FILE' },
  { label: 'URL', value: 'URL' },
  { label: 'Markdown', value: 'MARKDOWN' },
]

const treeData = computed<SandboxTreeNode[]>(() => pruneEmptySandboxTree(buildTree(sandboxViewData.value)))
const allFileNodes = computed<SandboxTreeNode[]>(() => collectFileNodes(treeData.value))
const focusedFileNode = computed<SandboxTreeNode | null>(
  () => allFileNodes.value.find((node) => node.key === focusedFileKey.value) || null,
)
const focusedInspectorTags = computed(() => {
  const node = focusedFileNode.value
  if (!node) return []
  return [
    ...(node.tag ? [{ label: node.tag, type: node.tagType || 'info' as const, effect: node.kind === 'node' ? 'light' as const : 'plain' as const }] : []),
    ...(node.assetType ? [{ label: node.assetType, type: 'info' as const, effect: 'plain' as const }] : []),
  ]
})
const focusedInspectorFields = computed(() => {
  const node = focusedFileNode.value
  if (!node) return []
  return [
    { label: '文件类型', value: resolveNodeType(node) },
    { label: '文件大小', value: formatBytes(node.fileSize || 0) },
    { label: '所属会话', value: node.conversationId ? `#${node.conversationId}` : '—' },
    { label: '来源说明', value: node.meta || '—', multiline: true },
  ]
})
const focusedInspectorSummary = computed(
  () => focusedFileNode.value?.meta || '可通过上方操作快速预览、下载或管理当前文件。',
)
const focusedInspectorActions = computed(() => {
  const node = focusedFileNode.value
  if (!node) return []
  const actions: Array<{ key: string; label: string; icon: any; variant: 'primary' | 'secondary' | 'danger' }> = []
  if (node.canPreview) actions.push({ key: 'preview', label: '预览', icon: View, variant: 'primary' })
  if (node.canDownload) actions.push({ key: 'download', label: '下载', icon: Download, variant: 'secondary' })
  if (node.canRename) actions.push({ key: 'rename', label: '重命名', icon: Edit, variant: 'secondary' })
  if (node.canRefetch) actions.push({ key: 'refetch', label: '重抓', icon: RefreshRight, variant: 'secondary' })
  if (node.canDelete) actions.push({ key: 'delete', label: '删除', icon: Delete, variant: 'danger' })
  return actions
})

const filteredTree = computed<SandboxTreeNode[]>(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return treeData.value

  const filterNode = (node: SandboxTreeNode): SandboxTreeNode | null => {
    const children = (node.children || [])
      .map((item) => filterNode(item))
      .filter((item): item is SandboxTreeNode => Boolean(item))

    if (node.searchableText.includes(q) || children.length > 0) {
      return {
        ...node,
        children,
      }
    }
    return null
  }

  return treeData.value
    .map((item) => filterNode(item))
    .filter((item): item is SandboxTreeNode => Boolean(item))
})

const directoryCount = computed(() => collectSandboxDirectoryCount(filteredTree.value))
const fileCount = computed(() => collectSandboxFileCount(filteredTree.value))
const archiveFileCount = computed(() => collectSandboxFileCount(treeData.value))

const projectAssetCount = computed(() =>
  (sandboxViewData.value?.assets || []).filter((item) => item.scope_type === 'PROJECT').length,
)

const requirementAssetCount = computed(() =>
  (sandboxViewData.value?.assets || []).filter((item) => item.scope_type === 'REQUIREMENT').length,
)

const requirementConversationFileCount = computed(() => {
  const nodes = sandboxViewData.value?.nodes || []
  return nodes.reduce((acc, node) => {
    if (node.instance_scope_type !== 'REQUIREMENT') return acc
    const count = node.conversations.reduce((subAcc, conv) => subAcc + conv.sandbox_files.length, 0)
    return acc + count
  }, 0)
})

const directoryKeys = computed(() => collectSandboxDirectoryKeys(filteredTree.value))
const topLevelDirectoryKeys = computed(() =>
  filteredTree.value
    .filter((item) => (item.children || []).length > 0)
    .map((item) => item.key),
)

const syncAssets = computed(() => sandboxViewData.value?.assets || [])
const drawerVisible = computed(() => props.modelValue)

const assetSyncPolling = useAssetSyncPolling({
  assets: syncAssets,
  isVisible: drawerVisible,
  refresh: () => {
    emit('refresh')
  },
  onSettled: (failedCount) => {
    if (failedCount > 0) {
      ElMessage.warning(`语雀资料同步结束：${failedCount} 条失败，可在详情中查看失败原因`)
      return
    }
    ElMessage.success('语雀资料已同步完成')
  },
})

watch(
  () => [props.modelValue, filteredTree.value.length],
  ([visible]) => {
    if (!visible) return
    expandAll()
  },
)

watch(
  () => props.sandboxView,
  (val) => {
    sandboxViewData.value = cloneView(val)
    syncFocusedFileNode()
  },
  { immediate: true },
)

watch(
  treeData,
  () => {
    syncFocusedFileNode()
  },
  { immediate: true },
)

function cloneView(data: RelatedSandboxView | null): RelatedSandboxView | null {
  if (!data) return null
  return JSON.parse(JSON.stringify(data)) as RelatedSandboxView
}

function isImage(type: string): boolean {
  return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'].includes(type.toLowerCase())
}

function isStandardFileNode(node: SandboxTreeNode): boolean {
  if (node.kind === 'file') return true
  if (node.kind !== 'asset') return false
  const assetType = String(node.assetType || '').toUpperCase()
  return assetType === 'FILE' || assetType === 'MARKDOWN' || Boolean(node.fileType)
}

function iconByNode(node: SandboxTreeNode) {
  if (node.kind === 'scope' || node.kind === 'requirement' || node.kind === 'group') return FolderOpened
  if (node.kind === 'node') return Files
  if (node.kind === 'conversation') return ChatDotRound
  if (isStandardFileNode(node)) return Document
  if (node.kind === 'asset') return Link
  return Document
}

function iconStyle(node: SandboxTreeNode): { color?: string } {
  if (isStandardFileNode(node)) return { color: resolveFileColor(node) }
  return {}
}

function isFileNode(node: SandboxTreeNode): boolean {
  return node.kind === 'file' || node.kind === 'asset'
}

function resolveNodeType(node: SandboxTreeNode): string {
  if (node.fileType) return node.fileType.toUpperCase()
  if (node.assetType) return node.assetType.toUpperCase()
  return '未知'
}

function collectFileNodes(nodes: SandboxTreeNode[]): SandboxTreeNode[] {
  const result: SandboxTreeNode[] = []
  const walk = (items: SandboxTreeNode[]) => {
    for (const item of items) {
      if (isFileNode(item)) {
        result.push(item)
      }
      if (item.children?.length) {
        walk(item.children)
      }
    }
  }
  walk(nodes)
  return result
}

function syncFocusedFileNode() {
  if (focusedFileKey.value && allFileNodes.value.some((node) => node.key === focusedFileKey.value)) {
    return
  }
  focusedFileKey.value = allFileNodes.value[0]?.key || null
}

function handleNodeClick(node: SandboxTreeNode) {
  if (!isFileNode(node)) return
  focusedFileKey.value = node.key
}

function resetProjectAssetForm() {
  projectAssetForm.value.asset_type = 'FILE'
  projectAssetForm.value.title = ''
  projectAssetForm.value.source_url = ''
  projectAssetForm.value.content = ''
  projectAssetForm.value.files = []
}

function openProjectAssetUploadDialog() {
  if (!props.projectId) {
    ElMessage.warning('项目信息未加载，暂时无法上传资料')
    return
  }
  resetProjectAssetForm()
  projectAssetUploadVisible.value = true
}

function handleProjectAssetFilesChange(files: File[]) {
  projectAssetForm.value.files = files
}

async function handleSubmitProjectAsset() {
  if (!props.projectId || projectAssetSubmitting.value) return

  const title = projectAssetForm.value.title.trim() || undefined
  const isUrlAsset = projectAssetForm.value.asset_type === 'URL'
  projectAssetSubmitting.value = true
  try {
    if (projectAssetForm.value.asset_type === 'FILE') {
      const selectedFiles = projectAssetForm.value.files
      if (!selectedFiles.length) {
        ElMessage.warning('请先选择上传文件')
        return
      }
      for (const file of selectedFiles) {
        await uploadProjectAssetFile(file, props.projectId, undefined, file.name)
      }
    } else if (projectAssetForm.value.asset_type === 'MARKDOWN') {
      const content = projectAssetForm.value.content.trim()
      if (!content) {
        ElMessage.warning('请填写 Markdown 内容')
        return
      }
      await createAsset({
        scope_type: 'PROJECT',
        scope_id: props.projectId,
        asset_type: 'MARKDOWN',
        title,
        content,
      })
    } else {
      const sourceUrl = projectAssetForm.value.source_url.trim()
      if (!sourceUrl) {
        ElMessage.warning('请填写 URL')
        return
      }
      const res = await createAsset({
        scope_type: 'PROJECT',
        scope_id: props.projectId,
        asset_type: 'URL',
        title,
        source_url: sourceUrl,
      })
      if (String(res.data?.refetch_status || '').toUpperCase() === 'PENDING') {
        ElMessage.info('语雀资料已提交后台下载，正在同步中...')
        assetSyncPolling.markTaskSubmitted()
      }
    }

    ElMessage.success(isUrlAsset ? '资料已保存，后台正在处理' : '项目级资料上传成功')
    projectAssetUploadVisible.value = false
    resetProjectAssetForm()
    emit('refresh')
  } finally {
    projectAssetSubmitting.value = false
  }
}

function mergeMetaWithStatus(baseMeta: string, status?: string): string {
  const syncStatus = getAssetSyncLabel(status)
  return syncStatus ? `${baseMeta} · ${syncStatus}` : baseMeta
}

const sandboxFileActions = useSandboxFileActions({
  filePreview,
  onRefresh: () => {
    emit('refresh')
  },
  getDeleteDialogConfig: (target) => ({
    title: '删除文件',
    subject: target.label,
    detail: target.assetId
      ? '删除后将从当前项目资料中移除，且不可恢复。'
      : '删除后将从对应项目级会话沙箱中移除，且不可恢复。',
    confirmText: '删除文件',
  }),
})

async function handleNodeCommand(commandValue: string | number | object, node: SandboxTreeNode) {
  if (typeof commandValue !== 'string') return
  if (isFileNode(node)) {
    focusedFileKey.value = node.key
  }
  const command = commandValue as NodeCommand
  if (command === 'preview') {
    await sandboxFileActions.handlePreview(node)
    return
  }
  if (command === 'download') {
    await sandboxFileActions.handleDownload(node)
    return
  }
  if (command === 'rename') {
    await sandboxFileActions.handleRename(node)
    return
  }
  if (command === 'refetch') {
    await sandboxFileActions.handleRefetch(node)
    return
  }
  if (command === 'delete') {
    await sandboxFileActions.handleDelete(node)
  }
}

async function handleArchiveDownload() {
  if (!props.projectId) {
    ElMessage.error('无效的项目 ID')
    return
  }
  if (archiveFileCount.value === 0) {
    ElMessage.warning('当前文件树为空，无法打包下载')
    return
  }
  archiveDownloading.value = true
  try {
    const res = await downloadProjectSandboxArchive(props.projectId)
    const headerFilename =
      (res.headers?.['x-archive-filename'] as string | undefined) ||
      (res.headers?.['X-Archive-Filename'] as string | undefined)
    const disposition =
      (res.headers?.['content-disposition'] as string | undefined) ||
      (res.headers?.['Content-Disposition'] as string | undefined)
    const fallbackFilename = buildZipFilename(
      props.sandboxView?.scope_name || props.projectName,
      `project_${props.projectId}`,
    )
    const filename = decodeArchiveFilename(headerFilename) || resolveFilenameFromDisposition(disposition) || fallbackFilename
    const blob = new Blob([res.data], { type: 'application/zip' })
    const url = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    window.URL.revokeObjectURL(url)
  } finally {
    archiveDownloading.value = false
  }
}

function resolveFilenameFromDisposition(disposition?: string): string {
  if (!disposition) return ''
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return utf8Match[1]
    }
  }
  const quotedMatch = disposition.match(/filename="([^"]+)"/i)
  if (quotedMatch?.[1]) return quotedMatch[1]
  const plainMatch = disposition.match(/filename=([^;]+)/i)
  return plainMatch?.[1]?.trim() || ''
}

function buildZipFilename(rawName: string | undefined, fallback: string): string {
  const normalized = (rawName || '').trim()
  const safeBase = (normalized || fallback).replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').trim()
  return `${safeBase || fallback}.zip`
}

function decodeArchiveFilename(value?: string): string {
  if (!value) return ''
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function handleNodeLabelDoubleClick(node: SandboxTreeNode) {
  if (!isFileNode(node) || !node.canPreview) return
  focusedFileKey.value = node.key
  void sandboxFileActions.handlePreview(node)
}

function handleInspectorAction(actionKey: string) {
  const node = focusedFileNode.value
  if (!node) return
  if (actionKey === 'preview' && node.canPreview) {
    void sandboxFileActions.handlePreview(node)
    return
  }
  if (actionKey === 'download' && node.canDownload) {
    void sandboxFileActions.handleDownload(node)
    return
  }
  if (actionKey === 'rename' && node.canRename) {
    void sandboxFileActions.handleRename(node)
    return
  }
  if (actionKey === 'refetch' && node.canRefetch) {
    void sandboxFileActions.handleRefetch(node)
    return
  }
  if (actionKey === 'delete' && node.canDelete) {
    void sandboxFileActions.handleDelete(node)
  }
}

function resolveAssetTag(assetType: string, fileType?: string, sourceUrl?: string): string {
  if (isYuqueUrl(sourceUrl || '')) return '语雀'
  return assetType === 'FILE' ? (fileType || 'FILE').toUpperCase() : assetType
}

function resolveFileColor(node: SandboxTreeNode): string {
  const normalizedName = node.label.trim().toLowerCase()
  const normalizedTag = (node.tag || '').trim().toLowerCase()
  const ext = normalizedName.includes('.') ? normalizedName.split('.').pop() || '' : ''
  const typeToken = `${normalizedTag} ${ext} ${normalizedName}`

  // PRD 文档优先红色
  if (typeToken.includes('prd')) return '#e11d48'
  // Excel
  if (['xls', 'xlsx', 'csv'].includes(ext) || normalizedTag.includes('xls') || normalizedTag.includes('csv')) return '#16a34a'
  // Word
  if (['doc', 'docx'].includes(ext) || normalizedTag.includes('doc')) return '#2563eb'
  // PPT
  if (['ppt', 'pptx'].includes(ext) || normalizedTag.includes('ppt')) return '#dc2626'
  // PDF
  if (ext === 'pdf' || normalizedTag.includes('pdf')) return '#ef4444'
  // Markdown / 文本
  if (['md', 'txt', 'json', 'yaml', 'yml'].includes(ext) || normalizedTag.includes('markdown') || normalizedTag.includes('语雀')) return '#7c3aed'
  // 图片
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext) || normalizedTag.includes('image')) return '#0ea5e9'
  // 默认文件色
  return '#3b82f6'
}

function buildTree(data: RelatedSandboxView | null): SandboxTreeNode[] {
  if (!data) return []

  const nodeNameByScopeAndCode = new Map<string, string>()
  for (const node of data.nodes || []) {
    const scopeType = node.instance_scope_type || 'PROJECT'
    const scopeId = node.instance_scope_id || 0
    nodeNameByScopeAndCode.set(`${scopeType}:${scopeId}:${node.node_code}`, node.node_name)
  }

  const resolveNodeName = (scopeType: 'PROJECT' | 'REQUIREMENT', scopeId: number, nodeCode?: string) => {
    if (!nodeCode) return ''
    return nodeNameByScopeAndCode.get(`${scopeType}:${scopeId}:${nodeCode}`) || nodeCode
  }

  const getStatusLabel = (status: string) => statusLabelMap[status] || status
  const getStatusTagType = (status: string) => statusTagTypeMap[status] || 'info'

  const buildAssetNode = (
    item: RelatedSandboxView['assets'][number],
    meta: string,
    scopePrefix: string,
  ): SandboxTreeNode => {
    const assetType = String(item.asset_type || '').toUpperCase()
    const isFileAsset = assetType === 'FILE' || Boolean(item.file_ref)
    const isUrlAsset = assetType === 'URL' || assetType === 'YUQUE_URL'
    const hasYuqueSource = isYuqueUrl(item.source_url || '')
    return {
      key: `${scopePrefix}-asset-${item.id}`,
      label: item.title || item.file_ref || item.source_url || `${item.asset_type} #${item.id}`,
      kind: 'asset',
      tag: resolveAssetTag(assetType, item.file_type || undefined, item.source_url || undefined),
      meta: mergeMetaWithStatus(meta, item.refetch_status),
      searchableText: `${item.title || ''} ${item.file_ref || ''} ${item.source_url || ''} ${item.node_code || ''}`.toLowerCase(),
      previewUrl: item.source_url || undefined,
      downloadUrl: item.source_url || undefined,
      assetId: item.id,
      assetType: assetType,
      fileType: item.file_type || undefined,
      fileSize: item.file_size || undefined,
      canPreview: isFileAsset || assetType === 'MARKDOWN' || isUrlAsset,
      canDownload: isFileAsset || assetType === 'MARKDOWN' || (isUrlAsset && isYuqueUrl(item.source_url || '')),
      canRename: isFileAsset || assetType === 'MARKDOWN' || (isUrlAsset && isYuqueUrl(item.source_url || '')),
      canRefetch: hasYuqueSource,
      canDelete: true,
    }
  }

  const projectNodeAssetMap = new Map<string, SandboxTreeNode[]>()
  const projectAssetNodes = (data.assets || [])
    .filter((item) => item.scope_type === 'PROJECT')
    .reduce<SandboxTreeNode[]>((acc, item) => {
      if (item.node_code) {
        const key = `PROJECT:${item.scope_id}:${item.node_code}`
        const scopedAssets = projectNodeAssetMap.get(key) || []
        scopedAssets.push(
          buildAssetNode(
            item,
            `节点 ${resolveNodeName('PROJECT', item.scope_id, item.node_code)}`,
            'project',
          ),
        )
        projectNodeAssetMap.set(key, scopedAssets)
        return acc
      }

      acc.push(buildAssetNode(item, '项目级资料', 'project'))
      return acc
    }, [])

  const projectNodeMap = new Map<string, SandboxTreeNode>()
  const requirementNodeMap = new Map<number, SandboxTreeNode>()

  const ensureProjectGroup = (groupLabel: string, keySuffix: string): SandboxTreeNode => {
    const key = `project-group-${keySuffix}`
    const exists = projectNodeMap.get(key)
    if (exists) return exists
    const node: SandboxTreeNode = {
      key,
      label: groupLabel,
      kind: 'group',
      searchableText: groupLabel.toLowerCase(),
      children: [],
    }
    projectNodeMap.set(key, node)
    return node
  }

  const ensureRequirementRoot = (requirementId: number, requirementTitle: string): SandboxTreeNode => {
    const exists = requirementNodeMap.get(requirementId)
    if (exists) return exists
    const node: SandboxTreeNode = {
      key: `requirement-${requirementId}`,
      label: requirementTitle,
      kind: 'requirement',
      searchableText: `${requirementTitle} ${requirementId}`.toLowerCase(),
      children: [],
    }
    requirementNodeMap.set(requirementId, node)
    return node
  }

  const requirementAssetsById = new Map<number, SandboxTreeNode[]>()
  for (const item of data.assets || []) {
    if (item.scope_type !== 'REQUIREMENT') continue
    const requirementId = item.scope_id
    const reqNodes = requirementAssetsById.get(requirementId) || []
    const assetType = String(item.asset_type || '').toUpperCase()
    const isFileAsset = assetType === 'FILE' || Boolean(item.file_ref)
    const isUrlAsset = assetType === 'URL' || assetType === 'YUQUE_URL'
    const hasYuqueSource = isYuqueUrl(item.source_url || '')
    reqNodes.push({
      key: `requirement-asset-${item.id}`,
      label: item.title || item.file_ref || item.source_url || `${item.asset_type} #${item.id}`,
      kind: 'asset',
      tag: resolveAssetTag(assetType, item.file_type || undefined, item.source_url || undefined),
      meta: mergeMetaWithStatus(
        item.node_code ? `节点 ${resolveNodeName('REQUIREMENT', requirementId, item.node_code)}` : '需求级资料',
        item.refetch_status,
      ),
      searchableText: `${item.title || ''} ${item.file_ref || ''} ${item.source_url || ''} ${item.node_code || ''}`.toLowerCase(),
      previewUrl: item.source_url || undefined,
      downloadUrl: item.source_url || undefined,
      assetId: item.id,
      assetType: assetType,
      fileType: item.file_type || undefined,
      fileSize: item.file_size || undefined,
      canPreview: isFileAsset || assetType === 'MARKDOWN' || isUrlAsset,
      canDownload: isFileAsset || assetType === 'MARKDOWN' || (isUrlAsset && isYuqueUrl(item.source_url || '')),
      canRename: isFileAsset || assetType === 'MARKDOWN' || (isUrlAsset && isYuqueUrl(item.source_url || '')),
      canRefetch: hasYuqueSource,
      canDelete: true,
    })
    requirementAssetsById.set(requirementId, reqNodes)
  }

  const aggregatedNodeMap = new Map<string, AggregatedNodeBucket>()
  for (const item of data.nodes || []) {
    const scopeType = (item.instance_scope_type || 'PROJECT') as 'PROJECT' | 'REQUIREMENT'
    const scopeId = item.instance_scope_id || 0
    const scopeTitle = item.instance_scope_title || (scopeType === 'REQUIREMENT' ? `需求 #${scopeId}` : '项目级')
    const aggregateKey = `${scopeType}:${scopeId}:${item.node_code}`

    let bucket = aggregatedNodeMap.get(aggregateKey)
    if (!bucket) {
      bucket = {
        node_id: item.node_id,
        node_code: item.node_code,
        node_name: item.node_name,
        status: item.status,
        instance_id: item.instance_id,
        scope_type: scopeType,
        scope_id: scopeId,
        scope_title: scopeTitle,
        conversations: new Map<number, AggregatedConversation>(),
      }
      aggregatedNodeMap.set(aggregateKey, bucket)
    } else if (item.instance_id > bucket.instance_id) {
      // 使用较新的实例状态作为“当前状态”
      bucket.status = item.status
      bucket.instance_id = item.instance_id
      bucket.node_name = item.node_name
      bucket.node_id = item.node_id
    }

    for (const conv of item.conversations) {
      const existed = bucket.conversations.get(conv.conversation_id)
      if (!existed) {
        bucket.conversations.set(conv.conversation_id, {
          conversation_id: conv.conversation_id,
          conversation_title: conv.conversation_title,
          binding_type: conv.binding_type,
          sandbox_files: [...conv.sandbox_files],
        })
        continue
      }

      const existedFileIds = new Set(existed.sandbox_files.map((f) => f.file_id))
      for (const file of conv.sandbox_files) {
        if (existedFileIds.has(file.file_id)) continue
        existed.sandbox_files.push(file)
      }
    }
  }

  const aggregatedNodes = Array.from(aggregatedNodeMap.values())
  aggregatedNodes.sort((a, b) => {
    if (a.scope_title !== b.scope_title) return a.scope_title.localeCompare(b.scope_title, 'zh-CN')
    return a.node_name.localeCompare(b.node_name, 'zh-CN')
  })

  for (const item of aggregatedNodes) {
    const conversations = Array.from(item.conversations.values())
      .sort((a, b) => a.conversation_id - b.conversation_id)
      .map((conv) => ({
        key: `conversation-${item.scope_type}-${item.scope_id}-${item.node_code}-${conv.conversation_id}`,
        label: `#${conv.conversation_id} ${conv.conversation_title || '未命名会话'}`,
        kind: 'conversation' as const,
        searchableText: `${conv.conversation_id} ${conv.conversation_title || ''}`.toLowerCase(),
        children: conv.sandbox_files.map((file) => ({
          key: `file-${file.file_id}`,
          label: file.original_name,
          kind: 'file' as const,
          tag: file.file_type.toUpperCase(),
          meta: formatBytes(file.file_size),
          searchableText: `${file.original_name} ${file.file_type} ${file.sandbox_path || ''}`.toLowerCase(),
          previewUrl: file.preview_url,
          downloadUrl: file.download_url,
          fileId: file.file_id,
          fileType: file.file_type,
          fileSize: file.file_size,
          conversationId: conv.conversation_id,
          canPreview: true,
          canDownload: true,
          canRename: true,
          canDelete: item.scope_type === 'PROJECT',
        })),
      }))

    const nodeTree: SandboxTreeNode = {
      key: `workflow-node-${item.scope_type}-${item.scope_id}-${item.node_code}`,
      label: item.node_name,
      kind: 'node',
      tag: getStatusLabel(item.status),
      tagType: getStatusTagType(item.status),
      searchableText: `${item.node_name} ${item.node_code} ${item.status} ${item.scope_title}`.toLowerCase(),
      children: [],
    }

    const nodeAssets = projectNodeAssetMap.get(`${item.scope_type}:${item.scope_id}:${item.node_code}`) || []
    if (nodeAssets.length > 0) {
      nodeTree.children?.push({
        key: `node-assets-${item.scope_type}-${item.scope_id}-${item.node_code}`,
        label: '节点资料',
        kind: 'group',
        searchableText: `${item.node_name} 节点资料 ${item.node_code}`.toLowerCase(),
        children: nodeAssets,
      })
    }
    nodeTree.children?.push(...conversations)

    if (item.scope_type === 'PROJECT') {
      const projectNodeGroup = ensureProjectGroup('项目级节点会话文件', 'workflow')
      projectNodeGroup.children?.push(nodeTree)
      continue
    }

    const requirementRoot = ensureRequirementRoot(item.scope_id, item.scope_title)
    let workflowGroup = requirementRoot.children?.find((child) => child.key === `requirement-workflow-${item.scope_id}`)
    if (!workflowGroup) {
      workflowGroup = {
        key: `requirement-workflow-${item.scope_id}`,
        label: '需求关联对话文件',
        kind: 'group',
        searchableText: '需求关联对话文件'.toLowerCase(),
        children: [],
      }
      requirementRoot.children?.push(workflowGroup)
    }
    workflowGroup.children?.push(nodeTree)
  }

  const projectScopeNode: SandboxTreeNode = {
    key: 'scope-project',
    label: '项目级文件',
    kind: 'scope',
    searchableText: '项目级文件'.toLowerCase(),
    children: [
      {
        key: 'project-assets-group',
        label: '项目级资料',
        kind: 'group',
        searchableText: '项目级资料'.toLowerCase(),
        children: projectAssetNodes,
      },
      ...Array.from(projectNodeMap.values()),
    ],
  }

  for (const [requirementId, assetNodes] of requirementAssetsById.entries()) {
    const requirementTitle =
      (data.assets || []).find((item) => item.scope_type === 'REQUIREMENT' && item.scope_id === requirementId)?.scope_title
      || `需求 #${requirementId}`
    const requirementRoot = ensureRequirementRoot(requirementId, requirementTitle)
    let assetGroup = requirementRoot.children?.find((child) => child.key === `requirement-assets-${requirementId}`)
    if (!assetGroup) {
      assetGroup = {
        key: `requirement-assets-${requirementId}`,
        label: '需求级资料',
        kind: 'group',
        searchableText: '需求级资料'.toLowerCase(),
        children: [],
      }
      requirementRoot.children?.unshift(assetGroup)
    }
    assetGroup.children?.push(...assetNodes)
  }

  const requirementNodes = Array.from(requirementNodeMap.values())
  requirementNodes.sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))

  return [
    projectScopeNode,
    {
      key: 'scope-requirements',
      label: '关联需求文件',
      kind: 'scope',
      searchableText: '关联需求文件'.toLowerCase(),
      children: requirementNodes,
    },
  ]
}

function expandOneLevel() {
  expandedKeys.value = [...topLevelDirectoryKeys.value]
  treeRenderSeed.value += 1
}

function expandAll() {
  expandedKeys.value = [...directoryKeys.value]
  treeRenderSeed.value += 1
}

function collapseAll() {
  expandedKeys.value = []
  treeRenderSeed.value += 1
}

function formatBytes(size: number): string {
  if (!size || Number.isNaN(size)) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let index = 0
  let value = size
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`
}
</script>

<style scoped>
.sandbox-drawer-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sandbox-drawer-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.sandbox-drawer-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: #0f172a;
}

.sandbox-drawer-subtitle {
  margin: 0;
  color: #64748b;
  font-size: 14px;
  line-height: 1.7;
}

.sandbox-drawer-project {
  font-size: 13px;
  color: #334155;
  font-weight: 600;
}

.file-sandbox-shell {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 460px;
}

.file-sandbox-summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  border: 1px solid rgba(148, 163, 184, 0.32);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(248, 250, 252, 1) 100%);
  padding: 12px;
}

.summary-card--action {
  grid-column: span 2;
  padding: 0;
  border: none;
  background: transparent;
  box-shadow: none;
}

.action-card-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.upload-entry-card,
.download-entry-card {
  width: 100%;
  height: 100%;
  min-height: 66px;
  border: 1px solid rgba(96, 165, 250, 0.35);
  border-radius: 12px;
  background:
    radial-gradient(circle at 16% 18%, rgba(191, 219, 254, 0.55) 0, rgba(191, 219, 254, 0) 52%),
    linear-gradient(138deg, rgba(239, 246, 255, 0.96) 0%, rgba(219, 234, 254, 0.72) 58%, rgba(255, 255, 255, 0.95) 100%);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  text-align: left;
  cursor: pointer;
  transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
}

.download-entry-card {
  border-color: #edcd98;
  background: #FDF6EC;
}

.upload-entry-card:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.55);
  background:
    radial-gradient(circle at 16% 18%, rgba(191, 219, 254, 0.62) 0, rgba(191, 219, 254, 0) 52%),
    linear-gradient(138deg, rgba(239, 246, 255, 0.98) 0%, rgba(219, 234, 254, 0.76) 58%, rgba(255, 255, 255, 0.97) 100%);
  box-shadow: 0 10px 20px rgba(59, 130, 246, 0.16);
}

.download-entry-card:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: #e7b96e;
  background: #f9ecd8;
  box-shadow: 0 10px 20px rgba(193, 122, 31, 0.16);
}

.download-entry-card:disabled,
.upload-entry-card:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.upload-entry-card__icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(59, 130, 246, 0.22);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #2563eb;
  font-size: 18px;
  flex-shrink: 0;
}

.download-entry-card .upload-entry-card__icon {
  background: #fff8ee;
  border-color: #efcc9a;
  color: #b2772a;
}

.upload-entry-card__content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.upload-entry-card__title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
}

.upload-entry-card__hint {
  color: #64748b;
  font-size: 12px;
  line-height: 1.2;
  white-space: nowrap;
}

.summary-label {
  font-size: 12px;
  color: #64748b;
}

.summary-value {
  margin-top: 4px;
  font-size: 22px;
  color: #0f172a;
  font-weight: 700;
}

.file-sandbox-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: rgba(248, 250, 252, 0.9);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  color: #475569;
  font-size: 12px;
}

.toolbar-pill {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: #0f172a;
  color: #fff;
  font-weight: 600;
}

.toolbar-right {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.sandbox-search {
  width: 320px;
  min-width: 240px;
}

:deep(.sandbox-search .el-input__wrapper) {
  height: 32px;
  border-radius: 999px;
  box-shadow: 0 0 0 1px rgba(203, 213, 225, 0.9) inset;
  background: #fff;
}

.tree-controls {
  display: inline-flex;
  gap: 6px;
  border-radius: 999px;
  padding: 4px;
  background: #fff;
  border: 1px solid rgba(203, 213, 225, 0.88);
}

.tree-control-button {
  border: none;
  background: transparent;
  border-radius: 999px;
  padding: 6px 10px;
  color: #475569;
  font-size: 12px;
  cursor: pointer;
}

.tree-control-button:hover {
  background: #f1f5f9;
}

.tree-wrap {
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: #fff;
  padding: 8px 0;
  min-height: 420px;
}

.file-sandbox-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(380px, 1.08fr);
  gap: 14px;
}

.tree-node {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-right: 12px;
}

.tree-node-main {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  gap: 8px;
  cursor: pointer;
}

.node-icon {
  color: #3b82f6;
}

.tree-node-label {
  color: #0f172a;
  font-size: 13px;
  max-width: 440px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-tag {
  margin-left: 4px;
}

.node-meta {
  font-size: 12px;
  color: #64748b;
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
  color: #94a3b8;
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
  color: #0f172a;
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
  color: #0f172a;
  word-break: break-word;
}

.preview-dialog-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  width: 100%;
  color: #64748b;
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
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

.preview-text {
  background: #f5f5f5;
  padding: 20px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: monospace;
  font-size: 14px;
  color: #303133;
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
  color: #606266;
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

:deep(.el-tree-node__content) {
  height: 36px;
  border-radius: 8px;
  margin: 0 8px;
}

:deep(.el-tree-node__content:hover) {
  background: #f8fafc;
}

:global(.sandbox-preview-dialog .el-dialog) {
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 26px;
  overflow: hidden;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
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
  color: #475569;
}

:global(.asset-upload-dialog-panel) {
  border: 1px solid rgba(226, 232, 240, 0.95) !important;
  border-radius: 32px !important;
  overflow: hidden !important;
  background: #ffffff !important;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04) !important;
}

:global(.asset-upload-dialog-panel .el-dialog__header) {
  margin: 0;
  padding: 0;
  min-height: 0;
}

:global(.asset-upload-dialog-panel .el-dialog__body) {
  padding: 22px 24px 24px !important;
  background: transparent !important;
}

:global(.asset-upload-dialog-panel .el-dialog__content) {
  padding: 0 !important;
  background: transparent !important;
}

:global(.sandbox-preview-dialog .el-dialog__footer .preview-dialog-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.08);
  color: #0f172a;
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
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08), 0 2px 8px rgba(15, 23, 42, 0.04);
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
  color: #0f172a;
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
  box-shadow: 0 20px 48px rgba(15, 23, 42, 0.08), 0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

:global(.sandbox-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.sandbox-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
}

:global(.sandbox-confirm-dialog .el-message-box__headerbtn) {
  top: 20px;
  right: 20px;
}

:global(.sandbox-confirm-dialog .el-message-box__content) {
  padding: 16px 24px 8px;
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

:global(.danger-confirm-content) {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

:global(.danger-confirm-badge) {
  width: fit-content;
  height: 26px;
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  color: #b91c1c;
  background: #fef2f2;
}

:global(.danger-confirm-subject) {
  color: #0f172a;
  font-size: 16px;
  font-weight: 700;
}

:global(.danger-confirm-detail) {
  margin: 0;
  color: #64748b;
  line-height: 1.7;
  font-size: 14px;
}

:global(.sandbox-confirm-dialog .el-message-box__btns) {
  padding: 18px 24px 24px;
  gap: 10px;
}

:global(.sandbox-confirm-dialog .el-message-box__btns .el-button) {
  min-width: 102px;
  height: 40px;
  border-radius: 12px;
  font-weight: 600;
}

:global(.sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.28);
  color: #475569;
  background: #ffffff;
}

:global(.sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-primary) {
  border: none;
  color: #ffffff;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
}

:global(.project-file-sandbox-drawer) {
  --el-drawer-padding-primary: 22px;
}

:global(.project-file-sandbox-drawer .el-drawer__container) {
  padding: 24px 0;
  box-sizing: border-box;
}

:global(.project-file-sandbox-drawer .el-drawer) {
  top: 0;
  bottom: 0;
  margin-top: 18px;
  margin-bottom: 18px;
  height: auto !important;
  max-height: calc(100vh - 84px);
  border-radius: 28px 0 0 28px;
  overflow: hidden;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 1) 100%);
  box-shadow: 0 28px 72px rgba(15, 23, 42, 0.24), 0 8px 28px rgba(15, 23, 42, 0.12);
}

:global(.project-file-sandbox-drawer .el-drawer::before) {
  content: '';
  position: absolute;
  top: 50%;
  left: -30px;
  transform: translateY(-50%);
  width: 30px;
  height: 102px;
  border-radius: 18px 0 0 18px;
  border: 1px solid rgba(59, 130, 246, 0.22);
  border-right: none;
  background: linear-gradient(180deg, rgba(245, 250, 255, 0.98) 0%, rgba(233, 243, 255, 1) 100%);
  box-shadow: 0 16px 34px rgba(37, 99, 235, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.9);
  pointer-events: none;
}

:global(.project-file-sandbox-drawer .el-drawer::after) {
  content: '文件';
  position: absolute;
  top: 50%;
  left: -26px;
  transform: translateY(-50%);
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.04em;
  color: #0f172a;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  pointer-events: none;
}

:global(.project-file-sandbox-drawer .el-drawer__header) {
  margin-bottom: 8px;
  padding-top: 26px;
  padding-bottom: 0;
}

:global(.project-file-sandbox-drawer .el-drawer__body) {
  padding-top: 8px;
  overflow: auto;
}

:global(.project-file-sandbox-mask) {
  background: rgba(15, 23, 42, 0.38);
  backdrop-filter: blur(5px);
}

:global(html.dark .project-file-sandbox-drawer .el-drawer) {
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%) !important;
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48), 0 8px 28px rgba(2, 6, 23, 0.28) !important;
}

:global(html.dark .project-file-sandbox-drawer .el-drawer::before) {
  background: rgba(96, 165, 250, 0.14) !important;
  border-color: rgba(96, 165, 250, 0.24) !important;
  box-shadow: none !important;
}

:global(html.dark .project-file-sandbox-drawer .el-drawer::after) {
  color: #bfdbfe !important;
}

:global(html.dark .project-file-sandbox-mask) {
  background: rgba(2, 6, 23, 0.48) !important;
}

:global(html.dark .sandbox-node-menu.el-popper),
:global(html.dark .project-file-sandbox-drawer .sandbox-node-menu.el-popper) {
  background: color-mix(in srgb, var(--bg-card, #0f172a) 94%, #020617 6%);
  box-shadow: 0 20px 48px rgba(2, 6, 23, 0.34);
  border: 1px solid rgba(148, 163, 184, 0.08);
}

:global(html.dark .sandbox-node-menu.el-popper .el-popper__arrow),
:global(html.dark .sandbox-node-menu.el-popper .el-popper__arrow::before),
:global(html.dark .project-file-sandbox-drawer .sandbox-node-menu.el-popper .el-popper__arrow),
:global(html.dark .project-file-sandbox-drawer .sandbox-node-menu.el-popper .el-popper__arrow::before) {
  background: color-mix(in srgb, var(--bg-card, #0f172a) 94%, #020617 6%);
  border-color: rgba(148, 163, 184, 0.08);
}

:global(html.dark .sandbox-node-menu .el-dropdown-menu),
:global(html.dark .project-file-sandbox-drawer .sandbox-node-menu .el-dropdown-menu) {
  background: transparent;
}

:global(html.dark .sandbox-node-menu .el-dropdown-menu__item),
:global(html.dark .project-file-sandbox-drawer .sandbox-node-menu .el-dropdown-menu__item) {
  color: var(--text-secondary, #cbd5e1);
}

:global(html.dark .sandbox-node-menu .el-dropdown-menu__item:hover),
:global(html.dark .project-file-sandbox-drawer .sandbox-node-menu .el-dropdown-menu__item:hover) {
  background: rgba(96, 165, 250, 0.12);
  color: #f8fafc;
}

:global(html.dark .sandbox-node-menu .el-dropdown-menu__item.danger-item),
:global(html.dark .project-file-sandbox-drawer .sandbox-node-menu .el-dropdown-menu__item.danger-item) {
  color: #fca5a5;
}

:global(html.dark .sandbox-node-menu .el-dropdown-menu__item.danger-item:hover),
:global(html.dark .project-file-sandbox-drawer .sandbox-node-menu .el-dropdown-menu__item.danger-item:hover) {
  background: rgba(248, 113, 113, 0.14);
  color: #fecaca;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-confirm-dialog.el-message-box),
:global(html.dark .project-file-sandbox-drawer .sandbox-preview-dialog .el-dialog),
:global(html.dark .project-file-sandbox-drawer .asset-upload-dialog-panel) {
  border-color: rgba(148, 163, 184, 0.12) !important;
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%) !important;
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48) !important;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-confirm-dialog .el-message-box__title),
:global(html.dark .project-file-sandbox-drawer .danger-confirm-subject),
:global(html.dark .project-file-sandbox-drawer .sandbox-preview-dialog .el-dialog__title) {
  color: #f8fafc !important;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-rename-dialog .el-input__wrapper) {
  background: rgba(148, 163, 184, 0.08);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.18) inset;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-rename-dialog .el-input__inner) {
  color: #e2e8f0;
}

:global(html.dark .project-file-sandbox-drawer .danger-confirm-badge) {
  background: rgba(248, 113, 113, 0.14);
  color: #fca5a5;
}

:global(html.dark .project-file-sandbox-drawer .danger-confirm-detail),
:global(html.dark .project-file-sandbox-drawer .sandbox-preview-dialog .preview-dialog-meta) {
  color: #94a3b8 !important;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-preview-dialog .preview-dialog-meta span) {
  background: rgba(148, 163, 184, 0.1);
}

:global(html.dark .project-file-sandbox-drawer .sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-secondary),
:global(html.dark .project-file-sandbox-drawer .sandbox-preview-dialog .el-dialog__footer .preview-dialog-secondary) {
  border: none !important;
  background: transparent !important;
  color: #94a3b8 !important;
  box-shadow: none !important;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-secondary:hover),
:global(html.dark .project-file-sandbox-drawer .sandbox-preview-dialog .el-dialog__footer .preview-dialog-secondary:hover) {
  border: none !important;
  background: transparent !important;
  color: #94a3b8 !important;
  box-shadow: none !important;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-preview-dialog .el-dialog__footer .preview-dialog-primary),
:global(html.dark .project-file-sandbox-drawer .asset-upload-dialog-panel .el-dialog__footer .el-button--primary),
:global(html.dark .project-file-sandbox-drawer .sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-primary) {
  border: none !important;
  background: transparent !important;
  color: #60a5fa !important;
  box-shadow: none !important;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-preview-dialog .el-dialog__footer .preview-dialog-primary:hover),
:global(html.dark .project-file-sandbox-drawer .asset-upload-dialog-panel .el-dialog__footer .el-button--primary:hover),
:global(html.dark .project-file-sandbox-drawer .sandbox-confirm-dialog .el-message-box__btns .sandbox-confirm-primary:hover) {
  border: none !important;
  background: transparent !important;
  color: #60a5fa !important;
  box-shadow: none !important;
}

:global(html.dark .project-file-sandbox-drawer .asset-upload-dialog-panel .el-dialog__footer .el-button:not(.el-button--primary)),
:global(html.dark .project-file-sandbox-drawer .asset-upload-dialog-panel .el-dialog__footer .el-button:not(.el-button--primary):hover) {
  border: none !important;
  background: transparent !important;
  color: #94a3b8 !important;
  box-shadow: none !important;
}

:global(html.dark .asset-upload-dialog-panel .el-dialog__footer .el-button:not(.el-button--primary)),
:global(html.dark .asset-upload-dialog-panel .el-dialog__footer .el-button:not(.el-button--primary):hover) {
  border: none !important;
  background: transparent !important;
  color: #94a3b8 !important;
  box-shadow: none !important;
  transform: none !important;
}

:global(html.dark .asset-upload-dialog-panel .el-dialog__footer .el-button--primary),
:global(html.dark .asset-upload-dialog-panel .el-dialog__footer .el-button--primary:hover) {
  border: none !important;
  background: transparent !important;
  color: #60a5fa !important;
  box-shadow: none !important;
  transform: none !important;
}

:global(html.dark .asset-upload-dialog .el-dialog__footer .el-button:not(.el-button--primary)),
:global(html.dark .asset-upload-dialog .el-dialog__footer .el-button:not(.el-button--primary):hover) {
  border: none !important;
  background: transparent !important;
  color: #94a3b8 !important;
  box-shadow: none !important;
  transform: none !important;
}

:global(html.dark .asset-upload-dialog .el-dialog__footer .el-button--primary),
:global(html.dark .asset-upload-dialog .el-dialog__footer .el-button--primary:hover) {
  border: none !important;
  background: transparent !important;
  color: #60a5fa !important;
  box-shadow: none !important;
  transform: none !important;
}

:global(html.dark .asset-upload-dialog .el-button:not(.asset-upload-editor__resolve-btn)),
:global(html.dark .asset-upload-dialog .el-button:not(.asset-upload-editor__resolve-btn):hover),
:global(html.dark .asset-upload-dialog .el-button:not(.asset-upload-editor__resolve-btn):focus-visible) {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  transform: none !important;
}

:global(html.dark .asset-upload-dialog .el-button--primary),
:global(html.dark .asset-upload-dialog .el-button--primary:hover) {
  color: #60a5fa !important;
}

:global(html.dark .asset-upload-dialog .el-button:not(.el-button--primary)),
:global(html.dark .asset-upload-dialog .el-button:not(.el-button--primary):hover) {
  color: #94a3b8 !important;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-drawer-project) {
  color: #94a3b8;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-drawer-title) {
  color: #e6efff;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-drawer-subtitle) {
  color: #94a3b8;
}

:global(html.dark .project-file-sandbox-drawer .summary-card) {
  border-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 82%, #6b7280 18%);
  background: linear-gradient(180deg, rgba(34, 38, 46, 0.96) 0%, rgba(27, 31, 38, 0.98) 100%);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.28);
}

:global(html.dark .project-file-sandbox-drawer .upload-entry-card),
:global(html.dark .project-file-sandbox-drawer .download-entry-card) {
  border-color: rgba(107, 114, 128, 0.24);
  background: linear-gradient(180deg, rgba(34, 38, 46, 0.96) 0%, rgba(27, 31, 38, 0.98) 100%);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.24);
}

:global(html.dark .project-file-sandbox-drawer .upload-entry-card:hover:not(:disabled)),
:global(html.dark .project-file-sandbox-drawer .download-entry-card:hover:not(:disabled)) {
  border-color: rgba(96, 165, 250, 0.24);
  background: linear-gradient(180deg, rgba(38, 43, 52, 0.98) 0%, rgba(30, 34, 42, 1) 100%);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.3);
}

:global(html.dark .project-file-sandbox-drawer .upload-entry-card__icon) {
  background: rgba(96, 165, 250, 0.14);
  border-color: rgba(96, 165, 250, 0.18);
  color: #93c5fd;
}

:global(html.dark .project-file-sandbox-drawer .upload-entry-card__title) {
  color: #f8fafc;
}

:global(html.dark .project-file-sandbox-drawer .upload-entry-card__hint) {
  color: #94a3b8;
}

:global(html.dark .project-file-sandbox-drawer .file-sandbox-toolbar) {
  border-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 78%, #4b5563 22%);
  background: linear-gradient(90deg, rgba(30, 34, 42, 0.96) 0%, rgba(24, 28, 35, 0.92) 100%);
  box-shadow: 0 14px 32px rgba(0, 0, 0, 0.22);
}

:global(html.dark .project-file-sandbox-drawer .tree-wrap) {
  border-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 78%, #4b5563 22%);
  background: linear-gradient(180deg, rgba(23, 27, 34, 0.96) 0%, rgba(18, 21, 27, 0.98) 100%);
  box-shadow: 0 20px 44px rgba(0, 0, 0, 0.26);
}

:global(html.dark .project-file-sandbox-drawer .toolbar-left),
:global(html.dark .project-file-sandbox-drawer .node-meta),
:global(html.dark .project-file-sandbox-drawer .summary-label) {
  color: var(--text-secondary, #b3b3b3);
}

:global(html.dark .project-file-sandbox-drawer .summary-value),
:global(html.dark .project-file-sandbox-drawer .tree-node-label) {
  color: #f8fafc;
}

:global(html.dark .project-file-sandbox-drawer .toolbar-left > span) {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.08);
  color: var(--text-secondary, #cbd5e1);
  font-size: 12px;
  font-weight: 600;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-search .el-input__wrapper) {
  background: rgba(17, 24, 39, 0.56);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.12) inset;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-search .el-input__inner),
:global(html.dark .project-file-sandbox-drawer .sandbox-search .el-input__inner::placeholder) {
  color: #cbd5e1;
}

:global(html.dark .project-file-sandbox-drawer .sandbox-search .el-input__inner::placeholder) {
  color: #94a3b8;
}

:global(html.dark .project-file-sandbox-drawer .tree-controls) {
  border-color: rgba(148, 163, 184, 0.12);
  background: rgba(148, 163, 184, 0.06);
}

:global(html.dark .project-file-sandbox-drawer .tree-control-button) {
  color: #94a3b8;
}

:global(html.dark .project-file-sandbox-drawer .tree-control-button:hover),
:global(html.dark .project-file-sandbox-drawer .tree-control-button:focus-visible) {
  background: rgba(96, 165, 250, 0.12);
  color: #f8fafc;
}

:global(html.dark .project-file-sandbox-drawer .tree-control-button.is-active) {
  background: linear-gradient(135deg, rgba(96, 165, 250, 0.16) 0%, rgba(37, 99, 235, 0.26) 100%);
  color: #f8fafc;
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.18);
}

:global(html.dark .project-file-sandbox-drawer .action-trigger) {
  border-color: rgba(148, 163, 184, 0.18);
  background: rgba(148, 163, 184, 0.08);
  color: var(--text-secondary, #94a3b8);
}

:global(html.dark .project-file-sandbox-drawer .action-trigger:hover),
:global(html.dark .project-file-sandbox-drawer .action-trigger:focus-visible) {
  background: rgba(96, 165, 250, 0.14);
  color: #e2e8f0;
  border-color: rgba(96, 165, 250, 0.32);
}

:global(html.dark .project-file-sandbox-drawer .el-tree-node__content:hover) {
  background: rgba(96, 165, 250, 0.1) !important;
}

:global(html.dark .project-file-sandbox-drawer .el-tree-node.is-current > .el-tree-node__content) {
  background: rgba(96, 165, 250, 0.14) !important;
}

:global(html.dark .project-file-sandbox-drawer .el-tree-node.is-current > .el-tree-node__content:hover) {
  background: rgba(96, 165, 250, 0.18) !important;
}

:global(html.dark .project-file-sandbox-drawer .el-tree-node:focus > .el-tree-node__content) {
  background: rgba(96, 165, 250, 0.14) !important;
}

:global(html.dark .project-file-sandbox-drawer :deep(.el-tree-node__content:hover .tree-node-label)),
:global(html.dark .project-file-sandbox-drawer :deep(.el-tree-node__content:hover .node-meta)),
:global(html.dark .project-file-sandbox-drawer :deep(.el-tree-node.is-current > .el-tree-node__content .tree-node-label)),
:global(html.dark .project-file-sandbox-drawer :deep(.el-tree-node.is-current > .el-tree-node__content .node-meta)) {
  color: #f8fafc;
}

:global(html.dark .project-file-sandbox-drawer .preview-content),
:global(html.dark .project-file-sandbox-drawer .preview-markdown),
:global(html.dark .project-file-sandbox-drawer .preview-table-wrap) {
  color: #dbe5f5;
}

:global(html.dark .project-file-sandbox-drawer .preview-pdf),
:global(html.dark .project-file-sandbox-drawer .preview-text) {
  background: color-mix(in srgb, var(--bg-code, #252525) 92%, #0f172a 8%);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 14px;
  color: #dbe5f5;
}

:global(html.dark .project-file-sandbox-drawer .preview-dialog-badge) {
  background: rgba(96, 165, 250, 0.14);
  color: #bfdbfe;
}

:global(html.dark .project-file-sandbox-drawer .preview-dialog-title) {
  color: #f8fafc;
}

:global(html.dark .project-file-sandbox-drawer .preview-dialog-meta) {
  color: #94a3b8;
}

:global(html.dark .project-file-sandbox-drawer .preview-dialog-meta span) {
  background: rgba(148, 163, 184, 0.1);
}

:global(html.dark .project-file-sandbox-drawer .sheet-meta),
:global(html.dark .project-file-sandbox-drawer .el-empty__description p) {
  color: #94a3b8;
}

:global(html.dark .project-file-sandbox-drawer .xlsx-table) {
  --el-table-bg-color: rgba(8, 13, 24, 0.68);
  --el-table-tr-bg-color: rgba(8, 13, 24, 0.68);
  --el-table-expanded-cell-bg-color: rgba(8, 13, 24, 0.68);
  --el-table-header-bg-color: rgba(15, 23, 42, 0.86);
  --el-table-row-hover-bg-color: rgba(96, 165, 250, 0.1);
  --el-table-border-color: rgba(148, 163, 184, 0.12);
  --el-table-header-text-color: #cbd5e1;
  --el-table-text-color: #e2e8f0;
}

@media (max-width: 960px) {
  .file-sandbox-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .upload-entry-card__title,
  .upload-entry-card__hint {
    white-space: normal;
  }

  .file-sandbox-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-right {
    width: 100%;
    justify-content: flex-end;
  }

  .sandbox-search {
    width: min(100%, 460px);
  }

  .file-sandbox-workbench {
    grid-template-columns: 1fr;
  }

}

@media (hover: none), (pointer: coarse) {
  .action-trigger {
    opacity: 1;
    pointer-events: auto;
    transform: translateX(0);
  }
}
</style>
