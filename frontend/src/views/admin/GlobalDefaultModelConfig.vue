<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getModelProviderList, setDefaultModel } from '@/api/admin/modelProviders'

interface ModelItem {
  model_name: string
  is_enabled: boolean
  is_default?: boolean
}

interface ProviderItem {
  id: number
  provider_name: string
  is_enabled: boolean
  models: ModelItem[]
}

interface GroupedSelectOption {
  label: string
  value: string
}

interface GroupedSelectItem {
  providerId: number
  providerName: string
  options: GroupedSelectOption[]
}

const loading = ref(false)
const providers = ref<ProviderItem[]>([])
const globalDefaultModelValue = ref<string | null>(null)

const globalDefaultModelOptions = computed<GroupedSelectItem[]>(() => {
  const grouped = new Map<number, GroupedSelectItem>()
  for (const provider of providers.value) {
    if (!provider.is_enabled) continue
    const options = provider.models
      .filter((model) => model.is_enabled)
      .map((model) => ({
        label: model.model_name,
        value: JSON.stringify([provider.id, model.model_name]),
      }))

    if (options.length === 0) continue
    grouped.set(provider.id, {
      providerId: provider.id,
      providerName: provider.provider_name || 'Provider',
      options,
    })
  }
  return Array.from(grouped.values())
})

function syncGlobalDefaultModelSelection() {
  for (const provider of providers.value) {
    const defaultModel = provider.models.find((model) => model.is_default)
    if (defaultModel) {
      globalDefaultModelValue.value = JSON.stringify([provider.id, defaultModel.model_name])
      return
    }
  }
  globalDefaultModelValue.value = null
}

async function fetchProviders() {
  loading.value = true
  try {
    const res: any = await getModelProviderList()
    providers.value = Array.isArray(res?.data) ? res.data : []
    syncGlobalDefaultModelSelection()
  } finally {
    loading.value = false
  }
}

async function handleSetGlobalDefaultModel(value: string) {
  let providerId = 0
  let modelName = ''
  try {
    const parsed = JSON.parse(value)
    providerId = Number(parsed?.[0])
    modelName = String(parsed?.[1] || '')
  } catch {
    ElMessage.error('默认模型参数无效')
    return
  }

  if (!providerId || !modelName) {
    ElMessage.error('默认模型参数无效')
    return
  }

  await setDefaultModel(providerId, modelName)
  ElMessage.success(`已将 ${modelName} 设为全局默认模型`)
  await fetchProviders()
}

onMounted(fetchProviders)
</script>

<template>
  <el-card shadow="never" class="global-default-card" v-loading="loading">
    <template #header>
      <div class="card-header">
        <div class="card-title">
          <span class="provider-name">全局默认模型配置</span>
        </div>
      </div>
    </template>
    <div class="global-default-model-row">
      <div class="config-label">对话全局默认模型</div>
      <el-select
        v-model="globalDefaultModelValue"
        placeholder="请选择全局默认模型"
        filterable
        style="width: 100%"
        @change="handleSetGlobalDefaultModel"
      >
        <el-option-group
          v-for="provider in globalDefaultModelOptions"
          :key="provider.providerId"
          :label="provider.providerName"
        >
          <el-option
            v-for="model in provider.options"
            :key="model.value"
            :label="model.label"
            :value="model.value"
          />
        </el-option-group>
      </el-select>
    </div>
  </el-card>
</template>

<style scoped>
.global-default-card {
  margin-bottom: 12px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.provider-name {
  font-size: 16px;
  font-weight: 600;
}

.global-default-model-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-label {
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-secondary, #606266);
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
}
</style>
