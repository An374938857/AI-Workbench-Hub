<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { UploadFile, UploadFiles, UploadInstance, UploadUserFile } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Paperclip } from '@element-plus/icons-vue'
import { resolveUrlTitle } from '@/api/assets'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

interface AssetTypeOption {
  label: string
  value: string
}

interface UrlPreviewCard {
  title: string
  description: string
  sourceUrl: string
  iconUrl: string
  imageUrl: string
  hostname: string
}

const props = withDefaults(defineProps<{
  assetType: string
  title: string
  sourceUrl: string
  content: string
  files: File[]
  typeOptions: AssetTypeOption[]
  urlTypes?: string[]
  markdownType?: string
  titlePlaceholder?: string
  urlPlaceholder?: string
  markdownPlaceholder?: string
  uploadTitle?: string
  uploadHint?: string
  enableUrlAutoTitle?: boolean
  showHero?: boolean
}>(), {
  urlTypes: () => ['URL'],
  markdownType: 'MARKDOWN',
  titlePlaceholder: '资料标题（可选）',
  urlPlaceholder: '填写 URL（支持语雀与其他网页链接）',
  markdownPlaceholder: '填写 Markdown 内容',
  uploadTitle: '拖拽文件到这里，或点击选择文件',
  uploadHint: '支持常见文档格式上传',
  enableUrlAutoTitle: true,
  showHero: true,
})

const emit = defineEmits<{
  (e: 'update:assetType', value: string): void
  (e: 'update:title', value: string): void
  (e: 'update:sourceUrl', value: string): void
  (e: 'update:content', value: string): void
  (e: 'files-change', files: File[]): void
  (e: 'file-clear'): void
}>()

const isUrlType = computed(() => props.urlTypes.includes(props.assetType))
const isMarkdownType = computed(() => props.assetType === props.markdownType)
const isFileType = computed(() => !isUrlType.value && !isMarkdownType.value)
const markdownPanelMode = ref<'edit' | 'preview'>('edit')
const isResolvingUrlTitle = ref(false)
const urlPreviewCard = ref<UrlPreviewCard | null>(null)
const lastResolvedUrl = ref('')
const lastAutoResolvedTitle = ref('')
const isUrlPreviewImageBroken = ref(false)
const uploadRef = ref<UploadInstance>()
const uploadFileList = ref<UploadUserFile[]>([])

watch(
  () => props.sourceUrl,
  (next) => {
    const normalizedInput = next.trim()
    if (!normalizedInput) {
      urlPreviewCard.value = null
      lastResolvedUrl.value = ''
      isUrlPreviewImageBroken.value = false
      return
    }
    if (normalizedInput !== lastResolvedUrl.value) {
      urlPreviewCard.value = null
      isUrlPreviewImageBroken.value = false
    }
  },
)

watch(
  () => props.assetType,
  () => {
    markdownPanelMode.value = 'edit'
    if (!isUrlType.value) {
      urlPreviewCard.value = null
      lastResolvedUrl.value = ''
      isUrlPreviewImageBroken.value = false
    }
  },
)

watch(
  () => props.files,
  (next) => {
    if (next.length === 0 && uploadFileList.value.length) {
      uploadRef.value?.clearFiles()
      uploadFileList.value = []
    }
  },
  { deep: true },
)

function syncSelectedFiles(files: UploadUserFile[]) {
  uploadFileList.value = files
  const selectedFiles: File[] = []
  for (const item of files) {
    if (item.raw) {
      selectedFiles.push(item.raw as File)
    }
  }
  emit('files-change', selectedFiles)
}

function handleFileChange(_: UploadFile, uploadFiles: UploadFiles) {
  syncSelectedFiles(uploadFiles)
}

function handleAssetTypeUpdate(value: string | number | boolean) {
  emit('update:assetType', String(value))
}

function handleTitleUpdate(value: string) {
  emit('update:title', value)
}

function handleSourceUrlUpdate(value: string) {
  emit('update:sourceUrl', value)
}

