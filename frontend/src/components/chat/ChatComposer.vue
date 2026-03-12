<script setup lang="ts">
import { computed, type VNodeRef } from 'vue'
import FileUploader from '@/components/FileUploader.vue'
import MessageQuote from '@/components/MessageQuote.vue'
import SkillManager from '@/components/SkillManager.vue'
import ModelSelector from '@/components/ModelSelector.vue'
import ConversationCommandPalette from '@/components/chat/ConversationCommandPalette.vue'
import ReferenceComposerBar from '@/components/chat/ReferenceComposerBar.vue'
import PromptTemplateSelector from '@/components/common/PromptTemplateSelector.vue'

const props = defineProps<{
  setChatInputAreaRef: (el: HTMLElement | null) => void
  setFileUploaderRef: (instance: InstanceType<typeof FileUploader> | null) => void
  setSkillManagerRef: (instance: InstanceType<typeof SkillManager> | null) => void
  currentConvId: number | null
  quotedMessages: any[]
  showReferenceComposerBar: boolean
  referenceEmptyMode: 'none' | 'sticky'
  referenceSelectedCount: number
  clearReferenceDisabled: boolean
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
  isForkMode: boolean
  isMessageEditMode: boolean
  isDragging: boolean
  isGenerating: boolean
  optimizing: boolean
  inputText: string
  inputKey: number
  inputExpanded: boolean
  isComposing: boolean
  templatePopoverVisible: boolean
  currentTemplateLabel: string
  currentTemplateId: number | null
  visibleTemplateList: any[]
  loadingTemplate: boolean
  autoRouteEnabled: boolean
  compareMode: boolean
  selectedProviderId: number | null
  selectedModelName: string | null
  compareModelBProviderId: number | null
  compareModelBName: string | null
  currentProviderId: number | null
  currentModelName: string | null
}>()

const emit = defineEmits<{
  'update:fileIds': [ids: number[]]
  'remove-quote': [messageId: number]
  'skill-activated': [payload: any]
  'skill-rejected': [payload: any]
  'skill-deactivated': [skillId: number]
  'update:listSearchQuery': [value: string]
  'list-keydown': [event: KeyboardEvent]
  'command-select': [command: any]
  'template-select': [templateId: number | null]
  'skill-select': [skill: any]
  'model-select': [model: any]
  'open-reference-dialog': []
  'clear-reference': []
  dragenter: [event: DragEvent]
  dragleave: [event: DragEvent]
  drop: [event: DragEvent]
  'optimize-prompt': []
  'update:inputText': [value: string]
  keydown: [event: KeyboardEvent]
  'update:isComposing': [value: boolean]
  paste: [event: ClipboardEvent]
  'update:templatePopoverVisible': [value: boolean]
  'template-popover-visible': [value: boolean]
  'add-attachment': []
  'toggle-expand': []
  'update:autoRouteEnabled': [value: boolean]
  'auto-route-toggle': [value: boolean]
  'update:compareMode': [value: boolean]
  'reload-after-model-change': []
  'model-selected': [providerId: number, modelName: string]
  'model-b-selected': [providerId: number, modelName: string]
  stop: []
  send: []
  'cancel-fork': []
  'cancel-message-edit': []
}>()

const chatInputAreaRef: VNodeRef = (el) => {
  props.setChatInputAreaRef(el as HTMLElement | null)
}

const fileUploaderComponentRef: VNodeRef = (el) => {
  props.setFileUploaderRef(el as InstanceType<typeof FileUploader> | null)
}

const skillManagerComponentRef: VNodeRef = (el) => {
  props.setSkillManagerRef(el as InstanceType<typeof SkillManager> | null)
}

const inputTextModel = computed({
  get: () => props.inputText,
  set: (value: string) => emit('update:inputText', value),
})

const templatePopoverVisibleModel = computed({
  get: () => props.templatePopoverVisible,
  set: (value: boolean) => emit('update:templatePopoverVisible', value),
})

const autoRouteEnabledModel = computed({
  get: () => props.autoRouteEnabled,
  set: (value: boolean) => emit('update:autoRouteEnabled', value),
})

const compareModeModel = computed({
  get: () => props.compareMode,
  set: (value: boolean) => emit('update:compareMode', value),
})
</script>

