<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GlobalDefaultModelConfig from '@/views/admin/GlobalDefaultModelConfig.vue'
import ModelProvider from '@/views/admin/ModelProvider.vue'
import RoutingRules from '@/views/admin/RoutingRules.vue'

type ModelTabKey = 'global-model-config' | 'routing-rules'

const route = useRoute()
const router = useRouter()

const activeTab = computed<ModelTabKey>({
  get() {
    const tab = route.query.tab
    return tab === 'routing-rules' ? 'routing-rules' : 'global-model-config'
  },
  set(value) {
    const query = { ...route.query }
    if (value === 'global-model-config') {
      delete query.tab
    } else {
      query.tab = value
    }
    router.replace({ path: '/admin/model-providers', query })
  },
})
</script>

<template>
  <div class="model-manage-tabs">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="模型配置" name="global-model-config">
        <ModelProvider />
      </el-tab-pane>
      <el-tab-pane label="路由规则" name="routing-rules">
        <GlobalDefaultModelConfig />
        <RoutingRules />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.model-manage-tabs {
  width: 100%;
}
</style>
