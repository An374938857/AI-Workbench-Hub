<script setup lang="ts">
import { computed, ref } from 'vue'
import draggable from 'vuedraggable'
import TagBadge from '@/components/TagBadge.vue'
import BatchToolbar from '@/components/BatchToolbar.vue'
import { Plus, PriceTag, Loading, Check, MoreFilled, Delete } from '@element-plus/icons-vue'
import type { TagInfo, ActiveSkillLite, LiveExecutionState, SidebarSignal } from '@/types/chat'
import type { ConversationExecutionSnapshot } from '@/types/chatExecution'
import { resolveConversationStatusSignal } from '@/utils/chatConversationStatus'

interface SidebarConversation {
  id: number
  skill_id: number | null
  skill_name: string
  title: string
  updated_at: string
  active_skills?: ActiveSkillLite[]
  tags?: TagInfo[]
  live_execution?: LiveExecutionState
  sidebar_signal?: SidebarSignal
}

interface Props {
  conversations: SidebarConversation[]
  allTags: TagInfo[]
  activeTagFilter: number | null
  isSelectMode: boolean
  selectedConvIds: Set<number>
  currentConvId: number | null
  editingSidebarTitleConvId: number | null
  editingSidebarTitleText: string
  generatingConvIds: Set<number>
  conversationExecutionStates: Map<number, ConversationExecutionSnapshot>
  pollingHealth: 'healthy' | 'retrying' | 'degraded'
  loadingMoreConversations: boolean
  hasMoreConversations: boolean
  getTagFilterItemStyle: (tag: TagInfo, active: boolean) => Record<string, string>
  formatTime: (value: string) => string
  convHasTag: (conv: SidebarConversation, tagId: number) => boolean
  setSidebarTitleInputRef: (convId: number, el: HTMLInputElement | null) => void
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (event: 'update:conversations', value: SidebarConversation[]): void
  (event: 'update:editingSidebarTitleText', value: string): void
  (event: 'new-chat'): void
  (event: 'toggle-select-mode'): void
  (event: 'open-tag-manager'): void
  (event: 'tag-filter', value: number | null): void
  (event: 'select-all'): void
  (event: 'conv-list-scroll', value: Event): void
  (event: 'conv-drag-end'): void
  (event: 'conv-click', value: SidebarConversation): void
  (event: 'toggle-select', value: number): void
  (event: 'start-edit-sidebar-title', convId: number, title: string): void
  (event: 'save-sidebar-edit-title'): void
  (event: 'cancel-sidebar-edit-title'): void
  (event: 'tag-command', value: string): void
  (event: 'delete-conv', value: SidebarConversation): void
  (event: 'row-command', value: { conversationId: number; action: 'tag' | 'delete'; tagId?: number }): void
  (event: 'batch-delete'): void
  (event: 'batch-export'): void
  (event: 'batch-tag'): void
}>()

const VISIBLE_TAG_LIMIT = 2
const expandedSkillConvIds = ref<Set<number>>(new Set())

const conversationModel = computed({
  get: () => props.conversations,
  set: (value) => emit('update:conversations', value),
})

function updateEditingSidebarTitleText(event: Event) {
  const target = event.target as HTMLInputElement | null
  emit('update:editingSidebarTitleText', target?.value || '')
}

function getConversationStatusSignal(conv: SidebarConversation) {
  const isCurrentConversation = props.currentConvId === conv.id
  return resolveConversationStatusSignal({
    sidebarSignalState: conv.sidebar_signal ? conv.sidebar_signal.state : undefined,
    liveExecutionStatus: conv.live_execution?.status,
    executionSnapshot: props.conversationExecutionStates.get(conv.id) ?? null,
    executionState: props.conversationExecutionStates.get(conv.id)?.state ?? null,
    isGenerating: props.generatingConvIds.has(conv.id),
    pollingHealth: props.pollingHealth,
    isCurrentConversation,
  })
}

function getVisibleTags(conv: SidebarConversation) {
  return Array.isArray(conv.tags) ? conv.tags.slice(0, VISIBLE_TAG_LIMIT) : []
}

function getHiddenTags(conv: SidebarConversation) {
  return Array.isArray(conv.tags) ? conv.tags.slice(VISIBLE_TAG_LIMIT) : []
}

function getHiddenTagCount(conv: SidebarConversation) {
  return getHiddenTags(conv).length
}

function getActiveSkillCount(conv: SidebarConversation) {
  return Array.isArray(conv.active_skills) ? conv.active_skills.length : 0
}

