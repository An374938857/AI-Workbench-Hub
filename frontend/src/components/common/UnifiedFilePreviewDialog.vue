<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import type { FilePreviewSheet, FilePreviewType } from '@/types/filePreview'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    loading?: boolean
    saving?: boolean
    title: string
    fileType?: string
    fileSize?: number
    mode: FilePreviewType
    canEdit?: boolean
    enterEditToken?: number
    content?: string
    previewNotice?: string
    previewUrl?: string
    sheets?: FilePreviewSheet[]
    activeSheetName?: string
    canDownload?: boolean
  }>(),
  {
    loading: false,
    saving: false,
    fileType: '',
    fileSize: 0,
    canEdit: false,
    enterEditToken: 0,
    content: '',
    previewNotice: '',
    previewUrl: '',
    sheets: () => [],
    activeSheetName: '',
    canDownload: true,
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'update:activeSheetName', value: string): void
  (e: 'download'): void
  (e: 'open-external'): void
  (e: 'save-edit', content: string): void
}>()

const htmlTab = ref<'preview' | 'source'>('preview')
const markdownEditing = ref(false)
const markdownDraft = ref('')
const markdownEditorPaneRef = ref<HTMLElement | null>(null)
const markdownLivePreviewRef = ref<HTMLElement | null>(null)
const markdownTextareaEl = ref<HTMLTextAreaElement | null>(null)
const markdownSyncSource = ref<'editor' | 'preview' | null>(null)
const htmlPreviewDoc = computed(() => props.content || '<!doctype html><html><body></body></html>')
const imageViewportRef = ref<HTMLElement | null>(null)
const imageStageRef = ref<HTMLElement | null>(null)
const imageZoom = ref(1)
const imageFullscreen = ref(false)
const imageDragging = ref(false)
const imageDragStartX = ref(0)
const imageDragStartY = ref(0)
const imageDragStartScrollLeft = ref(0)
const imageDragStartScrollTop = ref(0)

const MIN_IMAGE_ZOOM = 0.2
const MAX_IMAGE_ZOOM = 5

const imageZoomPercent = computed(() => `${Math.round(imageZoom.value * 100)}%`)
const imageStyle = computed(() => ({
  width: `${Math.max(imageZoom.value, MIN_IMAGE_ZOOM) * 100}%`,
}))
const dialogWidth = computed(() =>
  markdownEditing.value ? 'min(1720px, 99vw)' : 'min(1080px, 88vw)',
)

watch(
  () => [props.modelValue, props.mode, props.title],
  () => {
    htmlTab.value = 'preview'
    if (!props.modelValue || props.mode !== 'markdown') {
      markdownEditing.value = false
      markdownDraft.value = props.content || ''
    } else if (!markdownEditing.value) {
      markdownDraft.value = props.content || ''
    }
    if (props.mode !== 'image') {
      imageZoom.value = 1
      imageFullscreen.value = false
      resetImageDrag()
      void exitImageFullscreen()
    }
    if (!props.modelValue) {
      imageZoom.value = 1
      imageFullscreen.value = false
      resetImageDrag()
      void exitImageFullscreen()
      return
    }
    syncImageFullscreenState()
  },
)

watch(
  () => props.content,
  (next) => {
    if (!markdownEditing.value) {
      markdownDraft.value = next || ''
    }
  },
)

watch(
  () => props.enterEditToken,
  () => {
    if (props.modelValue && props.mode === 'markdown' && props.canEdit) {
      startMarkdownEdit()
    }
  },
)

watch(
  () => [props.modelValue, markdownEditing.value],
  async ([visible, editing]) => {
    if (visible && editing) {
      await nextTick()
      bindMarkdownEditorTextarea()
      syncMarkdownScrollByRatio('editor')
      return
    }
    unbindMarkdownEditorTextarea()
  },
)

watch(
  () => markdownDraft.value,
  () => {
    if (!markdownEditing.value) return
    requestAnimationFrame(() => {
      syncMarkdownScrollByRatio('editor')
    })
  },
)

