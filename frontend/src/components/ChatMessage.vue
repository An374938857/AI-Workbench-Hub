<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ToolCallCard from './ToolCallCard.vue'
import ThinkingBlock from './ThinkingBlock.vue'
import BranchNavigator from './BranchNavigator.vue'
import { ElMessage } from 'element-plus'

interface FileItem {
  file_id: number
  original_name: string
  file_type: string
  file_size: number
  is_image?: boolean
}

interface ToolCallInfo {
  toolCallId: string
  toolName: string
  arguments?: string
  status: 'calling' | 'success' | 'error'
  progressTick?: number
  elapsedMs?: number
  elapsedSeconds?: number
  resultPreview?: string
  errorMessage?: string
  files?: { fileId: number; filename: string; fileSize: number }[]
}

export interface TimelineItem {
  type: 'thinking' | 'tool_call'
  // thinking fields
  content?: string
  isThinking?: boolean
  // tool_call fields
  toolCallId?: string
  toolName?: string
  arguments?: string
  status?: 'calling' | 'success' | 'error'
  progressTick?: number
  elapsedMs?: number
  elapsedSeconds?: number
  resultPreview?: string
  errorMessage?: string
  files?: { fileId: number; filename: string; fileSize: number }[]
}

const props = defineProps<{
  role: 'user' | 'assistant' | 'tool' | 'system_notice'
  content: string
  conversationId?: number | null
  files?: FileItem[]
  isStreaming?: boolean
  timeline?: TimelineItem[]
  messageId?: number
  siblingCount?: number
  branchIndex?: number
  parentId?: number | null
  childBranchCount?: number
  activeChildBranchIndex?: number
  referencedMessageIds?: number[]
  forceToolbarVisible?: boolean
  exportHintActive?: boolean
  exportHintPulse?: boolean
}>()

const emit = defineEmits<{
  edit: [messageId: number]
  regenerate: [messageId: number]
  fork: [messageId: number]
  switchBranch: [messageId: number, branchIndex: number]
  switchChildBranch: [parentMessageId: number, branchIndex: number]
  quote: [messageId: number]
  exportMessage: [messageId: number, format: 'md' | 'docx']
  exportHintAcknowledge: [messageId: number]
  skillDecision: [payload: { approved: boolean; skillId: number; skillName?: string; resumeAssistantMessageId?: number | null; resumeToolMessageId?: number | null }]
}>()

const isUser = computed(() => props.role === 'user')
const isSystemNotice = computed(() => props.role === 'system_notice')
const shouldForceToolbarVisible = computed(() => Boolean(props.forceToolbarVisible || props.exportHintActive))

function acknowledgeExportHint() {
  if (!props.exportHintActive || !props.messageId) return
  emit('exportHintAcknowledge', props.messageId)
}

function handleQuickExportMarkdown() {
  if (!props.messageId) return
  emit('exportMessage', props.messageId, 'md')
  acknowledgeExportHint()
}

// 图片文件
const IMAGE_EXTS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'])
const imageFiles = computed(() => (props.files || []).filter(f => f.is_image || IMAGE_EXTS.has(f.file_type)))
const nonImageFiles = computed(() => (props.files || []).filter(f => !f.is_image && !IMAGE_EXTS.has(f.file_type)))
const showPreview = ref(false)
const previewIndex = ref(0)
const previewScale = ref(1)

function openPreview(index: number) {
  previewIndex.value = index
  previewScale.value = 1
  showPreview.value = true
}

// 预览键盘事件
function handlePreviewKeydown(e: KeyboardEvent) {
  if (!showPreview.value) return
  if (e.key === 'Escape') showPreview.value = false
  else if (e.key === 'ArrowLeft' && previewIndex.value > 0) { previewIndex.value--; previewScale.value = 1 }
  else if (e.key === 'ArrowRight' && previewIndex.value < imageFiles.value.length - 1) { previewIndex.value++; previewScale.value = 1 }
}
function handlePreviewWheel(e: WheelEvent) {
  e.preventDefault()
  previewScale.value = Math.min(5, Math.max(0.2, previewScale.value * (e.deltaY < 0 ? 1.1 : 0.9)))
}
watch(showPreview, (v) => {
  if (v) document.addEventListener('keydown', handlePreviewKeydown)
  else document.removeEventListener('keydown', handlePreviewKeydown)
})
onUnmounted(() => document.removeEventListener('keydown', handlePreviewKeydown))

