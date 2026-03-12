<script setup lang="ts">
import { computed } from 'vue'
import SandboxFiles from '@/views/SandboxFiles.vue'

const props = defineProps<{
  currentConvId: number | null
  sandboxLauncherVisible: boolean
  sandboxPanelVisible: boolean
  unreadChangeCount: number
  sandboxLauncherDragging: boolean
  sandboxLauncherStyle: Record<string, string>
}>()

const emit = defineEmits<{
  'update:sandboxPanelVisible': [visible: boolean]
  'launcher-pointerdown': [event: PointerEvent]
  'launcher-pointermove': [event: PointerEvent]
  'launcher-pointerup': [event: PointerEvent]
  'launcher-pointercancel': [event: PointerEvent]
  'drawer-close': []
  'drawer-closed': []
}>()

const panelVisible = computed({
  get: () => props.sandboxPanelVisible,
  set: (value: boolean) => emit('update:sandboxPanelVisible', value),
})
</script>

<template>
  <button
    v-if="currentConvId && sandboxLauncherVisible"
    type="button"
    class="sandbox-launcher"
    :class="{
      'is-active': sandboxPanelVisible,
      'is-dragging': sandboxLauncherDragging,
    }"
    :style="sandboxLauncherStyle"
    @pointerdown="emit('launcher-pointerdown', $event)"
    @pointermove="emit('launcher-pointermove', $event)"
    @pointerup="emit('launcher-pointerup', $event)"
    @pointercancel="emit('launcher-pointercancel', $event)"
  >
    <el-icon class="sandbox-launcher-icon" :size="18"><FolderOpened /></el-icon>
    <span class="sandbox-launcher-copy">
      <strong>文件</strong>
    </span>
    <span v-if="unreadChangeCount > 0" class="sandbox-launcher-badge">
      {{ unreadChangeCount > 99 ? '99+' : unreadChangeCount }}
    </span>
  </button>

  <el-drawer
    v-model="panelVisible"
    direction="rtl"
    size="min(1320px, 97vw)"
    class="sandbox-drawer"
    modal-class="sandbox-drawer-mask"
    destroy-on-close
    append-to-body
    @close="emit('drawer-close')"
    @closed="emit('drawer-closed')"
  >
    <template #header>
      <div class="sandbox-drawer-header">
        <div class="sandbox-drawer-badge">历史对话工作区</div>
        <h3 class="sandbox-drawer-title">当前对话沙箱</h3>
        <p class="sandbox-drawer-subtitle">管理当前会话挂载的引用文件、上传附件和模型生成结果。</p>
      </div>
    </template>
    <SandboxFiles
      v-if="currentConvId"
      :conversation-id="currentConvId"
      :embedded="true"
    />
  </el-drawer>
</template>

<style scoped>
.sandbox-launcher {
  --sandbox-drawer-width: min(940px, 96vw);
  --sandbox-drawer-motion: 320ms cubic-bezier(0.22, 1, 0.36, 1);
  position: fixed;
  right: 18px;
  z-index: 2202;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 30px;
  min-height: 102px;
  padding: 10px 4px;
  border: 1px solid rgba(96, 165, 250, 0.22);
  border-radius: 18px 0 0 18px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.94) 0%, rgba(239, 246, 255, 0.98) 100%);
  box-shadow:
    0 14px 30px rgba(15, 23, 42, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.74);
  color: #0f172a;
  cursor: grab;
  user-select: none;
  touch-action: none;
  transform: translateX(0);
  transition:
    right var(--sandbox-drawer-motion),
    transform var(--sandbox-drawer-motion),
    opacity var(--sandbox-drawer-motion),
    box-shadow var(--sandbox-drawer-motion),
    border-color var(--sandbox-drawer-motion),
    background var(--sandbox-drawer-motion);
  overflow: hidden;
}

.sandbox-launcher:hover {
  transform: translateX(-3px);
  box-shadow:
    0 18px 36px rgba(37, 99, 235, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.84);
}

.sandbox-launcher.is-active {
  opacity: 0;
  pointer-events: none;
  transform: translateX(8px);
}

.sandbox-launcher.is-dragging {
  cursor: grabbing;
  transform: translateX(-5px) scale(1.01);
  box-shadow:
    0 22px 48px rgba(37, 99, 235, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.92);
}

.sandbox-launcher-copy {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  min-width: 0;
}

.sandbox-launcher-copy strong {
  font-size: 11px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  letter-spacing: 0.04em;
}

.sandbox-launcher-icon {
  position: relative;
  z-index: 1;
  color: #2563eb;
}

.sandbox-launcher-badge {
  position: absolute;
  top: 6px;
  right: 5px;
  z-index: 3;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: #ef4444;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
  text-align: center;
  box-shadow: 0 6px 14px rgba(239, 68, 68, 0.35);
}

.sandbox-drawer-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sandbox-drawer-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.sandbox-drawer-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

