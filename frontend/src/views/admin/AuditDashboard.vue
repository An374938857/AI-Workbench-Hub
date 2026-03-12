<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchAuditMetrics, type AuditMetricsOverview } from '@/api/adminAudit'

const router = useRouter()
const loading = ref(false)
const window = ref<'day' | 'week' | 'month'>('day')
const metrics = ref<AuditMetricsOverview>({
  window: 'day',
  total_traces: 0,
  abnormal_traces: 0,
  abnormal_ratio: 0,
  traceability_coverage: 0,
  replay_success_rate: 0,
  abnormal_distribution: [],
})

const cards = computed(() => [
  { title: '异常会话', value: metrics.value.abnormal_traces },
  { title: '总 Trace', value: metrics.value.total_traces },
  { title: '可追溯覆盖率', value: `${(metrics.value.traceability_coverage * 100).toFixed(1)}%` },
  { title: '回放成功率', value: `${(metrics.value.replay_success_rate * 100).toFixed(1)}%` },
])

async function loadMetrics() {
  loading.value = true
  try {
    const res = await fetchAuditMetrics(window.value)
    metrics.value = res.data
  } finally {
    loading.value = false
  }
}

function drillAbnormal() {
  router.push('/admin/audit/conversations?is_abnormal=1')
}

onMounted(loadMetrics)
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="page-header">
      <div>
        <h2>异常监控</h2>
        <p>异常趋势、覆盖率、回放成功率（仅超级管理员可见）</p>
      </div>
      <el-space>
        <el-radio-group v-model="window" @change="loadMetrics">
          <el-radio-button value="day">日</el-radio-button>
          <el-radio-button value="week">周</el-radio-button>
          <el-radio-button value="month">月</el-radio-button>
        </el-radio-group>
        <el-button type="primary" @click="drillAbnormal">下钻异常会话</el-button>
      </el-space>
    </div>

    <div class="cards">
      <el-card v-for="item in cards" :key="item.title" shadow="never" class="metric-card">
        <div class="metric-title">{{ item.title }}</div>
        <div class="metric-value">{{ item.value }}</div>
      </el-card>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span>异常类型分布</span>
          <el-button link type="primary" @click="drillAbnormal">查看异常明细</el-button>
        </div>
      </template>
      <el-table :data="metrics.abnormal_distribution" stripe>
        <el-table-column prop="type" label="异常类型" min-width="220" />
        <el-table-column prop="count" label="次数" width="120" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-header h2 {
  margin: 0 0 6px;
}

.page-header p {
  margin: 0;
  color: var(--text-secondary, #6b7280);
}

.cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  border: 1px solid var(--border-primary, #e5e7eb);
}

.metric-title {
  color: var(--text-secondary, #6b7280);
  font-size: 13px;
}

.metric-value {
  margin-top: 6px;
  font-size: 24px;
  font-weight: 700;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

@media (max-width: 1200px) {
  .cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