function enterEditMode() {
  if (!props.messageId) {
    ElMessage.warning('请等待消息完成后再编辑')
    return
  }
  emit('edit', props.messageId!)
}

function handleCopy() {
  navigator.clipboard.writeText(props.content).then(() => {
    ElMessage.success('已复制到剪贴板')
  })
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

const fileIcon: Record<string, string> = {
  docx: '📄', xlsx: '📊', csv: '📊', md: '📝', txt: '📃',
}

async function handleDownload(fileId: number, fileName: string) {
  const token = localStorage.getItem('access_token')
  const resp = await fetch(`/api/files/download/${fileId}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  })
  if (!resp.ok) {
    ElMessage.error('下载失败')
    return
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div v-if="isSystemNotice" class="chat-message system-notice">
    <div class="system-notice-line">
      <span class="system-notice-text">{{ content }}</span>
    </div>
  </div>
  <div v-else class="chat-message" :class="{ 'is-user': isUser }">
    <div class="msg-avatar">
      <el-icon v-if="isUser" :size="20"><User /></el-icon>
      <el-icon v-else :size="20" color="#409eff"><Promotion /></el-icon>
    </div>
    <div class="msg-body">
      <div class="msg-role">{{ isUser ? '你' : 'AI' }}</div>
      <div class="msg-content">
        <!-- 引用提示 -->
        <div v-if="referencedMessageIds && referencedMessageIds.length > 0" class="reference-hint">
          <el-icon :size="12"><ChatLineSquare /></el-icon>
          引用了 {{ referencedMessageIds.length }} 条消息
        </div>
        
        <!-- 用户消息 -->
        <template v-if="isUser">
          <!-- 图片缩略图 -->
          <div v-if="imageFiles.length > 0" class="msg-images">
            <div v-for="(img, i) in imageFiles" :key="img.file_id" class="image-thumb-wrapper" @click="openPreview(i)">
              <img :src="`/api/files/image/${img.file_id}`" :alt="img.original_name" class="image-thumb" loading="lazy" decoding="async" :title="img.original_name" />
            </div>
          </div>

          <!-- 非图片文件 -->
          <div v-if="nonImageFiles.length > 0" class="msg-files">
            <div v-for="f in nonImageFiles" :key="f.file_id" class="msg-file-item" @click="handleDownload(f.file_id, f.original_name)">
              <span class="file-icon">{{ fileIcon[f.file_type] || '📎' }}</span>
              <span class="file-name">{{ f.original_name }}</span>
              <span class="file-size">{{ formatSize(f.file_size) }}</span>
              <el-icon class="download-icon"><Download /></el-icon>
            </div>
          </div>

          <div class="user-text">{{ content }}</div>
        </template>

        <!-- AI 消息 -->
        <template v-else>
          <template v-for="(item, idx) in timeline" :key="idx">
            <ThinkingBlock
              v-if="item.type === 'thinking'"
              :content="item.content || ''"
              :is-thinking="!!item.isThinking"
            />
            <div v-else-if="item.type === 'tool_call'" class="tool-calls-area">
              <ToolCallCard
                :data="item as any"
                :conversation-id="conversationId"
                @skill-decision="emit('skillDecision', $event)"
              />
            </div>
          </template>
          <MarkdownRenderer v-if="content" :content="content" />
          <span v-if="isStreaming && !content && (!timeline || timeline.every(t => t.type === 'thinking' || t.status === 'calling'))" class="cursor-blink">▍</span>
          <span v-else-if="isStreaming && content" class="cursor-blink">▍</span>
        </template>
      </div>

      <!-- 消息工具栏 -->
      <div
        v-if="!isStreaming"
        class="msg-toolbar"
        :class="{ 'is-forced': shouldForceToolbarVisible }"
      >
        <!-- 用户消息工具栏 -->
        <template v-if="isUser">
          <el-tooltip content="复制内容" placement="top" :show-after="400">
            <button class="toolbar-btn" aria-label="复制内容" @click.stop="handleCopy">
              <el-icon :size="14"><CopyDocument /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip content="编辑消息" placement="top" :show-after="400">
            <button class="toolbar-btn" aria-label="编辑消息" @click.stop="enterEditMode">
              <el-icon :size="14"><Edit /></el-icon>
            </button>
          </el-tooltip>
        </template>

        <!-- AI 消息工具栏 -->
        <template v-if="!isUser && content">
          <el-tooltip content="复制内容" placement="top" :show-after="400">
            <button class="toolbar-btn" aria-label="复制内容" @click.stop="handleCopy">
              <el-icon :size="14"><CopyDocument /></el-icon>
            </button>
          </el-tooltip>
          <el-dropdown trigger="click" @command="(fmt: string) => { emit('exportMessage', messageId!, fmt as 'md' | 'docx'); acknowledgeExportHint() }">
            <button
              class="toolbar-btn"
              :class="{ 'export-hint-btn': exportHintActive, 'export-hint-btn-pulse': exportHintActive && exportHintPulse }"
              aria-label="导出消息"
            >
              <el-icon :size="14"><Download /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="md">导出为 Markdown</el-dropdown-item>
                <el-dropdown-item command="docx">导出为 Word</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <button
            v-if="exportHintActive"
            type="button"
            class="export-hint-action"
            @click.stop="handleQuickExportMarkdown"
          >
            导出为Markdown？
          </button>
          <el-tooltip content="引用这条消息" placement="top" :show-after="400">
            <button class="toolbar-btn" aria-label="引用这条消息" @click.stop="emit('quote', messageId!)">
              <el-icon :size="14"><ChatLineSquare /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip content="重新生成回复" placement="top" :show-after="400">
            <button class="toolbar-btn" aria-label="重新生成回复" @click.stop="emit('regenerate', messageId!)">
              <el-icon :size="14"><RefreshRight /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip content="从这里继续对话" placement="top" :show-after="400">
            <button class="toolbar-btn" aria-label="从这里继续对话" @click.stop="emit('fork', messageId!)">
              <el-icon :size="14"><Share /></el-icon>
            </button>
          </el-tooltip>
        </template>
        
        <!-- 用户消息也可以引用 -->
        <template v-if="isUser && content">
          <el-tooltip content="引用这条消息" placement="top" :show-after="400">
            <button class="toolbar-btn" @click.stop="emit('quote', messageId!)">
              <el-icon :size="14"><ChatLineSquare /></el-icon>
            </button>
          </el-tooltip>
        </template>

        <!-- 自身的分支导航器（编辑/重新生成产生的同级分支） -->
        <BranchNavigator
          v-if="(siblingCount ?? 1) > 1"
          :current-index="branchIndex ?? 0"
          :total-count="siblingCount ?? 1"
          @prev="emit('switchBranch', messageId!, (branchIndex ?? 0) - 1)"
          @next="emit('switchBranch', messageId!, (branchIndex ?? 0) + 1)"
        />
        <!-- 子级的分支导航器（从这里继续产生的子分支） -->
        <BranchNavigator
          v-if="(childBranchCount ?? 0) > 1"
          :current-index="activeChildBranchIndex ?? 0"
          :total-count="childBranchCount ?? 0"
          @prev="emit('switchChildBranch', messageId!, (activeChildBranchIndex ?? 0) - 1)"
          @next="emit('switchChildBranch', messageId!, (activeChildBranchIndex ?? 0) + 1)"
        />
      </div>
    </div>
  </div>

  <!-- 图片全屏预览 -->
  <Teleport to="body">
    <div v-if="showPreview" class="image-preview-overlay" @wheel.prevent="handlePreviewWheel">
      <div class="preview-counter">{{ previewIndex + 1 }} / {{ imageFiles.length }}</div>
      <img :src="`/api/files/image/${imageFiles[previewIndex]?.file_id}`" :alt="imageFiles[previewIndex]?.original_name" class="preview-image" :style="{ transform: `scale(${previewScale})` }" />
      <button v-if="imageFiles.length > 1 && previewIndex > 0" class="preview-nav preview-prev" aria-label="上一张图片" @click.stop="previewIndex--">&lt;</button>
      <button v-if="imageFiles.length > 1 && previewIndex < imageFiles.length - 1" class="preview-nav preview-next" aria-label="下一张图片" @click.stop="previewIndex++">&gt;</button>
      <button class="preview-close" aria-label="关闭预览" @click="showPreview = false">&times;</button>
    </div>
  </Teleport>
</template>

<style scoped>
.chat-message {
  display: flex;
  gap: 12px;
  padding: 16px 0;
}

.chat-message.is-user {
  flex-direction: row-reverse;
}

.msg-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.is-user .msg-avatar { background: var(--bg-user-msg, #ecf5ff) }
.chat-message:not(.is-user) .msg-avatar { background: var(--border-light, #f0f2f5) }

.msg-body {
  flex: 1;
  min-width: 0;
  max-width: 80%;
}

.is-user .msg-body {
  flex: unset;
}

.msg-role {
  font-size: 12px;
  color: var(--text-muted, #909399);
  margin-bottom: 4px;
}

.is-user .msg-role { text-align: right }
.msg-content { line-height: 1.6 }
.is-user .msg-content { text-align: left }

.user-text {
  background: var(--bg-user-msg, #ecf5ff);
  padding: 10px 14px;
  border-radius: 10px;
  display: inline-block;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  color: var(--text-primary, #303133);
}

.msg-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
  justify-content: flex-end;
}

.msg-file-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: var(--border-light, #f0f2f5);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary, #303133);
  cursor: pointer;
  transition: background 0.2s;
}

.msg-file-item:hover {
  background: var(--border-primary, #e6e8eb);
}

.download-icon {
  color: var(--text-muted, #909399);
  font-size: 14px;
  margin-left: 2px;
}

.msg-file-item:hover .download-icon {
  color: #409eff;
}

.file-icon { font-size: 15px }
.file-name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-size { color: var(--text-muted, #c0c4cc); font-size: 11px }

.reference-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  width: fit-content;
}

.is-user .reference-hint {
  margin-left: auto;
}

.msg-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  opacity: 0;
  transition: opacity 0.2s;
}

.msg-toolbar.is-forced {
  opacity: 1;
}

.is-user .msg-toolbar {
  justify-content: flex-end;
}

.chat-message:hover .msg-toolbar { opacity: 1 }

.toolbar-btn {
  border: 1px solid var(--border-primary, #ebeef5);
  background: var(--bg-card, #fff);
  cursor: pointer;
  font-size: 14px;
  padding: 4px 8px;
  border-radius: 6px;
  color: var(--text-muted, #909399);
  display: inline-flex;
  align-items: center;
  transition: all 0.15s;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.toolbar-btn:hover {
  background: var(--border-light, #f0f2f5);
  color: #409eff;
  border-color: #409eff;
}

.export-hint-btn {
  border-color: #409eff;
  color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

.export-hint-btn-pulse {
  animation: export-hint-pulse 1.8s ease-in-out infinite;
}

.export-hint-action {
  border: 1px solid rgba(64, 158, 255, 0.4);
  background: rgba(64, 158, 255, 0.08);
  color: #1f6feb;
  font-size: 12px;
  line-height: 1;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.export-hint-action:hover {
  background: rgba(64, 158, 255, 0.16);
  border-color: #409eff;
}

.cursor-blink {
  animation: blink 1s infinite;
  color: #409eff;
}

@keyframes blink {
  0%, 50% { opacity: 1 }
  51%, 100% { opacity: 0 }
}

@keyframes export-hint-pulse {
  0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(64, 158, 255, 0.35); }
  50% { transform: scale(1.04); box-shadow: 0 0 0 8px rgba(64, 158, 255, 0.1); }
  100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(64, 158, 255, 0.2); }
}

.tool-calls-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.system-notice {
  justify-content: center;
}

.system-notice-line {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted, #909399);
  font-size: 12px;
  position: relative;
  padding: 4px 0;
}

.system-notice-line::before,
.system-notice-line::after {
  content: '';
  position: absolute;
  height: 1px;
  background: var(--border-light, #e4e7ed);
  width: 28%;
}

.system-notice-line::before {
  left: 0;
}

.system-notice-line::after {
  right: 0;
}

.system-notice-text {
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-card, #fff);
  border: 1px dashed var(--border-light, #e4e7ed);
}

/* 图片缩略图 */
.msg-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.image-thumb-wrapper { cursor: pointer; }
.image-thumb {
  max-width: 300px;
  max-height: 200px;
  border-radius: 8px;
  object-fit: cover;
  transition: opacity 0.2s;
}
.image-thumb:hover { opacity: 0.85; }

/* 全屏预览 */
.image-preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.85);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.preview-image {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 4px;
}
.preview-counter {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  color: #fff;
  font-size: 14px;
  background: rgba(0,0,0,0.5);
  padding: 4px 12px;
  border-radius: 12px;
}
.preview-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255,255,255,0.2);
  border: none;
  color: #fff;
  font-size: 28px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.preview-nav:hover { background: rgba(255,255,255,0.4); }
.preview-prev { left: 16px; }
.preview-next { right: 16px; }
.preview-close {
  position: absolute;
  top: 16px;
  right: 16px;
  background: rgba(255,255,255,0.2);
  border: none;
  color: #fff;
  font-size: 24px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.preview-close:hover { background: rgba(255,255,255,0.4); }
</style>
