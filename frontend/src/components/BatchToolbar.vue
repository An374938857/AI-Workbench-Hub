<script setup lang="ts">
defineProps<{
  selectedCount: number
}>()

const emit = defineEmits<{
  delete: []
  export: []
  tag: [event: MouseEvent]
  cancel: []
}>()
</script>

<template>
  <Transition name="slide-up">
    <div v-if="selectedCount > 0" class="batch-toolbar">
      <span class="bt-count">已选 {{ selectedCount }} 项</span>
      <div class="bt-actions">
        <el-button size="small" type="danger" @click="emit('delete')">
          <el-icon><Delete /></el-icon> 删除
        </el-button>
        <el-button size="small" @click="emit('export')">
          <el-icon><Download /></el-icon> 导出
        </el-button>
        <el-button size="small" class="bt-tag-btn" @click="emit('tag', $event)">
          <el-icon><PriceTag /></el-icon> 打标签
        </el-button>
        <el-button size="small" text @click="emit('cancel')">取消选择</el-button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.batch-toolbar {
  position: absolute;
  bottom: 18px;
  left: calc(50% + 105px);
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-card, #ffffff);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.14);
  z-index: 100;
  width: max-content;
  max-width: none;
  white-space: nowrap;
}

.bt-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #475569);
  white-space: nowrap;
  padding: 0 2px;
}

.bt-actions {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
}

.bt-actions :deep(.el-button) {
  height: 32px;
  padding: 0 13px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.1px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.bt-actions :deep(.el-button:not(.is-text)) {
  border: 1px solid rgba(15, 23, 42, 0.1);
  background: rgba(255, 255, 255, 0.86);
}

.bt-actions :deep(.el-button .el-icon) {
  font-size: 14px;
}

.bt-actions :deep(.el-button--danger) {
  border-color: #ed4141;
  background: rgba(237, 65, 65, 0.08);
  color: #d93636;
}

.bt-actions :deep(.el-button--danger:hover) {
  background: rgba(237, 65, 65, 0.16);
}

.bt-actions :deep(.el-button.is-text) {
  color: #64748b;
  padding: 0 10px;
}

.bt-actions :deep(.el-button.is-text:hover) {
  background: rgba(100, 116, 139, 0.08);
  color: #475569;
}

html.dark .batch-toolbar {
  background: #1f2937;
  border-color: rgba(148, 163, 184, 0.2);
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.42);
}

html.dark .bt-count {
  color: #cbd5e1;
}

html.dark .bt-actions :deep(.el-button:not(.is-text)) {
  border-color: rgba(148, 163, 184, 0.2);
  background: rgba(255, 255, 255, 0.04);
  color: #e2e8f0;
}

html.dark .bt-actions :deep(.el-button--danger) {
  border-color: #ed4141;
  background: rgba(237, 65, 65, 0.2);
  color: #fecaca;
}

html.dark .bt-actions :deep(.el-button.is-text) {
  color: #94a3b8;
}

html.dark .bt-actions :deep(.el-button.is-text:hover) {
  background: rgba(148, 163, 184, 0.14);
  color: #cbd5e1;
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.22s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(14px);
}
</style>
