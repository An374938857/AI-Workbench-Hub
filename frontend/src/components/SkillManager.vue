<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, CircleCheck, Close } from '@element-plus/icons-vue'
import { showDangerConfirm } from '@/composables/useDangerConfirm'

interface ActiveSkill {
  id: number
  name: string
  brief_desc: string
}

interface SkillActivatedEvent extends ActiveSkill {
  resumeAssistantMessageId?: number | null
  resumeToolMessageId?: number | null
}

interface SkillRejectedEvent {
  id: number
  name: string
  resumeAssistantMessageId?: number | null
  resumeToolMessageId?: number | null
}

const props = defineProps<{
  conversationId: number | null
}>()

const emit = defineEmits<{
  (e: 'skill-activated', skill: SkillActivatedEvent): void
  (e: 'skill-rejected', skill: SkillRejectedEvent): void
  (e: 'skill-deactivated', skillId: number): void
}>()

// 激活的 Skill 列表
const activeSkills = ref<ActiveSkill[]>([])
const loading = ref(false)
const showConfirmDialog = ref(false)
const pendingSkill = ref<{ id: number; name: string; description: string } | null>(null)
const handlingDecision = ref(false)
const suppressAutoRejectOnClose = ref(false)

// Skill 数量提示
const skillCountText = computed(() => {
  if (activeSkills.value.length === 0) return '未激活技能'
  return `已激活 ${activeSkills.value.length}/3 个技能`
})
const activeSkillCount = computed(() => activeSkills.value.length)
const isSkillLimitReached = computed(() => activeSkills.value.length >= 3)

const canActivateMore = computed(() => activeSkills.value.length < 3)

// 加载激活的 Skill 列表
async function loadActiveSkills() {
  if (!props.conversationId) return

  loading.value = true
  try {
    const response = await fetch(`/api/conversations/${props.conversationId}/skills`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      }
    })

    if (!response.ok) {
      throw new Error('加载失败')
    }

    const result = await response.json()
    if (result.data) {
      activeSkills.value = result.data
    }
  } catch (error) {
    console.error('加载激活的 Skill 失败:', error)
  } finally {
    loading.value = false
  }
}

// 停用 Skill
async function deactivateSkill(skillId: number) {
  if (!props.conversationId) return

  try {
    const skillName = activeSkills.value.find((skill) => skill.id === skillId)?.name || `技能 #${skillId}`
    await showDangerConfirm({
      title: '停用技能',
      subject: skillName,
      detail: '停用后该技能的功能将不再可用，但不会删除既有对话内容。',
      confirmText: '确认停用',
    })

    const response = await fetch(
      `/api/conversations/${props.conversationId}/skills/${skillId}`,
      {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      }
    )

    if (!response.ok) {
      throw new Error('停用失败')
    }

    ElMessage.success('技能已停用')
    emit('skill-deactivated', skillId)
    await loadActiveSkills()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '停用失败')
    }
  }
}

// 显示 Skill 激活确认弹窗
function showSkillActivation(skill: { id: number; name: string; description: string }) {
  pendingSkill.value = skill
  showConfirmDialog.value = true
}

function handleConfirmDialogClosed() {
  if (
    pendingSkill.value
    && !handlingDecision.value
    && !suppressAutoRejectOnClose.value
  ) {
    void rejectActivateSkill({ silent: true, closeDialog: false })
    return
  }
  suppressAutoRejectOnClose.value = false
  pendingSkill.value = null
}

// 确认激活 Skill
async function confirmActivateSkill() {
  if (!props.conversationId || !pendingSkill.value) return

  const skill = pendingSkill.value
  const skillId = skill.id
  handlingDecision.value = true
  suppressAutoRejectOnClose.value = true
  showConfirmDialog.value = false

  try {
    const response = await fetch(
      `/api/conversations/${props.conversationId}/skills/${skillId}/confirm`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      }
    )

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.message || '激活失败')
    }

    const result = await response.json()
    if (!result?.data?.success) {
      throw new Error(result?.data?.message || '激活失败')
    }
    ElMessage.success(result?.data?.message || `已激活技能「${skill.name}」`)
    emit('skill-activated', {
      id: skillId,
      name: skill.name,
      brief_desc: skill.description,
      resumeAssistantMessageId: result?.data?.resume_assistant_message_id ?? null,
      resumeToolMessageId: result?.data?.resume_tool_message_id ?? null,
    })
    await loadActiveSkills()
  } catch (error: any) {
    ElMessage.error(error.message || '激活失败')
  } finally {
    handlingDecision.value = false
  }
}

