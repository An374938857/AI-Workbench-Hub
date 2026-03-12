<script setup lang="ts">
const props = defineProps<{
  visible: boolean
  format: 'md' | 'docx'
  scope: 'last' | 'all'
  exporting: boolean
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'update:format': [value: 'md' | 'docx']
  'update:scope': [value: 'last' | 'all']
  submit: []
}>()
</script>

<template>
  <el-dialog
    :model-value="visible"
    width="480px"
    destroy-on-close
    class="styled-dialog"
    :show-close="false"
    @update:model-value="(value: boolean) => emit('update:visible', value)"
  >
    <template #header>
      <div class="dialog-header">
        <div class="dialog-header-icon export-icon">
          <el-icon :size="20"><Download /></el-icon>
        </div>
        <div>
          <div class="dialog-header-title">导出对话</div>
          <div class="dialog-header-desc">选择格式和范围，导出对话内容</div>
        </div>
      </div>
    </template>
    <div class="export-section">
      <div class="option-label">导出格式</div>
      <div class="option-cards">
        <button
          v-for="f in [{ val: 'md', label: 'Markdown', ext: '.md' }, { val: 'docx', label: 'Word', ext: '.docx' }]"
          :key="f.val"
          type="button"
          class="option-card"
          :class="{ active: format === f.val }"
          @click="emit('update:format', f.val as 'md' | 'docx')"
        >
          <span class="option-card-name">{{ f.label }}</span>
          <span class="option-card-ext">{{ f.ext }}</span>
        </button>
      </div>
    </div>
    <div class="export-section">
      <div class="option-label">导出范围</div>
      <div class="option-cards">
        <button
          v-for="s in [{ val: 'last', label: '最后一条', desc: '仅最后一条 AI 回复' }, { val: 'all', label: '全部内容', desc: '所有 AI 回复' }]"
          :key="s.val"
          type="button"
          class="option-card"
          :class="{ active: scope === s.val }"
          @click="emit('update:scope', s.val as 'last' | 'all')"
        >
          <span class="option-card-name">{{ s.label }}</span>
          <span class="option-card-ext">{{ s.desc }}</span>
        </button>
      </div>
    </div>
    <template #footer>
      <div class="dialog-footer">
        <button type="button" class="dialog-btn secondary" @click="emit('update:visible', false)">取消</button>
        <button type="button" class="dialog-btn primary" :disabled="exporting" @click="emit('submit')">
          <el-icon v-if="exporting" class="is-loading"><Loading /></el-icon>
          导出
        </button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.dialog-header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.dialog-header-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.dialog-header-icon.export-icon {
  background: linear-gradient(135deg, #e0f2fe, #dbeafe);
  color: #3b82f6;
}

html.dark .dialog-header-icon.export-icon {
  background: rgba(59, 130, 246, 0.15);
}

.dialog-header-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
}

.dialog-header-desc {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
  margin-top: 1px;
}

.export-section {
  margin-bottom: 24px;
}

.export-section:last-child {
  margin-bottom: 0;
}

.option-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted, #94a3b8);
  margin-bottom: 10px;
  letter-spacing: 0.3px;
}

.option-cards {
  display: flex;
  gap: 10px;
}

.option-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 16px 10px;
  border: 1.5px solid var(--border-primary, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  background: var(--bg-card, #fff);
  cursor: pointer;
  font-family: inherit;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}

.option-card:hover {
  border-color: rgba(59, 130, 246, 0.3);
}

.option-card.active {
  border-color: #3b82f6;
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.15);
  background: rgba(59, 130, 246, 0.03);
}

.option-card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
}

.option-card-ext {
  font-size: 11px;
  color: var(--text-muted, #94a3b8);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.dialog-btn {
  padding: 7px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.dialog-btn:active {
  transform: scale(0.97);
}

.dialog-btn.secondary {
  background: var(--bg-card, #fff);
  border-color: var(--border-primary, rgba(0, 0, 0, 0.1));
  color: var(--text-secondary, #64748b);
}

.dialog-btn.secondary:hover {
  background: var(--bg-hover, #f8fafc);
}

.dialog-btn.primary {
  background: #3b82f6;
  color: #fff;
}

.dialog-btn.primary:hover {
  background: #2f6fec;
}

.dialog-btn.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

html.dark .dialog-btn.primary {
  background: #397ef5;
}

html.dark .dialog-btn.primary:hover {
  background: #4d8bf7;
}

:global(.styled-dialog.el-dialog__wrapper .el-dialog),
.styled-dialog :deep(.el-dialog) {
  border-radius: 20px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.12), 0 0 1px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.styled-dialog :deep(.el-dialog__header) {
  padding: 28px 28px 18px;
  margin: 0;
}

.styled-dialog :deep(.el-dialog__body) {
  padding: 10px 28px 24px;
}

.styled-dialog :deep(.el-dialog__footer) {
  padding: 0 28px 28px;
}

:global(html.dark .styled-dialog .el-dialog) {
  border: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow: 0 16px 56px rgba(0, 0, 0, 0.45);
}

@media (max-width: 480px) {
  .option-cards {
    flex-direction: column;
  }
}
</style>
