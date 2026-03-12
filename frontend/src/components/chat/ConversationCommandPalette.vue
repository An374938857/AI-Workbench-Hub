<script setup lang="ts">
interface Props {
  showCommandSuggestions: boolean
  commandSuggestions: any[]
  selectedCommandIndex: number
  showTemplateList: boolean
  filteredTemplateList: any[]
  selectedTemplateIndex: number
  isFreeTemplateGlobalDefault: boolean
  globalDefaultTemplateId: number | null
  showMcpList: boolean
  filteredMcpList: any[]
  selectedMcpIndex: number
  showSkillList: boolean
  filteredSkillList: any[]
  selectedSkillIndex: number
  showModelList: boolean
  filteredModelList: any[]
  selectedModelIndex: number
  listSearchQuery: string
  getTemplatePreview: (template: any) => string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (event: 'update:listSearchQuery', value: string): void
  (event: 'command-select', command: any): void
  (event: 'template-select', template: any): void
  (event: 'skill-select', skill: any): void
  (event: 'model-select', model: any): void
  (event: 'list-keydown', value: KeyboardEvent): void
}>()

function updateListSearchQuery(event: Event) {
  const target = event.target as HTMLInputElement | null
  emit('update:listSearchQuery', target?.value || '')
}

function handleListKeydown(event: KeyboardEvent) {
  emit('list-keydown', event)
}
</script>

<template>
  <div v-if="showCommandSuggestions" class="command-suggestions">
    <div
      v-for="(cmd, index) in commandSuggestions"
      :key="cmd.name"
      class="command-suggestion-item"
      :class="{ active: index === selectedCommandIndex }"
      @click="emit('command-select', cmd)"
    >
      <div class="cmd-name">{{ cmd.name }}</div>
      <div class="cmd-desc">{{ cmd.description }}</div>
    </div>
  </div>

  <div v-if="showTemplateList" class="command-suggestions template-list">
    <input
      :value="listSearchQuery"
      class="list-search-input"
      placeholder="搜索模板..."
      @input="updateListSearchQuery"
      @keydown.stop="handleListKeydown"
    />
    <div
      v-for="(tpl, index) in filteredTemplateList"
      :key="`tpl-${tpl.id ?? 'free'}`"
      class="command-suggestion-item"
      :class="{ active: index === selectedTemplateIndex }"
      @click="emit('template-select', tpl)"
    >
      <div class="cmd-name">
        <span>{{ tpl.name }}</span>
        <span v-if="tpl.id != null && tpl.is_favorited" class="template-badge template-badge--favorite">收藏</span>
        <span v-if="(tpl.id == null && isFreeTemplateGlobalDefault) || (tpl.id != null && tpl.id === globalDefaultTemplateId)" class="template-badge">默认</span>
      </div>
      <div class="cmd-desc">{{ props.getTemplatePreview(tpl) }}</div>
    </div>
  </div>

  <div v-if="showMcpList" class="command-suggestions mcp-list">
    <input
      :value="listSearchQuery"
      class="list-search-input"
      placeholder="搜索 MCP..."
      @input="updateListSearchQuery"
      @keydown.stop="handleListKeydown"
    />
    <div
      v-for="(mcp, index) in filteredMcpList"
      :key="mcp.id"
      class="command-suggestion-item"
      :class="{ active: index === selectedMcpIndex }"
    >
      <div class="cmd-name">
        {{ mcp.name }}
        <el-tag :type="mcp.last_test_result === 'success' ? 'success' : 'danger'" size="small" style="margin-left: 8px">
          {{ mcp.last_test_result === 'success' ? '可用' : '不可用' }}
        </el-tag>
      </div>
      <div class="cmd-desc">{{ mcp.description }}</div>
    </div>
  </div>

  <div v-if="showSkillList" class="command-suggestions skill-list">
    <input
      :value="listSearchQuery"
      class="list-search-input"
      placeholder="搜索技能..."
      @input="updateListSearchQuery"
      @keydown.stop="handleListKeydown"
    />
    <div
      v-for="(skill, index) in filteredSkillList"
      :key="skill.id"
      class="command-suggestion-item"
      :class="{ active: index === selectedSkillIndex }"
      @click="emit('skill-select', skill)"
    >
      <div class="cmd-name">{{ skill.name }}</div>
      <div class="cmd-desc">{{ skill.description }}</div>
    </div>
  </div>

  <div v-if="showModelList" class="command-suggestions model-list">
    <input
      :value="listSearchQuery"
      class="list-search-input"
      placeholder="搜索模型..."
      @input="updateListSearchQuery"
      @keydown.stop="handleListKeydown"
    />
    <div
      v-for="(model, index) in filteredModelList"
      :key="`${model.provider_id}-${model.model_name}`"
      class="command-suggestion-item"
      :class="{ active: index === selectedModelIndex }"
      @click="emit('model-select', model)"
    >
      <div class="cmd-name">{{ model.display_name }}</div>
      <div class="cmd-desc">{{ model.provider_name }}</div>
    </div>
  </div>
</template>

<style scoped>
.command-suggestions {
  position: absolute;
  bottom: calc(100% - 20px);
  left: 20px;
  right: 20px;
  margin-bottom: 8px;
  background: var(--bg-card, #fff);
  border: 2px solid var(--el-color-primary);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  max-height: 300px;
  overflow-y: auto;
  z-index: 9999;
}

.list-search-input {
  width: 100%;
  padding: 8px 12px;
  border: none;
  border-bottom: 1px solid var(--border-primary, #e4e7ed);
  outline: none;
  font-size: 13px;
  background: var(--bg-card, #fff);
  color: var(--text-primary, #303133);
  box-sizing: border-box;
  position: sticky;
  top: 0;
  z-index: 1;
}

.command-suggestion-item {
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid var(--border-light, #ebeef5);
}

.command-suggestion-item:last-child {
  border-bottom: none;
}

.command-suggestion-item:hover,
.command-suggestion-item.active {
  background: var(--bg-hover, #f5f7fa);
}

.cmd-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-color-primary);
  margin-bottom: 2px;
}

.cmd-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.template-list .cmd-name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.template-list .template-badge {
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
</style>
