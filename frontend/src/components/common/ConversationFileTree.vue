<template>
  <div class="conversation-file-tree">
    <div class="file-tree-toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="keyword"
          clearable
          :placeholder="searchPlaceholder"
          class="file-tree-search"
        />
        <span>{{ directoryCount }} 个目录</span>
        <span>{{ fileCount }} 个文件</span>
      </div>
      <div class="toolbar-right">
        <div class="tree-controls" role="tablist" aria-label="目录树展开控制">
          <button
            type="button"
            class="tree-control-button"
            :class="{ 'is-active': expandMode === 'top' }"
            @click="expandOneLevel"
          >
            展开一级
          </button>
          <button
            type="button"
            class="tree-control-button"
            :class="{ 'is-active': expandMode === 'all' }"
            @click="expandAll"
          >
            全部展开
          </button>
          <button
            type="button"
            class="tree-control-button"
            :class="{ 'is-active': expandMode === 'collapsed' }"
            @click="collapseAll"
          >
            全部收起
          </button>
        </div>
      </div>
    </div>

    <div v-loading="loading" class="tree-wrap">
      <el-tree
        v-if="filteredTree.length > 0"
        ref="treeRef"
        :data="filteredTree"
        node-key="key"
        :default-expanded-keys="expandedKeys"
        :expand-on-click-node="false"
        :empty-text="emptyTitle"
      >
        <template #default="{ data }">
          <div class="tree-node">
            <div
              class="tree-node-main"
              :class="{
                'is-selectable': selectable && data.type === 'file',
                'is-selected': data.item && selectedKeySet.has(String(data.item.key)),
                'is-recommended': data.item && recommendedKeySet.has(String(data.item.key)),
                'is-active': data.item && currentKeySet.has(String(data.item.key)),
              }"
              @click="handleNodeClick(data)"
              @dblclick.stop="handleNodeDblClick(data)"
            >
              <el-checkbox
                v-if="selectable && data.type === 'file' && data.item"
                :model-value="selectedKeySet.has(String(data.item.key))"
                class="node-checkbox"
                @click.stop
                @change="toggleSelection(data.item)"
              />
              <el-icon class="file-icon">
                <component :is="resolveIcon(data)" />
              </el-icon>
              <div class="tree-node-content">
                <div class="tree-node-head">
                  <span class="tree-node-label">{{ data.label }}</span>
                  <template v-if="data.item">
                    <el-tag
                      v-if="showSourceTag && data.item.sourceLabel"
                      :type="data.item.sourceTagType"
                      size="small"
                      class="node-tag"
                    >
                      {{ data.item.sourceLabel }}
                    </el-tag>
                    <el-tag
                      v-if="recommendedKeySet.has(String(data.item.key))"
                      size="small"
                      effect="light"
                      type="success"
                    >
                      推荐
                    </el-tag>
                    <span v-if="formatSize(data.item.fileSize)" class="node-meta">
                      {{ formatSize(data.item.fileSize) }}
                    </span>
                    <span v-if="formatTime(data.item.updatedAt)" class="node-meta">
                      {{ formatTime(data.item.updatedAt) }}
                    </span>
                  </template>
                </div>
                <div v-if="showPath && data.item" class="tree-node-path">{{ data.item.path }}</div>
                <div v-if="showSummary && data.item?.summary" class="tree-node-summary">
                  {{ data.item.summary }}
                </div>
              </div>
            </div>
            <div v-if="$slots.actions" class="tree-node-actions">
              <slot name="actions" :node="data" />
            </div>
          </div>
        </template>
      </el-tree>
      <div v-else-if="!loading" class="tree-empty-state">
        <div class="tree-empty-icon">
          <el-icon><Folder /></el-icon>
        </div>
        <div class="tree-empty-title">{{ emptyTitle }}</div>
        <div class="tree-empty-text">{{ emptyText }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { Document, Folder, Picture } from "@element-plus/icons-vue";
import type { ConversationFileTreeItem, ConversationFileTreeNode } from "@/utils/conversationFileTree";
import {
  buildConversationFileTree,
  collectConversationDirectoryKeys,
  countConversationDirectories,
  countConversationFiles,
  filterConversationFileTree,
  formatConversationFileSize,
  formatConversationFileTime,
} from "@/utils/conversationFileTree";

const props = withDefaults(defineProps<{
  items: ConversationFileTreeItem[];
  sortMode?: "directory-first" | "file-first";
  loading?: boolean;
  selectable?: boolean;
  selectedKeys?: Array<string | number>;
  recommendedKeys?: Array<string | number>;
  currentKey?: string | number | null;
  showSummary?: boolean;
  showPath?: boolean;
  showSourceTag?: boolean;
  selectOnRowClick?: boolean;
  searchPlaceholder?: string;
  emptyTitle?: string;
  emptyText?: string;
}>(), {
  sortMode: "directory-first",
  loading: false,
  selectable: false,
  selectedKeys: () => [],
  recommendedKeys: () => [],
  showSummary: false,
  showPath: true,
  showSourceTag: true,
  selectOnRowClick: false,
  searchPlaceholder: "按文件名模糊搜索",
  emptyTitle: "暂无文件",
  emptyText: "当前没有可展示的文件。",
});

const emit = defineEmits<{
  (e: "update:selectedKeys", value: Array<string | number>): void;
  (e: "file-click", item: ConversationFileTreeItem): void;
  (e: "file-dblclick", item: ConversationFileTreeItem): void;
}>();

const keyword = ref("");
const treeRef = ref();
const expandedKeys = ref<string[]>([]);

const selectedKeySet = computed(() => new Set((props.selectedKeys || []).map((item) => String(item))));
const recommendedKeySet = computed(() => new Set((props.recommendedKeys || []).map((item) => String(item))));
const currentKeySet = computed(() =>
  props.currentKey == null ? new Set<string>() : new Set([String(props.currentKey)]),
);
const treeData = computed<ConversationFileTreeNode[]>(() =>
  orderConversationTree(buildConversationFileTree(props.items), props.sortMode),
);
const filteredTree = computed<ConversationFileTreeNode[]>(() =>
  filterConversationFileTree(treeData.value, keyword.value),
);
const directoryKeys = computed(() => collectConversationDirectoryKeys(filteredTree.value));
const topLevelDirectoryKeys = computed(() =>
  filteredTree.value.filter((node) => node.type === "directory").map((node) => node.key),
);
const directoryCount = computed(() => countConversationDirectories(filteredTree.value));
const fileCount = computed(() => countConversationFiles(filteredTree.value));
const expandMode = computed<"all" | "top" | "collapsed" | "custom">(() => {
  if (!directoryKeys.value.length || !expandedKeys.value.length) {
    return "collapsed";
  }

  const expanded = [...expandedKeys.value].sort().join("|");
  const allKeys = [...directoryKeys.value].sort().join("|");
  const topKeys = [...topLevelDirectoryKeys.value].sort().join("|");
  if (expanded === allKeys) return "all";
  if (expanded === topKeys) return "top";
  return "custom";
});

watch(
  filteredTree,
  (tree) => {
    if (!tree.length) {
      expandedKeys.value = [];
      return;
    }
    void applyExpandedKeys(directoryKeys.value);
  },
  { immediate: true },
);

function resolveIcon(node: ConversationFileTreeNode) {
  if (node.type === "directory") return Folder;
  const type = String(node.item?.fileType || "").toLowerCase();
  if (["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"].includes(type)) {
    return Picture;
  }
  return Document;
}

function formatSize(value?: number | null) {
  return formatConversationFileSize(value);
}

function formatTime(value?: string | null) {
  return formatConversationFileTime(value);
}

function emitSelected(next: string[]) {
  emit("update:selectedKeys", next);
}

function toggleSelection(item: ConversationFileTreeItem) {
  const next = new Set((props.selectedKeys || []).map((value) => String(value)));
  const key = String(item.key);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  emitSelected(Array.from(next));
}

function handleNodeClick(node: ConversationFileTreeNode) {
  if (node.type !== "file" || !node.item) {
    return;
  }
  emit("file-click", node.item);
  if (props.selectable && props.selectOnRowClick) {
    toggleSelection(node.item);
  }
}

function handleNodeDblClick(node: ConversationFileTreeNode) {
  if (node.type !== "file" || !node.item) return;
  emit("file-dblclick", node.item);
}

function orderConversationTree(
  nodes: ConversationFileTreeNode[],
  sortMode: "directory-first" | "file-first",
): ConversationFileTreeNode[] {
  const copied = nodes.map((node) => ({
    ...node,
    children: node.children ? orderConversationTree(node.children, sortMode) : undefined,
  }));

  copied.sort((left, right) => {
    if (left.type !== right.type) {
      if (sortMode === "file-first") return left.type === "file" ? -1 : 1;
      return left.type === "directory" ? -1 : 1;
    }
    return left.label.localeCompare(right.label, "zh-CN");
  });

  return copied;
}

async function applyExpandedKeys(keys: string[]) {
  expandedKeys.value = [...keys];
  await nextTick();

  const store = treeRef.value?.store;
  const nodesMap = store?.nodesMap as Record<string, { key: string; expanded: boolean; data?: ConversationFileTreeNode }> | undefined;
  if (!nodesMap) return;

  const expandedSet = new Set(keys);
  Object.values(nodesMap).forEach((node) => {
    if (node?.data?.type === "directory") {
      node.expanded = expandedSet.has(node.key);
    }
  });
}

function expandAll() {
  void applyExpandedKeys(directoryKeys.value);
}

function expandOneLevel() {
  void applyExpandedKeys(topLevelDirectoryKeys.value);
}

function collapseAll() {
  void applyExpandedKeys([]);
}
</script>

<style scoped>
.conversation-file-tree {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.file-tree-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--text-muted, #64748b);
  font-size: 12px;
}

.file-tree-search {
  width: min(340px, 72vw);
}

:deep(.file-tree-search .el-input__wrapper) {
  border-radius: 999px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.18) inset;
  background: rgba(255, 255, 255, 0.96);
}