async function handleResolveUrlClick() {
  const sourceUrl = props.sourceUrl.trim()
  if (!props.enableUrlAutoTitle || !isUrlType.value || !sourceUrl) return
  if (isResolvingUrlTitle.value) return
  if (sourceUrl === lastResolvedUrl.value) return

  isResolvingUrlTitle.value = true
  try {
    const response = await resolveUrlTitle(sourceUrl)
    const title = response?.data?.title?.trim()
    const description = response?.data?.description?.trim() || ''
    const normalizedUrl = response?.data?.source_url?.trim()
    const iconUrl = response?.data?.icon_url?.trim() || ''
    const imageUrl = response?.data?.image_url?.trim() || ''
    const currentTitle = props.title.trim()
    const canAutofillTitle = !currentTitle || currentTitle === lastAutoResolvedTitle.value
    if (title && canAutofillTitle) {
      emit('update:title', title)
      lastAutoResolvedTitle.value = title
    }
    if (normalizedUrl && normalizedUrl !== props.sourceUrl) {
      emit('update:sourceUrl', normalizedUrl)
    }
    const cardUrl = normalizedUrl || sourceUrl
    let hostname = ''
    try {
      hostname = new URL(cardUrl).hostname.replace(/^www\./, '')
    } catch {
      hostname = ''
    }
    if (title) {
      urlPreviewCard.value = {
        title,
        description,
        sourceUrl: cardUrl,
        iconUrl,
        imageUrl,
        hostname,
      }
      isUrlPreviewImageBroken.value = false
    }
    lastResolvedUrl.value = cardUrl
  } catch {
    lastResolvedUrl.value = ''
    ElMessage.warning('未能自动解析网页标题，请手动填写标题')
  } finally {
    isResolvingUrlTitle.value = false
  }
}

function handleContentUpdate(value: string) {
  emit('update:content', value)
}

function openUrlCard(sourceUrl: string) {
  window.open(sourceUrl, '_blank', 'noopener,noreferrer')
}

function handleUrlPreviewImageError() {
  isUrlPreviewImageBroken.value = true
}

function handleClearFile() {
  uploadRef.value?.clearFiles()
  uploadFileList.value = []
  emit('file-clear')
  emit('files-change', [])
}

function handleRemoveFile(index: number) {
  const next = uploadFileList.value.filter((_, idx) => idx !== index)
  syncSelectedFiles(next)
}

