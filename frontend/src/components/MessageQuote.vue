<script setup lang="ts">
import { computed } from 'vue'

interface QuotedMessage {
  id: number
  role: string
  content: string
  created_at: string
}

const props = defineProps<{
  messages: QuotedMessage[]
}>()

const emit = defineEmits<{
  remove: [messageId: number]
}>()

function truncateContent(content: string, maxLength: number = 50): string {
  if (content.length <= maxLength) return content
  return content.substring(0, maxLength) + '...'
}

function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', { 
    month: '2-digit', 
    day: '2-digit', 
    hour: '2-digit', 
    minute: '2-digit' 
  })
}
</script>

<template>
  <div v-if="messages.length > 0" class="message-quotes">
    <div class="quote-header">引用 {{ messages.length }} 条消息</div>
    <div class="quote-list">
      <div v-for="msg in messages" :key="msg.id" class="quote-item">
        <div class="quote-role">{{ msg.role === 'user' ? '用户' : 'AI' }}</div>
        <div class="quote-content">{{ truncateContent(msg.content) }}</div>
        <div class="quote-time">{{ formatTime(msg.created_at) }}</div>
        <el-button
          size="small"
          text
          class="quote-remove-btn"
          @click="emit('remove', msg.id)"
        >
          取消
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-quotes {
  margin-bottom: 12px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  border-left: 3px solid var(--el-color-primary);
}

.quote-header {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  font-weight: 500;
}

.quote-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.quote-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: var(--el-bg-color);
  border-radius: 6px;
  font-size: 13px;
}

.quote-role {
  flex-shrink: 0;
  padding: 2px 8px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.quote-content {
  flex: 1;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-time {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.quote-remove-btn {
  flex-shrink: 0;
  padding: 0 6px;
}
</style>