onMounted(() => {
  document.addEventListener('fullscreenchange', syncImageFullscreenState)
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', syncImageFullscreenState)
  window.removeEventListener('mousemove', handleImageMouseMove)
  window.removeEventListener('mouseup', handleImageMouseUp)
  unbindMarkdownEditorTextarea()
})

function formatBytes(size: number): string {
  if (!size || size <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = size
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value.toFixed(value >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function resolveModeText(): string {
  if (props.mode === 'download_only') {
    return props.previewNotice || '该文件类型暂不支持在线预览，请使用下载功能。'
  }
  return props.content || props.previewNotice || '暂无可展示内容'
}

function clampImageZoom(next: number): number {
  return Math.min(MAX_IMAGE_ZOOM, Math.max(MIN_IMAGE_ZOOM, next))
}

function setImageZoom(next: number) {
  imageZoom.value = clampImageZoom(next)
}

function zoomInImage() {
  setImageZoom(imageZoom.value * 1.1)
}

function zoomOutImage() {
  setImageZoom(imageZoom.value / 1.1)
}

function resetImageZoom() {
  imageZoom.value = 1
}

function setImageZoomPreset(command: string | number) {
  const value = Number(command)
  if (!Number.isFinite(value)) return
  setImageZoom(value)
}

function handleImageWheel(event: WheelEvent) {
  if (props.mode !== 'image') return
  event.preventDefault()
  if (event.deltaY < 0) {
    zoomInImage()
  } else if (event.deltaY > 0) {
    zoomOutImage()
  }
}

function syncImageFullscreenState() {
  const viewport = imageViewportRef.value
  imageFullscreen.value = Boolean(viewport) && document.fullscreenElement === viewport
}

function resetImageDrag() {
  imageDragging.value = false
  window.removeEventListener('mousemove', handleImageMouseMove)
  window.removeEventListener('mouseup', handleImageMouseUp)
}

function handleImageMouseDown(event: MouseEvent) {
  if (!imageStageRef.value) return
  if (event.button !== 0) return
  event.preventDefault()
  imageDragging.value = true
  imageDragStartX.value = event.clientX
  imageDragStartY.value = event.clientY
  imageDragStartScrollLeft.value = imageStageRef.value.scrollLeft
  imageDragStartScrollTop.value = imageStageRef.value.scrollTop
  window.addEventListener('mousemove', handleImageMouseMove)
  window.addEventListener('mouseup', handleImageMouseUp)
}

function handleImageMouseMove(event: MouseEvent) {
  if (!imageStageRef.value || !imageDragging.value) return
  event.preventDefault()
  const deltaX = event.clientX - imageDragStartX.value
  const deltaY = event.clientY - imageDragStartY.value
  imageStageRef.value.scrollLeft = imageDragStartScrollLeft.value - deltaX
  imageStageRef.value.scrollTop = imageDragStartScrollTop.value - deltaY
}

function handleImageMouseUp() {
  resetImageDrag()
}

async function exitImageFullscreen() {
  if (document.fullscreenElement === imageViewportRef.value) {
    try {
      await document.exitFullscreen()
    } catch {
      // Ignore exit errors caused by browser permission or quick state changes.
    }
  }
  syncImageFullscreenState()
}

async function toggleImageFullscreen() {
  if (!imageViewportRef.value) return
  if (document.fullscreenElement === imageViewportRef.value) {
    await exitImageFullscreen()
    return
  }
  try {
    await imageViewportRef.value.requestFullscreen()
  } catch {
    // Ignore request errors caused by browser limitation.
  }
  syncImageFullscreenState()
}

function startMarkdownEdit() {
  markdownEditing.value = true
  markdownDraft.value = props.content || ''
}

function cancelMarkdownEdit() {
  markdownEditing.value = false
  markdownDraft.value = props.content || ''
}

function saveMarkdownEdit() {
  emit('save-edit', markdownDraft.value)
  markdownEditing.value = false
}

function bindMarkdownEditorTextarea() {
  const textarea = markdownEditorPaneRef.value?.querySelector('textarea') as HTMLTextAreaElement | null
  if (!textarea || textarea === markdownTextareaEl.value) return
  unbindMarkdownEditorTextarea()
  markdownTextareaEl.value = textarea
  markdownTextareaEl.value.addEventListener('scroll', handleMarkdownEditorScroll, { passive: true })
}

function unbindMarkdownEditorTextarea() {
  if (!markdownTextareaEl.value) return
  markdownTextareaEl.value.removeEventListener('scroll', handleMarkdownEditorScroll)
  markdownTextareaEl.value = null
}

function getScrollRatio(el: HTMLElement): number {
  const max = el.scrollHeight - el.clientHeight
  if (max <= 0) return 0
  return el.scrollTop / max
}

function setScrollByRatio(el: HTMLElement, ratio: number) {
  const clamped = Math.max(0, Math.min(1, ratio))
  const max = el.scrollHeight - el.clientHeight
  el.scrollTop = max > 0 ? max * clamped : 0
}

function syncMarkdownScrollByRatio(source: 'editor' | 'preview') {
  const editor = markdownTextareaEl.value
  const preview = markdownLivePreviewRef.value
  if (!editor || !preview) return

  if (source === 'editor') {
    setScrollByRatio(preview, getScrollRatio(editor))
    return
  }
  setScrollByRatio(editor, getScrollRatio(preview))
}

function releaseMarkdownSyncLock() {
  requestAnimationFrame(() => {
    markdownSyncSource.value = null
  })
}

function handleMarkdownEditorScroll() {
  if (markdownSyncSource.value === 'preview') return
  markdownSyncSource.value = 'editor'
  syncMarkdownScrollByRatio('editor')
  releaseMarkdownSyncLock()
}

function handleMarkdownPreviewScroll() {
  if (markdownSyncSource.value === 'editor') return
  markdownSyncSource.value = 'preview'
  syncMarkdownScrollByRatio('preview')
  releaseMarkdownSyncLock()
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :class="['unified-preview-dialog', { 'is-editing': markdownEditing }]"
    :width="dialogWidth"
    :show-close="false"
    destroy-on-close
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
  >
    <template #header>
      <div class="preview-dialog-header">
        <div class="preview-dialog-heading">
          <div class="preview-dialog-badge">文件预览</div>
          <h3 class="preview-dialog-title">{{ title }}</h3>
        </div>
        <div class="preview-dialog-meta">
          <span>{{ formatBytes(fileSize || 0) }}</span>
          <span>{{ (fileType || 'file').toUpperCase() }}</span>
        </div>
      </div>
    </template>

    <div v-loading="loading" :class="['preview-content', { 'preview-content--image': mode === 'image' }]">
      <div
        v-if="mode === 'image' && previewUrl"
        ref="imageViewportRef"
        class="preview-image-wrap"
        @wheel.prevent="handleImageWheel"
      >
        <div class="preview-image-toolbar">
          <span class="preview-image-tip">滚轮可缩放</span>
          <div class="preview-image-actions">
            <el-dropdown trigger="click" :teleported="false" @command="setImageZoomPreset">
              <button class="preview-image-zoom" type="button">
                {{ imageZoomPercent }}
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item :command="0.5">50%</el-dropdown-item>
                  <el-dropdown-item :command="1">100%</el-dropdown-item>
                  <el-dropdown-item :command="1.5">150%</el-dropdown-item>
                  <el-dropdown-item :command="2">200%</el-dropdown-item>
                  <el-dropdown-item :command="3">300%</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button text class="preview-image-action" @click="zoomOutImage">缩小</el-button>
            <el-button text class="preview-image-action" @click="zoomInImage">放大</el-button>
            <el-button text class="preview-image-action" @click="resetImageZoom">重置</el-button>
            <el-button text class="preview-image-action" @click="toggleImageFullscreen">
              {{ imageFullscreen ? '退出全屏' : '全屏' }}
            </el-button>
          </div>
        </div>
        <div
          ref="imageStageRef"
          :class="['preview-image-stage', { 'is-draggable': true, 'is-dragging': imageDragging }]"
          @mousedown="handleImageMouseDown"
        >
          <img
            :src="previewUrl"
            :alt="title"
            class="preview-image"
            :style="imageStyle"
            draggable="false"
          />
        </div>
      </div>
      <iframe
        v-else-if="mode === 'pdf' && previewUrl"
        :src="previewUrl"
        class="preview-pdf"
        title="PDF 预览"
      />
      <div v-else-if="mode === 'html'" class="preview-html-wrap">
        <div class="preview-html-toolbar">
          <div class="preview-html-badge">HTML</div>
          <div class="preview-html-tip">支持页内渲染，也可以直接在浏览器新窗口打开</div>
        </div>
        <el-tabs v-model="htmlTab" class="preview-html-tabs">
          <el-tab-pane label="页面预览" name="preview" />
          <el-tab-pane label="源码" name="source" />
        </el-tabs>
        <iframe
          v-if="htmlTab === 'preview'"
          :srcdoc="htmlPreviewDoc"
          class="preview-html-frame"
          sandbox="allow-downloads allow-forms allow-modals allow-popups allow-same-origin allow-scripts"
          title="HTML 页面预览"
        />
        <pre v-else class="preview-text preview-html-source">{{ resolveModeText() }}</pre>
      </div>
      <div v-else-if="mode === 'xlsx_table'" class="preview-table-wrap">
        <el-tabs
          :model-value="activeSheetName"
          @update:model-value="(name: string) => emit('update:activeSheetName', name)"
        >
          <el-tab-pane
            v-for="sheet in sheets"
            :key="sheet.name"
            :name="sheet.name"
            :label="sheet.name"
          />
        </el-tabs>
        <div
          v-for="sheet in sheets"
          v-show="sheet.name === activeSheetName"
          :key="`table-${sheet.name}`"
          class="sheet-panel"
        >
          <div class="sheet-meta">
            共 {{ sheet.total_rows }} 行，{{ sheet.total_columns }} 列
            <span v-if="sheet.truncated_rows || sheet.truncated_columns">
              （当前仅预览前 {{ sheet.rows.length }} 行、前 {{ sheet.columns.length }} 列）
            </span>
          </div>
          <el-table
            :data="sheet.rows"
            border
            stripe
            class="xlsx-table"
            max-height="460"
          >
            <el-table-column
              v-for="(column, idx) in sheet.columns"
              :key="`${idx}-${column}`"
              :label="column || '(空列名)'"
              min-width="140"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                {{ formatCell(row[column]) }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
      <div v-else-if="mode === 'markdown'" class="preview-markdown">
        <div v-if="markdownEditing" class="preview-markdown-split">
          <div ref="markdownEditorPaneRef" class="preview-markdown-editor-pane">
            <div class="preview-markdown-pane-title">编辑区</div>
            <el-input
              v-model="markdownDraft"
              type="textarea"
              class="preview-markdown-editor"
              resize="none"
              placeholder="请输入 Markdown 内容"
            />
          </div>
          <div class="preview-markdown-render-pane">
            <div class="preview-markdown-pane-title">实时预览</div>
            <div
              ref="markdownLivePreviewRef"
              class="preview-markdown-live"
              @scroll="handleMarkdownPreviewScroll"
            >
              <MarkdownRenderer :content="markdownDraft || ' '" />
            </div>
          </div>
        </div>
        <MarkdownRenderer v-else :content="resolveModeText()" />
      </div>
      <pre v-else class="preview-text">{{ resolveModeText() }}</pre>
    </div>

    <template #footer>
      <div class="preview-dialog-footer">
        <el-button class="preview-dialog-secondary" @click="emit('update:modelValue', false)">关闭</el-button>
        <template v-if="mode === 'markdown' && canEdit">
          <el-button
            v-if="!markdownEditing"
            class="preview-dialog-secondary"
            @click="startMarkdownEdit"
          >
            编辑
          </el-button>
          <template v-else>
            <el-button class="preview-dialog-secondary" @click="cancelMarkdownEdit">取消编辑</el-button>
            <el-button class="preview-dialog-primary" :loading="saving" @click="saveMarkdownEdit">保存</el-button>
          </template>
        </template>
        <el-button
          v-if="mode === 'html'"
          class="preview-dialog-secondary"
          @click="emit('open-external')"
        >
          新窗口打开
        </el-button>
        <el-button v-if="canDownload && !markdownEditing" class="preview-dialog-primary" @click="emit('download')">下载</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.preview-content {
  height: 60vh;
  min-height: 300px;
  max-height: 60vh;
  overflow: auto;
}

.preview-content--image {
  height: 60vh;
  min-height: 300px;
  max-height: 60vh;
  overflow: hidden;
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
  display: block;
  width: 100%;
  max-width: none;
  height: auto;
  margin: 0 auto;
  -webkit-user-drag: none;
  user-select: none;
}

.preview-image-wrap {
  height: 100%;
  min-height: 0;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.78);
  overflow: hidden;
}

.preview-image-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(255, 255, 255, 0.8);
}

.preview-image-tip {
  color: var(--text-secondary, #64748b);
  font-size: 12px;
  font-weight: 500;
}

.preview-image-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
}

.preview-image-action {
  padding: 0 8px;
}

.preview-image-zoom {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 26px;
  min-width: 56px;
  padding: 0 10px;
  border: none;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.1);
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.preview-image-stage {
  height: calc(100% - 48px);
  overflow: auto;
  padding: 16px;
}

.preview-image-stage.is-draggable {
  cursor: grab;
  user-select: none;
}

.preview-image-stage.is-dragging {
  cursor: grabbing;
}

:global(.preview-image-wrap:fullscreen) {
  width: 100vw;
  height: 100vh;
  border-radius: 0;
  border: none;
  background: #0b1220;
}

:global(.preview-image-wrap:fullscreen .preview-image-toolbar) {
  border-bottom-color: rgba(148, 163, 184, 0.3);
  background: rgba(15, 23, 42, 0.88);
}

:global(.preview-image-wrap:fullscreen .preview-image-tip) {
  color: rgba(226, 232, 240, 0.86);
}

:global(.preview-image-wrap:fullscreen .preview-image-zoom) {
  background: rgba(96, 165, 250, 0.2);
  color: #bfdbfe;
}

:global(.preview-image-wrap:fullscreen .preview-image-action) {
  color: #dbeafe;
}

:global(.preview-image-wrap:fullscreen .preview-image-stage) {
  height: calc(100vh - 50px);
  padding: 24px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.16), transparent 48%),
    #0b1220;
}

:global(.preview-image-wrap:fullscreen .preview-image) {
  margin: 0 auto;
  box-shadow: 0 24px 60px rgba(2, 6, 23, 0.6);
}

:global(html.dark) .preview-image-wrap {
  background: rgba(15, 23, 42, 0.88);
  border-color: rgba(71, 85, 105, 0.55);
}

:global(html.dark) .preview-image-toolbar {
  background: rgba(15, 23, 42, 0.86);
  border-bottom-color: rgba(71, 85, 105, 0.55);
}

:global(html.dark) .preview-image-tip {
  color: rgba(148, 163, 184, 0.95);
}

:global(html.dark) .preview-image-zoom {
  background: rgba(59, 130, 246, 0.2);
  color: #bfdbfe;
}

:global(html.dark) .preview-image-stage {
  background: rgba(15, 23, 42, 0.72);
}

:global(html.dark) .preview-image-action {
  color: #dbeafe;
}

:global(html.dark) .preview-image-action:hover {
  color: #eff6ff;
}

@media (max-width: 768px) {
  .preview-content--image {
    height: 52vh;
    min-height: 0;
    max-height: 52vh;
  }

  .preview-image-wrap {
    height: 100%;
  }

  .preview-image-toolbar {
    align-items: flex-start;
  }

  .preview-image-stage {
    height: calc(100% - 48px);
    padding: 12px;
  }

  .preview-markdown-split {
    grid-template-columns: 1fr;
  }
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
  height: 100%;
  overflow: auto;
}

.preview-markdown-editor {
  width: 100%;
  height: 100%;
}

.preview-markdown-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  height: 100%;
  min-height: 0;
}

