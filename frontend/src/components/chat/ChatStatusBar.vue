<template>
  <div
    v-if="visible"
    class="chat-status-bar"
    :class="[`is-${tone}`, { 'is-generating': isGenerating }]"
  >
    <div class="chat-status-bar__main">
      <span class="chat-status-bar__dot" />
      <span class="chat-status-bar__text">{{ title }}</span>
      <span v-if="detail" class="chat-status-bar__detail">{{ detail }}</span>
    </div>
    <div v-if="showActions" class="chat-status-bar__actions">
      <button
        v-if="canRetry"
        type="button"
        class="chat-status-bar__btn"
        @click="emit('retry')"
      >
        重试本轮
      </button>
      <button
        v-if="canRefresh"
        type="button"
        class="chat-status-bar__btn"
        @click="emit('refresh')"
      >
        刷新会话
      </button>
      <button
        v-if="canViewDetails"
        type="button"
        class="chat-status-bar__btn"
        @click="emit('details')"
      >
        查看错误详情
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ConversationExecutionState, ActionTerminalReason } from '@/types/chatExecution'
import type { LiveExecutionState } from '@/types/chat'
import { resolveConversationStatusSignal } from '@/utils/chatConversationStatus'

const props = withDefaults(defineProps<{
  state?: ConversationExecutionState | null
  pollingHealth?: 'healthy' | 'retrying' | 'degraded'
  lastTerminalReason?: ActionTerminalReason | null
  lastErrorMessage?: string | null
  liveExecution?: LiveExecutionState | null
}>(), {
  state: null,
  pollingHealth: 'healthy',
  lastTerminalReason: null,
  lastErrorMessage: null,
  liveExecution: null,
})

const emit = defineEmits<{
  (e: 'retry'): void
  (e: 'refresh'): void
  (e: 'details'): void
}>()

const title = computed(() => {
  if (props.state === 'waiting_skill_confirmation') return '待确认'
  if (props.state === 'cancelling') return '正在停止'
  if (props.state === 'streaming' || props.state === 'preparing') return '生成中'
  if (props.lastTerminalReason === 'cancelled' || props.lastTerminalReason === 'user_stop') return '已取消'
  if (props.lastTerminalReason === 'error' || props.lastTerminalReason === 'throw') return '已失败'
  if (props.pollingHealth === 'degraded') return '同步异常，可重试'
  if (props.pollingHealth === 'retrying') return '重试中'
  if (props.lastTerminalReason === 'stream_disconnected') return '连接中断'
  return ''
})

const detail = computed(() => {
  if ((props.state === 'streaming' || props.state === 'preparing') && props.liveExecution?.stage_detail) {
    return props.liveExecution.stage_detail
  }
  if (props.state === 'waiting_skill_confirmation' && props.liveExecution?.stage_detail) {
    return props.liveExecution.stage_detail
  }
  if (props.lastTerminalReason === 'cancelled' || props.lastTerminalReason === 'user_stop') {
    return '本轮对话已停止，可重新发送。'
  }
  if (props.lastTerminalReason === 'stream_disconnected') {
    return props.lastErrorMessage || '流式连接已断开，可刷新后继续。'
  }
  if (props.lastTerminalReason === 'error' || props.lastTerminalReason === 'throw') {
    return props.lastErrorMessage || '生成失败，请重试。'
  }
  if (props.pollingHealth === 'degraded') {
    return props.lastErrorMessage || '后台同步多次失败，请手动恢复。'
  }
  return ''
})

const tone = computed(() => {
  const signal = resolveConversationStatusSignal({
    executionState: props.state,
    executionSnapshot: {
      state: props.state ?? 'idle',
      actionType: null,
      streamSessionId: null,
      startedAt: null,
      updatedAt: Date.now(),
      lastTerminalReason: props.lastTerminalReason,
      lastErrorMessage: props.lastErrorMessage,
      lastDisconnectedAt: null,
      resumeAttemptCount: 0,
    },
    isGenerating: props.state === 'streaming' || props.state === 'preparing',
    pollingHealth: props.pollingHealth,
    isCurrentConversation: true,
  })
  return signal?.tone ?? 'primary'
})

const visible = computed(() => Boolean(title.value))
const isGenerating = computed(() => props.state === 'streaming' || props.state === 'preparing')
const canRetry = computed(() =>
  props.lastTerminalReason === 'stream_disconnected'
  || props.lastTerminalReason === 'error'
  || props.lastTerminalReason === 'throw'
  || props.pollingHealth === 'degraded')
const canRefresh = computed(() =>
  props.pollingHealth !== 'healthy'
  || props.lastTerminalReason === 'stream_disconnected'
  || props.lastTerminalReason === 'error'
  || props.lastTerminalReason === 'throw')
const canViewDetails = computed(() => {
  if (!props.lastErrorMessage) return false
  return (
    props.pollingHealth === 'degraded'
    || props.lastTerminalReason === 'stream_disconnected'
    || props.lastTerminalReason === 'error'
    || props.lastTerminalReason === 'throw'
  )
})
const showActions = computed(() => canRetry.value || canRefresh.value || canViewDetails.value)
</script>

<style scoped>
.chat-status-bar {
  margin: 8px 16px 0;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.26);
  background: rgba(248, 250, 252, 0.9);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.chat-status-bar__main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.chat-status-bar__dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #3b82f6;
  flex: 0 0 8px;
}

.chat-status-bar__text {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
  white-space: nowrap;
}

.chat-status-bar__detail {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-status-bar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-status-bar__btn {
  height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: rgba(255, 255, 255, 0.9);
  color: var(--text-secondary, #475569);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.chat-status-bar__btn:hover {
  border-color: rgba(59, 130, 246, 0.32);
  color: var(--text-primary, #0f172a);
}

.chat-status-bar.is-warning {
  border-color: rgba(245, 158, 11, 0.28);
  background: rgba(255, 251, 235, 0.9);
}

.chat-status-bar.is-warning .chat-status-bar__dot {
  background: #f59e0b;
}

.chat-status-bar.is-info {
  border-color: rgba(59, 130, 246, 0.28);
  background: rgba(239, 246, 255, 0.9);
}

.chat-status-bar.is-info .chat-status-bar__dot {
  background: #3b82f6;
}

.chat-status-bar.is-danger {
  border-color: rgba(248, 113, 113, 0.32);
  background: rgba(254, 242, 242, 0.9);
}

.chat-status-bar.is-danger .chat-status-bar__dot {
  background: #ef4444;
}

.chat-status-bar.is-neutral {
  border-color: rgba(148, 163, 184, 0.32);
  background: rgba(248, 250, 252, 0.95);
}

.chat-status-bar.is-neutral .chat-status-bar__dot {
  background: #64748b;
}

.chat-status-bar.is-success {
  border-color: rgba(34, 197, 94, 0.28);
  background: rgba(240, 253, 244, 0.9);
}

.chat-status-bar.is-success .chat-status-bar__dot {
  background: #22c55e;
}

.chat-status-bar.is-success.is-generating .chat-status-bar__dot {
  animation: dot-breathing 2.6s ease-in-out infinite;
  will-change: transform, box-shadow, opacity;
}

@keyframes dot-breathing {
  0%,
  100% {
    transform: scale(0.92);
    opacity: 0.7;
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.1);
  }
  50% {
    transform: scale(1.12);
    opacity: 1;
    box-shadow: 0 0 0 6px rgba(34, 197, 94, 0.2);
  }
}

@media (max-width: 900px) {
  .chat-status-bar {
    margin: 8px 12px 0;
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
