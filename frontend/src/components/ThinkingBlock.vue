<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'

const props = defineProps<{
  content: string
  isThinking: boolean
}>()

const expanded = ref(props.isThinking)
const contentRef = ref<HTMLElement>()

// 思考完毕后自动折叠
watch(() => props.isThinking, (val) => {
  if (!val) expanded.value = false
})

// 思考中自动滚到底部
watch(() => props.content, () => {
  if (props.isThinking && expanded.value) {
    nextTick(() => {
      const el = contentRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }
})

function toggle() {
  expanded.value = !expanded.value
}
</script>

<template>
  <div class="thinking-block" :class="{ 'is-thinking': isThinking }" @click="toggle">
    <div class="tb-header">
      <span class="tb-icon" :class="{ 'tb-loading': isThinking }">💭</span>
      <span class="tb-label">{{ isThinking ? '思考中...' : '已完成思考' }}</span>
      <span class="tb-toggle">{{ expanded ? '▾ 收起' : '▸ 展开' }}</span>
    </div>
    <div v-if="expanded" ref="contentRef" class="tb-content">
      <pre class="tb-text">{{ content }}</pre>
    </div>
  </div>
</template>

<style scoped>
.thinking-block {
  border: 1px solid var(--border-primary, #e4e7ed);
  border-radius: 8px;
  font-size: 13px;
  background: var(--bg-code, #fafafa);
  cursor: pointer;
  transition: border-color 0.2s;
  overflow: hidden;
  margin-bottom: 10px;
}

.thinking-block:hover {
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.thinking-block.is-thinking {
  border-color: #e6a23c60;
  background: var(--bg-code, #fdf6ec);
}

.tb-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
}

.tb-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.tb-loading {
  animation: pulse 1.2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.tb-label {
  color: var(--text-secondary, #606266);
  flex: 1;
}

.tb-toggle {
  font-size: 12px;
  color: var(--text-muted, #909399);
  flex-shrink: 0;
}

.tb-content {
  border-top: 1px solid var(--border-primary, #e4e7ed);
  padding: 10px 12px;
  max-height: 300px;
  overflow-y: auto;
}

.tb-text {
  margin: 0;
  font-family: inherit;
  font-size: 13px;
  color: var(--text-secondary, #606266);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}
</style>
