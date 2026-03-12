<template>
  <section class="sandbox-file-inspector">
    <div class="sandbox-file-inspector__header">
      <div v-if="badge" class="sandbox-file-inspector__badge">{{ badge }}</div>
      <h4 class="sandbox-file-inspector__title">{{ title }}</h4>
    </div>

    <template v-if="fileName">
      <div class="sandbox-file-inspector__hero">
        <div class="sandbox-file-inspector__file">
          <span class="sandbox-file-inspector__file-icon">
            <el-icon><Document /></el-icon>
          </span>
          <div class="sandbox-file-inspector__file-main">
            <div v-if="overline" class="sandbox-file-inspector__overline">{{ overline }}</div>
            <div class="sandbox-file-inspector__name">{{ fileName }}</div>
            <div v-if="filePath" class="sandbox-file-inspector__path">{{ filePath }}</div>
          </div>
        </div>
        <div v-if="tags.length" class="sandbox-file-inspector__tags">
          <el-tag
            v-for="tag in tags"
            :key="`${tag.label}-${tag.type || 'none'}-${tag.effect || 'none'}`"
            size="small"
            :type="tag.type"
            :effect="tag.effect || 'light'"
          >
            {{ tag.label }}
          </el-tag>
        </div>
      </div>

      <div
        v-if="actions.length"
        class="sandbox-file-inspector__actions"
        :class="{ 'is-compact': compactActions }"
      >
        <button
          v-for="action in actions"
          :key="action.key"
          type="button"
          :class="[
            'sandbox-file-inspector__btn',
            `sandbox-file-inspector__btn--${action.variant || 'secondary'}`,
          ]"
          :disabled="action.disabled"
          @click="emit('action', action.key)"
        >
          <el-icon v-if="action.icon"><component :is="action.icon" /></el-icon>
          <span class="sandbox-file-inspector__btn-label">{{ action.label }}</span>
        </button>
      </div>

      <div
        v-if="fields.length"
        class="sandbox-file-inspector__grid"
        :class="{ 'is-three': fields.length === 3 }"
      >
        <div v-for="field in fields" :key="field.label" class="sandbox-file-inspector__field">
          <span>{{ field.label }}</span>
          <strong :class="{ 'is-multiline': field.multiline }">{{ field.value || '-' }}</strong>
        </div>
      </div>

      <div class="sandbox-file-inspector__summary">
        <div class="sandbox-file-inspector__section-title">{{ summaryTitle }}</div>
        <div class="sandbox-file-inspector__summary-body">{{ summary || fallbackSummary }}</div>
      </div>
    </template>

    <div v-else class="sandbox-file-inspector__empty">{{ emptyText }}</div>
  </section>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import { Document } from '@element-plus/icons-vue'

interface InspectorTag {
  label: string
  type?: 'primary' | 'success' | 'warning' | 'info' | 'danger'
  effect?: 'dark' | 'light' | 'plain'
}

interface InspectorField {
  label: string
  value: string
  multiline?: boolean
}

interface InspectorAction {
  key: string
  label: string
  variant?: 'primary' | 'secondary' | 'danger'
  icon?: Component
  disabled?: boolean
}

withDefaults(defineProps<{
  badge?: string
  title?: string
  overline?: string
  fileName?: string
  filePath?: string
  tags?: InspectorTag[]
  fields?: InspectorField[]
  summary?: string
  summaryTitle?: string
  fallbackSummary?: string
  emptyText?: string
  actions?: InspectorAction[]
  compactActions?: boolean
}>(), {
  badge: '文件沙箱',
  title: '文件详情',
  overline: '当前聚焦文件',
  fileName: '',
  filePath: '',
  tags: () => [],
  fields: () => [],
  summary: '',
  summaryTitle: '说明',
  fallbackSummary: '可通过上方操作快速预览、下载或管理当前文件。',
  emptyText: '从左侧树中选择一个文件，这里会显示更完整的信息和快捷操作。',
  actions: () => [],
  compactActions: false,
})

const emit = defineEmits<{
  (e: 'action', key: string): void
}>()
</script>

<style scoped>
.sandbox-file-inspector {
  padding: 18px;
  border-radius: 24px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background:
    radial-gradient(circle at top right, rgba(96, 165, 250, 0.18), transparent 38%),
    linear-gradient(180deg, rgba(248, 250, 252, 0.98) 0%, rgba(241, 245, 249, 0.96) 100%);
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sandbox-file-inspector__header {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sandbox-file-inspector__title {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary, #1e293b);
}

.sandbox-file-inspector__badge {
  display: inline-flex;
  align-self: flex-start;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.92);
}

.sandbox-file-inspector__hero {
  padding: 18px;
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.14), transparent 42%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.88) 0%, rgba(248, 250, 252, 0.94) 100%);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.sandbox-file-inspector__file {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.sandbox-file-inspector__file-icon {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(219, 234, 254, 0.96) 0%, rgba(191, 219, 254, 0.82) 100%);
  color: #1d4ed8;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.sandbox-file-inspector__file-main {
  min-width: 0;
  flex: 1;
}

.sandbox-file-inspector__overline {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #2563eb;
  margin-bottom: 8px;
}

.sandbox-file-inspector__name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary, #1e293b);
  word-break: break-word;
}

.sandbox-file-inspector__path {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-muted, #64748b);
  word-break: break-all;
}

.sandbox-file-inspector__tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.sandbox-file-inspector__actions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
  gap: 10px;
}

