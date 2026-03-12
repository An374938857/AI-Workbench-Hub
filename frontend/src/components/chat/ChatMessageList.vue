<script setup lang="ts">
import type { VNodeRef } from 'vue'
import ChatMessage from '@/components/ChatMessage.vue'
import type { Msg } from '@/types/chat'

interface ComparisonResult {
  content: string
}

const props = defineProps<{
  messages: Msg[]
  conversationId: number | null
  setMessagesAreaRef: (el: HTMLElement | null) => void
  isGenerating: boolean
  compressionSummary: string
  compressionSavedTokens: number
  compressionSplitMessageId: number | null
  comparisonResults: ComparisonResult[]
  selectedModelName: string | null
  compareModelBName: string | null
  comparisonDone: boolean
  comparisonId: number | null
  choosingWinner: boolean
}>()

const emit = defineEmits<{
  edit: [messageId: number]
  regenerate: [messageId: number]
  fork: [index: number]
  quote: [messageId: number]
  'export-message': [messageId: number, format: 'md' | 'docx']
  'export-hint-acknowledge': [messageId: number]
  'skill-decision': [payload: { approved: boolean; skillId: number; skillName?: string; resumeAssistantMessageId?: number | null; resumeToolMessageId?: number | null }]
  'switch-branch': [messageId: number, branchIndex: number]
  'switch-child-branch': [parentMessageId: number, branchIndex: number]
  'choose-winner': [winner: 'a' | 'b']
}>()

const messagesAreaRef: VNodeRef = (el) => {
  props.setMessagesAreaRef(el as HTMLElement | null)
}
</script>

<template>
  <div class="messages-area" :ref="messagesAreaRef">
    <template v-for="(msg, i) in messages" :key="msg.clientKey">
      <div
        v-if="compressionSummary && compressionSplitMessageId && msg.id === compressionSplitMessageId"
        class="compression-divider"
      >
        <div class="divider-line-full" />
        <div class="divider-content">
          <div class="divider-title">
            <el-icon><FolderOpened /></el-icon>
            <span>早期对话已压缩</span>
            <el-tag v-if="compressionSavedTokens > 0" size="small" type="success">节省 {{ compressionSavedTokens }} tokens</el-tag>
          </div>
          <div class="divider-summary">{{ compressionSummary }}</div>
        </div>
      </div>

      <ChatMessage
        :role="msg.role"
        :content="msg.content"
        :conversation-id="conversationId"
        :files="msg.files"
        :timeline="msg.timeline"
        :is-streaming="isGenerating && i === messages.length - 1 && msg.role === 'assistant'"
        :message-id="msg.id"
        :sibling-count="msg.siblingCount"
        :branch-index="msg.branchIndex"
        :parent-id="msg.parentId"
        :child-branch-count="msg.childBranchCount"
        :active-child-branch-index="msg.activeChildBranchIndex"
        :referenced-message-ids="msg.referencedMessageIds"
        :force-toolbar-visible="msg.forceToolbarVisible"
        :export-hint-active="msg.exportHintActive"
        :export-hint-pulse="msg.exportHintPulse"
        @edit="(id) => emit('edit', id ?? msg.id!)"
        @regenerate="(id) => emit('regenerate', id ?? msg.id!)"
        @fork="emit('fork', i)"
        @quote="(id) => emit('quote', id)"
        @export-message="(id, format) => emit('export-message', id, format)"
        @export-hint-acknowledge="(id) => emit('export-hint-acknowledge', id)"
        @skill-decision="(payload) => emit('skill-decision', payload)"
        @switch-branch="(id, branchIndex) => emit('switch-branch', id, branchIndex)"
        @switch-child-branch="(parentId, branchIndex) => emit('switch-child-branch', parentId, branchIndex)"
      />
    </template>

    <div v-if="comparisonResults.length > 0" class="comparison-results">
      <div class="comparison-side">
        <div class="comparison-header">模型 A: {{ selectedModelName }}</div>
        <div class="comparison-content">{{ comparisonResults[0]?.content || '' }}</div>
      </div>
      <div class="comparison-side">
        <div class="comparison-header">模型 B: {{ compareModelBName }}</div>
        <div class="comparison-content">{{ comparisonResults[1]?.content || '' }}</div>
      </div>
    </div>

    <Transition name="comparison-choice">
      <div v-if="comparisonDone && comparisonId" class="comparison-choice-card">
        <div class="comparison-choice-title">哪个回复更好？</div>
        <div class="comparison-choice-actions">
          <button class="choice-btn choice-btn-a" :disabled="choosingWinner" @click="emit('choose-winner', 'a')">
            👈 模型 A · {{ selectedModelName }}
          </button>
          <button class="choice-btn choice-btn-b" :disabled="choosingWinner" @click="emit('choose-winner', 'b')">
            模型 B · {{ compareModelBName }} 👉
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}

.comparison-results {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 16px;
  background: var(--bg-secondary, #f5f7fa);
  border-radius: 8px;
  margin: 16px 0;
}

.comparison-side {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.comparison-header {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary, #303133);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--el-color-primary, #409eff);
}

.comparison-content {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary, #303133);
  white-space: pre-wrap;
  word-break: break-word;
}

.comparison-choice-card {
  text-align: center;
  padding: 20px 16px;
  margin: 0 0 16px;
  background: var(--bg-secondary, #f5f7fa);
  border-radius: 12px;
}

.comparison-choice-title {
  font-size: 14px;
  color: var(--text-muted, #909399);
  margin-bottom: 14px;
}

.comparison-choice-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.choice-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px 20px;
  border: 2px solid transparent;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  background: white;
  color: var(--text-primary, #303133);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.choice-btn:hover:not(:disabled) {
  border-color: var(--el-color-primary, #409eff);
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
  transform: translateY(-1px);
}

.choice-btn:active:not(:disabled) {
  transform: translateY(0);
}

.choice-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.comparison-choice-enter-active {
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.comparison-choice-leave-active {
  transition: all 0.2s ease-in;
}

.comparison-choice-enter-from {
  opacity: 0;
  transform: translateY(12px);
}

.comparison-choice-leave-to {
  opacity: 0;
}

.compression-divider {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 24px 20px;
}

.divider-line-full {
  width: 100%;
  height: 1px;
  background: var(--el-border-color-light);
  margin-bottom: 16px;
}

.divider-content {
  max-width: 600px;
  width: 100%;
  padding: 16px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
}

.divider-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
}

.divider-summary {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

@media (max-width: 768px) {
  .comparison-results {
    grid-template-columns: 1fr;
  }

  .comparison-choice-actions {
    grid-template-columns: 1fr;
  }
}
</style>
