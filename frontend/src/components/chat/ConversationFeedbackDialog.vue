<script setup lang="ts">
const props = defineProps<{
  visible: boolean
  rating: number
  comment: string
  submitting: boolean
  starHover: number
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'update:rating': [value: number]
  'update:comment': [value: string]
  'update:starHover': [value: number]
  submit: []
}>()
</script>

<template>
  <el-dialog
    :model-value="visible"
    width="480px"
    destroy-on-close
    class="styled-dialog"
    :show-close="false"
    @update:model-value="(value: boolean) => emit('update:visible', value)"
  >
    <template #header>
      <div class="dialog-header">
        <div class="dialog-header-icon feedback-icon">
          <el-icon :size="20"><Star /></el-icon>
        </div>
        <div>
          <div class="dialog-header-title">评价对话</div>
          <div class="dialog-header-desc">你的反馈帮助我们持续改进</div>
        </div>
      </div>
    </template>

    <div class="feedback-stars">
      <button
        v-for="s in 5"
        :key="s"
        type="button"
        class="star-btn"
        :class="{ active: s <= rating, hover: s <= starHover }"
        @mouseenter="emit('update:starHover', s)"
        @mouseleave="emit('update:starHover', 0)"
        @click="emit('update:rating', s)"
      >
        <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
        </svg>
      </button>
    </div>

    <div class="feedback-rating-text">{{ ['', '很差', '较差', '一般', '满意', '非常满意'][rating] }}</div>

    <textarea
      :value="comment"
      class="feedback-textarea"
      rows="4"
      placeholder="留下你的反馈意见（选填）"
      maxlength="500"
      @input="emit('update:comment', ($event.target as HTMLTextAreaElement).value)"
    />

    <template #footer>
      <div class="dialog-footer">
        <button type="button" class="dialog-btn secondary" @click="emit('update:visible', false)">取消</button>
        <button type="button" class="dialog-btn primary" :disabled="submitting" @click="emit('submit')">
          <el-icon v-if="submitting" class="is-loading"><Loading /></el-icon>
          提交评价
        </button>
      </div>
    </template>
  </el-dialog>
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

.dialog-header-icon.feedback-icon {
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  color: #d97706;
}

html.dark .dialog-header-icon.feedback-icon {
  background: rgba(245, 158, 11, 0.15);
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

.feedback-stars {
  display: flex;
  justify-content: center;
  gap: 8px;
  padding: 16px 0 8px;
}

.star-btn {
  padding: 4px;
  border: none;
  background: none;
  cursor: pointer;
  color: #e2e8f0;
  transition: color 0.15s, transform 0.2s;
  border-radius: 6px;
}

.star-btn:hover,
.star-btn.hover {
  color: #fbbf24;
  transform: scale(1.15);
}

.star-btn.active {
  color: #f59e0b;
}

.feedback-rating-text {
  text-align: center;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted, #94a3b8);
  height: 20px;
  margin-bottom: 20px;
}

.feedback-textarea {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border-primary, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  background: var(--bg-input, #f8fafc);
  color: var(--text-primary, #1e293b);
  font-size: 13px;
  font-family: inherit;
  resize: none;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.feedback-textarea:focus {
  border-color: #3b82f6;
}

.feedback-textarea::placeholder {
  color: var(--text-muted, #94a3b8);
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
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.dialog-btn:active {
  transform: scale(0.97);
}

.dialog-btn.secondary {
  background: var(--bg-card, #fff);
  border-color: var(--border-primary, rgba(0, 0, 0, 0.1));
  color: var(--text-secondary, #64748b);
}

.dialog-btn.secondary:hover {
  background: var(--bg-hover, #f8fafc);
}

.dialog-btn.primary {
  background: #3b82f6;
  color: #fff;
}

.dialog-btn.primary:hover {
  background: #2f6fec;
}

.dialog-btn.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

:global(.styled-dialog.el-dialog__wrapper .el-dialog),
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

:global(html.dark .styled-dialog .el-dialog) {
  border: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow: 0 16px 56px rgba(0, 0, 0, 0.45);
}
</style>
