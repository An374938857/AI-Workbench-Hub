<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  emptyMode: 'none' | 'sticky'
  selectedCount: number
  isGenerating: boolean
  clearDisabled: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (event: 'adjust'): void
  (event: 'clear'): void
}>()

const statusType = computed(() => {
  if (props.emptyMode === 'sticky') return 'warning'
  if (props.selectedCount > 0) return 'success'
  return 'info'
})

const statusText = computed(() => {
  if (props.emptyMode === 'sticky') return '持续不引用'
  if (props.selectedCount > 0) return `默认引用 ${props.selectedCount} 个文件`
  return '未设置默认引用'
})

const tipText = computed(() => {
  if (props.emptyMode === 'sticky') {
    return '后续轮次不会自动弹出推荐，可手动恢复。'
  }
  return '发送前会根据问题智能推荐，并支持手动调整。'
})
</script>

<template>
  <div class="reference-status-bar reference-status-bar--composer">
    <div class="reference-status-main">
      <el-tag size="small" :type="statusType">
        {{ statusText }}
      </el-tag>
      <span class="reference-status-tip">{{ tipText }}</span>
    </div>
    <div class="reference-status-actions">
      <button
        type="button"
        class="reference-action-btn"
        :disabled="isGenerating"
        @click="emit('adjust')"
      >
        调整引用
      </button>
      <button
        type="button"
        class="reference-action-btn is-danger"
        :disabled="clearDisabled"
        @click="emit('clear')"
      >
        清空
      </button>
    </div>
  </div>
</template>

<style scoped>
.reference-status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 20px 12px;
  padding: 10px 12px;
  border: 1px solid var(--border-primary, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  background: var(--bg-card, #ffffff);
}

.reference-status-bar--composer {
  margin: 0;
  padding: 7px 10px;
  border-radius: 14px 14px 0 0;
  border-bottom: none;
  background: color-mix(in srgb, var(--bg-card, #ffffff) 92%, var(--bg-page, #f8fafc) 8%);
}

.reference-status-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.reference-status-tip {
  font-size: 12px;
  color: var(--text-muted, #64748b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.reference-status-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.reference-action-btn {
  min-width: 78px;
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--border-primary, rgba(15, 23, 42, 0.12));
  border-radius: 999px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.98) 100%);
  color: var(--text-secondary, #475569);
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  letter-spacing: 0.01em;
  cursor: pointer;
  transition: all 0.18s ease;
}

.reference-action-btn:hover {
  border-color: rgba(59, 130, 246, 0.35);
  color: #1d4ed8;
  box-shadow: 0 8px 16px rgba(15, 23, 42, 0.08);
  transform: translateY(-1px);
}

.reference-action-btn:active {
  transform: translateY(0);
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.08);
}

.reference-action-btn.is-danger {
  border-color: rgba(239, 68, 68, 0.22);
  color: #dc2626;
  background: linear-gradient(180deg, #fff8f8 0%, #fff3f3 100%);
}

.reference-action-btn.is-danger:hover {
  border-color: rgba(239, 68, 68, 0.4);
  color: #b91c1c;
  box-shadow: 0 8px 16px rgba(220, 38, 38, 0.12);
}

.reference-action-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.reference-status-bar--composer .reference-action-btn {
  min-width: 74px;
  height: 28px;
  padding: 0 10px;
}

.reference-status-bar--composer .reference-status-tip {
  color: color-mix(in srgb, var(--text-muted, #64748b) 86%, #94a3b8 14%);
}

html.dark .reference-status-bar {
  border-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 78%, #4b5563 22%);
  background: linear-gradient(180deg, rgba(23, 27, 34, 0.96) 0%, rgba(18, 21, 27, 0.98) 100%);
}

html.dark .reference-status-bar--composer {
  border-bottom: none;
  background: linear-gradient(180deg, rgba(27, 31, 38, 0.94) 0%, rgba(20, 23, 29, 0.96) 100%);
}

html.dark .reference-action-btn {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

html.dark .reference-action-btn:hover {
  border-color: rgba(148, 163, 184, 0.24);
  background: rgba(148, 163, 184, 0.12);
  color: #f8fafc;
  box-shadow: none;
}

html.dark .reference-action-btn.is-danger {
  border-color: rgba(248, 113, 113, 0.38);
  color: #fecaca;
  background: linear-gradient(180deg, rgba(127, 29, 29, 0.35) 0%, rgba(69, 10, 10, 0.45) 100%);
}

html.dark .reference-action-btn.is-danger:hover {
  border-color: rgba(252, 165, 165, 0.55);
  color: #fee2e2;
  box-shadow: 0 10px 18px rgba(127, 29, 29, 0.42);
}

@media (max-width: 640px) {
  .reference-status-bar--composer {
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .reference-status-bar--composer .reference-status-main {
    width: 100%;
  }

  .reference-status-bar--composer .reference-status-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