.sandbox-drawer-subtitle {
  margin: 0;
  color: var(--text-secondary, #64748b);
  font-size: 14px;
  line-height: 1.7;
}

:global(.sandbox-drawer) {
  --el-drawer-padding-primary: 22px;
  --sandbox-drawer-motion: 320ms cubic-bezier(0.22, 1, 0.36, 1);
}

:global(.sandbox-drawer .el-drawer__container) {
  padding: 18px 0 4px;
  box-sizing: border-box;
}

:global(.sandbox-drawer .el-drawer) {
  top: 0;
  bottom: 0;
  margin-top: 12px;
  margin-bottom: 4px;
  height: auto !important;
  max-height: calc(100vh - 20px);
  border-radius: 28px 0 0 28px;
  overflow: hidden;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--bg-card, #ffffff) 96%, var(--bg-page, #f8fafc) 4%) 0%, color-mix(in srgb, var(--bg-card, #ffffff) 98%, transparent 2%) 100%);
  box-shadow:
    0 28px 72px rgba(15, 23, 42, 0.24),
    0 8px 28px rgba(15, 23, 42, 0.12);
  animation: sandboxDrawerFloatIn 280ms cubic-bezier(0.22, 1, 0.36, 1);
  transition: transform var(--sandbox-drawer-motion) !important;
}

:global(.sandbox-drawer .el-drawer::before) {
  content: '';
  position: absolute;
  top: 50%;
  left: -30px;
  transform: translateY(-50%);
  width: 30px;
  height: 102px;
  border-radius: 18px 0 0 18px;
  border: 1px solid rgba(59, 130, 246, 0.22);
  border-right: none;
  background:
    linear-gradient(180deg, rgba(245, 250, 255, 0.98) 0%, rgba(233, 243, 255, 1) 100%);
  box-shadow:
    0 16px 34px rgba(37, 99, 235, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  pointer-events: none;
}

:global(.sandbox-drawer .el-drawer::after) {
  content: '文件';
  position: absolute;
  top: 50%;
  left: -26px;
  transform: translateY(-50%);
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.04em;
  color: #0f172a;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  pointer-events: none;
}

:global(.sandbox-drawer .el-drawer__header) {
  margin-bottom: 8px;
  padding-top: 26px;
  padding-bottom: 0;
}

:global(.sandbox-drawer .el-drawer__body) {
  padding: 6px 0 2px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

:global(.sandbox-drawer-mask) {
  background: rgba(15, 23, 42, 0.38);
  backdrop-filter: blur(5px);
}

@keyframes sandboxDrawerFloatIn {
  from {
    opacity: 0;
    transform: translateX(24px) scale(0.985);
  }
  to {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
}

:global(html.dark .sandbox-launcher) {
  border-color: rgba(125, 211, 252, 0.16);
  background:
    linear-gradient(135deg, rgba(15, 23, 42, 0.96) 0%, rgba(12, 19, 34, 0.98) 100%);
  box-shadow:
    0 18px 36px rgba(2, 6, 23, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

:global(html.dark .sandbox-launcher:hover),
:global(html.dark .sandbox-launcher.is-active) {
  background:
    linear-gradient(135deg, rgba(16, 33, 63, 0.98) 0%, rgba(11, 24, 43, 1) 100%);
  box-shadow:
    0 22px 44px rgba(2, 6, 23, 0.46),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

:global(html.dark .sandbox-drawer .el-drawer::before) {
  background:
    linear-gradient(180deg, rgba(16, 33, 63, 0.98) 0%, rgba(11, 24, 43, 1) 100%);
  border-color: rgba(125, 211, 252, 0.14);
  border-right: none;
  box-shadow:
    0 16px 34px rgba(2, 6, 23, 0.24),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

:global(html.dark .sandbox-drawer .el-drawer::after) {
  color: #f8fafc;
}

:global(html.dark .sandbox-launcher-copy strong) {
  color: #f8fafc;
}

:global(html.dark .sandbox-launcher-icon) {
  color: #93c5fd;
}

:global(html.dark .sandbox-drawer-badge) {
  background: rgba(96, 165, 250, 0.14);
  color: #bfdbfe;
}

:global(html.dark .sandbox-drawer-title) {
  color: #f8fafc;
}

:global(html.dark .sandbox-drawer-subtitle) {
  color: #94a3b8;
}

:global(html.dark .sandbox-drawer .el-drawer) {
  box-shadow:
    0 30px 84px rgba(2, 6, 23, 0.52),
    0 10px 34px rgba(2, 6, 23, 0.28);
  background:
    linear-gradient(180deg, rgba(17, 24, 39, 0.98) 0%, rgba(10, 15, 27, 1) 100%);
}

@media (max-width: 1200px) {
  .sandbox-launcher.is-active {
    right: calc(var(--sandbox-drawer-width) - 1px);
  }
}

@media (max-width: 768px) {
  .sandbox-launcher {
    right: 10px;
    width: 28px;
    min-height: 90px;
    padding: 8px 3px;
  }

  .sandbox-launcher.is-active {
    right: calc(var(--sandbox-drawer-width) - 1px);
  }
}
</style>