function formatFileSize(size: number): string {
  if (!size || size <= 0) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <div class="asset-upload-editor">
    <div v-if="showHero" class="asset-upload-editor__hero">
      <h4 class="asset-upload-editor__hero-title">资料上传</h4>
      <p class="asset-upload-editor__hero-desc">结构化录入资料信息，确保文件和上下文在沙箱内可追踪、可复用。</p>
    </div>

    <div class="asset-upload-editor__meta" :class="{ 'asset-upload-editor__meta--compact': isFileType }">
      <el-select
        :model-value="assetType"
        class="asset-upload-editor__type"
        @update:model-value="handleAssetTypeUpdate"
      >
        <el-option
          v-for="option in typeOptions"
          :key="option.value"
          :label="option.label"
          :value="option.value"
        />
      </el-select>
      <el-input
        v-if="!isFileType"
        :model-value="title"
        :placeholder="titlePlaceholder"
        class="asset-upload-editor__title"
        @update:model-value="handleTitleUpdate"
      />
    </div>

    <el-input
      v-if="isUrlType"
      :model-value="sourceUrl"
      :placeholder="urlPlaceholder"
      class="asset-upload-editor__field"
      @update:model-value="handleSourceUrlUpdate"
    >
      <template #append>
        <button
          type="button"
          class="asset-upload-editor__resolve-btn"
          :class="{ 'is-loading': isResolvingUrlTitle }"
          :disabled="!sourceUrl.trim()"
          @click="handleResolveUrlClick"
        >
          {{ isResolvingUrlTitle ? '解析中...' : '解析' }}
        </button>
      </template>
    </el-input>
    <div v-if="isUrlType && isResolvingUrlTitle" class="asset-upload-editor__resolving">
      正在解析网页标题...
    </div>
    <div v-if="isUrlType">
      <button
        v-if="urlPreviewCard"
        type="button"
        class="asset-upload-editor__url-card"
        @click="openUrlCard(urlPreviewCard.sourceUrl)"
      >
        <div class="asset-upload-editor__url-card-media">
          <img
            v-if="urlPreviewCard.imageUrl && !isUrlPreviewImageBroken"
            :src="urlPreviewCard.imageUrl"
            alt=""
            class="asset-upload-editor__url-card-image"
            @error="handleUrlPreviewImageError"
          >
          <div v-else class="asset-upload-editor__url-card-placeholder">
            <div class="asset-upload-editor__url-card-placeholder-mark">WEB</div>
            <div class="asset-upload-editor__url-card-placeholder-host">
              {{ urlPreviewCard.hostname || 'link' }}
            </div>
          </div>
        </div>
        <div class="asset-upload-editor__url-card-content">
          <div class="asset-upload-editor__url-card-title">{{ urlPreviewCard.title }}</div>
          <div v-if="urlPreviewCard.description" class="asset-upload-editor__url-card-desc">
            {{ urlPreviewCard.description }}
          </div>
          <div class="asset-upload-editor__url-card-link">{{ urlPreviewCard.hostname || urlPreviewCard.sourceUrl }}</div>
        </div>
      </button>
    </div>

    <div v-else-if="isMarkdownType" class="asset-upload-editor__markdown">
      <div class="asset-upload-editor__markdown-tabs">
        <button
          type="button"
          class="asset-upload-editor__markdown-tab"
          :class="{ 'is-active': markdownPanelMode === 'edit' }"
          @click="markdownPanelMode = 'edit'"
        >
          编辑
        </button>
        <button
          type="button"
          class="asset-upload-editor__markdown-tab"
          :class="{ 'is-active': markdownPanelMode === 'preview' }"
          @click="markdownPanelMode = 'preview'"
        >
          预览
        </button>
      </div>

      <el-input
        v-show="markdownPanelMode === 'edit'"
        :model-value="content"
        type="textarea"
        :rows="8"
        :placeholder="markdownPlaceholder"
        class="asset-upload-editor__field"
        @update:model-value="handleContentUpdate"
      />
      <div v-show="markdownPanelMode === 'preview'" class="asset-upload-editor__markdown-preview">
        <MarkdownRenderer :content="content || '暂无 Markdown 内容'" />
      </div>
    </div>

    <div v-else class="asset-upload-editor__upload">
      <el-upload
        ref="uploadRef"
        drag
        multiple
        :auto-upload="false"
        :show-file-list="false"
        :file-list="uploadFileList"
        class="asset-upload-editor__dragger"
        :on-change="handleFileChange"
      >
        <div class="asset-upload-editor__copy">
          <el-icon class="asset-upload-editor__copy-icon" :size="24"><Paperclip /></el-icon>
          <div class="asset-upload-editor__copy-title">{{ uploadTitle }}</div>
          <div class="asset-upload-editor__copy-hint">{{ uploadHint }}</div>
        </div>
      </el-upload>
      <div v-if="uploadFileList.length" class="asset-upload-editor__files">
        <div
          v-for="(selectedFile, index) in uploadFileList"
          :key="selectedFile.uid ?? `${selectedFile.name}-${index}`"
          class="asset-upload-editor__file-item"
        >
          <div class="asset-upload-editor__file-main">
            <div class="asset-upload-editor__file-name">{{ selectedFile.name }}</div>
            <div class="asset-upload-editor__file-meta">{{ formatFileSize(selectedFile.size || 0) }}</div>
          </div>
          <button type="button" class="asset-upload-editor__file-remove" @click="handleRemoveFile(index)">删除</button>
        </div>
      </div>
      <div v-if="uploadFileList.length" class="asset-upload-editor__files-actions">
        <el-button link @click="handleClearFile">清空列表</el-button>
      </div>
    </div>

    <div class="asset-upload-editor__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.asset-upload-editor {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.asset-upload-editor__hero {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.asset-upload-editor__hero-title {
  margin: 0;
  color: #0f172a;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.3;
}

.asset-upload-editor__hero-desc {
  margin: 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.75;
}

.asset-upload-editor__meta {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 10px;
}

.asset-upload-editor__meta--compact {
  grid-template-columns: 140px;
}

.asset-upload-editor__type,
.asset-upload-editor__title,
.asset-upload-editor__field {
  width: 100%;
}

.asset-upload-editor__upload {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.asset-upload-editor__resolving {
  margin-top: -6px;
  color: #64748b;
  font-size: 12px;
}

.asset-upload-editor__url-card {
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr);
  width: 100%;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(248, 250, 255, 0.95) 0%, #ffffff 100%);
  padding: 10px;
  gap: 12px;
  text-align: left;
  cursor: pointer;
  transition: all 180ms ease;
}