<template>
  <div :ref="chatInputAreaRef" class="input-area" :class="{ 'without-reference': !showReferenceComposerBar }">
    <div v-if="isForkMode" class="fork-banner">
      <span class="fork-banner-text">
        <el-icon :size="14"><Share /></el-icon> 从这里继续 — 输入新消息创建分支
      </span>
      <el-button size="small" text @click="emit('cancel-fork')">取消 <kbd class="fork-esc">Esc</kbd></el-button>
    </div>

    <div v-if="isMessageEditMode" class="fork-banner">
      <span class="fork-banner-text">
        <el-icon :size="14"><Edit /></el-icon> 编辑消息 — 输入新内容并重新生成
      </span>
      <el-button size="small" text @click="emit('cancel-message-edit')">取消 <kbd class="fork-esc">Esc</kbd></el-button>
    </div>

    <FileUploader
      :ref="fileUploaderComponentRef"
      :conversation-id="currentConvId"
      @change="(ids: number[]) => emit('update:fileIds', ids)"
    />

    <MessageQuote
      :messages="quotedMessages"
      @remove="(messageId: number) => emit('remove-quote', messageId)"
    />

    <SkillManager
      :ref="skillManagerComponentRef"
      :conversation-id="currentConvId"
      @skill-activated="(payload) => emit('skill-activated', payload)"
      @skill-rejected="(payload) => emit('skill-rejected', payload)"
      @skill-deactivated="(skillId) => emit('skill-deactivated', skillId)"
    />

    <ConversationCommandPalette
      :show-command-suggestions="showCommandSuggestions"
      :command-suggestions="commandSuggestions"
      :selected-command-index="selectedCommandIndex"
      :show-template-list="showTemplateList"
      :filtered-template-list="filteredTemplateList"
      :selected-template-index="selectedTemplateIndex"
      :is-free-template-global-default="isFreeTemplateGlobalDefault"
      :global-default-template-id="globalDefaultTemplateId"
      :show-mcp-list="showMcpList"
      :filtered-mcp-list="filteredMcpList"
      :selected-mcp-index="selectedMcpIndex"
      :show-skill-list="showSkillList"
      :filtered-skill-list="filteredSkillList"
      :selected-skill-index="selectedSkillIndex"
      :show-model-list="showModelList"
      :filtered-model-list="filteredModelList"
      :selected-model-index="selectedModelIndex"
      :list-search-query="listSearchQuery"
      :get-template-preview="getTemplatePreview"
      @update:list-search-query="(value) => emit('update:listSearchQuery', value)"
      @list-keydown="(event) => emit('list-keydown', event)"
      @command-select="(command) => emit('command-select', command)"
      @template-select="(templateId) => emit('template-select', templateId)"
      @skill-select="(skill) => emit('skill-select', skill)"
      @model-select="(model) => emit('model-select', model)"
    />

    <ReferenceComposerBar
      v-if="showReferenceComposerBar"
      :empty-mode="referenceEmptyMode"
      :selected-count="referenceSelectedCount"
      :is-generating="isGenerating"
      :clear-disabled="clearReferenceDisabled"
      @adjust="emit('open-reference-dialog')"
      @clear="emit('clear-reference')"
    />

    <div
      class="input-box"
      :class="{ 'fork-active': isForkMode, 'with-reference-bar': showReferenceComposerBar }"
      @dragenter.prevent="emit('dragenter', $event)"
      @dragleave.prevent="emit('dragleave', $event)"
      @dragover.prevent
      @drop.prevent="emit('drop', $event)"
    >
      <div v-if="isDragging" class="drop-overlay">
        <div class="drop-hint">
          <el-icon :size="24"><Paperclip /></el-icon>
          <span>将文件拖放到此处</span>
        </div>
      </div>

      <button
        v-if="!isGenerating"
        type="button"
        class="optimize-icon-btn"
        title="优化提示词"
        :disabled="optimizing || !inputText.trim()"
        @click="emit('optimize-prompt')"
      >
        <el-icon :class="{ 'is-loading': optimizing }"><MagicStick /></el-icon>
      </button>

      <label for="chat-input" class="sr-only">输入消息</label>
      <el-input
        id="chat-input"
        :key="inputKey"
        v-model="inputTextModel"
        type="textarea"
        :autosize="inputExpanded ? { minRows: 10, maxRows: 20 } : { minRows: 3, maxRows: 8 }"
        :placeholder="isMessageEditMode ? '编辑消息内容，按 Enter 保存并重新生成，Esc 取消' : isForkMode ? '输入新的追问，按 Enter 发送，Esc 取消' : isGenerating ? '生成中... 按 Esc 停止' : '输入消息，按 Enter 发送，Shift+Enter 换行，输入 / 查看指令'"
        @keydown="emit('keydown', $event)"
        @compositionstart="emit('update:isComposing', true)"
        @compositionend="emit('update:isComposing', false)"
        @paste="emit('paste', $event)"
      />

      <div class="input-actions">
        <div class="input-actions-left">
          <PromptTemplateSelector
            :popover-visible="templatePopoverVisibleModel"
            :current-template-label="currentTemplateLabel"
            :current-template-id="currentTemplateId"
            :is-free-template-global-default="isFreeTemplateGlobalDefault"
            :global-default-template-id="globalDefaultTemplateId"
            :visible-template-list="visibleTemplateList"
            :loading="loadingTemplate"
            @update:popover-visible="(value) => (templatePopoverVisibleModel = value)"
            @visible-change="(value) => emit('template-popover-visible', value)"
            @select="(templateId) => emit('template-select', templateId)"
          />

          <button type="button" class="action-icon-btn" title="添加附件" @click="emit('add-attachment')">
            <el-icon :size="18"><Plus /></el-icon>
          </button>
          <button
            type="button"
            class="action-icon-btn expand-btn"
            :title="inputExpanded ? '收起输入框' : '展开输入框'"
            @click="emit('toggle-expand')"
          >
            <el-icon :class="{ 'rotate-icon': inputExpanded }"><component :is="inputExpanded ? 'ArrowDown' : 'ArrowUp'" /></el-icon>
          </button>
        </div>

        <div class="input-actions-right">
          <el-tooltip content="根据提问内容自动选择最佳模型" placement="top">
            <el-switch
              v-model="autoRouteEnabledModel"
              active-text="智能选择"
              size="small"
              style="margin-right: 12px"
              @change="(value: boolean) => emit('auto-route-toggle', value)"
            />
          </el-tooltip>

          <template v-if="!autoRouteEnabled">
            <el-switch
              v-model="compareModeModel"
              active-text="对比模式"
              size="small"
              style="margin-right: 12px"
            />
            <ModelSelector
              v-if="!compareMode"
              :conversation-id="currentConvId"
              :current-provider-id="currentProviderId"
              :current-model-name="currentModelName"
              @model-changed="emit('reload-after-model-change')"
              @model-selected="(providerId, modelName) => emit('model-selected', providerId, modelName)"
            />
            <template v-else>
              <span style="font-size: 12px; color: #909399; margin-right: 8px">模型 A:</span>
              <ModelSelector
                :conversation-id="null"
                :current-provider-id="selectedProviderId"
                :current-model-name="selectedModelName"
                @model-selected="(providerId, modelName) => emit('model-selected', providerId, modelName)"
                style="margin-right: 12px"
              />
              <span style="font-size: 12px; color: #909399; margin-right: 8px">模型 B:</span>
              <ModelSelector
                :conversation-id="null"
                :current-provider-id="compareModelBProviderId"
                :current-model-name="compareModelBName"
                @model-selected="(providerId, modelName) => emit('model-b-selected', providerId, modelName)"
              />
            </template>
          </template>

          <el-button
            v-if="isGenerating"
            type="primary"
            size="small"
            class="send-btn stop-btn"
            @click="emit('stop')"
          >
            ■ 停止
          </el-button>
          <el-button
            v-else
            type="primary"
            size="small"
            class="send-btn"
            :class="{ 'send-btn--edit': isMessageEditMode }"
            :disabled="!inputText.trim()"
            @click="emit('send')"
          >
            {{ isMessageEditMode ? '保存并重新生成 ↵' : '发送 ↵' }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

.drop-overlay {
  position: absolute;
  inset: 0;
  background: rgba(219, 228, 243, 0.45);
  border: 1.5px dashed #7cacf8;
  border-radius: 20px;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(2px);
}

.drop-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #4285f4;
  font-size: 14px;
  font-weight: 500;
}

