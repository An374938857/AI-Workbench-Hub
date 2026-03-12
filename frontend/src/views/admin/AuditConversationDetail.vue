<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchConversationTimeline, fetchAuditReplay, type AuditRoundSummary } from '@/api/adminAudit'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const timeline = ref<AuditRoundSummary[]>([])
const traceCount = ref(0)
const replayLoading = ref(false)
const replayEvents = ref(0)

const conversationId = computed(() => Number(route.params.id))

async function loadTimeline() {
  loading.value = true
  try {
    const res = await fetchConversationTimeline(conversationId.value)
    timeline.value = res.data.rounds
    traceCount.value = res.data.trace_count
  } finally {
    loading.value = false
  }
}

function goRound(roundNo: number) {
  router.push(`/admin/audit/conversations/${conversationId.value}/round/${roundNo}`)
}

async function replay(traceId: string) {
  replayLoading.value = true
  try {
    const res = await fetchAuditReplay(traceId)
    replayEvents.value = res.data.events.length
  } finally {
    replayLoading.value = false
  }
}

function formatDuration(seconds: number) {
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)}ms`
  }
  return `${seconds.toFixed(3)}s`
}

onMounted(loadTimeline)
</script>

<template>
  <div class="page" v-loading="loading || replayLoading">
    <div class="page-header">
      <div>
        <h2>会话详情 #{{ conversationId }}</h2>
        <p>Trace 数：{{ traceCount }}，支持只读回放</p>
      </div>
      <el-button @click="router.push('/admin/audit/conversations')">返回列表</el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="timeline" stripe>
        <el-table-column prop="round_no" label="轮次" width="80" />
        <el-table-column prop="event_count" label="事件数" width="100" />
        <el-table-column prop="start_time" label="开始时间" min-width="180" />
        <el-table-column prop="end_time" label="结束时间" min-width="180" />
        <el-table-column label="耗时" width="120">
          <template #default="{ row }">
            {{ formatDuration(row.duration_seconds) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.is_abnormal ? 'danger' : 'success'">{{ row.is_abnormal ? '异常' : '正常' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常类型" min-width="220">
          <template #default="{ row }">
            <el-space wrap>
              <el-tag v-for="item in row.abnormal_types" :key="item" type="danger" effect="plain">{{ item }}</el-tag>
              <span v-if="!row.abnormal_types.length">-</span>
            </el-space>
          </template>
        </el-table-column>
        <el-table-column label="trace_id" min-width="260">
          <template #default="{ row }">
            <el-space wrap>
              <el-tag v-for="traceId in row.trace_ids" :key="traceId" effect="plain">{{ traceId }}</el-tag>
            </el-space>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="goRound(row.round_no)">查看 JSON</el-button>
            <el-button
              v-if="row.trace_ids.length"
              link
              type="warning"
              @click="replay(row.trace_ids[0])"
            >
              回放
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-alert
      v-if="replayEvents"
      :title="`回放完成，已重建 ${replayEvents} 条事件（只读，不触发真实执行）`"
      type="success"
      show-icon
      :closable="false"
    />
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
  justify-content: space-between;
  align-items: center;
}

.page-header h2 {
  margin: 0 0 6px;
}

.page-header p {
  margin: 0;
  color: var(--text-secondary, #6b7280);
}
</style>