.asset-upload-editor__url-card:hover {
  border-color: #7ca3ff;
  box-shadow: 0 8px 22px rgba(59, 130, 246, 0.14);
  transform: translateY(-1px);
}

.asset-upload-editor__url-card-media {
  height: 86px;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(226, 232, 240, 0.45);
}

.asset-upload-editor__url-card-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.asset-upload-editor__url-card-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background:
    radial-gradient(circle at 18% 16%, rgba(59, 130, 246, 0.18) 0, rgba(59, 130, 246, 0) 50%),
    radial-gradient(circle at 84% 80%, rgba(14, 165, 233, 0.22) 0, rgba(14, 165, 233, 0) 48%),
    linear-gradient(140deg, #f8fbff 0%, #eef5ff 48%, #ffffff 100%);
}

.asset-upload-editor__url-card-placeholder-mark {
  border-radius: 999px;
  border: 1px solid rgba(37, 99, 235, 0.2);
  background: rgba(255, 255, 255, 0.92);
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  padding: 4px 10px;
}

.asset-upload-editor__url-card-placeholder-host {
  max-width: calc(100% - 16px);
  color: #475569;
  font-size: 11px;
  line-height: 1.3;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.asset-upload-editor__url-card-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 7px;
}

.asset-upload-editor__url-card-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.45;
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.asset-upload-editor__url-card-desc {
  color: #475569;
  font-size: 12px;
  line-height: 1.55;
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.asset-upload-editor__url-card-link {
  color: #2563eb;
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.asset-upload-editor__markdown {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.asset-upload-editor__markdown-tabs {
  display: inline-flex;
  align-items: center;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: rgba(248, 250, 252, 0.95);
  padding: 3px;
  width: fit-content;
}

.asset-upload-editor__markdown-tab {
  border: none;
  background: transparent;
  color: #64748b;
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 160ms ease;
}

.asset-upload-editor__markdown-tab.is-active {
  background: #ffffff;
  color: #1d4ed8;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.asset-upload-editor__markdown-preview {
  min-height: 206px;
  max-height: 320px;
  overflow: auto;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: rgba(255, 255, 255, 0.96);
  padding: 12px 14px;
}

.asset-upload-editor__dragger {
  width: 100%;
}

.asset-upload-editor__copy {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.asset-upload-editor__copy-title {
  color: #1f2937;
  font-size: 14px;
  font-weight: 500;
}

.asset-upload-editor__copy-hint {
  color: #6b7280;
  font-size: 12px;
}

.asset-upload-editor__copy-icon {
  color: #4285f4;
}

.asset-upload-editor__files {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.asset-upload-editor__file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.26);
  background: #ffffff;
  padding: 10px 12px 10px 13px;
}

.asset-upload-editor__file-main {
  min-width: 0;
}

.asset-upload-editor__file-name {
  color: #1e293b;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  word-break: break-all;
}

.asset-upload-editor__file-meta {
  margin-top: 3px;
  color: #475569;
  font-size: 12px;
}

.asset-upload-editor__file-remove {
  border: none;
  background: transparent;
  color: #dc2626;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  padding: 4px 2px;
  flex-shrink: 0;
}

.asset-upload-editor__file-remove:hover {
  color: #b91c1c;
}

.asset-upload-editor__files-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: -2px;
}

.asset-upload-editor__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.asset-upload-editor__actions :deep(.el-button) {
  min-width: 108px;
  height: 42px;
  border-radius: 14px;
  font-weight: 600;
}

.asset-upload-editor__actions :deep(.el-button:not(.el-button--primary)) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: #475569;
}

.asset-upload-editor__actions :deep(.el-button:not(.el-button--primary):hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: #0f172a;
}

.asset-upload-editor__actions :deep(.el-button--primary) {
  border: none;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.2);
}

.asset-upload-editor__actions :deep(.el-button--primary:hover) {
  background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
}

:deep(.asset-upload-editor__dragger .el-upload-dragger) {
  width: 100%;
  border-radius: 20px;
  border: 1.5px dashed #7cacf8;
  background: rgba(219, 228, 243, 0.45);
  padding: 24px 14px;
  backdrop-filter: blur(2px);
  transition: border-color 180ms ease, background-color 180ms ease;
}

