<script setup lang="ts">
import type { VNodeRef } from 'vue'

const props = defineProps<{
  loading: boolean
  editingHeaderTitle: boolean
  editingHeaderTitleText: string
  currentConvId: number | null
  currentTitle: string
  currentSkillName: string
  isGenerating: boolean
  regeneratingTitle: boolean
  adminView: boolean
  messageCount: number
  currentFeedback: { rating: number; comment: string } | null
  setHeaderTitleInputRef: (el: HTMLInputElement | null) => void
}>()

const emit = defineEmits<{
  'update:editingHeaderTitleText': [value: string]
  'start-edit-header-title': []
  'save-header-edit-title': []
  'cancel-header-edit-title': []
  'regenerate-title': []
  'open-feedback': []
  'open-export': []
}>()

const titleInputRef: VNodeRef = (el) => {
  props.setHeaderTitleInputRef(el as HTMLInputElement | null)
}
</script>

<template>
  <div class="chat-header" :class="{ 'is-loading': loading }">
    <h3 @dblclick="emit('start-edit-header-title')">
      <input
        v-if="editingHeaderTitle"
        :ref="titleInputRef"
        :value="editingHeaderTitleText"
        class="title-edit-input header-title-input"
        @input="emit('update:editingHeaderTitleText', ($event.target as HTMLInputElement).value)"
        @blur="emit('save-header-edit-title')"
        @keyup.enter="($event.target as HTMLInputElement)?.blur()"
        @keyup.escape="emit('cancel-header-edit-title')"
      />
      <span v-else>{{ currentTitle || currentSkillName || '新对话' }}</span>
      <button
        v-if="currentConvId"
        type="button"
        class="header-title-refresh-btn"
        :class="{ 'is-regenerating': regeneratingTitle }"
        :disabled="isGenerating || editingHeaderTitle || regeneratingTitle"
        title="重新生成标题"
        @click.stop="emit('regenerate-title')"
      >
        <el-icon :size="14" class="header-title-refresh-icon" :class="{ 'is-spinning': regeneratingTitle }">
          <RefreshRight />
        </el-icon>
      </button>
    </h3>
    <div class="header-actions">
      <button
        v-if="!adminView"
        type="button"
        class="header-action-btn"
        :class="{ rated: currentFeedback }"
        :disabled="isGenerating || messageCount <= 1"
        @click="emit('open-feedback')"
      >
        <el-icon :size="15"><Star /></el-icon>
        <span>{{ currentFeedback ? `${currentFeedback.rating} 星` : '评价' }}</span>
      </button>
      <button
        type="button"
        class="header-action-btn"
        :disabled="isGenerating || messageCount <= 1"
        @click="emit('open-export')"
      >
        <el-icon :size="15"><Download /></el-icon>
        <span>导出</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.title-edit-input {
  width: 100%;
  border: 1px solid var(--el-color-primary);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: inherit;
  font-family: inherit;
  color: inherit;
  background: var(--bg-primary, #fff);
  outline: none;
  box-sizing: border-box;
}

.header-title-input {
  font-size: 16px;
  font-weight: 600;
  padding: 2px 8px;
}

.chat-header {
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-primary, #ebeef5);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chat-header h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary, #303133);
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-title-refresh-btn {
  position: relative;
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 999px;
  background:
    linear-gradient(var(--bg-primary, #fff), var(--bg-primary, #fff)) padding-box,
    linear-gradient(135deg, rgba(59, 130, 246, 0.24), rgba(16, 185, 129, 0.18)) border-box;
  color: var(--text-secondary, #64748b);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
  cursor: pointer;
  transition: color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.header-title-refresh-btn::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  opacity: 0;
  box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.28);
  transition: opacity 0.2s ease;
}

.header-title-refresh-btn:hover {
  transform: translateY(-1px);
  color: var(--text-primary, #334155);
  background:
    linear-gradient(var(--bg-primary, #fff), var(--bg-primary, #fff)) padding-box,
    linear-gradient(135deg, rgba(59, 130, 246, 0.42), rgba(16, 185, 129, 0.3)) border-box;
  box-shadow: 0 6px 14px rgba(59, 130, 246, 0.14);
}

.header-title-refresh-btn:hover::after {
  opacity: 1;
}

.header-title-refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.header-title-refresh-btn:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px rgba(59, 130, 246, 0.2),
    0 4px 12px rgba(59, 130, 246, 0.16);
}

.header-title-refresh-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.96);
}

.header-title-refresh-icon {
  transition: transform 0.2s ease;
}

.header-title-refresh-btn:hover .header-title-refresh-icon {
  transform: rotate(-12deg);
}

.header-title-refresh-icon.is-spinning {
  animation: title-refresh-spin 0.88s linear infinite;
}

.header-title-refresh-btn.is-regenerating {
  color: var(--el-color-primary);
  background:
    linear-gradient(var(--bg-primary, #fff), var(--bg-primary, #fff)) padding-box,
    linear-gradient(135deg, rgba(59, 130, 246, 0.62), rgba(14, 165, 233, 0.44)) border-box;
  box-shadow:
    0 0 0 1px rgba(59, 130, 246, 0.2),
    0 8px 18px rgba(59, 130, 246, 0.2);
  animation: title-refresh-breath 1.6s ease-in-out infinite;
}

.header-title-refresh-btn.is-regenerating::after {
  opacity: 1;
  animation: title-refresh-ring 1.6s ease-out infinite;
}

@keyframes title-refresh-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes title-refresh-breath {
  0%,
  100% {
    transform: translateY(0);
    box-shadow:
      0 0 0 1px rgba(59, 130, 246, 0.2),
      0 6px 14px rgba(59, 130, 246, 0.15);
  }
  50% {
    transform: translateY(-1px);
    box-shadow:
      0 0 0 1px rgba(59, 130, 246, 0.28),
      0 10px 20px rgba(59, 130, 246, 0.24);
  }
}

@keyframes title-refresh-ring {
  0% {
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.35);
  }
  75% {
    box-shadow: 0 0 0 5px rgba(59, 130, 246, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0);
  }
}

.header-actions {
  display: flex;
  gap: 4px;
}

.header-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted, #94a3b8);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.header-action-btn:hover {
  background: var(--bg-hover, rgba(0, 0, 0, 0.04));
  color: var(--text-primary, #1e293b);
}

.header-action-btn:active {
  transform: scale(0.95);
}

.header-action-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.header-action-btn:disabled:hover {
  background: transparent;
  color: var(--text-muted, #94a3b8);
}

.header-action-btn:disabled:active {
  transform: none;
}

.header-action-btn.rated {
  color: #f59e0b;
}

.header-action-btn.rated:hover {
  color: #d97706;
}
</style>
