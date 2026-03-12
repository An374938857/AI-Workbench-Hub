<script setup lang="ts">
defineProps<{
  mcp: {
    id: number
    name: string
    description: string
    tool_count: number
    health_status: string
  }
  testing?: boolean
}>()

const emit = defineEmits<{
  click: [id: number]
  test: [id: number]
}>()

function onTest(e: Event) {
  e.stopPropagation()
  emit('test', 0)
}

function healthColor(status: string) {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    healthy: 'success',
    degraded: 'warning',
    circuit_open: 'danger',
    unknown: 'info',
  }
  return map[status] || 'info'
}

function healthLabel(status: string) {
  const map: Record<string, string> = {
    healthy: '正常',
    degraded: '降级',
    circuit_open: '熔断中',
    unknown: '未知',
  }
  return map[status] || '未知'
}
</script>

<template>
  <div class="mcp-card" @click="$emit('click', mcp.id)">
    <div class="mcp-icon">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
      </svg>
    </div>
    <div class="mcp-body">
      <div class="mcp-header">
        <h3 class="mcp-title">{{ mcp.name }}</h3>
        <el-tag size="small" :type="healthColor(mcp.health_status)">
          {{ healthLabel(mcp.health_status) }}
        </el-tag>
      </div>
      <p class="mcp-desc">{{ mcp.description }}</p>
      <div class="mcp-meta">
        <div class="mcp-meta-tags">
          <el-tag size="small" type="info">{{ mcp.tool_count }} 个工具</el-tag>
        </div>
        <el-button size="small" :loading="testing" @click="onTest">测试连接</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mcp-card {
  background: var(--bg-card, #fff);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 16px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.25s;
  display: flex;
  gap: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 2px 8px rgba(0, 0, 0, 0.02);
  margin-bottom: 2px; /* 预留 hover 空间 */
}

.mcp-card:hover {
  border-color: #409eff;
  box-shadow: 0 4px 20px rgba(64, 158, 255, 0.14), 0 1px 3px rgba(0, 0, 0, 0.04);
  transform: translateY(-2px);
  margin-bottom: 0; /* 补偿 transform 偏移 */
}

.mcp-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(135deg, #e0f2fe, #f0f4ff);
  color: #3b82f6;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  flex-shrink: 0;
}

html.dark .mcp-icon {
  background: linear-gradient(135deg, rgba(59,130,246,0.15), rgba(99,102,241,0.12));
  color: #60a5fa;
}

.mcp-body {
  flex: 1;
  min-width: 0;
}

.mcp-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  margin: 0;
}

.mcp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.mcp-desc {
  font-size: 13px;
  color: var(--text-muted, #909399);
  margin: 0 0 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.5;
}

.mcp-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.mcp-meta-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