:deep(.asset-upload-editor__dragger .el-upload-dragger:hover) {
  border-color: #4285f4;
  background: rgba(219, 228, 243, 0.52);
}

:deep(.asset-upload-editor__type .el-select__wrapper),
:deep(.asset-upload-editor__title .el-input__wrapper),
:deep(.asset-upload-editor__field .el-input__wrapper),
:deep(.asset-upload-editor__field .el-textarea__inner) {
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.24) inset;
  background: rgba(255, 255, 255, 0.96);
}

:deep(.asset-upload-editor__field .el-input-group__append) {
  display: flex;
  align-items: center;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  padding: 0 0 0 8px;
}

.asset-upload-editor__resolve-btn {
  height: 32px;
  min-width: 82px;
  border: none;
  border-radius: 10px;
  padding: 0 14px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #ffffff;
  font-size: 13px;
  line-height: 1;
  font-weight: 600;
  letter-spacing: 0.02em;
  white-space: nowrap;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(37, 99, 235, 0.2);
  transition: box-shadow 160ms ease, filter 160ms ease, opacity 160ms ease;
}

.asset-upload-editor__resolve-btn:hover:not(:disabled) {
  box-shadow: 0 6px 12px rgba(37, 99, 235, 0.24);
  filter: brightness(1.04);
}

.asset-upload-editor__resolve-btn:active:not(:disabled) {
  box-shadow: 0 3px 8px rgba(37, 99, 235, 0.2);
}

