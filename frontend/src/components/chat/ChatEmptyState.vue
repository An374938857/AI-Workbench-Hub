<script setup lang="ts">
const emit = defineEmits<{
  browse: []
}>()
</script>

<template>
  <div class="empty-state">
    <el-icon :size="48" color="#dcdfe6"><ChatDotRound /></el-icon>
    <h3>选择一个 AI 能力开始对话</h3>
    <p>从能力广场选择 Skill，或从左侧打开历史对话</p>
    <el-button type="primary" @click="emit('browse')">浏览能力广场</el-button>
  </div>
</template>

<style scoped>
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #909399;
}

.empty-state h3 {
  margin: 8px 0 0;
  color: #606266;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}
</style>
