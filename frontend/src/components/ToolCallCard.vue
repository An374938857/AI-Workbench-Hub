<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

interface GeneratedFile {
  fileId: number
  filename: string
  fileSize: number
}

interface ToolCallInfo {
  toolCallId: string
  toolName: string
  arguments?: string
  status: 'calling' | 'success' | 'error'
  progressTick?: number
  elapsedMs?: number
  elapsedSeconds?: number
  resultPreview?: string
  errorMessage?: string
  files?: GeneratedFile[]
}

const props = defineProps<{
  data: ToolCallInfo
  conversationId?: number | null
}>()

const emit = defineEmits<{
  (e: 'skill-decision', payload: { approved: boolean; skillId: number; skillName?: string; resumeAssistantMessageId?: number | null; resumeToolMessageId?: number | null }): void
}>()

const expanded = ref(false)
const deciding = ref(false)
const decision = ref<'approved' | 'rejected' | null>(null)

const activationSkillId = computed<number | null>(() => {
  const match = props.data.toolName.match(/^activate_skill_(\d+)$/)
  if (!match) return null
  const parsed = Number(match[1])
  return Number.isFinite(parsed) ? parsed : null
})

function parseResultPreviewPayload() {
  if (!props.data.resultPreview) return null
  try {
    return JSON.parse(props.data.resultPreview) as Record<string, unknown>
  } catch {
    return null
  }
}

function normalizeSkillName(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed || undefined
}

function extractSkillNameFromMessage(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const matched = /「([^」]+)」/.exec(value)
  return normalizeSkillName(matched?.[1])
}

const displayToolName = computed(() => {
  const skillId = activationSkillId.value
  if (skillId === null) return props.data.toolName
  const payload = parseResultPreviewPayload()
  const parsedName = normalizeSkillName(payload?.skill_name)
  if (parsedName) return `激活技能「${parsedName}」`
  return `激活技能（ID: ${skillId}）`
})

const showDecisionActions = computed(() =>
  props.data.status === 'calling' && decision.value === null && activationSkillId.value !== null && !!props.conversationId,
)

const statusIcon = computed(() => {
  switch (props.data.status) {
    case 'calling': return '⏳'
    case 'success': return '🔧'
    case 'error': return '🔧'
  }
})

const statusLabel = computed(() => {
  if (decision.value === 'approved') return '已确认激活技能'
  if (decision.value === 'rejected') return '已拒绝激活技能'
  switch (props.data.status) {
    case 'calling': return '正在调用工具'
    case 'success': return '已调用工具'
    case 'error': return '调用工具失败'
  }
})

const progressText = computed(() => {
  if (props.data.status !== 'calling') return ''
  const elapsedSeconds = Number(props.data.elapsedSeconds || 0)
  const progressTick = Number(props.data.progressTick || 0)
  if (elapsedSeconds > 0) return `已等待 ${elapsedSeconds}s · 心跳 ${progressTick}`
  if (progressTick > 0) return `心跳 ${progressTick}`
  return ''
})

const formattedArgs = computed(() => {
  if (!props.data.arguments) return ''
  try {
    return JSON.stringify(JSON.parse(props.data.arguments), null, 2)
  } catch {
    return props.data.arguments
  }
})

const formattedResult = computed(() => {
  if (!props.data.resultPreview) return ''
  try {
    return JSON.stringify(JSON.parse(props.data.resultPreview), null, 2)
  } catch {
    return props.data.resultPreview
  }
})

function toggle() {
  if (props.data.status === 'calling') return
  expanded.value = !expanded.value
}