// 拒绝激活 Skill
async function rejectActivateSkill(options?: { silent?: boolean; closeDialog?: boolean }) {
  if (!props.conversationId || !pendingSkill.value) return

  const skill = pendingSkill.value
  const skillId = skill.id
  const silent = options?.silent ?? false
  const closeDialog = options?.closeDialog ?? true
  handlingDecision.value = true
  suppressAutoRejectOnClose.value = true
  if (closeDialog) {
    showConfirmDialog.value = false
  }

  try {
    const response = await fetch(
      `/api/conversations/${props.conversationId}/skills/${skillId}/reject`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        keepalive: true,
      },
    )

    if (!response.ok) {
      throw new Error('拒绝激活失败')
    }

    const result = await response.json()
    emit('skill-rejected', {
      id: skillId,
      name: skill.name,
      resumeAssistantMessageId: result?.data?.resume_assistant_message_id ?? null,
      resumeToolMessageId: result?.data?.resume_tool_message_id ?? null,
    })
    if (!silent) {
      ElMessage.info(result?.data?.message || `已拒绝加载技能「${skill.name}」`)
    }
  } catch (error: any) {
    if (!silent) {
      ElMessage.error(error.message || '拒绝激活失败')
    }
  } finally {
    handlingDecision.value = false
    if (!showConfirmDialog.value) {
      pendingSkill.value = null
    }
  }
}

function hasPendingSkillActivation() {
  return !!pendingSkill.value
}

async function rejectPendingSkillActivation() {
  if (!pendingSkill.value) return
  await rejectActivateSkill({ silent: true })
}

watch(
  () => props.conversationId,
  (newId, oldId) => {
    if (oldId && newId !== oldId && pendingSkill.value) {
      void rejectActivateSkill({ silent: true })
    }
  },
)

// 暴露方法给父组件
defineExpose({
  showSkillActivation,
  loadActiveSkills,
  hasPendingSkillActivation,
  rejectPendingSkillActivation,
})

// 监听对话 ID 变化
watch(() => props.conversationId, (newId) => {
  if (newId) {
    loadActiveSkills()
  } else {
    activeSkills.value = []
  }
}, { immediate: true })

onMounted(() => {
  if (props.conversationId) {
    loadActiveSkills()
  }
})

onBeforeUnmount(() => {
  if (pendingSkill.value) {
    void rejectActivateSkill({ silent: true })
  }
})
</script>

<template>
  <div class="skill-manager">
    <!-- Skill 状态条 -->
    <div v-show="activeSkills.length > 0" class="skill-status-bar" :title="skillCountText">
      <div class="skill-status-info">
        <span class="skill-status-icon">
          <el-icon><MagicStick /></el-icon>
        </span>
        <span class="skill-status-label">技能</span>
        <Transition name="count-swap" mode="out-in">
          <span :key="activeSkillCount" class="skill-status-count" :class="{ 'is-limit': isSkillLimitReached }">{{ activeSkillCount }}/3</span>
        </Transition>
      </div>

      <TransitionGroup name="skill-chip" tag="div" class="active-skills-list">
        <el-tag
          v-for="skill in activeSkills"
          :key="skill.id"
          class="skill-tag"
          effect="dark"
          closable
          @close="deactivateSkill(skill.id)"
        >
          {{ skill.name }}
        </el-tag>
      </TransitionGroup>
    </div>

    <!-- Skill 激活确认弹窗 -->
    <el-dialog
      v-model="showConfirmDialog"
      width="min(436px, calc(100vw - 32px))"
      :show-close="false"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      class="skill-confirm-dialog"
      align-center
      destroy-on-close
      @closed="handleConfirmDialogClosed"
    >
      <div class="skill-confirm-header">
        <div class="skill-icon-shell">
          <span class="skill-icon-orbit skill-icon-orbit-left"></span>
          <span class="skill-icon-orbit skill-icon-orbit-right"></span>
          <div class="skill-icon">
            <el-icon class="skill-icon-glyph" :size="30"><MagicStick /></el-icon>
          </div>
        </div>
        <div class="skill-title-group">
          <div class="skill-title">激活技能</div>
          <div class="skill-subtitle">确认后将为当前对话解锁对应能力</div>
        </div>
      </div>

      <div v-if="pendingSkill" class="skill-confirm-content">
        <div class="skill-name">「{{ pendingSkill.name }}」</div>
        <div class="skill-description">{{ pendingSkill.description }}</div>

        <div class="skill-limit-hint" v-if="!canActivateMore">
          <el-alert
            title="已达到最大激活数量（3个）"
            description="激活新技能将替换最早激活的技能"
            type="warning"
            :closable="false"
          />
        </div>
      </div>

      <template #footer>
        <div class="skill-confirm-actions">
          <el-button class="skill-action-btn is-ghost" @click="rejectActivateSkill">
            <el-icon><Close /></el-icon>
            <span>拒绝</span>
          </el-button>
          <el-button class="skill-action-btn is-primary" @click="confirmActivateSkill">
            <el-icon><CircleCheck /></el-icon>
            <span>激活</span>
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.skill-manager {
  display: block;
  min-height: 0;
  line-height: 0;
}