.asset-upload-editor__resolve-btn:disabled {
  background: linear-gradient(135deg, #93c5fd 0%, #60a5fa 100%);
  box-shadow: none;
  color: rgba(255, 255, 255, 0.9);
  opacity: 0.72;
  cursor: not-allowed;
}

.asset-upload-editor__resolve-btn.is-loading {
  pointer-events: none;
}

:deep(.asset-upload-editor__field .el-textarea__inner) {
  min-height: 112px;
}

:global(html.dark) .asset-upload-editor__hero-title,
:global(html.dark) .asset-upload-editor__url-card-title,
:global(html.dark) .asset-upload-editor__file-name {
  color: #f8fafc;
}

:global(html.dark) .asset-upload-editor__hero-desc,
:global(html.dark) .asset-upload-editor__resolving,
:global(html.dark) .asset-upload-editor__url-card-desc,
:global(html.dark) .asset-upload-editor__file-meta,
:global(html.dark) .asset-upload-editor__copy-hint {
  color: #94a3b8;
}

:global(html.dark) .asset-upload-editor__copy-title,
:global(html.dark) .asset-upload-editor__url-card-link {
  color: #bfdbfe;
}

:global(html.dark) .asset-upload-editor__url-card,
:global(html.dark) .asset-upload-editor__file-item,
:global(html.dark) .asset-upload-editor__markdown-preview {
  border-color: rgba(148, 163, 184, 0.14);
  background: #171b21 !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

:global(html.dark) .asset-upload-editor__url-card:hover {
  border-color: rgba(125, 211, 252, 0.28);
  box-shadow: 0 18px 36px rgba(2, 6, 23, 0.22);
}

:global(html.dark) .asset-upload-editor__url-card-media {
  background: rgba(15, 23, 42, 0.7);
}

:global(html.dark) .asset-upload-editor__url-card-placeholder {
  background:
    radial-gradient(circle at 18% 16%, rgba(59, 130, 246, 0.24) 0, rgba(59, 130, 246, 0) 50%),
    radial-gradient(circle at 84% 80%, rgba(14, 165, 233, 0.18) 0, rgba(14, 165, 233, 0) 48%),
    linear-gradient(140deg, rgba(17, 24, 39, 0.96) 0%, rgba(11, 24, 43, 1) 100%);
}

:global(html.dark) .asset-upload-editor__url-card-placeholder-mark {
  border-color: rgba(147, 197, 253, 0.18);
  background: rgba(255, 255, 255, 0.08);
  color: #93c5fd;
}

:global(html.dark) .asset-upload-editor__url-card-placeholder-host {
  color: #cbd5e1;
}

:global(html.dark) .asset-upload-editor__markdown-tabs {
  border-color: rgba(148, 163, 184, 0.14);
  background: rgba(148, 163, 184, 0.06);
}

:global(html.dark) .asset-upload-editor__markdown-tab {
  color: #94a3b8;
}

:global(html.dark) .asset-upload-editor__markdown-tab.is-active {
  background: rgba(96, 165, 250, 0.14);
  color: #f8fafc;
  box-shadow: none;
}

:global(html.dark) .asset-upload-editor__actions :deep(.el-button:not(.el-button--primary)) {
  border: none !important;
  background: transparent !important;
  color: #94a3b8;
  box-shadow: none !important;
}

:global(html.dark) .asset-upload-editor__actions :deep(.el-button:not(.el-button--primary):hover) {
  border: none !important;
  background: transparent !important;
  color: #94a3b8;
  box-shadow: none !important;
  transform: none !important;
}

:global(html.dark) .asset-upload-editor__actions :deep(.el-button--primary) {
  border: none !important;
  background: transparent !important;
  color: #60a5fa !important;
  box-shadow: none !important;
}

:global(html.dark) .asset-upload-editor__actions :deep(.el-button--primary:hover) {
  border: none !important;
  background: transparent !important;
  color: #60a5fa !important;
  box-shadow: none !important;
  transform: none !important;
}

:global(html.dark) :deep(.asset-upload-editor__dragger .el-upload-dragger) {
  border-color: rgba(125, 211, 252, 0.26);
  background: rgba(148, 163, 184, 0.08);
}

:global(html.dark) :deep(.asset-upload-editor__dragger .el-upload-dragger:hover) {
  border-color: rgba(125, 211, 252, 0.34);
  background: rgba(96, 165, 250, 0.12);
}

:global(html.dark) .asset-upload-editor__copy-icon {
  color: #60a5fa;
}

:global(html.dark) .asset-upload-editor__file-remove {
  color: #f87171;
}

:global(html.dark) .asset-upload-editor__file-remove:hover {
  color: #f87171;
}

:global(html.dark) .asset-upload-editor__files-actions :deep(.el-button),
:global(html.dark) .asset-upload-editor__files-actions :deep(.el-button:hover),
:global(html.dark) .asset-upload-editor__files-actions :deep(.el-button:focus-visible) {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  color: #94a3b8 !important;
  transform: none !important;
}

:global(html.dark) .asset-upload-editor__resolve-btn {
  border: none;
  background: transparent;
  color: #60a5fa;
  box-shadow: none;
}

:global(html.dark) .asset-upload-editor__resolve-btn:hover:not(:disabled),
:global(html.dark) .asset-upload-editor__resolve-btn:active:not(:disabled) {
  border: none;
  background: transparent;
  color: #60a5fa;
  box-shadow: none;
  filter: none;
}

:global(html.dark) .asset-upload-editor__resolve-btn:disabled {
  background: transparent;
  color: rgba(148, 163, 184, 0.68);
  box-shadow: none;
  opacity: 1;
}

:global(html.dark) :deep(.asset-upload-editor__type .el-select__wrapper),
:global(html.dark) :deep(.asset-upload-editor__title .el-input__wrapper),
:global(html.dark) :deep(.asset-upload-editor__field .el-input__wrapper),
:global(html.dark) :deep(.asset-upload-editor__field .el-textarea__inner) {
  background: rgba(15, 23, 42, 0.72);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.14) inset;
}

:global(html.dark) :deep(.asset-upload-editor__type .el-select__selected-item),
:global(html.dark) :deep(.asset-upload-editor__title .el-input__inner),
:global(html.dark) :deep(.asset-upload-editor__field .el-input__inner),
:global(html.dark) :deep(.asset-upload-editor__field .el-textarea__inner) {
  color: #f8fafc;
}

:global(html.dark) :deep(.asset-upload-editor__title .el-input__inner::placeholder),
:global(html.dark) :deep(.asset-upload-editor__field .el-input__inner::placeholder),
:global(html.dark) :deep(.asset-upload-editor__field .el-textarea__inner::placeholder),
:global(html.dark) :deep(.asset-upload-editor__type .el-select__placeholder) {
  color: #94a3b8;
}

@media (max-width: 768px) {
  .asset-upload-editor__meta {
    grid-template-columns: 1fr;
  }

  .asset-upload-editor__url-card {
    grid-template-columns: 1fr;
  }

  .asset-upload-editor__url-card-media {
    height: 126px;
  }
}
</style>

<style>
html.dark .asset-upload-editor__hero-title,
html.dark .asset-upload-editor__url-card-title,
html.dark .asset-upload-editor__file-name {
  color: #f8fafc;
}

html.dark .asset-upload-editor__hero-desc,
html.dark .asset-upload-editor__resolving,
html.dark .asset-upload-editor__url-card-desc,
html.dark .asset-upload-editor__file-meta,
html.dark .asset-upload-editor__copy-hint {
  color: #94a3b8;
}

html.dark .asset-upload-editor__copy-title,
html.dark .asset-upload-editor__url-card-link {
  color: #cbd5e1;
}

html.dark .asset-upload-editor__url-card,
html.dark .asset-upload-editor__file-item,
html.dark .asset-upload-editor__markdown-preview {
  border-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 82%, #6b7280 18%);
  background: linear-gradient(180deg, rgba(34, 38, 46, 0.96) 0%, rgba(27, 31, 38, 0.98) 100%);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.22);
}

