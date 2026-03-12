<script setup lang="ts">
import type { VNodeRef } from 'vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

const props = defineProps<{
  visible: boolean
  optimizing: boolean
  optimizedPrompt: string
  shouldAutoScrollOptimizedPrompt: boolean
  setOptimizedPromptContainerRef: (el: HTMLElement | null) => void
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  close: []
  stop: []
  apply: []
  scroll: []
  'scroll-bottom': []
}>()

const optimizedPromptContainerRef: VNodeRef = (el) => {
  props.setOptimizedPromptContainerRef(el as HTMLElement | null)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    width="760px"
    class="optimize-dialog"
    append-to-body
    align-center
    :destroy-on-close="false"
    :show-close="!optimizing"
    :close-on-click-modal="false"
    @update:model-value="(value: boolean) => emit('update:visible', value)"
    @close="emit('close')"
  >
    <div class="opt-dialog-body">
      <div class="opt-dialog-header">
        <div class="opt-dialog-icon">
          <el-icon :size="18"><MagicStick /></el-icon>
        </div>
        <div class="opt-dialog-title-wrap">
          <div class="opt-dialog-title">优化后的提示词</div>
          <div class="opt-dialog-subtitle">让表达更清晰、结构更完整、可执行性更高</div>
        </div>
      </div>
      <div v-if="optimizing && !optimizedPrompt" class="optimize-loading">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <div class="loading-title">正在优化提示词...</div>
        <div class="loading-subtitle">AI 正在理解你的意图并重写更高质量的版本</div>
      </div>
      <div
        v-show="!(optimizing && !optimizedPrompt)"
        :ref="optimizedPromptContainerRef"
        class="optimized-prompt-markdown"
        @scroll="emit('scroll')"
      >
        <MarkdownRenderer v-if="optimizedPrompt" :content="optimizedPrompt" />
        <div v-else class="optimized-prompt-placeholder">优化后的提示词将在这里显示...</div>
      </div>
      <button
        v-if="optimizedPrompt && !shouldAutoScrollOptimizedPrompt"
        type="button"
        class="opt-dialog-scroll-bottom-btn"
        @click="emit('scroll-bottom')"
      >
        回到底部
      </button>
    </div>

    <template #footer>
      <div class="opt-dialog-footer">
        <template v-if="optimizing">
          <button type="button" class="opt-dialog-btn danger" @click="emit('stop')">
            <el-icon><Close /></el-icon>
            中止优化
          </button>
        </template>
        <template v-else>
          <button type="button" class="opt-dialog-btn secondary" @click="emit('update:visible', false)">
            取消
          </button>
          <button type="button" class="opt-dialog-btn primary" :disabled="!optimizedPrompt" @click="emit('apply')">
            应用到输入框
          </button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.optimize-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 86px 20px;
  gap: 16px;
  color: var(--el-text-color-secondary);
}

.optimize-dialog :deep(.el-dialog) {
  border-radius: 24px;
  overflow: hidden;
}

.optimize-dialog :deep(.el-dialog__header) {
  padding: 0;
  margin: 0;
  height: 0;
  border: none;
}

.optimize-dialog :deep(.el-dialog__headerbtn) {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 32px;
  height: 32px;
  z-index: 10;
}

.optimize-dialog :deep(.el-dialog__headerbtn .el-dialog__close) {
  color: var(--text-muted, #94a3b8);
  transition: color 0.2s;
  font-size: 16px;
}

.optimize-dialog :deep(.el-dialog__headerbtn:hover .el-dialog__close) {
  color: var(--text-primary, #0f172a);
}

.optimize-dialog :deep(.el-dialog__body) {
  padding: 20px 24px 10px;
  background: var(--bg-primary, #ffffff);
}

.optimize-dialog :deep(.el-dialog__footer) {
  padding: 0 24px 12px;
  background: var(--bg-primary, #ffffff);
}

html.dark .optimize-dialog :deep(.el-dialog__body),
html.dark .optimize-dialog :deep(.el-dialog__footer) {
  background: var(--bg-primary, #1a1a1a);
}

.opt-dialog-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.opt-dialog-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(59, 130, 246, 0.18);
  background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.95), rgba(59, 130, 246, 0.12));
  color: #3b82f6;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7), 0 4px 12px rgba(59, 130, 246, 0.16);
}

.opt-dialog-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.opt-dialog-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
}

.opt-dialog-subtitle {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
}

.opt-dialog-body {
  border-radius: 14px;
  position: relative;
}

.loading-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #334155);
}

.loading-subtitle {
  font-size: 12px;
  color: var(--text-secondary, #94a3b8);
}

.optimized-prompt-markdown {
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  padding: 14px 16px;
  font-size: 14px;
  line-height: 1.75;
  min-height: 260px;
  max-height: 460px;
  overflow: auto;
  background: #fff;
  margin-top: 8px;
}

.optimized-prompt-placeholder {
  color: var(--text-secondary, #94a3b8);
}

.opt-dialog-scroll-bottom-btn {
  position: absolute;
  right: 12px;
  bottom: 14px;
  height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(59, 130, 246, 0.24);
  background: rgba(59, 130, 246, 0.08);
  color: #2563eb;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.opt-dialog-scroll-bottom-btn:hover {
  background: rgba(59, 130, 246, 0.14);
  border-color: rgba(59, 130, 246, 0.34);
}

.opt-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.opt-dialog-btn {
  height: 38px;
  padding: 0 18px;
  border-radius: 10px;
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.18s ease;
}

.opt-dialog-btn:active {
  transform: scale(0.98);
}

.opt-dialog-btn.secondary {
  background: var(--bg-card, #fff);
  color: var(--text-secondary, #64748b);
  border-color: rgba(0, 0, 0, 0.1);
}

.opt-dialog-btn.secondary:hover {
  background: var(--bg-hover, #f8fafc);
  border-color: rgba(0, 0, 0, 0.16);
}

.opt-dialog-btn.primary {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: #fff;
  box-shadow: 0 6px 18px rgba(37, 99, 235, 0.24);
}

.opt-dialog-btn.primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #4f8ff7, #2f6fec);
  box-shadow: 0 8px 22px rgba(37, 99, 235, 0.3);
}

.opt-dialog-btn.primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

.opt-dialog-btn.danger {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  color: #fff;
  box-shadow: 0 6px 18px rgba(220, 38, 38, 0.24);
}

.opt-dialog-btn.danger:hover {
  background: linear-gradient(135deg, #f15b5b, #e13636);
  box-shadow: 0 8px 22px rgba(220, 38, 38, 0.3);
}

html.dark .opt-dialog-header {
  border-bottom-color: rgba(255, 255, 255, 0.08);
}

html.dark .opt-dialog-icon {
  color: #93c5fd;
  border-color: rgba(147, 197, 253, 0.25);
  background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.1), rgba(59, 130, 246, 0.22));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.15), 0 6px 16px rgba(37, 99, 235, 0.28);
}

html.dark .optimized-prompt-markdown {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.02);
}

html.dark .opt-dialog-scroll-bottom-btn {
  border-color: rgba(147, 197, 253, 0.35);
  background: rgba(147, 197, 253, 0.16);
  color: #bfdbfe;
}

html.dark .opt-dialog-scroll-bottom-btn:hover {
  background: rgba(147, 197, 253, 0.24);
}

html.dark .opt-dialog-btn.secondary {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.14);
  color: var(--text-secondary, #cbd5e1);
}

html.dark .opt-dialog-btn.secondary:hover {
  background: rgba(255, 255, 255, 0.08);
}
</style>