.skill-status-bar {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  max-width: 100%;
  min-height: 42px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(139, 123, 198, 0.28);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.94)),
    radial-gradient(circle at 16% 50%, rgba(196, 181, 253, 0.24), transparent 52%);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.92) inset,
    0 6px 18px rgba(15, 23, 42, 0.08);
  overflow-x: auto;
  scrollbar-width: none;
}

.skill-status-bar::-webkit-scrollbar {
  display: none;
}

.skill-status-info {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 2px;
  flex-shrink: 0;
}

.skill-status-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #7c6ab8;
  background: rgba(139, 123, 198, 0.14);
}

.skill-status-label {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.skill-status-count {
  min-width: 34px;
  text-align: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
  color: #5b4f86;
  background: linear-gradient(135deg, rgba(221, 214, 254, 0.65), rgba(139, 123, 198, 0.34));
}

.skill-status-count.is-limit {
  color: #f5f3ff;
  background: linear-gradient(135deg, #8b7bc6, #6f5cb3);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.25) inset,
    0 6px 14px rgba(111, 92, 179, 0.3);
  animation: count-limit-pulse 0.9s ease-out 1;
}

.active-skills-list {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 6px;
  min-width: 0;
}

.skill-tag {
  --el-tag-bg-color: #8b7bc6;
  --el-tag-border-color: #8b7bc6;
  --el-tag-hover-color: #7c6ab8;
  --el-tag-text-color: #fff;
  border-radius: 12px;
  padding: 4px 10px;
  max-width: 180px;
  white-space: nowrap;
  flex-shrink: 0;
}

.skill-tag :deep(.el-tag__content) {
  overflow: hidden;
  text-overflow: ellipsis;
}

.skill-tag :deep(.el-tag__close) {
  color: #fff;
  margin-left: 4px;
}

.skill-tag :deep(.el-tag__close:hover) {
  background-color: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.count-swap-enter-active,
.count-swap-leave-active {
  transition: all 0.16s ease;
}

.count-swap-enter-from {
  opacity: 0;
  transform: translateY(-3px) scale(0.96);
}

.count-swap-leave-to {
  opacity: 0;
  transform: translateY(3px) scale(0.96);
}

.skill-chip-enter-active,
.skill-chip-leave-active {
  transition: all 0.18s ease;
}

.skill-chip-enter-from,
.skill-chip-leave-to {
  opacity: 0;
  transform: translateY(3px) scale(0.92);
}

.skill-chip-move {
  transition: transform 0.18s ease;
}

/* 确认弹窗样式 */
:global(.skill-confirm-dialog .el-dialog),
:global(.el-dialog.skill-confirm-dialog) {
  --el-dialog-padding-primary: 0px;
  border-radius: 26px;
  display: flex;
  flex-direction: column;
  min-height: 490px;
  max-width: calc(100vw - 32px);
  overflow: hidden;
  padding: 0 !important;
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.97));
  box-shadow:
    0 28px 80px rgba(15, 23, 42, 0.28),
    0 8px 24px rgba(139, 123, 198, 0.16);
}

:global(.skill-confirm-dialog .el-dialog__header),
:global(.el-dialog.skill-confirm-dialog .el-dialog__header) {
  display: none !important;
}

:global(.skill-confirm-dialog .el-dialog__body),
:global(.el-dialog.skill-confirm-dialog .el-dialog__body) {
  padding: 0 !important;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
}

:global(.skill-confirm-dialog .el-dialog__footer),
:global(.el-dialog.skill-confirm-dialog .el-dialog__footer) {
  padding: 0 28px 28px !important;
}

.skill-confirm-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin: 0;
  min-height: 182px;
  padding: 22px 30px 18px;
  width: 100%;
  box-sizing: border-box;
  border-radius: 26px 26px 0 0;
  overflow: hidden;
  background: linear-gradient(160deg, #f1ebff 0%, #e7ddff 42%, #ddd1ff 100%);
  position: relative;
}

.skill-confirm-header::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(130% 90% at 50% -12%, rgba(255, 255, 255, 0.54), rgba(255, 255, 255, 0) 64%),
    radial-gradient(80% 70% at 18% 24%, rgba(196, 181, 253, 0.3), rgba(196, 181, 253, 0) 74%);
  pointer-events: none;
}