html.dark .asset-upload-editor__url-card:hover {
  border-color: rgba(96, 165, 250, 0.24);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.28);
}

html.dark .asset-upload-editor__url-card-media {
  background: rgba(17, 24, 39, 0.56);
}

html.dark .asset-upload-editor__url-card-placeholder {
  background: linear-gradient(180deg, rgba(30, 34, 42, 0.96) 0%, rgba(21, 24, 30, 0.98) 100%);
}

html.dark .asset-upload-editor__url-card-placeholder-mark {
  border-color: rgba(96, 165, 250, 0.18);
  background: rgba(96, 165, 250, 0.14);
  color: #93c5fd;
}

html.dark .asset-upload-editor__url-card-placeholder-host {
  color: #cbd5e1;
}

html.dark .asset-upload-editor__markdown-tabs {
  border-color: rgba(148, 163, 184, 0.14);
  background: rgba(148, 163, 184, 0.06);
}

html.dark .asset-upload-editor__markdown-tab {
  color: #94a3b8;
}

html.dark .asset-upload-editor__markdown-tab.is-active {
  background: rgba(96, 165, 250, 0.14);
  color: #f8fafc;
  box-shadow: none;
}

html.dark .asset-upload-editor__actions .el-button:not(.el-button--primary) {
  border-color: rgba(107, 114, 128, 0.22);
  background: rgba(255, 255, 255, 0.03);
  color: #cbd5e1;
}

html.dark .asset-upload-editor__actions .el-button:not(.el-button--primary):hover {
  border-color: rgba(96, 165, 250, 0.2);
  background: rgba(96, 165, 250, 0.08);
  color: #f8fafc;
}

html.dark .asset-upload-editor__dragger .el-upload-dragger {
  border-color: rgba(125, 211, 252, 0.26);
  background: rgba(148, 163, 184, 0.06);
}

html.dark .asset-upload-editor__dragger .el-upload-dragger:hover {
  border-color: rgba(96, 165, 250, 0.28);
  background: rgba(96, 165, 250, 0.08);
}

html.dark .asset-upload-editor__copy-icon {
  color: #60a5fa;
}

html.dark .asset-upload-editor__type .el-select__wrapper,
html.dark .asset-upload-editor__title .el-input__wrapper,
html.dark .asset-upload-editor__field .el-input__wrapper,
html.dark .asset-upload-editor__field .el-textarea__inner {
  background: rgba(17, 24, 39, 0.56);
  box-shadow: 0 0 0 1px rgba(107, 114, 128, 0.2) inset;
}

html.dark .asset-upload-editor__type .el-select__selected-item,
html.dark .asset-upload-editor__title .el-input__inner,
html.dark .asset-upload-editor__field .el-input__inner,
html.dark .asset-upload-editor__field .el-textarea__inner {
  color: #f8fafc;
}

html.dark .asset-upload-editor__title .el-input__inner::placeholder,
html.dark .asset-upload-editor__field .el-input__inner::placeholder,
html.dark .asset-upload-editor__field .el-textarea__inner::placeholder,
html.dark .asset-upload-editor__type .el-select__placeholder {
  color: #94a3b8;
}
</style>