function getSkillSummaryText(conv: SidebarConversation) {
  const count = getActiveSkillCount(conv)
  return count > 0 ? `技能 ${count} 个` : '自由对话'
}

function isSkillExpanded(convId: number) {
  return expandedSkillConvIds.value.has(convId)
}

function toggleSkillExpanded(convId: number, event: Event) {
  event.stopPropagation()
  const next = new Set(expandedSkillConvIds.value)
  if (next.has(convId)) next.delete(convId)
  else next.add(convId)
  expandedSkillConvIds.value = next
}

function handleRowMenuCommand(conv: SidebarConversation, cmd: string | number | object) {
  if (typeof cmd !== 'string') return
  if (cmd === 'delete') {
    emit('row-command', { conversationId: conv.id, action: 'delete' })
    emit('delete-conv', conv)
    return
  }
  if (!cmd.startsWith('tag:')) return
  const tagId = Number(cmd.slice(4))
  if (!Number.isFinite(tagId)) return
  emit('row-command', { conversationId: conv.id, action: 'tag', tagId })
  emit('tag-command', `${conv.id}:${tagId}`)
}
</script>

<template>
  <div class="chat-sidebar">
    <div class="sidebar-header">
      <button class="new-chat-btn" @click="emit('new-chat')">
        <el-icon :size="16"><Plus /></el-icon>
        <span>新建对话</span>
      </button>
      <div class="sidebar-actions">
        <button type="button" class="sidebar-action-btn" @click="emit('toggle-select-mode')">
          {{ isSelectMode ? '取消' : '选择' }}
        </button>
        <button type="button" class="sidebar-action-btn" @click="emit('open-tag-manager')">
          <el-icon :size="13"><PriceTag /></el-icon>
          <span>标签</span>
        </button>
      </div>
    </div>

    <div v-if="allTags.length > 0" class="tag-filter-bar">
      <span
        class="tag-filter-item"
        :class="{ active: activeTagFilter === null }"
        @click="emit('tag-filter', null)"
      >全部</span>
      <span
        v-for="tag in allTags"
        :key="tag.id"
        class="tag-filter-item tag-filter-item--tag"
        :class="{ active: activeTagFilter === tag.id }"
        :style="getTagFilterItemStyle(tag, activeTagFilter === tag.id)"
        @click="emit('tag-filter', tag.id)"
      >{{ tag.name }}</span>
    </div>

    <div v-if="isSelectMode" class="select-bar">
      <div class="select-bar-inner">
        <el-checkbox
          class="select-all-checkbox"
          :model-value="selectedConvIds.size === conversations.length && conversations.length > 0"
          :indeterminate="selectedConvIds.size > 0 && selectedConvIds.size < conversations.length"
          @change="emit('select-all')"
        >全选</el-checkbox>
        <span class="select-count">已选 {{ selectedConvIds.size }}</span>
      </div>
    </div>

    <div class="conv-list-wrapper" @scroll="emit('conv-list-scroll', $event)">
      <draggable
        v-model="conversationModel"
        item-key="id"
        class="conv-list"
        ghost-class="conv-drag-ghost"
        animation="200"
        :disabled="isSelectMode"
        @end="emit('conv-drag-end')"
      >
        <template #item="{ element: conv }">
          <div
            class="conv-item"
            :class="{
              active: !isSelectMode && conv.id === currentConvId,
              'select-mode': isSelectMode,
              selected: isSelectMode && selectedConvIds.has(conv.id),
              'has-status': Boolean(getConversationStatusSignal(conv)),
            }"
            :data-conv-id="conv.id"
            @click="emit('conv-click', conv)"
          >
            <el-checkbox
              v-if="isSelectMode"
              :model-value="selectedConvIds.has(conv.id)"
              class="conv-checkbox"
              @click.stop
              @change="emit('toggle-select', conv.id)"
            />
            <div class="conv-info">
              <div class="conv-title" @dblclick.stop="emit('start-edit-sidebar-title', conv.id, conv.title)">
                <input
                  v-if="editingSidebarTitleConvId === conv.id"
                  :ref="(el) => setSidebarTitleInputRef(conv.id, el as HTMLInputElement | null)"
                  :value="editingSidebarTitleText"
                  class="title-edit-input"
                  @input="updateEditingSidebarTitleText"
                  @blur="emit('save-sidebar-edit-title')"
                  @keyup.enter="($event.target as HTMLInputElement)?.blur()"
                  @keyup.escape="emit('cancel-sidebar-edit-title')"
                  @click.stop
                />
                <span v-else class="conv-title-text">{{ conv.title }}</span>
              </div>
              <div class="conv-meta-row">
                <span class="conv-time">{{ formatTime(conv.updated_at) }}</span>
              </div>
              <div v-if="conv.tags && conv.tags.length > 0" class="conv-tags">
                <TagBadge
                  v-for="tag in getVisibleTags(conv)"
                  :key="tag.id"
                  :name="tag.name"
                  :color="tag.color"
                />
                <el-popover
                  v-if="getHiddenTagCount(conv) > 0"
                  placement="top-start"
                  trigger="hover"
                  :width="220"
                  popper-class="conv-tag-overflow-popper"
                >
                  <template #reference>
                    <button
                      type="button"
                      class="tag-overflow-trigger"
                      :data-test="`tag-overflow-trigger-${conv.id}`"
                      @click.stop
                    >
                      +{{ getHiddenTagCount(conv) }}
                    </button>
                  </template>
                  <div class="conv-tag-overflow-list">
                    <TagBadge
                      v-for="tag in getHiddenTags(conv)"
                      :key="`overflow-${conv.id}-${tag.id}`"
                      :name="tag.name"
                      :color="tag.color"
                    />
                  </div>
                </el-popover>
              </div>
              <div class="conv-skill-summary">
                <button
                  v-if="getActiveSkillCount(conv) > 0"
                  type="button"
                  class="skill-summary-toggle"
                  :data-test="`skill-summary-toggle-${conv.id}`"
                  @click="toggleSkillExpanded(conv.id, $event)"
                >
                  {{ getSkillSummaryText(conv) }}
                  <span class="skill-summary-caret" :class="{ expanded: isSkillExpanded(conv.id) }">▾</span>
                </button>
                <span v-else class="skill-summary-text">{{ getSkillSummaryText(conv) }}</span>
                <div
                  v-if="getActiveSkillCount(conv) > 0 && isSkillExpanded(conv.id)"
                  class="skill-expanded-list"
                  :data-test="`skill-expanded-${conv.id}`"
                >
                  <span
                    v-for="skill in conv.active_skills"
                    :key="`${conv.id}-${skill.id}`"
                    class="skill-expanded-item"
                  >
                    {{ skill.name }}
                  </span>
                </div>
              </div>
            </div>
            <div class="conv-trailing">
              <span
                v-if="getConversationStatusSignal(conv)"
                class="conv-status-pill"
                :class="[
                  `is-${getConversationStatusSignal(conv)?.tone}`,
                  `is-${getConversationStatusSignal(conv)?.variant}`,
                ]"
                :title="getConversationStatusSignal(conv)?.label"
              >
                {{ getConversationStatusSignal(conv)?.label }}
              </span>
              <div v-if="!isSelectMode" class="conv-actions">
                <el-dropdown
                  trigger="click"
                  popper-class="tag-picker-dropdown"
                  @command="(cmd: string | number | object) => handleRowMenuCommand(conv, cmd)"
                  @click.stop
                >
                  <el-button
                    link
                    size="small"
                    class="conv-action-btn"
                    :data-test="`row-action-trigger-${conv.id}`"
                    @click.stop
                  >
                    <el-icon><MoreFilled /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <div class="menu-section-title">标签</div>
                      <el-dropdown-item v-if="allTags.length === 0" disabled>暂无标签，请先创建</el-dropdown-item>
                      <el-dropdown-item
                        v-for="tag in allTags"
                        :key="tag.id"
                        :command="`tag:${tag.id}`"
                      >
                        <div class="tag-picker-item" :class="{ 'is-selected': convHasTag(conv, tag.id) }">
                          <span class="tag-picker-dot" :style="{ background: tag.color }" />
                          <span class="tag-picker-name">{{ tag.name }}</span>
                          <el-icon v-if="convHasTag(conv, tag.id)" color="#2563eb"><Check /></el-icon>
                        </div>
                      </el-dropdown-item>
                      <div class="menu-section-title menu-section-title--danger">危险操作</div>
                      <el-dropdown-item command="delete" class="row-delete-item">
                        <div class="row-delete-content">
                          <el-icon><Delete /></el-icon>
                          <span>删除会话</span>
                        </div>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </div>
        </template>
      </draggable>

      <div v-if="loadingMoreConversations" class="loading-more">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>

      <div v-if="!hasMoreConversations && conversations.length > 0" class="no-more">
        没有更多了
      </div>

      <div v-if="conversations.length === 0" class="conv-empty">
        暂无对话记录
      </div>
    </div>

    <BatchToolbar
      :selected-count="selectedConvIds.size"
      @delete="emit('batch-delete')"
      @export="emit('batch-export')"
      @tag="emit('batch-tag')"
      @cancel="emit('toggle-select-mode')"
    />
  </div>