.skill-confirm-header::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(139, 123, 198, 0.28), transparent);
}

.skill-icon-shell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 84px;
  height: 84px;
}

.skill-icon-shell::before {
  content: '';
  position: absolute;
  inset: 10px;
  border-radius: 999px;
  background: radial-gradient(circle at 36% 30%, rgba(196, 181, 253, 0.31), rgba(167, 139, 250, 0.07) 56%, transparent 76%);
  z-index: 0;
  animation: skill-icon-halo 3.6s ease-in-out infinite;
}

.skill-icon-shell::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(167, 139, 250, 0.17) 0%, rgba(167, 139, 250, 0.05) 48%, transparent 72%);
  z-index: 0;
  animation: skill-icon-halo 3.6s ease-in-out infinite reverse;
}

.skill-icon {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 2;
  animation: skill-icon-float 3.6s ease-in-out infinite;
}

.skill-icon-glyph {
  color: #8b7bc6;
  filter: drop-shadow(0 4px 10px rgba(111, 92, 179, 0.4));
  animation: skill-glyph-breathe 3.6s ease-in-out infinite;
}

.skill-icon-orbit {
  position: absolute;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(196, 181, 253, 0.98), rgba(124, 106, 184, 0.78));
  box-shadow: 0 10px 18px rgba(124, 106, 184, 0.26);
}

.skill-icon-orbit-left {
  width: 10px;
  height: 10px;
  top: 14px;
  left: 2px;
  animation: skill-orbit-left 4.2s ease-in-out infinite;
}

.skill-icon-orbit-right {
  width: 14px;
  height: 14px;
  right: 0;
  bottom: 14px;
  animation: skill-orbit-right 3.8s ease-in-out infinite;
}

.skill-title-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
  line-height: normal;
}

.skill-title {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #6550a8;
  line-height: 1.25;
}

.skill-subtitle {
  margin-top: 0;
  font-size: 13px;
  line-height: 1.5;
  color: #6b7280;
}

.skill-confirm-content {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  justify-content: center;
  text-align: center;
  min-height: 224px;
  padding: 28px 30px 20px;
}

.skill-name {
  font-size: 24px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 14px;
  line-height: 1.3;
}

.skill-description {
  font-size: 14px;
  color: #6b7280;
  line-height: 1.75;
  max-width: 320px;
  margin: 0 auto;
  text-align: left;
}

.skill-limit-hint {
  margin-top: 22px;
}

.skill-limit-hint :deep(.el-alert) {
  border-radius: 16px;
  text-align: left;
  border: 1px solid rgba(245, 158, 11, 0.18);
}

.skill-confirm-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  padding-top: 6px;
}

.skill-confirm-actions .skill-action-btn {
  min-width: 116px;
  height: 44px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-radius: 14px;
  font-weight: 600;
  letter-spacing: 0.01em;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.skill-confirm-actions .skill-action-btn:hover {
  transform: translateY(-1px);
}

.skill-confirm-actions .skill-action-btn :deep(.el-icon) {
  margin: 0;
  font-size: 15px;
  display: inline-flex;
}

.skill-confirm-actions .skill-action-btn span {
  display: inline-flex;
  align-items: center;
  line-height: 1;
}

.skill-confirm-actions .skill-action-btn.is-ghost {
  border-color: rgba(148, 163, 184, 0.32);
  background: rgba(255, 255, 255, 0.72);
  color: #475569;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.65),
    0 6px 14px rgba(15, 23, 42, 0.06);
}

.skill-confirm-actions .skill-action-btn.is-ghost:hover {
  border-color: rgba(100, 116, 139, 0.42);
  background: rgba(248, 250, 252, 0.94);
}

.skill-confirm-actions .skill-action-btn.is-primary {
  border-color: transparent;
  color: #fff;
  background: linear-gradient(135deg, #8b7bc6, #6f5cb3);
  box-shadow: 0 12px 24px rgba(111, 92, 179, 0.26);
}

.skill-confirm-actions .skill-action-btn.is-primary:hover {
  box-shadow: 0 16px 30px rgba(111, 92, 179, 0.34);
}

:global(html.dark .skill-confirm-dialog .el-dialog),
:global(html.dark .el-dialog.skill-confirm-dialog) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.96), rgba(2, 6, 23, 0.98));
}