.tree-controls {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tree-control-button {
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(255, 255, 255, 0.88);
  color: var(--text-secondary, #475569);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tree-control-button:hover,
.tree-control-button:focus-visible,
.tree-control-button.is-active {
  border-color: rgba(59, 130, 246, 0.3);
  color: #1d4ed8;
  background: rgba(239, 246, 255, 0.96);
}

.tree-wrap {
  min-height: 220px;
  background: transparent;
}

:deep(.el-tree) {
  background: transparent;
}

:deep(.el-tree-node__content) {
  height: auto;
  padding: 6px 0;
  border-radius: 14px;
}

:deep(.el-tree-node__content:hover) {
  background: rgba(59, 130, 246, 0.06);
}

.tree-node {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.tree-node-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: 14px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.tree-node-main.is-selectable {
  cursor: pointer;
}

.tree-node-main.is-selected {
  border-color: rgba(37, 99, 235, 0.38);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  background: rgba(239, 246, 255, 0.78);
}

.tree-node-main.is-recommended:not(.is-selected) {
  border-color: rgba(34, 197, 94, 0.28);
  background: rgba(240, 253, 244, 0.7);
}

.tree-node-main.is-active:not(.is-selected) {
  border-color: rgba(59, 130, 246, 0.24);
  background: rgba(248, 250, 252, 0.92);
}

.node-checkbox {
  flex-shrink: 0;
}

.file-icon {
  flex-shrink: 0;
  color: #64748b;
}

.tree-node-content {
  flex: 1;
  min-width: 0;
}

.tree-node-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tree-node-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
  line-height: 1.4;
  word-break: break-word;
}

.node-meta {
  font-size: 11px;
  color: var(--text-muted, #64748b);
}

.tree-node-path {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-muted, #64748b);
  word-break: break-all;
}

.tree-node-summary {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(148, 163, 184, 0.3);
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-secondary, #475569);
  white-space: pre-wrap;
}

.tree-node-actions {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  padding-right: 8px;
}

.tree-empty-state {
  min-height: 240px;
  border: 1px dashed rgba(148, 163, 184, 0.28);
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(248, 250, 252, 0.72);
  text-align: center;
  padding: 24px;
}

.tree-empty-icon {
  width: 52px;
  height: 52px;
  border-radius: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
  font-size: 22px;
}

.tree-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
}

.tree-empty-text {
  max-width: 420px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-muted, #64748b);
}

@media (max-width: 900px) {
  .file-tree-toolbar {
    padding: 0 8px;
    gap: 10px;
  }

  .toolbar-left,
  .toolbar-right {
    width: 100%;
  }

  .file-tree-search {
    width: 100%;
    min-width: 0;
  }
}

html.dark .toolbar-left,
html.dark .toolbar-right,
html.dark .node-meta,
html.dark .tree-node-path,
html.dark .tree-empty-text {
  color: rgba(226, 232, 240, 0.74);
}

html.dark :deep(.file-tree-search .el-input__wrapper) {
  background: rgba(15, 23, 42, 0.9);
  box-shadow: 0 0 0 1px rgba(71, 85, 105, 0.5) inset;
}

html.dark .tree-control-button {
  background: rgba(15, 23, 42, 0.9);
  border-color: rgba(71, 85, 105, 0.5);
  color: rgba(226, 232, 240, 0.82);
}

html.dark .tree-control-button:hover,
html.dark .tree-control-button:focus-visible,
html.dark .tree-control-button.is-active {
  background: rgba(30, 41, 59, 0.96);
  color: #93c5fd;
  border-color: rgba(96, 165, 250, 0.35);
}

html.dark :deep(.el-tree-node__content:hover) {
  background: rgba(59, 130, 246, 0.14);
}

:global(html.dark) .conversation-file-tree :deep(.el-tree),
:global(html.dark) .conversation-file-tree :deep(.el-tree-node),
:global(html.dark) .conversation-file-tree :deep(.el-tree-node__content) {
  background: transparent;
  color: var(--text-primary, #e5e5e5);
}

html.dark .tree-node-main.is-selected {
  background: rgba(30, 41, 59, 0.92);
  border-color: rgba(96, 165, 250, 0.42);
}

html.dark .tree-node-main.is-recommended:not(.is-selected) {
  background: rgba(20, 83, 45, 0.34);
  border-color: rgba(34, 197, 94, 0.28);
}

html.dark .tree-node-main.is-active:not(.is-selected) {
  background: rgba(30, 41, 59, 0.82);
  border-color: rgba(96, 165, 250, 0.28);
}

html.dark .tree-node-label,
html.dark .tree-empty-title {
  color: #f8fafc;
}

html.dark .tree-node-summary {
  border-top-color: rgba(71, 85, 105, 0.7);
  color: rgba(226, 232, 240, 0.88);
}

html.dark .tree-empty-state {
  background: rgba(15, 23, 42, 0.72);
  border-color: rgba(71, 85, 105, 0.55);
}

html.dark .tree-empty-icon {
  background: rgba(30, 64, 175, 0.2);
  color: #93c5fd;
}

@media (max-width: 768px) {
  .file-tree-search {
    width: 100%;
  }

  .file-tree-toolbar {
    align-items: stretch;
  }

  .toolbar-left,
  .toolbar-right {
    width: 100%;
  }

  .tree-node-main {
    padding: 8px 10px;
  }
}
</style>
