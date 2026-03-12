<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { getAvailableModels } from '@/api/models'
import { switchConversationModel } from '@/api/conversations'

const TAG_LABELS: Record<string, string> = {
  reasoning: '推理', creative_writing: '创意写作', coding: '代码', data_analysis: '数据分析',
  fast_response: '快速响应', deep_thinking: '深度思考', multimodal: '多模态', long_context: '超长上下文',
}
const TAG_COLORS: Record<string, string> = {
  reasoning: '#409eff', creative_writing: '#e6a23c', coding: '#67c23a', data_analysis: '#9b59b6',
  fast_response: '#f56c6c', deep_thinking: '#3498db', multimodal: '#e74c3c', long_context: '#1abc9c',
}

const SPEED_LABELS: Record<string, string> = { fast: '响应快', medium: '响应中等', slow: '响应较慢' }
const COST_LABELS: Record<string, string> = { low: '低成本', medium: '中成本', high: '高成本' }

interface AvailableModel {
  model_name: string
  display_name: string
  context_window: number
  capability_tags: string[]
  speed_rating?: string | null
  cost_rating?: string | null
  description?: string | null
  max_output_tokens?: number | null
  is_recommended?: boolean
}

interface ProviderGroup {
  provider_id: number
  provider_name: string
  protocol_type: string
  models: AvailableModel[]
}

const props = defineProps<{
  conversationId: number | null
  currentProviderId?: number | null
  currentModelName?: string | null
}>()

const emit = defineEmits<{
  modelChanged: []
  modelSelected: [providerId: number, modelName: string]
}>()

const loading = ref(false)
const providers = ref<ProviderGroup[]>([])
const selected = ref<string | null>(null)

const modelOptions = computed(() => providers.value)

function makeValue(providerId: number, modelName: string) {
  return `${providerId}:${modelName}`
}

function parseValue(val: string | null): { providerId: number; modelName: string } | null {
  if (!val) return null
  const [pid, name] = val.split(':')
  const id = Number(pid)
  if (!id || !name) return null
  return { providerId: id, modelName: name }
}

async function fetchModels() {
  loading.value = true
  try {
    const res: any = await getAvailableModels(props.conversationId)
    providers.value = res.data?.providers || []
    // 根据当前对话绑定模型预选中
    if (props.currentProviderId && props.currentModelName) {
      selected.value = makeValue(props.currentProviderId, props.currentModelName)
    } else {
      // 优先恢复上次使用的模型
      let found = false
      const defaultProvider = providers.value.find((pr: any) => (pr.models || []).some((m: any) => m.is_default))
      const defaultModel = defaultProvider?.models?.find((m: any) => m.is_default)
      if (defaultProvider && defaultModel) {
        selected.value = makeValue(defaultProvider.provider_id, defaultModel.model_name)
        emit('modelSelected', defaultProvider.provider_id, defaultModel.model_name)
        found = true
      }

      if (!found) {
        try {
          const last = JSON.parse(localStorage.getItem('last_model') || 'null')
          if (last?.pid && last?.name) {
            const p = providers.value.find((pr: any) => pr.provider_id === last.pid)
            if (p?.models?.some((m: any) => m.model_name === last.name)) {
              selected.value = makeValue(last.pid, last.name)
              emit('modelSelected', last.pid, last.name)
              found = true
            }
          }
        } catch {}
      }

      const firstProvider = providers.value[0]
      const firstModel = firstProvider?.models?.[0]
      if (!found && firstProvider && firstModel) {
        selected.value = makeValue(firstProvider.provider_id, firstModel.model_name)
        emit('modelSelected', firstProvider.provider_id, firstModel.model_name)
      }
    }
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.currentProviderId, props.currentModelName],
  ([pid, name]) => {
    if (pid && name) {
      selected.value = makeValue(pid as number, name as string)
    }
  },
  { immediate: true },
)

async function handleChange(val: string | null) {
  const parsed = parseValue(val)
  if (!parsed) return
  
  // 如果没有对话ID，只触发选择事件，不调用API
  if (!props.conversationId) {
    emit('modelSelected', parsed.providerId, parsed.modelName)
    return
  }
  
  // 有对话ID时，调用切换模型API
  try {
    await switchConversationModel(props.conversationId, parsed.providerId, parsed.modelName)
    ElMessage.success('模型已切换')
    emit('modelChanged')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '切换模型失败')
  }
}

const popoverVisible = ref(false)

const currentLabel = computed(() => {
  const parsed = parseValue(selected.value)
  if (!parsed) return '选择模型'
  for (const p of providers.value) {
    const m = p.models.find(m => m.model_name === parsed.modelName && p.provider_id === parsed.providerId)
    if (m) return m.display_name || m.model_name
  }
  return parsed.modelName
})