html.dark .skill-confirm-header {
  background: linear-gradient(160deg, #4e3f7d 0%, #40336b 42%, #312953 100%);
}

html.dark .skill-confirm-header::before {
  background:
    radial-gradient(130% 90% at 50% -12%, rgba(196, 181, 253, 0.34), rgba(196, 181, 253, 0) 64%),
    radial-gradient(80% 70% at 18% 24%, rgba(167, 139, 250, 0.2), rgba(167, 139, 250, 0) 74%);
}

html.dark .skill-title {
  color: #c4b5fd;
}

html.dark .skill-subtitle,
html.dark .skill-description {
  color: #94a3b8;
}

html.dark .skill-name {
  color: #e5e7eb;
}

html.dark .skill-icon {
  background: transparent;
}

html.dark .skill-icon-glyph {
  color: #c4b5fd;
  filter: drop-shadow(0 4px 10px rgba(124, 106, 184, 0.5));
}

html.dark .skill-icon-shell::before {
  background: radial-gradient(circle at 36% 30%, rgba(167, 139, 250, 0.26), rgba(76, 65, 120, 0.08) 56%, transparent 76%);
}

html.dark .skill-icon-shell::after {
  background: radial-gradient(circle, rgba(167, 139, 250, 0.2) 0%, rgba(124, 106, 184, 0.07) 48%, transparent 72%);
}

html.dark .skill-confirm-actions .skill-action-btn.is-ghost {
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.82), rgba(15, 23, 42, 0.68));
  color: #cbd5e1;
  border-color: rgba(71, 85, 105, 0.72);
  box-shadow:
    inset 0 1px 0 rgba(148, 163, 184, 0.08),
    0 8px 18px rgba(2, 6, 23, 0.24);
}

html.dark .skill-confirm-actions .skill-action-btn.is-ghost:hover,
html.dark .skill-confirm-actions .skill-action-btn.is-ghost:focus-visible {
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.9), rgba(15, 23, 42, 0.78));
  color: #e2e8f0;
  border-color: rgba(100, 116, 139, 0.78);
  box-shadow:
    inset 0 1px 0 rgba(148, 163, 184, 0.12),
    0 10px 22px rgba(2, 6, 23, 0.28);
}

html.dark .skill-status-bar {
  border-color: rgba(139, 123, 198, 0.36);
  background:
    linear-gradient(180deg, rgba(15, 23, 42, 0.86), rgba(15, 23, 42, 0.72)),
    radial-gradient(circle at 16% 50%, rgba(139, 123, 198, 0.26), transparent 58%);
  box-shadow:
    0 1px 0 rgba(148, 163, 184, 0.12) inset,
    0 8px 20px rgba(2, 6, 23, 0.32);
}

html.dark .skill-status-icon {
  color: #c4b5fd;
  background: rgba(139, 123, 198, 0.24);
}

html.dark .skill-status-label {
  color: #e2e8f0;
}

html.dark .skill-status-count {
  color: #ede9fe;
  background: linear-gradient(135deg, rgba(124, 106, 184, 0.52), rgba(101, 80, 168, 0.38));
}

html.dark .skill-status-count.is-limit {
  color: #f5f3ff;
  background: linear-gradient(135deg, #9d8ad7, #7c6ab8);
  box-shadow:
    0 0 0 1px rgba(196, 181, 253, 0.26) inset,
    0 8px 16px rgba(111, 92, 179, 0.34);
}

@media (max-width: 768px) {
  .skill-status-bar {
    width: 100%;
    border-radius: 16px;
  }

  .skill-tag {
    max-width: 132px;
  }
}

@keyframes count-limit-pulse {
  0% {
    transform: scale(1);
  }
  40% {
    transform: scale(1.08);
  }
  100% {
    transform: scale(1);
  }
}

@keyframes skill-icon-float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-4px);
  }
}

@keyframes skill-icon-halo {
  0%, 100% {
    transform: scale(0.96);
    opacity: 0.72;
  }
  50% {
    transform: scale(1.04);
    opacity: 0.85;
  }
}

@keyframes skill-glyph-breathe {
  0%, 100% {
    transform: rotate(0deg) scale(0.96);
    opacity: 0.92;
  }
  50% {
    transform: rotate(6deg) scale(1.04);
    opacity: 1;
  }
}

@keyframes skill-orbit-left {
  0%, 100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(-5px, -4px, 0) scale(1.12);
  }
}

@keyframes skill-orbit-right {
  0%, 100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(6px, 4px, 0) scale(0.92);
  }
}
</style>