.preview-markdown-editor-pane,
.preview-markdown-render-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.68);
  overflow: hidden;
}

.preview-markdown-pane-title {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary, #64748b);
  letter-spacing: 0.06em;
}

.preview-markdown-live {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

.preview-markdown-editor :deep(.el-textarea),
.preview-markdown-editor :deep(.el-textarea__inner) {
  height: 100%;
  min-height: 0;
}

.preview-markdown-editor :deep(.el-textarea__inner) {
  border: none;
  border-radius: 0;
  background: transparent;
  padding: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.preview-table-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-html-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.preview-html-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.preview-html-badge {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.12);
  color: #0369a1;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.preview-html-tip {
  color: var(--text-secondary, #64748b);
  font-size: 13px;
}

.preview-html-tabs {
  margin-top: -4px;
}

.preview-html-frame {
  width: 100%;
  min-height: 68vh;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 18px;
  background: #fff;
}

.preview-html-source {
  min-height: 68vh;
  margin: 0;
}

.sheet-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
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

:global(.unified-preview-dialog .el-dialog) {
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 26px;
  overflow: hidden;
  transition:
    width 0.52s cubic-bezier(0.22, 1, 0.36, 1),
    border-radius 0.52s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.52s cubic-bezier(0.22, 1, 0.36, 1);
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--bg-card, #ffffff) 95%, var(--bg-page, #f8fafc) 5%) 0%,
    color-mix(in srgb, var(--bg-card, #ffffff) 99%, transparent 1%) 100%
  );
  box-shadow: 0 28px 80px rgba(15, 23, 42, 0.22);
  will-change: width, border-radius, box-shadow;
}

:global(.unified-preview-dialog.is-editing .el-dialog) {
  border-radius: 22px;
  box-shadow: 0 34px 96px rgba(15, 23, 42, 0.24);
}

:global(.unified-preview-dialog .el-dialog__header) {
  margin: 0;
  padding: 24px 28px 0;
}

:global(.unified-preview-dialog .el-dialog__body) {
  padding: 18px 28px 0;
}

:global(.unified-preview-dialog .el-dialog__footer) {
  padding: 22px 28px 28px;
}

:global(.unified-preview-dialog .el-dialog__footer .el-button) {
  min-width: 108px;
  height: 42px;
  border-radius: 14px;
  font-weight: 600;
}

:global(.unified-preview-dialog .el-dialog__footer .preview-dialog-secondary) {
  border-color: rgba(148, 163, 184, 0.2);
  background: rgba(15, 23, 42, 0.04);
  color: var(--text-secondary, #475569);
}

:global(.unified-preview-dialog .el-dialog__footer .preview-dialog-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.08);
  color: var(--text-primary, #0f172a);
}

:global(.unified-preview-dialog .el-dialog__footer .preview-dialog-primary) {
  border: none;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #fff;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.24);
}

:global(.unified-preview-dialog .el-dialog__footer .preview-dialog-primary:hover) {
  background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
  color: #fff;
}

:global(html.dark) .preview-pdf,
:global(html.dark) .preview-html-wrap,
:global(html.dark) .preview-text,
:global(html.dark) .preview-markdown,
:global(html.dark) .preview-table-wrap {
  background: rgba(15, 23, 42, 0.88);
  border-color: rgba(71, 85, 105, 0.55);
  color: rgba(226, 232, 240, 0.95);
}

:global(html.dark) .preview-html-badge {
  background: rgba(56, 189, 248, 0.16);
  color: #7dd3fc;
}

:global(html.dark) .preview-html-tip {
  color: rgba(148, 163, 184, 0.9);
}

:global(html.dark) .preview-html-frame {
  border-color: rgba(71, 85, 105, 0.6);
  background: #0f172a;
}

:global(html.dark .unified-preview-dialog .el-dialog) {
  border-color: rgba(59, 130, 246, 0.28);
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.16), transparent 56%),
    linear-gradient(170deg, rgba(15, 23, 42, 0.95), rgba(15, 23, 42, 0.82));
  box-shadow: 0 36px 90px rgba(2, 6, 23, 0.75);
}
</style>