.input-area {
  padding: 0 20px 20px;
  position: relative;
  overflow: visible;
}

.input-area.without-reference > .file-uploader {
  margin-top: 10px;
}

.input-area.without-reference > .skill-manager {
  margin-top: 2px;
}

.fork-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  margin-bottom: 8px;
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
  border-radius: 8px;
  font-size: 13px;
  color: #409eff;
}

html.dark .fork-banner {
  background: var(--bg-input);
  border-color: #409eff40;
}

.fork-banner-text {
  display: flex;
  align-items: center;
  gap: 6px;
}

.fork-esc {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid currentColor;
  opacity: 0.6;
  margin-left: 4px;
  font-family: inherit;
}

.input-box {
  position: relative;
  background: var(--chat-input-bg, var(--bg-card, #fff));
  border: 1px solid color-mix(in srgb, var(--border-primary, #e5e7eb) 88%, transparent 12%);
  border-radius: 20px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.25s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 4px 16px rgba(0, 0, 0, 0.04);
}

.input-box.with-reference-bar {
  border-top: 1px solid color-mix(in srgb, var(--border-primary, #e5e7eb) 74%, transparent 26%);
  border-radius: 0 0 20px 20px;
}

.input-box:focus-within {
  border-color: color-mix(in srgb, #3b82f6 34%, var(--border-primary, #e5e7eb) 66%);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 8px 32px rgba(0, 0, 0, 0.08);
}

.input-box :deep(.el-textarea__inner) {
  transition: height 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.expand-btn .el-icon {
  transition: transform 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.expand-btn .rotate-icon {
  transform: rotate(180deg);
}

.input-box.fork-active {
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.15), 0 4px 16px rgba(0, 0, 0, 0.04);
}

.input-box :deep(.el-textarea__inner) {
  resize: none;
  border: none !important;
  box-shadow: none !important;
  padding: 12px 14px 8px;
  background: var(--chat-input-bg, var(--bg-card, #fff)) !important;
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px 8px;
  background: var(--chat-input-bg, var(--bg-card, #fff));
}

.input-actions-left {
  display: flex;
  gap: 2px;
  align-items: center;
}

.input-actions-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-icon-btn {
  width: 32px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 15px;
  color: #909399;
  transition: background 0.15s;
}

.action-icon-btn:hover {
  background: #f2f3f5;
}

html.dark .input-box {
  --chat-input-bg: #0f1115;
  border-color: rgba(148, 163, 184, 0.22);
}

html.dark .input-box.with-reference-bar {
  border-top-color: rgba(148, 163, 184, 0.14);
}

html.dark .action-icon-btn:hover {
  background: rgba(148, 163, 184, 0.16);
}

.send-btn {
  height: 30px;
  width: 72px;
  border-radius: 10px;
  flex-shrink: 0;
  font-size: 13px;
  --el-button-text-color: #ffffff;
  --el-button-bg-color: #397ef5;
  --el-button-border-color: #397ef5;
  --el-button-hover-bg-color: #2f6fec;
  --el-button-hover-border-color: #2f6fec;
  --el-button-active-bg-color: #255fdb;
  --el-button-active-border-color: #255fdb;
  --el-button-disabled-bg-color: #93c5fd;
  --el-button-disabled-border-color: #93c5fd;
  --el-button-disabled-text-color: #eff6ff;
}

.send-btn.send-btn--edit {
  width: auto;
  min-width: 112px;
  padding-left: 12px;
  padding-right: 12px;
}

html.dark .send-btn {
  --el-button-text-color: #ffffff;
  --el-button-bg-color: #397ef5;
  --el-button-border-color: #397ef5;
  --el-button-hover-bg-color: #4d8bf7;
  --el-button-hover-border-color: #4d8bf7;
  --el-button-active-bg-color: #2f6fec;
  --el-button-active-border-color: #2f6fec;
  --el-button-disabled-bg-color: #334155;
  --el-button-disabled-border-color: #334155;
  --el-button-disabled-text-color: #94a3b8;
}

.stop-btn {
  --el-button-text-color: #ffffff;
  --el-button-bg-color: #ed4141;
  --el-button-border-color: #ed4141;
  --el-button-hover-bg-color: #dd3a3a;
  --el-button-hover-border-color: #dd3a3a;
  --el-button-active-bg-color: #ca3535;
  --el-button-active-border-color: #ca3535;
}

html.dark .stop-btn {
  --el-button-text-color: #ffffff;
  --el-button-bg-color: #ed4141;
  --el-button-border-color: #ed4141;
  --el-button-hover-bg-color: #f05a5a;
  --el-button-hover-border-color: #f05a5a;
  --el-button-active-bg-color: #dd3a3a;
  --el-button-active-border-color: #dd3a3a;
}

.optimize-icon-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 10;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.optimize-icon-btn:hover {
  background: var(--el-fill-color-light);
  color: var(--el-color-primary);
}

.optimize-icon-btn:active {
  background: var(--el-fill-color);
}

.optimize-icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.optimize-icon-btn .el-icon {
  font-size: 16px;
}
</style>
