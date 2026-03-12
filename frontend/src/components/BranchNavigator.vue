<script setup lang="ts">
defineProps<{
  currentIndex: number
  totalCount: number
}>()

const emit = defineEmits<{
  prev: []
  next: []
}>()
</script>

<template>
  <div v-if="totalCount > 1" class="branch-nav">
    <button
      class="branch-btn"
      :disabled="currentIndex <= 0"
      @click.stop="emit('prev')"
    >&lt;</button>
    <span class="branch-label">{{ currentIndex + 1 }}/{{ totalCount }}</span>
    <button
      class="branch-btn"
      :disabled="currentIndex >= totalCount - 1"
      @click.stop="emit('next')"
    >&gt;</button>
  </div>
</template>

<style scoped>
.branch-nav {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  color: var(--text-muted, #909399);
}

.branch-btn {
  width: 20px;
  height: 20px;
  border: 1px solid var(--border-primary, #ebeef5);
  border-radius: 4px;
  background: var(--bg-card, #fff);
  color: var(--text-secondary, #606266);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  padding: 0;
  transition: all 0.2s;
}

.branch-btn:hover:not(:disabled) {
  color: #409eff;
  border-color: #409eff;
}

.branch-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.branch-label {
  min-width: 28px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
</style>