</template>

<style scoped>
.chat-sidebar {
  width: 308px;
  border-right: 1px solid var(--border-primary, #ebeef5);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  background: var(--bg-sidebar, #fafafa);
  position: relative;
}

.sidebar-header {
  padding: 12px 12px 8px;
  border-bottom: 1px solid var(--border-primary, #ebeef5);
}

.sidebar-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.sidebar-action-btn {
  flex: 1;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.7);
  color: var(--text-muted, #6b7280);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
}

.sidebar-action-btn:hover {
  color: var(--text-primary, #1f2937);
  border-color: rgba(15, 23, 42, 0.16);
  background: rgba(255, 255, 255, 0.9);
}

.sidebar-action-btn:active {
  transform: scale(0.98);
}

.tag-filter-bar {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  overflow-x: auto;
  border-bottom: 1px solid var(--border-light, #f2f3f5);
  flex-shrink: 0;
}

.tag-filter-bar::-webkit-scrollbar {
  height: 0;
}

.tag-filter-item {
  font-size: 11px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  color: var(--text-muted, #6b7280);
  background: rgba(255, 255, 255, 0.66);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.tag-filter-item:not(.tag-filter-item--tag):hover {
  color: #1f2937;
  border-color: rgba(59, 130, 246, 0.38);
  background: rgba(59, 130, 246, 0.06);
}

.tag-filter-item:not(.tag-filter-item--tag).active {
  color: #1d4ed8;
  border-color: rgba(59, 130, 246, 0.52);
  background: rgba(59, 130, 246, 0.12);
}

.tag-filter-item--tag:hover {
  color: var(--tag-color, #409eff);
  border-color: var(--tag-color, #409eff);
  background: var(--tag-bg, #409eff14);
}

.tag-filter-item--tag.active {
  color: var(--tag-color, #409eff);
  border-color: var(--tag-color, #409eff);
  background: var(--tag-bg, #409eff14);
}

.select-bar {
  padding: 8px;
  border-bottom: 1px solid var(--border-light, #f2f3f5);
  flex-shrink: 0;
}

.select-bar-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px 8px 12px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.84);
}

.select-all-checkbox {
  margin-right: 0;
}

.select-count {
  font-size: 12px;
  color: var(--text-muted, #64748b);
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.12);
  line-height: 1.4;
  flex-shrink: 0;
}

.conv-checkbox {
  flex-shrink: 0;
  margin-right: 8px;
  margin-left: 0;
}

.select-all-checkbox :deep(.el-checkbox__input),
.conv-checkbox :deep(.el-checkbox__input) {
  line-height: 1;
}

.select-all-checkbox :deep(.el-checkbox__inner),
.conv-checkbox :deep(.el-checkbox__inner) {
  width: 16px;
  height: 16px;
  border-radius: 5px;
  border-color: rgba(148, 163, 184, 0.45);
  transition: all 0.16s ease;
}

.select-all-checkbox :deep(.el-checkbox__input.is-checked .el-checkbox__inner),
.conv-checkbox :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background: #397ef5;
  border-color: #397ef5;
}

.select-all-checkbox :deep(.el-checkbox__label) {
  padding-left: 8px;
  color: var(--text-secondary, #475569);
  font-size: 13px;
  font-weight: 500;
}

.conv-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  min-height: 20px;
}

.new-chat-btn {
  width: 100%;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid color-mix(in srgb, var(--border-primary, #ebeef5) 82%, #94a3b8 18%);
  border-radius: 12px;
  background: color-mix(in srgb, var(--bg-card, #fff) 94%, #f8fafc 6%);
  color: var(--text-primary, #1e293b);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.65);
  font-family: inherit;
}

.new-chat-btn:hover {
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.7);
  transform: translateY(-1px);
  border-color: color-mix(in srgb, #60a5fa 42%, var(--border-primary, #ebeef5) 58%);
  background: color-mix(in srgb, var(--bg-card, #fff) 88%, #eff6ff 12%);
}

.new-chat-btn:active {
  transform: translateY(0);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.55);
}

.new-chat-btn:focus-visible {
  outline: none;
  border-color: rgba(59, 130, 246, 0.52);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.16), 0 4px 14px rgba(37, 99, 235, 0.14);
}

.conv-list-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.loading-more,
.no-more {
  text-align: center;
  padding: 12px;
  font-size: 12px;
  color: var(--text-muted, #c0c4cc);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.loading-more .el-icon {
  font-size: 14px;
}

.conv-item {
  --conv-title-row-height: 22px;
  display: flex;
  align-items: center;
  padding: 10px 10px 10px 12px;
  border-radius: 14px;
  cursor: pointer;
  margin-bottom: 0;
  transition: background 0.2s, border-color 0.2s;
  animation: conv-enter 0.35s cubic-bezier(0.2, 0.6, 0.35, 1) both;
  position: relative;
  border: 1px solid transparent;
  overflow: hidden;
}

.conv-item + .conv-item::before {
  content: '';
  position: absolute;
  left: 12px;
  right: 14px;
  top: 0;
  height: 1px;
  background: rgba(148, 163, 184, 0.2);
}

.conv-item.select-mode {
  border: 1px solid transparent;
  border-radius: 10px;
}

.conv-item:nth-child(1) {
  animation-delay: 0s;
}

.conv-item:nth-child(2) {
  animation-delay: 0.03s;
}

.conv-item:nth-child(3) {
  animation-delay: 0.06s;
}

.conv-item:nth-child(4) {
  animation-delay: 0.09s;
}

.conv-item:nth-child(5) {
  animation-delay: 0.12s;
}

.conv-item:nth-child(6) {
  animation-delay: 0.15s;
}

.conv-item:nth-child(7) {
  animation-delay: 0.18s;
}

.conv-item:nth-child(8) {
  animation-delay: 0.21s;
}

.conv-item:nth-child(n+9) {
  animation-delay: 0.24s;
}

@keyframes conv-enter {
  from {
    opacity: 0;
    transform: translateX(-12px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.conv-item:hover {
  background: rgba(148, 163, 184, 0.08);
  border-color: rgba(148, 163, 184, 0.2);
}

.conv-item.select-mode:hover {
  background: rgba(59, 130, 246, 0.06);
  border-color: rgba(59, 130, 246, 0.22);
}

.conv-item.select-mode.selected {
  background: rgba(57, 126, 245, 0.1);
  border-color: rgba(57, 126, 245, 0.34);
}

.conv-item.active {
  background: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.25);
}

.conv-item.highlight-flash {
  animation: highlight-pulse 2s ease-in-out;
}

@keyframes highlight-pulse {
  0%,
  100% {
    background: var(--bg-user-msg, #ecf5ff);
    box-shadow: 0 0 0 0 rgba(64, 158, 255, 0.4);
  }
  25% {
    background: #d9ecff;
    box-shadow: 0 0 0 4px rgba(64, 158, 255, 0.4);
  }
  50% {
    background: var(--bg-user-msg, #ecf5ff);
    box-shadow: 0 0 0 0 rgba(64, 158, 255, 0);
  }
  75% {
    background: #d9ecff;
    box-shadow: 0 0 0 4px rgba(64, 158, 255, 0.4);
  }
}

.conv-info {
  flex: 1;
  min-width: 0;
  padding-right: 40px;
}

.conv-item.has-status .conv-info {
  padding-right: 126px;
}

.conv-title {
  font-size: 14px;
  min-height: var(--conv-title-row-height);
  color: var(--text-primary, #303133);
  cursor: default;
  display: flex;
  align-items: center;
  gap: 6px;
}

.conv-title-text {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.32;
}

.title-edit-input {
  width: 100%;
  border: 1px solid var(--el-color-primary);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: inherit;
  font-family: inherit;
  color: inherit;
  background: var(--bg-primary, #fff);
  outline: none;
  box-sizing: border-box;
}

.conv-meta-row {
  margin-top: 2px;
  display: flex;
  align-items: center;
  min-height: 16px;
}

.conv-time {
  font-size: 11px;
  line-height: 1.2;
  color: var(--text-muted, #64748b);
}

.conv-status-pill {
  display: inline-flex;
  align-items: center;
  max-width: 118px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  padding: 3px 7px;
  border: 1px solid rgba(148, 163, 184, 0.26);
  color: #64748b;
  background: rgba(148, 163, 184, 0.1);
}

.conv-status-pill.is-success {
  color: #15803d;
  border-color: rgba(34, 197, 94, 0.34);
  background: rgba(34, 197, 94, 0.1);
}

.conv-status-pill.is-warning {
  color: #a16207;
  border-color: rgba(245, 158, 11, 0.36);
  background: rgba(245, 158, 11, 0.1);
}

.conv-status-pill.is-danger {
  color: #b91c1c;
  border-color: rgba(239, 68, 68, 0.36);
  background: rgba(239, 68, 68, 0.1);
}

.conv-status-pill.is-info {
  color: #1d4ed8;
  border-color: rgba(59, 130, 246, 0.36);
  background: rgba(59, 130, 246, 0.1);
}

.conv-status-pill.is-neutral {
  color: #475569;
  border-color: rgba(100, 116, 139, 0.34);
  background: rgba(100, 116, 139, 0.1);
}

.conv-status-pill.is-breathing,
.conv-status-pill.is-pulse {
  animation: conv-status-pill-pulse 1.9s ease-in-out infinite;
}

@keyframes conv-status-pill-pulse {
  0%,
  100% {
    transform: translateY(0);
    opacity: 0.86;
  }
  50% {
    transform: translateY(-0.5px);
    opacity: 1;
  }
}

.tag-overflow-trigger {
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: rgba(148, 163, 184, 0.12);
  color: #64748b;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  padding: 0 7px;
  height: 20px;
  cursor: pointer;
}

.conv-tag-overflow-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.conv-skill-summary {
  margin-top: 5px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.skill-summary-toggle {
  border: none;
  background: transparent;
  padding: 0;
  color: #64748b;
  font-size: 11px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.skill-summary-toggle:hover {
  color: #334155;
}

.skill-summary-text {
  color: #94a3b8;
  font-size: 11px;
}

.skill-summary-caret {
  font-size: 11px;
  transition: transform 0.16s ease;
}

.skill-summary-caret.expanded {
  transform: rotate(180deg);
}

.skill-expanded-list {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  width: 100%;
}

.skill-expanded-item {
  font-size: 11px;
  line-height: 1.4;
  color: #475569;
  background: rgba(148, 163, 184, 0.16);
  border-radius: 7px;
  padding: 1px 6px;
  max-width: 145px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  position: absolute;
  top: 50%;
  right: 0;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-50%) translateX(4px);
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.conv-trailing:hover .conv-actions,
.conv-actions:focus-within {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(-50%) translateX(0);
}

.conv-action-btn {
  width: 26px;
  height: 26px;
  padding: 0 !important;
  border-radius: 8px;
  color: #64748b;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(255, 255, 255, 0.82);
}

.conv-action-btn:hover {
  background: rgba(148, 163, 184, 0.14);
  border-color: rgba(100, 116, 139, 0.36);
  color: #334155;
}

.conv-trailing {
  position: absolute;
  right: 10px;
  top: 0;
  bottom: 0;
  width: 120px;
  pointer-events: auto;
}

.conv-trailing .conv-status-pill {
  position: absolute;
  top: calc(10px + (var(--conv-title-row-height) - 16px) / 2);
  right: 0;
  pointer-events: auto;
}

.conv-trailing .conv-actions {
  pointer-events: auto;
}

.conv-drag-ghost {
  opacity: 0.4;
  background: #409eff14 !important;
  border: 1px dashed #409eff !important;
}

.conv-empty {
  text-align: center;
  color: #c0c4cc;
  padding: 40px 0;
  font-size: 13px;
}

.tag-picker-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 12px;
  cursor: pointer;
  transition: color 0.16s ease, background 0.16s ease, transform 0.16s ease;
  min-width: 176px;
}

.tag-picker-item:hover {
  background: rgba(148, 163, 184, 0.1);
  transform: translateX(1px);
}

.tag-picker-item.is-selected {
  background: rgba(37, 99, 235, 0.08);
}

.tag-picker-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
}

.tag-picker-name {
  font-size: 12px;
  color: var(--text-primary, #303133);
  max-width: 106px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag-picker-item.is-selected .tag-picker-name {
  font-weight: 600;
}

.tag-picker-item :deep(.el-icon) {
  margin-left: auto;
}

:deep(.row-delete-item) {
  margin-top: 4px;
  color: #dc2626;
  border-radius: 12px;
  background: rgba(220, 38, 38, 0.06);
}

.row-delete-content {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.menu-section-title {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  padding: 6px 10px 6px;
  letter-spacing: 0.02em;
}

.menu-section-title--danger {
  position: relative;
  margin-top: 6px;
  padding-top: 10px;
  color: #b91c1c;
}

.menu-section-title--danger::before {
  content: '';
  position: absolute;
  left: 8px;
  right: 8px;
  top: 0;
  height: 1px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(148, 163, 184, 0), rgba(148, 163, 184, 0.34), rgba(148, 163, 184, 0));
}

:deep(.conv-tag-overflow-popper.el-popover) {
  border-radius: 10px;
  padding: 8px;
}

:deep(.tag-picker-dropdown.el-popper),
:deep(.el-popper.tag-picker-dropdown) {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 20px !important;
  box-shadow:
    0 18px 42px rgba(15, 23, 42, 0.16),
    0 4px 12px rgba(15, 23, 42, 0.08);
  overflow: hidden !important;
  min-width: 222px !important;
  backdrop-filter: blur(8px);
}

:deep(.tag-picker-dropdown .el-popper__arrow::before) {
  border-color: rgba(148, 163, 184, 0.22);
  background: var(--bg-card, #fff);
}

:deep(.tag-picker-dropdown .el-popper__content),
:deep(.el-popper.tag-picker-dropdown > .el-popper__content) {
  border-radius: 20px !important;
  overflow: hidden !important;
  background: transparent;
}

:deep(.tag-picker-dropdown .el-dropdown-menu) {
  min-width: 222px;
  width: 222px;
  padding: 10px;
  border: none;
  border-radius: 20px !important;
  overflow: hidden !important;
  background: color-mix(in srgb, var(--bg-card, #fff) 97%, #f8fafc 3%);
}

:deep(.tag-picker-dropdown .el-dropdown-menu__item) {
  padding: 0;
  margin: 2px 0;
  line-height: normal;
  border-radius: 12px;
}

:deep(.tag-picker-dropdown .el-dropdown-menu__item:not(.is-disabled):hover),
:deep(.tag-picker-dropdown .el-dropdown-menu__item:not(.is-disabled):focus) {
  background: transparent;
}

:deep(.tag-picker-dropdown .row-delete-item:not(.is-disabled):hover),
:deep(.tag-picker-dropdown .row-delete-item:not(.is-disabled):focus) {
  background: rgba(220, 38, 38, 0.14) !important;
  color: #b91c1c !important;
}

:deep(.tag-picker-dropdown .row-delete-item:hover .row-delete-content),
:deep(.tag-picker-dropdown .row-delete-item:focus .row-delete-content) {
  color: inherit;
}

html.dark .new-chat-btn {
  border-color: rgba(148, 163, 184, 0.28);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0.03));
  color: #f8fafc;
  box-shadow:
    0 10px 24px rgba(2, 6, 23, 0.18),
    inset 0 0 0 1px rgba(255, 255, 255, 0.03),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

html.dark .new-chat-btn:hover {
  border-color: rgba(96, 165, 250, 0.48);
  background: linear-gradient(180deg, rgba(96, 165, 250, 0.18), rgba(37, 99, 235, 0.08));
  box-shadow:
    0 14px 28px rgba(2, 6, 23, 0.24),
    inset 0 0 0 1px rgba(147, 197, 253, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

html.dark .new-chat-btn:active {
  box-shadow:
    0 6px 16px rgba(2, 6, 23, 0.22),
    inset 0 0 0 1px rgba(147, 197, 253, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

html.dark .new-chat-btn:focus-visible {
  border-color: rgba(125, 211, 252, 0.62);
  box-shadow:
    0 0 0 3px rgba(56, 189, 248, 0.18),
    0 10px 24px rgba(2, 6, 23, 0.24),
    inset 0 0 0 1px rgba(147, 197, 253, 0.14);
}

html.dark .sidebar-action-btn {
  border-color: rgba(148, 163, 184, 0.22);
  background: rgba(255, 255, 255, 0.03);
  color: #94a3b8;
}

html.dark .sidebar-action-btn:hover {
  color: #e2e8f0;
  border-color: rgba(148, 163, 184, 0.38);
  background: rgba(255, 255, 255, 0.08);
}

html.dark .tag-filter-item {
  border-color: rgba(148, 163, 184, 0.26);
  background: rgba(255, 255, 255, 0.04);
  color: #94a3b8;
}

html.dark .tag-filter-item:not(.tag-filter-item--tag):hover,
html.dark .tag-filter-item:not(.tag-filter-item--tag).active {
  color: #dbeafe;
  border-color: rgba(96, 165, 250, 0.5);
  background: rgba(96, 165, 250, 0.16);
}

html.dark .select-bar-inner {
  border-color: rgba(148, 163, 184, 0.2);
  background: rgba(255, 255, 255, 0.03);
}

html.dark .select-count {
  color: #cbd5e1;
  background: rgba(148, 163, 184, 0.2);
}

html.dark .select-all-checkbox :deep(.el-checkbox__label) {
  color: #cbd5e1;
}

html.dark .select-all-checkbox :deep(.el-checkbox__inner),
html.dark .conv-checkbox :deep(.el-checkbox__inner) {
  border-color: rgba(148, 163, 184, 0.5);
  background: rgba(255, 255, 255, 0.02);
}

html.dark .conv-item.select-mode:hover {
  background: rgba(96, 165, 250, 0.12);
  border-color: rgba(96, 165, 250, 0.3);
}

html.dark .conv-item.select-mode.selected {
  background: rgba(96, 165, 250, 0.18);
  border-color: rgba(96, 165, 250, 0.42);
}

html.dark .conv-item:hover {
  background: rgba(148, 163, 184, 0.12);
  border-color: rgba(148, 163, 184, 0.28);
}

html.dark .conv-item.active {
  background: rgba(59, 130, 246, 0.22);
  border-color: rgba(96, 165, 250, 0.42);
}

html.dark .conv-item + .conv-item::before {
  background: rgba(148, 163, 184, 0.24);
}

html.dark .conv-item + .conv-item::before {
  background: rgba(148, 163, 184, 0.24);
}

html.dark .conv-time,
html.dark .skill-summary-toggle,
html.dark .skill-summary-text {
  color: #94a3b8;
}

html.dark .conv-status-pill {
  color: #cbd5e1;
  border-color: rgba(148, 163, 184, 0.36);
  background: rgba(148, 163, 184, 0.16);
}

html.dark .conv-status-pill.is-success {
  color: #86efac;
  border-color: rgba(34, 197, 94, 0.46);
  background: rgba(34, 197, 94, 0.16);
}

html.dark .conv-status-pill.is-warning {
  color: #fcd34d;
  border-color: rgba(245, 158, 11, 0.5);
  background: rgba(245, 158, 11, 0.17);
}

html.dark .conv-status-pill.is-danger {
  color: #fca5a5;
  border-color: rgba(239, 68, 68, 0.5);
  background: rgba(239, 68, 68, 0.16);
}

html.dark .conv-status-pill.is-info {
  color: #93c5fd;
  border-color: rgba(59, 130, 246, 0.52);
  background: rgba(59, 130, 246, 0.17);
}

html.dark .conv-status-pill.is-neutral {
  color: #cbd5e1;
  border-color: rgba(148, 163, 184, 0.46);
  background: rgba(148, 163, 184, 0.2);
}

html.dark .skill-expanded-item {
  color: #cbd5e1;
  background: rgba(148, 163, 184, 0.18);
}

html.dark .tag-overflow-trigger,
html.dark .conv-action-btn:hover {
  background: rgba(148, 163, 184, 0.2);
  color: #cbd5e1;
  border-color: rgba(148, 163, 184, 0.3);
}

html.dark .conv-action-btn {
  background: rgba(15, 23, 42, 0.65);
  border-color: rgba(148, 163, 184, 0.34);
  color: #94a3b8;
}

html.dark .tag-picker-item:hover {
  background: rgba(148, 163, 184, 0.18);
}

html.dark .tag-picker-item.is-selected {
  background: rgba(59, 130, 246, 0.16);
}

html.dark .menu-section-title {
  color: #94a3b8;
}

html.dark .menu-section-title--danger {
  color: #fca5a5;
}

html.dark .menu-section-title--danger::before {
  background: linear-gradient(90deg, rgba(148, 163, 184, 0), rgba(148, 163, 184, 0.36), rgba(148, 163, 184, 0));
}

html.dark :deep(.tag-picker-dropdown.el-popper) {
  border-color: rgba(148, 163, 184, 0.3);
  box-shadow:
    0 18px 40px rgba(0, 0, 0, 0.46),
    0 4px 12px rgba(0, 0, 0, 0.3);
  border-radius: 20px !important;
  overflow: hidden !important;
}

html.dark :deep(.tag-picker-dropdown .el-popper__arrow::before) {
  border-color: rgba(255, 255, 255, 0.1);
  background: var(--bg-card, #1f2937);
}

html.dark :deep(.tag-picker-dropdown .el-dropdown-menu) {
  background: var(--bg-card, #1f2937);
  border-radius: 20px !important;
  overflow: hidden !important;
}

html.dark :deep(.row-delete-item) {
  color: #f87171;
  background: rgba(248, 113, 113, 0.12);
}

html.dark :deep(.tag-picker-dropdown .row-delete-item:not(.is-disabled):hover),
html.dark :deep(.tag-picker-dropdown .row-delete-item:not(.is-disabled):focus) {
  background: rgba(248, 113, 113, 0.2) !important;
  color: #fca5a5 !important;
}
</style>
