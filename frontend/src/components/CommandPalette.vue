<script setup lang="ts">
import { ref } from 'vue'

interface CommandItem {
  key: string
  label: string
  description: string
}

const props = defineProps<{
  commands: CommandItem[]
  dialogCommands: CommandItem[]
}>()

const visible = ref(false)

const keyDisplayMap: Record<string, string> = {
  meta: '⌘', cmd: '⌘', command: '⌘',
  ctrl: '⌃', control: '⌃',
  alt: '⌥', option: '⌥',
  shift: '⇧',
  enter: '↵', return: '↵',
  escape: 'Esc', esc: 'Esc',
  backspace: '⌫', delete: '⌫',
  arrowup: '↑', arrowdown: '↓', arrowleft: '←', arrowright: '→',
}

function parseKeys(key: string): string[] {
  return key.split(/(?=[⌘⇧⌥⌃])|(?<=[⌘⇧⌥⌃])|\+/).filter(Boolean).map(k => {
    const normalized = k.trim().toLowerCase()
    return keyDisplayMap[normalized] || k.trim().toUpperCase()
  }).filter(k => k.length > 0)
}

function open() {
  visible.value = true
}

function close() {
  visible.value = false
}

defineExpose({ open, close, visible })
</script>

<template>
  <el-dialog
    v-model="visible"
    :show-close="true"
    width="900px"
    class="command-palette-dialog"
    append-to-body
    :destroy-on-close="false"
    :close-on-click-modal="true"
    :close-on-press-escape="true"
    align-center
  >
    <div class="cp-title">快捷键</div>
    <div class="cp-grid">
      <div class="cp-column">
        <div class="cp-column-title">全局快捷键</div>
        <div v-for="cmd in props.commands" :key="`${cmd.key}-${cmd.label}`" class="cp-row">
          <div class="cp-copy">
            <span class="cp-label">{{ cmd.label }}</span>
            <span class="cp-desc">{{ cmd.description }}</span>
          </div>
          <span class="cp-keys">
            <kbd v-for="(k, index) in parseKeys(cmd.key)" :key="`${cmd.key}-${index}`" class="cp-key">{{ k }}</kbd>
          </span>
        </div>
      </div>

      <div class="cp-column">
        <div class="cp-column-title">对话快捷键</div>
        <div v-for="cmd in props.dialogCommands" :key="`${cmd.key}-${cmd.label}`" class="cp-row">
          <div class="cp-copy">
            <span class="cp-label">{{ cmd.label }}</span>
            <span class="cp-desc">{{ cmd.description }}</span>
          </div>
          <span class="cp-keys">
            <kbd v-for="(k, index) in parseKeys(cmd.key)" :key="`${cmd.key}-${index}`" class="cp-key">{{ k }}</kbd>
          </span>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<style>
.command-palette-dialog.el-dialog {
  border-radius: 24px !important;
  overflow: hidden;
}

.command-palette-dialog .el-dialog__header {
  padding: 0;
  margin: 0;
  height: 0;
  border: none;
}

.command-palette-dialog .el-dialog__headerbtn {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 32px;
  height: 32px;
  z-index: 10;
}

.command-palette-dialog .el-dialog__headerbtn .el-dialog__close {
  color: var(--text-muted, #94a3b8);
  transition: color 0.2s;
  font-size: 16px;
}

.command-palette-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: var(--text-primary, #0f172a);
}

.command-palette-dialog .el-dialog__body {
  padding: 24px !important;
  background: var(--bg-primary, #ffffff);
}

html.dark .command-palette-dialog .el-dialog__body {
  background: var(--bg-primary, #1a1a1a);
}
</style>

<style scoped>
.cp-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

html.dark .cp-title {
  border-bottom-color: rgba(255, 255, 255, 0.06);
}

.cp-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
}

.cp-column-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary, #64748b);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

html.dark .cp-column-title {
  border-bottom-color: rgba(255, 255, 255, 0.06);
}

.cp-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  border-radius: 8px;
  transition: background 0.2s;
  margin-bottom: 2px;
}

.cp-row:hover {
  background: rgba(59, 130, 246, 0.04);
}

.cp-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.cp-label {
  font-size: 14px;
  color: var(--text-primary, #0f172a);
  font-weight: 500;
}

.cp-desc {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
}

.cp-keys {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}

.cp-key {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 8px;
  font-size: 11px;
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-weight: 500;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.9) 0%, rgba(255, 255, 255, 0.7) 100%);
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-bottom-width: 2px;
  border-radius: 6px;
  color: var(--text-primary, #0f172a);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

html.dark .cp-key {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.1) 0%, rgba(255, 255, 255, 0.05) 100%);
  border-color: rgba(255, 255, 255, 0.15);
  color: var(--text-primary, #f1f5f9);
}

@media (max-width: 900px) {
  .cp-grid {
    grid-template-columns: 1fr;
    gap: 20px;
  }
}
</style>
