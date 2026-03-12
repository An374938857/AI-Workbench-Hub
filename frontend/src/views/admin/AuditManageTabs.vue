<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuditConversationList from '@/views/admin/AuditConversationList.vue'
import AuditDashboard from '@/views/admin/AuditDashboard.vue'

type AuditTabKey = 'conversations' | 'monitor'

const route = useRoute()
const router = useRouter()

const activeTab = computed<AuditTabKey>({
  get() {
    const tab = route.query.tab
    return tab === 'monitor' ? 'monitor' : 'conversations'
  },
  set(value) {
    const query = { ...route.query }
    if (value === 'conversations') {
      delete query.tab
    } else {
      query.tab = value
    }
    router.replace({ path: '/admin/audit/conversations', query })
  },
})
</script>

<template>
  <div class="audit-manage-tabs">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="会话管理" name="conversations">
        <AuditConversationList />
      </el-tab-pane>
      <el-tab-pane label="异常监控" name="monitor">
        <AuditDashboard />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.audit-manage-tabs {
  width: 100%;
}
</style>
