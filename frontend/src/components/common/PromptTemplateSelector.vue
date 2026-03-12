<script setup lang="ts">
import { computed } from 'vue'

interface PromptTemplateItem {
  id: number
  name: string
  is_favorited?: boolean
}

const props = withDefaults(defineProps<{
  popoverVisible: boolean
  currentTemplateLabel: string
  currentTemplateId: number | null
  isFreeTemplateGlobalDefault: boolean
  globalDefaultTemplateId: number | null
  visibleTemplateList: PromptTemplateItem[]
  loading?: boolean
  width?: number
}>(), {
  loading: false,
  width: 240,
})

const emit = defineEmits<{
  'update:popoverVisible': [value: boolean]
  'visible-change': [value: boolean]
  select: [templateId: number | null]
}>()

const popoverVisibleModel = computed({
  get: () => props.popoverVisible,
  set: (value: boolean) => emit('update:popoverVisible', value),
})

function handleVisibleChange(visible: boolean) {
  emit('visible-change', visible)
}

function handleSelect(templateId: number | null) {
  emit('update:popoverVisible', false)
  emit('visible-change', false)
  emit('select', templateId)
}
</script>

<template>
  <el-popover
    v-model:visible="popoverVisibleModel"
    placement="top-start"
    trigger="click"
    :width="width"
    :show-arrow="false"
    :offset="10"
    popper-class="template-popover"
    @show="handleVisibleChange(true)"
    @hide="handleVisibleChange(false)"
  >
    <template #reference>
      <button type="button" class="template-trigger" :class="{ active: popoverVisible }">
        <span class="template-trigger-label">{{ currentTemplateLabel }}</span>
        <svg class="template-trigger-chevron" width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </template>
    <div class="template-panel">
      <div class="template-panel-title">提示词模板</div>
      <div class="template-divider" />
      <div v-if="loading" class="template-empty">加载中...</div>
      <div v-else-if="visibleTemplateList.length === 0" class="template-empty">暂无模板</div>
      <button
        v-for="tpl in visibleTemplateList"
        :key="tpl.id"
        type="button"
        class="template-option"
        :class="{ active: currentTemplateId === tpl.id }"
        @click="handleSelect(tpl.id)"
      >
        <span class="template-option-name">{{ tpl.name }}</span>
        <span v-if="tpl.is_favorited || tpl.id === globalDefaultTemplateId" class="template-option-meta">
          <span v-if="tpl.is_favorited" class="template-badge template-badge--favorite">收藏</span>
          <span v-if="tpl.id === globalDefaultTemplateId" class="template-badge">默认</span>
        </span>
      </button>
    </div>
  </el-popover>
</template>

<style>
.template-popover.el-popover {
  border-radius: 16px !important;
  border: 1px solid rgba(0, 0, 0, 0.06) !important;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12), 0 0 1px rgba(0, 0, 0, 0.06) !important;
  padding: 2px 0 !important;
}

html.dark .template-popover.el-popover {
  border-color: rgba(255, 255, 255, 0.08) !important;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4) !important;
}
</style>

<style scoped>
.template-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 112px;
  width: fit-content;
  max-width: clamp(112px, 42vw, 320px);
  padding: 5px 9px 5px 11px;
  margin-right: 8px;
  border: 1px solid var(--border-primary, rgba(0, 0, 0, 0.08));
  border-radius: 20px;
  background: var(--bg-card, #fff);
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.template-trigger:hover {
  border-color: var(--border-hover, rgba(0, 0, 0, 0.15));
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.template-trigger.active {
  border-color: #3b82f6;
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.1);
}

.template-trigger-label {
  display: block;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1e293b);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  text-align: left;
}

.template-trigger-chevron {
  flex-shrink: 0;
  color: var(--text-muted, #94a3b8);
  transition: transform 0.2s ease;
}

.template-trigger.active .template-trigger-chevron {
  transform: rotate(180deg);
}

.template-panel {
  max-height: 320px;
  overflow-y: auto;
  padding: 6px 0;
}

.template-panel::-webkit-scrollbar {
  width: 4px;
}

.template-panel::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.1);
  border-radius: 4px;
}

.template-panel-title {
  padding: 8px 14px 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted, #94a3b8);
  letter-spacing: 0.2px;
}

.template-divider {
  height: 1px;
  margin: 4px 12px;
  background: var(--border-primary, rgba(0, 0, 0, 0.06));
}

.template-option {
  width: calc(100% - 12px);
  margin: 2px 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 9px 12px;
  border: none;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  transition: background 0.15s;
}

.template-option:hover {
  background: var(--bg-hover, rgba(0, 0, 0, 0.035));
}

.template-option.active {
  background: rgba(59, 130, 246, 0.06);
}

.template-option-name {
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1e293b);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  text-align: left;
}

.template-option-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  flex-shrink: 0;
}

.template-badge {
  font-size: 10px;
  line-height: 1;
  padding: 3px 6px;
  border-radius: 6px;
  color: #2563eb;
  background: rgba(37, 99, 235, 0.1);
  flex-shrink: 0;
}

.template-badge--favorite {
  color: #b45309;
  background: rgba(245, 158, 11, 0.16);
}

.template-empty {
  padding: 12px 14px;
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
}
</style>
