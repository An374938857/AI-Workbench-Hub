<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import JsonViewer from '@/components/JsonViewer.vue'
import {
  fetchRoundDetail,
  createAuditExportTask,
  fetchAuditExportTask,
  downloadAuditExport,
  type AuditEventDetail,
} from '@/api/adminAudit'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const exporting = ref(false)
const requestEvents = ref<AuditEventDetail[]>([])
const responseEvents = ref<AuditEventDetail[]>([])
const toolChainEvents = ref<AuditEventDetail[]>([])
const allEvents = ref<AuditEventDetail[]>([])

const conversationId = computed(() => Number(route.params.id))
const roundNo = computed(() => Number(route.params.roundNo))

const verifyFailedCount = computed(() => allEvents.value.filter((item) => item.verify_status === 'failed').length)

async function loadDetail() {
  loading.value = true
  try {
    const res = await fetchRoundDetail(conversationId.value, roundNo.value)
    requestEvents.value = res.data.request
    responseEvents.value = res.data.response
    toolChainEvents.value = res.data.tool_chain
    allEvents.value = res.data.events
  } finally {
    loading.value = false
  }
}

async function exportRound(format: 'ndjson' | 'json_array') {
  exporting.value = true
  try {
    const createRes = await createAuditExportTask({
      format,
      filters: {
        page_size: 5000,
      },
    })
    const taskId = createRes.data.task_id

    for (let i = 0; i < 20; i += 1) {
      const statusRes = await fetchAuditExportTask(taskId)
      const status = statusRes.data.status
      if (status === 'completed') {
        const blobRes = await downloadAuditExport(taskId)
        const blob = blobRes.data as Blob
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `audit-round-${conversationId.value}-${roundNo.value}.${format === 'ndjson' ? 'ndjson' : 'json'}`
        a.click()
        URL.revokeObjectURL(url)
        ElMessage.success('导出成功')
        return
      }
      if (status === 'failed') {
        ElMessage.error(statusRes.data.error || '导出失败')
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 1000))
    }

    ElMessage.warning('导出处理中，请稍后重试')
  } finally {
    exporting.value = false
  }
}

function combinePayload(items: AuditEventDetail[]): string {
  if (!items.length) {
    return '{}'
  }
  const firstItem = items[0]
  if (items.length === 1 && firstItem) {
    return firstItem.payload_raw
  }
  return JSON.stringify(
    items.map((item) => {
      try {
        return JSON.parse(item.payload_raw)
      } catch {
        return item.payload_raw
      }
    }),
    null,
    2,
  )
}

onMounted(loadDetail)
</script>

<template>
  <div class="page" v-loading="loading || exporting">
    <div class="page-header">
      <div>
        <h2>原始 JSON 详情</h2>
        <p>会话 #{{ conversationId }} / 轮次 #{{ roundNo }}</p>
      </div>
      <el-space>
        <el-button @click="router.push(`/admin/audit/conversations/${conversationId}`)">返回会话</el-button>
        <el-button type="primary" plain @click="exportRound('ndjson')">导出 NDJSON</el-button>
        <el-button type="primary" @click="exportRound('json_array')">导出 JSON 数组</el-button>
      </el-space>
    </div>

    <el-alert
      v-if="verifyFailedCount > 0"
      :title="`发现 ${verifyFailedCount} 条 hash 校验失败记录`"
      type="error"
      show-icon
      :closable="false"
    />

    <div class="grid">
      <JsonViewer title="请求原始 JSON" :raw="combinePayload(requestEvents)" filename="request.json" />
      <JsonViewer title="响应原始 JSON" :raw="combinePayload(responseEvents)" filename="response.json" />
    </div>

    <JsonViewer title="工具调用链路" :raw="combinePayload(toolChainEvents)" filename="tool-chain.json" />

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span>Trace 元信息与事件序列</span>
        </div>
      </template>
      <el-table :data="allEvents" stripe>
        <el-table-column prop="trace_id" label="trace_id" min-width="220" />
        <el-table-column prop="event_type" label="事件类型" width="180" />
        <el-table-column prop="event_time" label="时间" min-width="180" />
        <el-table-column label="校验" width="120">
          <template #default="{ row }">
            <el-tag :type="row.verify_status === 'failed' ? 'danger' : 'success'">{{ row.verify_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error_message" label="错误信息" min-width="220" />
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
  justify-content: space-between;
  align-items: flex-start;
}

.page-header h2 {
  margin: 0 0 6px;
}

.page-header p {
  margin: 0;
  color: var(--text-secondary, #6b7280);
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 1200px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
