<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { fetchAuditConversations, type AuditConversationItem } from '@/api/adminAudit'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const list = ref<AuditConversationItem[]>([])
const total = ref(0)

const filters = reactive({
  user_id: undefined as number | undefined,
  model_name: '',
  is_abnormal: undefined as boolean | undefined,
  mcp_tool: '',
})

const pagination = reactive({
  page: 1,
  page_size: 20,
})

async function loadList() {
  loading.value = true
  try {
    const res = await fetchAuditConversations({
      page: pagination.page,
      page_size: pagination.page_size,
      user_id: filters.user_id,
      model_name: filters.model_name || undefined,
      is_abnormal: filters.is_abnormal,
      mcp_tool: filters.mcp_tool || undefined,
    })
    list.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.user_id = undefined
  filters.model_name = ''
  filters.is_abnormal = undefined
  filters.mcp_tool = ''
  pagination.page = 1
  loadList()
}

function goDetail(row: AuditConversationItem) {
  router.push(`/admin/audit/conversations/${row.conversation_id}`)
}

function openRawConversation(row: AuditConversationItem) {
  const target = router.resolve({
    path: `/chat/${row.conversation_id}`,
    query: { admin_view: '1' },
  })
  window.open(target.href, '_blank')
}

onMounted(() => {
  if (route.query.is_abnormal === '1') {
    filters.is_abnormal = true
  }
  loadList()
})
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="page-header">
      <h2>会话管理</h2>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form inline>
        <el-form-item label="用户 ID">
          <el-input-number v-model="filters.user_id" :min="1" :controls="false" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="filters.model_name" placeholder="如 deepseek-chat" clearable />
        </el-form-item>
        <el-form-item label="异常状态">
          <el-select v-model="filters.is_abnormal" clearable placeholder="全部" style="width: 140px">
            <el-option :value="true" label="异常" />
            <el-option :value="false" label="正常" />
          </el-select>
        </el-form-item>
        <el-form-item label="MCP 工具">
          <el-input v-model="filters.mcp_tool" placeholder="工具名关键词" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="pagination.page = 1; loadList()">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="list" stripe>
        <el-table-column prop="conversation_id" label="会话 ID" width="120" />
        <el-table-column prop="conversation_title" label="会话名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="latest_message_preview" label="最近消息摘要" min-width="280" show-overflow-tooltip />
        <el-table-column prop="user_name" label="用户" min-width="140" />
        <el-table-column prop="model_name" label="模型" min-width="180" />
        <el-table-column prop="round_count" label="轮次" width="80" />
        <el-table-column prop="trace_count" label="Trace" width="90" />
        <el-table-column prop="created_at" label="创建时间" min-width="180" />
        <el-table-column prop="last_activity_at" label="最近活跃时间" min-width="180" />
        <el-table-column label="异常" width="140">
          <template #default="{ row }">
            <el-tag :type="row.is_abnormal ? 'danger' : 'success'">
              {{ row.is_abnormal ? '异常' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常类型" min-width="220">
          <template #default="{ row }">
            <el-space wrap>
              <el-tag
                v-for="item in row.abnormal_types"
                :key="item"
                type="danger"
                effect="plain"
              >
                {{ item }}
              </el-tag>
              <span v-if="!row.abnormal_types.length">-</span>
            </el-space>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="goDetail(row)">会话详情</el-button>
            <el-button type="warning" link @click="openRawConversation(row)">原始会话</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @change="loadList"
        />
      </div>
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
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
}

.filter-card {
  border: 1px solid var(--border-primary, #e5e7eb);
}

.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