function selectModel(providerId: number, model: AvailableModel) {
  const val = makeValue(providerId, model.model_name)
  selected.value = val
  popoverVisible.value = false
  handleChange(val)
}

onMounted(fetchModels)
</script>

<template>
  <el-popover
    v-model:visible="popoverVisible"
    placement="top-end"
    trigger="click"
    :width="320"
    :show-arrow="false"
    :offset="10"
    popper-class="model-popover"
  >
    <template #reference>
      <button type="button" class="model-trigger" :class="{ active: popoverVisible }">
        <span class="model-trigger-label">{{ currentLabel }}</span>
        <svg class="model-trigger-chevron" width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    </template>
    <div class="model-panel">
      <template v-for="(p, pi) in modelOptions" :key="p.provider_id">
        <div v-if="pi > 0" class="model-divider" />
        <div class="model-group-label">{{ p.provider_name }}</div>
        <div
          v-for="m in p.models"
          :key="`${p.provider_id}:${m.model_name}`"
          class="model-option"
          :class="{ active: selected === makeValue(p.provider_id, m.model_name) }"
          @click="selectModel(p.provider_id, m)"
        >
          <div class="model-option-left">
            <div class="model-option-name">
              {{ m.display_name || m.model_name }}
              <span v-if="m.is_recommended" class="model-rec">推荐</span>
            </div>
            <div v-if="m.capability_tags?.length || m.speed_rating" class="model-option-desc">
              <template v-for="(tag, i) in (m.capability_tags || []).slice(0, 3)" :key="tag">
                <span v-if="i > 0" class="model-option-dot">·</span>
                {{ TAG_LABELS[tag] || tag }}
              </template>
              <template v-if="m.speed_rating">
                <span v-if="m.capability_tags?.length" class="model-option-dot">·</span>
                {{ SPEED_LABELS[m.speed_rating] || m.speed_rating }}
              </template>
            </div>
          </div>
          <svg v-if="selected === makeValue(p.provider_id, m.model_name)" class="model-check" width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="9" r="9" fill="#3b82f6"/>
            <path d="M5.5 9.2L7.8 11.5L12.5 6.5" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
      </template>
    </div>
  </el-popover>
</template>

<style scoped>
/* ── Trigger: pill button ── */
.model-trigger {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px 5px 14px;
  border: 1px solid var(--border-primary, rgba(0, 0, 0, 0.08));
  border-radius: 20px;
  background: var(--bg-card, #fff);
  cursor: pointer;
  font-family: inherit;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.model-trigger:hover {
  border-color: var(--border-hover, rgba(0, 0, 0, 0.15));
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}
.model-trigger.active {
  border-color: #3b82f6;
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.1);
}
.model-trigger-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1e293b);
  white-space: nowrap;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.model-trigger-chevron {
  flex-shrink: 0;
  color: var(--text-muted, #94a3b8);
  transition: transform 0.2s ease;
}
.model-trigger.active .model-trigger-chevron {
  transform: rotate(180deg);
}

/* ── Panel ── */
.model-panel {
  max-height: 380px;
  overflow-y: auto;
  padding: 6px 0;
}
.model-panel::-webkit-scrollbar { width: 4px; }
.model-panel::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.1); border-radius: 4px; }

.model-group-label {
  padding: 6px 16px 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted, #94a3b8);
  letter-spacing: 0.3px;
}
.model-divider {
  height: 1px;
  margin: 4px 12px;
  background: var(--border-primary, rgba(0, 0, 0, 0.06));
}

/* ── Option row ── */
.model-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin: 2px 6px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
}
.model-option:hover {
  background: var(--bg-hover, rgba(0, 0, 0, 0.035));
}
.model-option.active {
  background: rgba(59, 130, 246, 0.06);
}
.model-option-left {
  flex: 1;
  min-width: 0;
}
.model-option-name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--text-primary, #1e293b);
  display: flex;
  align-items: center;
  gap: 6px;
}
.model-rec {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 4px;
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  color: #92400e;
}
.model-option-desc {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--text-muted, #94a3b8);
  line-height: 1.4;
}
.model-option-dot {
  margin: 0 3px;
  opacity: 0.5;
}
.model-check {
  flex-shrink: 0;
}
</style>

<style>
.model-popover.el-popover {
  border-radius: 16px !important;
  border: 1px solid rgba(0, 0, 0, 0.06) !important;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12), 0 0 1px rgba(0, 0, 0, 0.06) !important;
  padding: 2px 0 !important;
}
html.dark .model-popover.el-popover {
  border-color: rgba(255, 255, 255, 0.08) !important;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4) !important;
}
</style>