.sandbox-file-inspector__actions.is-compact {
  display: flex;
  align-items: stretch;
  flex-wrap: nowrap;
  min-width: 0;
  gap: 8px;
}

.sandbox-file-inspector__btn {
  min-height: 42px;
  min-width: 96px;
  padding: 0 8px;
  border-radius: 14px;
  border: 1px solid transparent;
  font-size: 13px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.sandbox-file-inspector__actions.is-compact .sandbox-file-inspector__btn {
  flex: 1;
  min-width: 0;
}

.sandbox-file-inspector__btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.sandbox-file-inspector__btn:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.sandbox-file-inspector__btn-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: clip;
}

.sandbox-file-inspector__btn--primary {
  color: white;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  box-shadow: 0 16px 28px rgba(37, 99, 235, 0.24);
}

.sandbox-file-inspector__btn--secondary {
  color: var(--text-primary, #1e293b);
  border-color: rgba(148, 163, 184, 0.22);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(241, 245, 249, 0.96) 100%);
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
}

.sandbox-file-inspector__btn--danger {
  color: #991b1b;
  border-color: rgba(248, 113, 113, 0.32);
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.96) 0%, rgba(254, 226, 226, 0.92) 100%);
  box-shadow: 0 12px 24px rgba(220, 38, 38, 0.12);
}

.sandbox-file-inspector__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.sandbox-file-inspector__grid.is-three {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.sandbox-file-inspector__field {
  padding: 14px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.82) 0%, rgba(248, 250, 252, 0.86) 100%);
  border: 1px solid rgba(148, 163, 184, 0.16);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 82px;
}

.sandbox-file-inspector__field span {
  font-size: 11px;
  color: var(--text-muted, #64748b);
}

.sandbox-file-inspector__field strong {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary, #1e293b);
  word-break: break-word;
}

.sandbox-file-inspector__field strong.is-multiline {
  white-space: pre-wrap;
}

.sandbox-file-inspector__summary {
  padding: 16px;
  border-radius: 20px;
  border: 1px dashed rgba(148, 163, 184, 0.3);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.72) 0%, rgba(248, 250, 252, 0.8) 100%);
}

.sandbox-file-inspector__section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary, #475569);
  margin-bottom: 8px;
}

.sandbox-file-inspector__summary-body,
.sandbox-file-inspector__empty {
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-secondary, #475569);
  white-space: pre-wrap;
}

.sandbox-file-inspector__empty {
  padding: 18px;
  border-radius: 18px;
  border: 1px dashed rgba(148, 163, 184, 0.35);
  background: rgba(255, 255, 255, 0.5);
}

html.dark .sandbox-file-inspector,
html.dark .sandbox-file-inspector__field,
html.dark .sandbox-file-inspector__summary,
html.dark .sandbox-file-inspector__empty {
  border-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 78%, #4b5563 22%);
  background: linear-gradient(180deg, rgba(23, 27, 34, 0.96) 0%, rgba(18, 21, 27, 0.98) 100%);
  box-shadow: none;
}

html.dark .sandbox-file-inspector__hero,
html.dark .sandbox-file-inspector__btn--secondary {
  background: linear-gradient(180deg, rgba(30, 34, 42, 0.96) 0%, rgba(24, 28, 35, 0.92) 100%);
  border-color: color-mix(in srgb, var(--border-primary, #3a3a3a) 80%, #4b5563 20%);
}

html.dark .sandbox-file-inspector__title,
html.dark .sandbox-file-inspector__name,
html.dark .sandbox-file-inspector__field strong {
  color: #f8fafc;
}

html.dark .sandbox-file-inspector__path,
html.dark .sandbox-file-inspector__field span,
html.dark .sandbox-file-inspector__summary-body,
html.dark .sandbox-file-inspector__empty {
  color: rgba(226, 232, 240, 0.74);
}

html.dark .sandbox-file-inspector__badge {
  background: rgba(148, 163, 184, 0.08);
  color: #e2e8f0;
}

html.dark .sandbox-file-inspector__overline {
  color: #cbd5e1;
}

html.dark .sandbox-file-inspector__file-icon {
  background: rgba(148, 163, 184, 0.08);
  color: #cbd5e1;
  box-shadow: none;
}

html.dark .sandbox-file-inspector__btn--primary {
  background: rgba(148, 163, 184, 0.12);
  border-color: rgba(148, 163, 184, 0.16);
  color: #f8fafc;
  box-shadow: none;
}

html.dark .sandbox-file-inspector__btn--primary:hover:not(:disabled) {
  background: rgba(148, 163, 184, 0.18);
  border-color: rgba(148, 163, 184, 0.24);
}

html.dark .sandbox-file-inspector__btn--secondary {
  color: #f8fafc;
  box-shadow: none;
}

html.dark .sandbox-file-inspector__btn--danger {
  color: #fecaca;
  border-color: rgba(248, 113, 113, 0.38);
  background: linear-gradient(180deg, rgba(127, 29, 29, 0.35) 0%, rgba(69, 10, 10, 0.45) 100%);
  box-shadow: none;
}

@media (max-width: 640px) {
  .sandbox-file-inspector {
    padding: 14px;
    border-radius: 18px;
  }

  .sandbox-file-inspector__grid {
    grid-template-columns: 1fr;
  }

  .sandbox-file-inspector__actions.is-compact .sandbox-file-inspector__btn-label {
    display: none;
  }

  .sandbox-file-inspector__actions.is-compact .sandbox-file-inspector__btn {
    min-width: 42px;
    padding: 0;
  }
}
</style>