async function submitSkillDecision(approve: boolean) {
  if (!props.conversationId || activationSkillId.value === null || deciding.value || decision.value !== null) return
  deciding.value = true
  const action = approve ? 'confirm' : 'reject'
  try {
    const response = await fetch(
      `/api/conversations/${props.conversationId}/skills/${activationSkillId.value}/${action}`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        },
      },
    )
    if (!response.ok) {
      throw new Error(approve ? '确认激活失败' : '拒绝激活失败')
    }
    const result = await response.json()
    const success = approve ? !!result?.data?.success : false
    if (approve && !success) {
      throw new Error(result?.data?.message || '确认激活失败')
    }
    const activeSkills = Array.isArray(result?.data?.active_skills)
      ? (result.data.active_skills as Array<{ id?: number; name?: string }>)
      : []
    const matchedActiveSkill = activeSkills.find((skill) => Number(skill?.id) === activationSkillId.value)
    const resolvedSkillName = (
      normalizeSkillName(result?.data?.skill_name)
      || normalizeSkillName(matchedActiveSkill?.name)
      || extractSkillNameFromMessage(result?.data?.message)
    )
    decision.value = approve ? 'approved' : 'rejected'
    emit('skill-decision', {
      approved: approve,
      skillId: activationSkillId.value,
      skillName: resolvedSkillName,
      resumeAssistantMessageId: result?.data?.resume_assistant_message_id ?? null,
      resumeToolMessageId: result?.data?.resume_tool_message_id ?? null,
    })
    ElMessage.success(result?.data?.message || (approve ? '已确认激活技能' : '已拒绝激活技能'))
  } catch (error: any) {
    ElMessage.error(error?.message || (approve ? '确认激活失败' : '拒绝激活失败'))
  } finally {
    deciding.value = false
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function downloadFile(file: GeneratedFile) {
  const token = localStorage.getItem('access_token')
  fetch(`/api/files/download/${file.fileId}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  }).then(res => {
    if (!res.ok) throw new Error('下载失败')
    return res.blob()
  }).then(blob => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = file.filename
    a.click()
    URL.revokeObjectURL(url)
  }).catch(() => {})
}
</script>

<template>
  <div class="tool-call-card" :class="'tc-' + data.status" @click="toggle">
    <div class="tc-header">
      <span class="tc-icon" :class="{ 'tc-loading': data.status === 'calling' }">{{ statusIcon }}</span>
      <span class="tc-label">{{ statusLabel }}：<strong>{{ displayToolName }}</strong></span>
      <span v-if="progressText" class="tc-progress">{{ progressText }}</span>
      <span v-if="data.status === 'success'" class="tc-mark tc-mark-ok">✓</span>
      <span v-else-if="data.status === 'error'" class="tc-mark tc-mark-err">✗</span>
      <div v-if="showDecisionActions" class="tc-actions" @click.stop>
        <button class="tc-action-btn tc-action-approve" :disabled="deciding" @click="submitSkillDecision(true)">
          确认
        </button>
        <button class="tc-action-btn tc-action-reject" :disabled="deciding" @click="submitSkillDecision(false)">
          拒绝
        </button>
      </div>
      <span v-if="data.status !== 'calling'" class="tc-toggle">{{ expanded ? '▾ 收起' : '▸ 展开详情' }}</span>
    </div>

    <!-- 文件卡片：始终显示在 header 下方 -->
    <div v-if="data.files && data.files.length > 0" class="tc-files" @click.stop>
      <div v-for="f in data.files" :key="f.fileId" class="tc-file-card">
        <span class="tc-file-icon">📄</span>
        <div class="tc-file-info">
          <span class="tc-file-name">{{ f.filename }}</span>
          <span class="tc-file-size">{{ formatSize(f.fileSize) }}</span>
        </div>
        <button class="tc-file-download" @click="downloadFile(f)">下载</button>
      </div>
    </div>

    <div v-if="expanded" class="tc-detail">
      <div v-if="formattedArgs" class="tc-section">
        <div class="tc-section-title">调用参数</div>
        <pre class="tc-code">{{ formattedArgs }}</pre>
      </div>
      <div v-if="data.status === 'success' && formattedResult" class="tc-section">
        <div class="tc-section-title">返回结果</div>
        <pre class="tc-code">{{ formattedResult }}</pre>
      </div>
      <div v-if="data.status === 'error' && data.errorMessage" class="tc-section">
        <div class="tc-section-title">错误原因</div>
        <div class="tc-error-text">{{ data.errorMessage }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-call-card {
  border: 1px solid var(--border-primary, #e4e7ed);
  border-radius: 8px;
  font-size: 13px;
  background: var(--bg-code, #fafafa);
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
  overflow: hidden;
}

.tool-call-card:hover {
  box-shadow: var(--shadow-sm, 0 1px 4px rgba(0, 0, 0, 0.06));
}

.tool-call-card.tc-calling {
  border-color: #409eff60;
  background: var(--bg-code, #f0f9ff);
  cursor: default;
}

.tool-call-card.tc-success {
  border-color: #67c23a40;
  background: var(--bg-code, #f4fbf0);
}

.tool-call-card.tc-error {
  border-color: #f56c6c40;
  background: var(--bg-code, #fef0f0);
}

.tc-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
}

.tc-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.tc-loading {
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1 }
  51%, 100% { opacity: 0 }
}

.tc-label {
  color: var(--text-secondary, #606266);
  flex: 1;
}

.tc-label strong {
  color: var(--text-primary, #303133);
}

.tc-progress {
  color: var(--text-muted, #909399);
  font-size: 12px;
  white-space: nowrap;
}

.tc-mark {
  font-weight: 600;
  flex-shrink: 0;
}

.tc-mark-ok { color: #67c23a; }
.tc-mark-err { color: #f56c6c; }

.tc-toggle {
  font-size: 12px;
  color: var(--text-muted, #909399);
  flex-shrink: 0;
  margin-left: 4px;
}

.tc-actions {
  display: inline-flex;
  gap: 6px;
  margin-left: 8px;
}

.tc-action-btn {
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
  line-height: 1.4;
}

.tc-action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.tc-action-approve {
  color: #fff;
  background: #67c23a;
}

.tc-action-reject {
  color: #fff;
  background: #f56c6c;
}

/* 文件卡片 */
.tc-files {
  padding: 6px 12px 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tc-file-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid var(--border-primary, #e4e7ed);
  border-radius: 6px;
  background: var(--bg-page, #fff);
  cursor: default;
}

.tc-file-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.tc-file-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.tc-file-name {
  font-size: 13px;
  color: var(--text-primary, #303133);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.tc-file-size {
  font-size: 11px;
  color: var(--text-muted, #909399);
}

.tc-file-download {
  padding: 3px 10px;
  font-size: 12px;
  border: 1px solid #409eff;
  border-radius: 4px;
  background: #409eff;
  color: #fff;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.2s;
}

.tc-file-download:hover {
  background: #337ecc;
}

.tc-detail {
  border-top: 1px solid var(--border-primary, #e4e7ed);
  padding: 10px 12px;
}

.tc-section {
  margin-bottom: 8px;
}

.tc-section:last-child {
  margin-bottom: 0;
}

.tc-section-title {
  font-size: 12px;
  color: var(--text-muted, #909399);
  margin-bottom: 4px;
  font-weight: 500;
}

.tc-code {
  background: var(--bg-code, #f5f7fa);
  border: 1px solid var(--border-primary, #ebeef5);
  border-radius: 4px;
  padding: 8px 10px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-primary, #303133);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.tc-error-text {
  color: #f56c6c;
  font-size: 12px;
  padding: 4px 0;
}
</style>
