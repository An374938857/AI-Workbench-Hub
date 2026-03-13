<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter, useRoute, onBeforeRouteLeave } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useChatStore } from '@/stores/chat'
import { createConversation, getConversationList, getConversationDetail, getConversationLiveState, deleteConversation, cancelConversationGenerationWithMeta, updateConversationTitle, regenerateConversationTitle, submitFeedback, getFeedback, switchBranch, batchDeleteConversations, batchExportConversations, batchTagConversations, addConversationTag, removeConversationTag, switchConversationModel, getPromptTemplate, switchPromptTemplate, activateConversationSkill, markConversationSidebarSignalRead } from '@/api/conversations'
import { getTagList } from '@/api/tags'
import { compressConversation, getCompressionSummary } from '@/api/compression'
import { exportConversation } from '@/utils/export'
import { applyMessageUiState, areMessagesRenderEqual, canPatchLatestAssistantOnly } from '@/utils/chatMessageRender'
import { areActiveSkillsEqual, areConversationListsRenderEqual, areTagsEqual, formatSkillDisplayName } from '@/utils/chatConversationComparators'
import FileUploader from '@/components/FileUploader.vue'
import ChatHeader from '@/components/chat/ChatHeader.vue'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatEmptyState from '@/components/chat/ChatEmptyState.vue'
import ChatWorkspace from '@/components/chat/ChatWorkspace.vue'
import ConversationExportDialog from '@/components/chat/ConversationExportDialog.vue'
import ConversationFeedbackDialog from '@/components/chat/ConversationFeedbackDialog.vue'
import OptimizedPromptDialog from '@/components/chat/OptimizedPromptDialog.vue'
import ConversationReferenceDialog from '@/components/chat/ConversationReferenceDialog.vue'
import ChatStatusBar from '@/components/chat/ChatStatusBar.vue'
import SandboxPanelLauncher from '@/components/chat/SandboxPanelLauncher.vue'
import ConversationSidebar from '@/components/chat/ConversationSidebar.vue'
import TagManager from '@/components/TagManager.vue'
import SkillManager from '@/components/SkillManager.vue'
import { getTagFilterItemStyle, showDangerConfirm } from '@/composables/useChatUiHelpers'
import { useConversationExecution } from '@/composables/useConversationExecution'
import { useConversationLiveState } from '@/composables/useConversationLiveState'
import { useConversationEvents } from '@/composables/useConversationEvents'
import { useConversationDraft, type ConversationDraftSnapshot } from '@/composables/useConversationDraft'
import { useConversationSidebar } from '@/composables/useConversationSidebar'
import { useConversationReferences } from '@/composables/useConversationReferences'
import { useConversationUiState } from '@/composables/useConversationUiState'
import { useConversationFileInput } from '@/composables/useConversationFileInput'
import { useConversationKeydown } from '@/composables/useConversationKeydown'
import { useSandboxLauncher } from '@/composables/useSandboxLauncher'
import { useConversationBatchActions } from '@/composables/useConversationBatchActions'
import { useConversationTagging } from '@/composables/useConversationTagging'
import { useConversationFeedback } from '@/composables/useConversationFeedback'
import { useConversationExportHints } from '@/composables/useConversationExportHints'
import { useConversationMessageActions } from '@/composables/useConversationMessageActions'
import { useComposerCatalogs } from '@/composables/useComposerCatalogs'
import { usePromptOptimizer } from '@/composables/usePromptOptimizer'
import { useAutoRoutePreference } from '@/composables/useAutoRoutePreference'
import { useMultimodalGuard } from '@/composables/useMultimodalGuard'
import { useCommandDispatcher } from '@/composables/useCommandDispatcher'
import { markSandboxChangesRead } from '@/api/sandbox'
import { shouldRequestRemoteCancelOnRouteSwitch } from '@/utils/conversationCancelPolicy'
import { isEmptyAssistantPlaceholder, shouldForceRefreshConversationDetailFromCache } from '@/utils/conversationCachePolicy'
import { extractPendingSkillActivationFromMessages } from '@/utils/skillActivationRecovery'
import { buildSkillResumeKey, SkillResumeGuard } from '@/utils/skillResumeGuard'
import { getLatestRetryableAssistantMessageId } from '@/utils/conversationRetryPolicy'
import type {
  ActiveSkillLite,
  ConversationLiveStateSnapshot,
  ConversationSyncEvent,
  GeneratedFile,
  LiveExecutionState,
  Msg,
  PendingSkillResume,
  SkillActivatedEvent,
  SkillActivationRequestEvent,
  SkillRejectedEvent,
  SidebarSignal,
  TagInfo,
} from '@/types/chat'
import { ElMessage, ElLoading, ElMessageBox } from 'element-plus'

interface ConvItem {
  id: number
  skill_id: number | null
  skill_name: string
  active_skills?: ActiveSkillLite[]
  title: string
  updated_at: string
  tags?: TagInfo[]
  live_execution?: LiveExecutionState
  sidebar_signal?: SidebarSignal
}

interface ConversationDetailVersionPayload {
  status?: string
  message_id?: number | null
  error_message?: string | null
  stage?: string | null
  stage_detail?: string | null
  round_no?: number | null
  title?: string
  active_skill_ids?: string
  current_provider_id?: number | null
  current_model_name?: string | null
  sandbox_unread_change_count?: number
  live_updated_at?: string | null
  updated_at?: string | null
}

const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()
const {
  messageCache: msgCache,
  generatingConversationIds: generatingConvIds,
  conversationExecutionStates,
} = storeToRefs(chatStore)

const currentConvId = ref<number | null>(null)
const activeTagFilter = ref<number | null>(null)
const currentTitle = ref('')
const currentSkillName = ref('')
const messages = ref<Msg[]>([])
const currentProviderId = ref<number | null>(null)
const currentModelName = ref<string | null>(null)
const currentConversationFingerprint = ref('')
const currentConversationLiveStateVersion = ref('')
const sandboxUnreadChangeCount = ref(0)
const streamOwnerId = `chat-view-${Date.now()}-${Math.random().toString(36).slice(2)}`
let conversationLoadRequestSeq = 0
let pendingSkillResumeRecoveryTimer: number | null = null
const conversationExecution = useConversationExecution({ chatStore, ownerPrefix: streamOwnerId })
// 从 localStorage 恢复上次使用的模型
const _lastModel = (() => { try { return JSON.parse(localStorage.getItem('last_model') || 'null') } catch { return null } })()
const selectedProviderId = ref<number | null>(_lastModel?.pid ?? null)
const selectedModelName = ref<string | null>(_lastModel?.name ?? null)
const messagesRef = ref<HTMLElement>()
const fileUploaderRef = ref<InstanceType<typeof FileUploader>>()
const skillManagerRef = ref<InstanceType<typeof SkillManager>>()
const pendingSkillActivation = ref<SkillActivationRequestEvent | null>(null)
const pendingSkillResume = ref<PendingSkillResume | null>(null)
const pendingSkillResumeGuard = new SkillResumeGuard()
const recoveredWaitingPromptKeys = new Set<string>()
const handledWaitingPromptKeys = new Set<string>()
const loadingConv = ref(false)
const {
  inputText,
  fileIds,
  quotedMessages,
  forkFromMessageId,
  messagesBeforeFork,
  snapshotDraft,
  restoreDraft,
  clearDraft,
} = useConversationDraft()
const editingMessageId = ref<number | null>(null)
const editDraftBackup = ref<{
  draft: ConversationDraftSnapshot
  files: any[]
} | null>(null)
const {
  showCommandSuggestions,
  commandSuggestions,
  selectedCommandIndex,
  allCommands,
  chatInputAreaRef,
  showTemplateList,
  selectedTemplateIndex,
  showModelList,
  selectedModelIndex,
  showSkillList,
  selectedSkillIndex,
  showMcpList,
  selectedMcpIndex,
  listSearchQuery,
  modelList,
  skillList,
  mcpList,
  templateList,
  currentTemplateId,
  loadingTemplate,
  templatePopoverVisible,
  currentTemplateLabel,
  globalDefaultTemplateId,
  isFreeTemplateGlobalDefault,
  visibleTemplateList,
  getTemplatePreview,
  filteredModelList,
  filteredSkillList,
  filteredMcpList,
  filteredTemplateList,
  optimizing,
  showOptimizedDialog,
  optimizedPrompt,
  optimizeAbortController,
  optimizedPromptContainerRef,
  shouldAutoScrollOptimizedPrompt,
  editingSidebarTitleConvId,
  editingSidebarTitleText,
  editingHeaderTitle,
  editingHeaderTitleText,
  headerTitleInputRef,
  sidebarTitleInputRefs,
  setSidebarTitleInputRef,
  resetListSelectionIndices,
  closeCommandPanels,
  updateCommandSuggestionsByInput,
} = useConversationUiState()

function setHeaderTitleInputRef(el: HTMLInputElement | null) {
  headerTitleInputRef.value = el
}

function setMessagesAreaRef(el: HTMLElement | null) {
  messagesRef.value = el ?? undefined
}

function setChatInputAreaRef(el: HTMLElement | null) {
  chatInputAreaRef.value = el
}

function setFileUploaderComponentRef(instance: InstanceType<typeof FileUploader> | null) {
  fileUploaderRef.value = instance ?? undefined
}

function setSkillManagerComponentRef(instance: InstanceType<typeof SkillManager> | null) {
  skillManagerRef.value = instance ?? undefined
}

const {
  nextTurnReferenceMode,
  referenceState,
  referenceAllFiles,
  referenceSelectedIds,
  referenceFocusedFileId,
  referenceDialogVisible,
  referenceDialogLoading,
  referenceFilePreview,
  referenceTreeItems,
  focusedReferenceFile,
  focusedReferenceInspectorTags,
  focusedReferenceInspectorFields,
  focusedReferenceInspectorSummary,
  referenceSelectedCount,
  referenceBindingSummary,
  showReferenceComposerBar,
  loadReferenceState,
  openReferenceDialog,
  cancelReferenceDialog,
  updateReferenceSelectedIds,
  handleReferenceTreeItemClick,
  handleReferenceTreeItemDblClick,
  handleReferenceInspectorAction,
  formatReferenceDisplayPath,
  applyReferenceMode,
  handleClearReference,
} = useConversationReferences({
  getCurrentConversationId: () => currentConvId.value,
  showDangerConfirm,
})
const {
  maybeActivateExportHintForLatestAssistant,
  maybeActivateExportHintForMessage,
  acknowledgeExportHint,
  acknowledgeAllExportHints,
  resetExportHints,
} = useConversationExportHints({
  messages,
  getCurrentConversationId: () => currentConvId.value,
  cacheConversationMessages: (conversationId, cachedMessages) => {
    chatStore.cacheConversationMessages(conversationId, cachedMessages)
  },
})

function buildMessageClientKey(
  messageId: number | undefined,
  role: Msg['role'],
  previousClientKeysById: Map<number, string>,
): string {
  if (typeof messageId === 'number') {
    const existing = previousClientKeysById.get(messageId)
    if (existing) return existing
    return `server-${messageId}`
  }
  return nextMessageClientKey(role)
}

const {
  conversations,
  hasMoreConversations,
  loadingMoreConversations,
  loadConversationList,
  loadMoreConversations,
  handleConvListScroll,
  handleConvDragEnd,
  resetPagination,
  startAutoRefresh: startConversationListAutoRefresh,
  stopAutoRefresh: stopConversationListAutoRefresh,
} = useConversationSidebar<ConvItem>({
  getActiveTagFilter: () => activeTagFilter.value,
  getCurrentConversationId: () => currentConvId.value,
  onCurrentConversationActiveSkills: (skills) => {
    applyCurrentActiveSkills(skills as ActiveSkillLite[])
  },
  areConversationListsRenderEqual,
  fetchConversationList: async (params, options) => {
    return await getConversationList(params, options)
  },
  fetchSortPreferences: async () => {
    return await (await import('@/api/sortPreferences')).getSortPreferences('conversation') as any
  },
  saveSortPreferences: async (items) => {
    await (await import('@/api/sortPreferences')).updateSortPreferences('conversation', items)
  },
})

function getPendingSkillResumeStorageKey(conversationId: number) {
  return `chat:pending-skill-resume:${conversationId}`
}

function persistPendingSkillResume(conversationId: number, payload: PendingSkillResume | null) {
  const storageKey = getPendingSkillResumeStorageKey(conversationId)
  if (!payload) {
    sessionStorage.removeItem(storageKey)
    return
  }
  sessionStorage.setItem(storageKey, JSON.stringify(payload))
}

function loadPersistedPendingSkillResume(conversationId: number): PendingSkillResume | null {
  const raw = sessionStorage.getItem(getPendingSkillResumeStorageKey(conversationId))
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as PendingSkillResume
    if (!parsed?.toolMessageId && !parsed?.assistantMessageId) return null
    return parsed
  } catch {
    sessionStorage.removeItem(getPendingSkillResumeStorageKey(conversationId))
    return null
  }
}

function clearPendingSkillResumeRecoveryTimer() {
  if (pendingSkillResumeRecoveryTimer != null) {
    window.clearTimeout(pendingSkillResumeRecoveryTimer)
    pendingSkillResumeRecoveryTimer = null
  }
}

function schedulePendingSkillResumeRecovery() {
  clearPendingSkillResumeRecoveryTimer()
  pendingSkillResumeRecoveryTimer = window.setTimeout(() => {
    void runPendingSkillResume({ force: true })
  }, 1500)
}

function applyCurrentActiveSkills(skills: ActiveSkillLite[]) {
  currentSkillName.value = formatSkillDisplayName(skills)

  if (!currentConvId.value) return
  const current = conversations.value.find((conv) => conv.id === currentConvId.value)
  if (current) {
    current.active_skills = skills
    current.skill_name = currentSkillName.value
  }
}

async function refreshCurrentConversationActiveSkills() {
  if (!currentConvId.value) return
  try {
    const response = await fetch(`/api/conversations/${currentConvId.value}/skills`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem('access_token')}`,
      },
    })
    if (!response.ok) return
    const payload = await response.json()
    const rawSkills = Array.isArray(payload?.data)
      ? (payload.data as Array<{ id: number; name: string }>)
      : []
    const skills: ActiveSkillLite[] = rawSkills.map((item) => ({
      id: item.id,
      name: item.name,
    }))
    applyCurrentActiveSkills(skills)
  } catch (error) {
    console.error('刷新激活技能失败:', error)
  }
}

function hasVisibleSkillActivationPrompt() {
  if (pendingSkillActivation.value) return true
  return Boolean(skillManagerRef.value?.hasPendingSkillActivation?.())
}

function buildWaitingPromptKey(
  conversationId: number,
  messageId?: number | null,
) {
  return `${conversationId}:${messageId ?? 'unknown'}`
}

function getHandledWaitingPromptStorageKey(conversationId: number) {
  return `chat:handled-waiting-skill-prompt:${conversationId}`
}

function hydrateHandledWaitingPromptKeys(conversationId: number) {
  const storageKey = getHandledWaitingPromptStorageKey(conversationId)
  const raw = sessionStorage.getItem(storageKey)
  if (!raw) return
  try {
    const parsed = JSON.parse(raw) as string[]
    if (!Array.isArray(parsed)) return
    parsed.forEach((key) => {
      if (typeof key !== 'string') return
      handledWaitingPromptKeys.add(key)
    })
  } catch {
    sessionStorage.removeItem(storageKey)
  }
}

function persistHandledWaitingPromptKeys(conversationId: number) {
  const prefix = `${conversationId}:`
  const keys = Array.from(handledWaitingPromptKeys).filter((key) => key.startsWith(prefix))
  const storageKey = getHandledWaitingPromptStorageKey(conversationId)
  if (!keys.length) {
    sessionStorage.removeItem(storageKey)
    return
  }
  sessionStorage.setItem(storageKey, JSON.stringify(keys))
}

function markWaitingPromptHandled(
  conversationId: number,
  messageId?: number | null,
) {
  const key = buildWaitingPromptKey(conversationId, messageId ?? null)
  handledWaitingPromptKeys.add(key)
  recoveredWaitingPromptKeys.add(key)
  persistHandledWaitingPromptKeys(conversationId)
}

function getCurrentWaitingPromptKey() {
  const convId = currentConvId.value
  if (!convId) return null
  const current = conversations.value.find((item) => item.id === convId)
  if (current?.live_execution?.status !== 'waiting_skill_confirmation') return null
  return buildWaitingPromptKey(convId, current.live_execution?.message_id ?? null)
}

function clearRecoveredWaitingPromptKeysForConversation(conversationId: number) {
  const prefix = `${conversationId}:`
  for (const key of Array.from(recoveredWaitingPromptKeys)) {
    if (!key.startsWith(prefix)) continue
    recoveredWaitingPromptKeys.delete(key)
  }
}

function syncRecoveredWaitingPromptKeys(
  conversationId: number,
  liveExecution?: LiveExecutionState | null,
) {
  if (liveExecution?.status !== 'waiting_skill_confirmation') {
    clearRecoveredWaitingPromptKeysForConversation(conversationId)
    return null
  }
  const currentKey = buildWaitingPromptKey(conversationId, liveExecution?.message_id ?? null)
  const prefix = `${conversationId}:`
  for (const key of Array.from(recoveredWaitingPromptKeys)) {
    if (!key.startsWith(prefix) || key === currentKey) continue
    recoveredWaitingPromptKeys.delete(key)
  }
  return currentKey
}

function resolveSkillDescriptionById(skillId: number): string | undefined {
  const matched = skillList.value.find((item: any) => Number(item?.id) === skillId)
  if (!matched) return undefined
  const description = typeof matched.description === 'string' ? matched.description.trim() : ''
  return description || undefined
}

function resolveSkillNameById(skillId: number): string | undefined {
  const matchedFromList = skillList.value.find((item: any) => Number(item?.id) === skillId)
  const listName = typeof matchedFromList?.name === 'string' ? matchedFromList.name.trim() : ''
  if (listName) return listName

  const matchedFromConversation = conversations.value
    .flatMap((conversation) => (Array.isArray(conversation.active_skills) ? conversation.active_skills : []))
    .find((skill) => Number(skill?.id) === skillId)
  const conversationName = typeof matchedFromConversation?.name === 'string'
    ? matchedFromConversation.name.trim()
    : ''
  if (conversationName) return conversationName

  return undefined
}

function recoverSkillActivationPromptIfMissing(
  conversationId: number,
  liveExecution?: LiveExecutionState | null,
) {
  const waitingPromptKey = syncRecoveredWaitingPromptKeys(conversationId, liveExecution)
  if (!waitingPromptKey) return
  hydrateHandledWaitingPromptKeys(conversationId)
  if (handledWaitingPromptKeys.has(waitingPromptKey)) return
  if (recoveredWaitingPromptKeys.has(waitingPromptKey)) return
  if (hasVisibleSkillActivationPrompt()) return
  const recovered = extractPendingSkillActivationFromMessages(
    messages.value,
    resolveSkillDescriptionById,
  )
  if (!recovered) return
  recoveredWaitingPromptKeys.add(waitingPromptKey)
  void handleSkillActivationRequest(recovered, waitingPromptKey)
}

function detectResolvedSkillActivationNotice(): string | null {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const timeline = messages.value[i]?.timeline
    if (!timeline?.length) continue
    for (let j = timeline.length - 1; j >= 0; j -= 1) {
      const item = timeline[j]
      if (!item || item.type !== 'tool_call' || !item.resultPreview) continue
      try {
        const parsed = JSON.parse(item.resultPreview) as { type?: string; skill_name?: string }
        const skillName = parsed.skill_name ? `「${parsed.skill_name}」` : '技能'
        if (parsed.type === 'skill_activation_confirmed') {
          return `${skillName}已激活，正在继续执行当前请求…`
        }
        if (parsed.type === 'skill_activation_rejected') {
          return `已拒绝加载${skillName}，正在继续在无技能模式下执行当前请求…`
        }
      } catch {
        // ignore parse errors
      }
    }
  }
  return null
}

function recoverPendingSkillResumeIfResolved(
  conversationId: number,
  liveExecution?: LiveExecutionState | null,
) {
  if (liveExecution?.status !== 'waiting_skill_confirmation') return
  if (pendingSkillResume.value) return
  if (!liveExecution.message_id) return

  const notice = detectResolvedSkillActivationNotice()
  if (!notice) return

  pendingSkillResume.value = {
    assistantMessageId: liveExecution.message_id,
    toolMessageId: null,
    notice,
  }
  persistPendingSkillResume(conversationId, pendingSkillResume.value)
  schedulePendingSkillResumeRecovery()
  void runPendingSkillResume({ force: true })
}

async function handleSkillActivationRequest(
  data: SkillActivationRequestEvent,
  waitingPromptKey?: string | null,
) {
  const resolvedWaitingPromptKey = waitingPromptKey ?? getCurrentWaitingPromptKey()
  if (resolvedWaitingPromptKey) {
    recoveredWaitingPromptKeys.add(resolvedWaitingPromptKey)
  }
  pendingSkillActivation.value = data
  await nextTick()
  if (!skillManagerRef.value || !pendingSkillActivation.value) return
  const request = pendingSkillActivation.value
  skillManagerRef.value.showSkillActivation({
    id: request.skill_id,
    name: request.skill_name || resolveSkillNameById(request.skill_id) || `技能 ${request.skill_id}`,
    description: request.skill_description,
  })
  pendingSkillActivation.value = null
}

async function runPendingSkillResume(options: { force?: boolean } = {}) {
  const convId = currentConvId.value
  if (convId && !pendingSkillResume.value) {
    pendingSkillResume.value = loadPersistedPendingSkillResume(convId)
  }

  const pendingResume = pendingSkillResume.value
  if (!pendingResume) return
  if (!convId) return
  const resumeKey = buildSkillResumeKey({
    assistantMessageId: pendingResume.assistantMessageId,
    toolMessageId: pendingResume.toolMessageId,
  })
  if (!resumeKey) return
  if (!pendingSkillResumeGuard.tryBegin(convId, resumeKey)) return

  const pendingResumeForRun: PendingSkillResume = {
    assistantMessageId: pendingResume.assistantMessageId ?? null,
    toolMessageId: pendingResume.toolMessageId ?? null,
    notice: pendingResume.notice,
  }

  // 原子地消费恢复任务，防止并发 watcher/timer/focus 读取到相同 payload 后重复继续执行。
  pendingSkillResume.value = null
  persistPendingSkillResume(convId, null)

  if (isGenerating.value) {
    if (!options.force) {
      pendingSkillResume.value = pendingResumeForRun
      persistPendingSkillResume(convId, pendingResumeForRun)
      pendingSkillResumeGuard.end(convId, resumeKey)
      return
    }
    try {
      const activeOwner = chatStore.getStreamOwner(convId)
      // waiting_skill_confirmation 期间可能没有活跃流 owner，仅残留 generating 标记，此时允许直接继续。
      if (activeOwner) {
        if (!activeOwner.startsWith(streamOwnerId)) {
          pendingSkillResume.value = pendingResumeForRun
          persistPendingSkillResume(convId, pendingResumeForRun)
          pendingSkillResumeGuard.end(convId, resumeKey)
          return
        }
        await conversationExecution.cancelConversationAction(convId, {
          reason: 'resume_replace',
          requestRemoteCancel: (conversationId) =>
            cancelConversationGenerationWithMeta(conversationId, {
              reason: 'resume_replace',
              source: 'pending_skill_resume_force',
            }),
          suppressRemoteError: true,
        })
      }
    } catch {
      pendingSkillResume.value = pendingResumeForRun
      persistPendingSkillResume(convId, pendingResumeForRun)
      pendingSkillResumeGuard.end(convId, resumeKey)
      return
    }
  }
  if (!pendingResumeForRun.toolMessageId && !pendingResumeForRun.assistantMessageId) {
    pendingSkillResumeGuard.end(convId, resumeKey)
    return
  }
  clearPendingSkillResumeRecoveryTimer()

  if (convId) {
    const snapshot = chatStore.getConversationExecutionState(convId)
    if (snapshot) {
      chatStore.patchConversationExecutionState(convId, {
        resumeAttemptCount: (snapshot.resumeAttemptCount ?? 0) + 1,
      })
    } else {
      chatStore.setConversationExecutionState(convId, {
        state: 'idle',
        resumeAttemptCount: 1,
      })
    }
  }

  if (import.meta.env.DEV && import.meta.env.MODE !== 'test') {
    console.info('chat.execution.resume_start', {
      conversationId: convId,
      assistantMessageId: pendingResumeForRun.assistantMessageId ?? null,
      toolMessageId: pendingResumeForRun.toolMessageId ?? null,
      forced: Boolean(options.force),
    })
  }

  try {
    await handleContinueAfterSkillActivation(
      pendingResumeForRun.assistantMessageId ?? null,
      pendingResumeForRun.toolMessageId ?? null,
      pendingResumeForRun.notice,
    )
    if (import.meta.env.DEV && import.meta.env.MODE !== 'test') {
      console.info('chat.execution.resume_finish', {
        conversationId: convId,
        success: true,
        assistantMessageId: pendingResumeForRun.assistantMessageId ?? null,
        toolMessageId: pendingResumeForRun.toolMessageId ?? null,
      })
    }
  } catch {
    pendingSkillResume.value = pendingResumeForRun
    persistPendingSkillResume(convId, pendingResumeForRun)
    schedulePendingSkillResumeRecovery()
  } finally {
    pendingSkillResumeGuard.end(convId, resumeKey)
  }
}

function markSkillActivationToolConfirmed(event: SkillActivatedEvent) {
  const toolName = `activate_skill_${event.id}`
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const timeline = messages.value[i]?.timeline
    if (!timeline?.length) continue
    for (let j = timeline.length - 1; j >= 0; j -= 1) {
      const item = timeline[j]
      if (!item) continue
      if (item.type !== 'tool_call' || item.toolName !== toolName) continue
      item.status = 'success'
      item.resultPreview = JSON.stringify(
        {
          type: 'skill_activation_confirmed',
          success: true,
          skill_name: event.name,
          message: `已成功激活「${event.name}」技能。`,
        },
        null,
        2,
      )
      messages.value = [...messages.value]
      return
    }
  }
}

function markSkillActivationToolRejected(event: SkillRejectedEvent) {
  const toolName = `activate_skill_${event.id}`
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const timeline = messages.value[i]?.timeline
    if (!timeline?.length) continue
    for (let j = timeline.length - 1; j >= 0; j -= 1) {
      const item = timeline[j]
      if (!item) continue
      if (item.type !== 'tool_call' || item.toolName !== toolName) continue
      item.status = 'error'
      item.errorMessage = `用户拒绝加载技能「${event.name}」，当前请求将继续在不使用该技能的情况下执行。`
      item.resultPreview = JSON.stringify(
        {
          type: 'skill_activation_rejected',
          success: false,
          skill_name: event.name,
          message: `用户拒绝加载技能「${event.name}」，当前请求将继续在不使用该技能的情况下执行。`,
        },
        null,
        2,
      )
      messages.value = [...messages.value]
      return
    }
  }
}

async function handleSkillActivated(event: SkillActivatedEvent) {
  const convId = currentConvId.value
  if (convId) {
    const currentWaitingKey = getCurrentWaitingPromptKey()
    if (currentWaitingKey) {
      handledWaitingPromptKeys.add(currentWaitingKey)
      recoveredWaitingPromptKeys.add(currentWaitingKey)
    }
    if (event.resumeAssistantMessageId != null) {
      markWaitingPromptHandled(convId, event.resumeAssistantMessageId)
    } else {
      persistHandledWaitingPromptKeys(convId)
    }
    conversationExecution.clearWaitingSkillConfirmation(convId, 'idle')
  }
  markSkillActivationToolConfirmed(event)
  await refreshCurrentConversationActiveSkills()
  await loadConversationList()
  if (!event.resumeAssistantMessageId) return
  pendingSkillResume.value = {
    assistantMessageId: event.resumeAssistantMessageId,
    toolMessageId: event.resumeToolMessageId,
    notice: '技能已激活，正在继续执行当前请求…',
  }
  if (currentConvId.value) {
    persistPendingSkillResume(currentConvId.value, pendingSkillResume.value)
  }
  schedulePendingSkillResumeRecovery()
  if (!isGenerating.value) {
    await runPendingSkillResume()
  }
}

async function handleSkillDeactivated() {
  await refreshCurrentConversationActiveSkills()
  await loadConversationList()
}

async function handleSkillRejected(event: SkillRejectedEvent) {
  const convId = currentConvId.value
  if (convId) {
    const currentWaitingKey = getCurrentWaitingPromptKey()
    if (currentWaitingKey) {
      handledWaitingPromptKeys.add(currentWaitingKey)
      recoveredWaitingPromptKeys.add(currentWaitingKey)
    }
    if (event.resumeAssistantMessageId != null) {
      markWaitingPromptHandled(convId, event.resumeAssistantMessageId)
    } else {
      persistHandledWaitingPromptKeys(convId)
    }
    conversationExecution.clearWaitingSkillConfirmation(convId, 'idle')
  }
  markSkillActivationToolRejected(event)
  if (!event.resumeAssistantMessageId) return
  pendingSkillResume.value = {
    assistantMessageId: event.resumeAssistantMessageId,
    toolMessageId: event.resumeToolMessageId,
    notice: '已拒绝加载技能，正在继续在无技能模式下执行当前请求…',
  }
  if (currentConvId.value) {
    persistPendingSkillResume(currentConvId.value, pendingSkillResume.value)
  }
  schedulePendingSkillResumeRecovery()
  if (!isGenerating.value) {
    await runPendingSkillResume()
  }
}

async function handleToolSkillDecision(event: { approved: boolean; skillId: number; skillName?: string; resumeAssistantMessageId?: number | null; resumeToolMessageId?: number | null }) {
  const convId = currentConvId.value
  if (convId) {
    const currentWaitingKey = getCurrentWaitingPromptKey()
    if (currentWaitingKey) {
      handledWaitingPromptKeys.add(currentWaitingKey)
      recoveredWaitingPromptKeys.add(currentWaitingKey)
      persistHandledWaitingPromptKeys(convId)
    }
  }
  const skillName = event.skillName || resolveSkillNameById(event.skillId) || `技能 ${event.skillId}`
  if (event.approved) {
    await handleSkillActivated({
      id: event.skillId,
      name: skillName,
      brief_desc: '',
      resumeAssistantMessageId: event.resumeAssistantMessageId,
      resumeToolMessageId: event.resumeToolMessageId,
    })
    return
  }

  await handleSkillRejected({
    id: event.skillId,
    name: skillName,
    resumeAssistantMessageId: event.resumeAssistantMessageId,
    resumeToolMessageId: event.resumeToolMessageId,
  })
}

watch(
  () => skillManagerRef.value,
  (manager) => {
    if (!manager || !pendingSkillActivation.value) return
    const request = pendingSkillActivation.value
    manager.showSkillActivation({
      id: request.skill_id,
      name: request.skill_name,
      description: request.skill_description,
    })
    pendingSkillActivation.value = null
  },
)

const {
  isDragging,
  handleDragEnter: handleComposerDragEnter,
  handleDragLeave: handleComposerDragLeave,
  handleDrop,
  handlePaste,
} = useConversationFileInput({
  ensureConversation,
  uploadFile: async (file: File) => {
    await fileUploaderRef.value?.uploadFile(file)
  },
  onUnsupportedFile: (filename: string) => {
    ElMessage.warning(`不支持的文件格式: ${filename}`)
  },
})

const localMessageKeySeed = ref(0)
const referenceProgressNoticeKey = ref<string | null>(null)

function nextMessageClientKey(prefix = 'msg'): string {
  localMessageKeySeed.value += 1
  return `${prefix}-${localMessageKeySeed.value}`
}

function createLocalMessage(payload: Omit<Msg, 'clientKey'>): Msg {
  return {
    ...payload,
    clientKey: nextMessageClientKey(payload.role),
  }
}

function removeTrailingEmptyAssistantPlaceholder(target: Msg[]): boolean {
  const last = target[target.length - 1]
  if (!isEmptyAssistantPlaceholder(last)) return false
  target.pop()
  return true
}

function upsertReferenceProgressNotice(content: string) {
  const noticeKey = referenceProgressNoticeKey.value
  if (noticeKey) {
    const index = messages.value.findIndex((item) => item.clientKey === noticeKey)
    if (index >= 0) {
      const current = messages.value[index]
      if (current) {
        current.content = content
        messages.value = [...messages.value]
        scrollToBottom()
        return
      }
    }
  }
  const notice = createLocalMessage({ role: 'system_notice', content })
  messages.value.push(notice)
  referenceProgressNoticeKey.value = notice.clientKey
  scrollToBottom()
}

function clearReferenceProgressNotice() {
  const noticeKey = referenceProgressNoticeKey.value
  if (!noticeKey) return
  const index = messages.value.findIndex((item) => item.clientKey === noticeKey)
  if (index >= 0) {
    messages.value.splice(index, 1)
    messages.value = [...messages.value]
  }
  referenceProgressNoticeKey.value = null
}

function ensureTrailingAssistantMessage(target: Msg[]): Msg | null {
  let last = target[target.length - 1]
  if (!last || last.role !== 'assistant') {
    last = createLocalMessage({ role: 'assistant', content: '', timeline: [] })
    target.push(last)
  }
  if (!last.timeline) {
    last.timeline = []
  }
  return last
}

function appendRunningToolCall(
  target: Msg[],
  data: { toolCallId: string; toolName: string; arguments?: string },
): boolean {
  const last = ensureTrailingAssistantMessage(target)
  if (!last) return false
  const alreadyExists = last.timeline?.some(
    item => item.type === 'tool_call' && item.toolCallId === data.toolCallId,
  )
  if (alreadyExists) return false
  last.timeline = [
    ...(last.timeline || []),
    {
      type: 'tool_call',
      toolCallId: data.toolCallId,
      toolName: data.toolName,
      arguments: data.arguments,
      status: 'calling' as const,
    },
  ]
  return true
}

function updateToolCallTimeline(
  target: Msg[],
  toolCallId: string,
  patch: {
    status?: 'calling' | 'success' | 'error'
    progressTick?: number
    elapsedMs?: number
    elapsedSeconds?: number
    resultPreview?: string
    errorMessage?: string
    files?: GeneratedFile[]
  },
): boolean {
  for (let i = target.length - 1; i >= 0; i -= 1) {
    const message = target[i]
    if (!message?.timeline?.length) continue
    const index = message.timeline.findIndex(
      item => item.type === 'tool_call' && item.toolCallId === toolCallId,
    )
    if (index === -1) continue
    const current = message.timeline[index]
    if (!current) return false
    message.timeline[index] = {
      ...current,
      ...patch,
      type: 'tool_call',
    }
    message.timeline = [...message.timeline]
    return true
  }
  return false
}

function getLiveExecutionErrorText(liveExecution?: LiveExecutionState | null): string {
  const raw = (liveExecution?.error_message || '').trim()
  if (raw) return `⚠️ ${raw}`
  return '⚠️ 生成遇到问题，请重试。如持续失败请联系管理员。'
}

function applyLiveExecutionErrorToMessages(
  target: Msg[],
  liveExecution?: LiveExecutionState | null,
): Msg[] {
  if (!Array.isArray(target) || !target.length) return target
  if (!liveExecution || liveExecution.status !== 'error') return target

  for (let i = target.length - 1; i >= 0; i -= 1) {
    const message = target[i]
    if (!message || message.role !== 'assistant') continue
    const hasContent = !!message.content?.trim()
    const hasTimeline = !!message.timeline?.length
    if (hasContent || hasTimeline) return target

    const next = [...target]
    next[i] = {
      ...message,
      content: getLiveExecutionErrorText(liveExecution),
    }
    return next
  }

  return target
}

// 压缩摘要
const compressionSummary = ref<string>('')
const compressionSavedTokens = ref<number>(0)
const compressionSplitMsgId = ref<number | null>(null)
const regeneratingTitle = ref(false)
// 对比模式
const compareMode = ref(false)
const compareModelBProviderId = ref<number | null>(null)
const compareModelBName = ref<string | null>(null)
const autoRouteEnabled = ref(true)
const comparingConvId = ref<number | null>(null)
const comparisonResults = ref<{
  side: 'a' | 'b'
  content: string
}[]>([])
const comparisonId = ref<number | null>(null)
const comparisonDone = ref(false)
const choosingWinner = ref(false)

const {
  loadModelList,
  loadSkillList,
  loadMcpList,
  loadTemplateList,
} = useComposerCatalogs({
  modelList,
  skillList,
  mcpList,
  templateList,
  currentTemplateId,
  loadingTemplate,
  shouldApplyTemplateDefault: () => !currentConvId.value,
})

const {
  setOptimizedPromptContainerRef,
  updateOptimizedPromptAutoScroll,
  scrollOptimizedPromptToBottom,
  handleOptimizePrompt,
  stopOptimizing,
  applyOptimizedPrompt,
} = usePromptOptimizer({
  inputText,
  optimizing,
  showOptimizedDialog,
  optimizedPrompt,
  optimizeAbortController,
  optimizedPromptContainerRef,
  shouldAutoScrollOptimizedPrompt,
})

const {
  initAutoRoutePreference,
  setAutoRouteEnabled,
  disableAutoRoute,
} = useAutoRoutePreference({
  autoRouteEnabled,
  onEnable: () => {
    compareMode.value = false
  },
})

const { ensureMultimodalSupport } = useMultimodalGuard()

async function openModelList() {
  try {
    await loadModelList()
  } catch {
    ElMessage.error('加载模型列表失败')
    return
  }
  listSearchQuery.value = ''
  showModelList.value = true
  selectedModelIndex.value = 0
  nextTick(() => { (document.querySelector('.model-list .list-search-input') as HTMLInputElement)?.focus() })
}

async function openSkillList() {
  try {
    await loadSkillList()
  } catch {
    ElMessage.error('加载技能列表失败')
    return
  }
  listSearchQuery.value = ''
  showSkillList.value = true
  selectedSkillIndex.value = 0
  nextTick(() => { (document.querySelector('.skill-list .list-search-input') as HTMLInputElement)?.focus() })
}

async function openMcpList() {
  try {
    await loadMcpList()
  } catch {
    ElMessage.error('加载 MCP 列表失败')
    return
  }
  listSearchQuery.value = ''
  showMcpList.value = true
  selectedMcpIndex.value = 0
  nextTick(() => { (document.querySelector('.mcp-list .list-search-input') as HTMLInputElement)?.focus() })
}

async function openTemplateList() {
  try {
    await loadTemplateList()
  } catch {
    ElMessage.error('加载模板列表失败')
    return
  }
  listSearchQuery.value = ''
  showTemplateList.value = true
  selectedTemplateIndex.value = 0
  nextTick(() => { (document.querySelector('.template-list .list-search-input') as HTMLInputElement)?.focus() })
}

// 加载当前对话的模板
async function loadCurrentTemplate(convId: number) {
  if (!convId) {
    currentTemplateId.value = null
    return
  }
  try {
    const res: any = await getPromptTemplate(convId)
    currentTemplateId.value = res.data?.prompt_template_id ?? null
  } catch {
    currentTemplateId.value = null
  }
}

// 切换模板
async function handleTemplateChange(templateId: number | null) {
  const previousTemplateId = currentTemplateId.value
  currentTemplateId.value = templateId

  if (!currentConvId.value) return

  loadingTemplate.value = true
  try {
    if (templateId) {
      await switchPromptTemplate(currentConvId.value, templateId)
      ElMessage.success('模板已切换')
    }
    await loadCurrentTemplate(currentConvId.value)
  } catch (error: any) {
    console.error('切换模板失败:', error)
    ElMessage.error(error.response?.data?.message || '切换模板失败')
    currentTemplateId.value = previousTemplateId
  } finally {
    loadingTemplate.value = false
  }
}

async function handleTemplatePopoverVisible(visible: boolean) {
  templatePopoverVisible.value = visible
  if (!visible) return
  try {
    await loadTemplateList()
  } catch {
    ElMessage.error('加载模板列表失败')
  }
}

async function handleTemplateSelect(templateId: number | null) {
  templatePopoverVisible.value = false
  await handleTemplateChange(templateId)
}

// 加载所有可用指令
async function loadAllCommands() {
  if (allCommands.value.length > 0) return
  
  const commands: any[] = [
    { name: '/new', label: '新建对话', description: '创建新的对话' },
    { name: '/prompt', label: '选择模板', description: '选择提示词模板' },
    { name: '/sandbox', label: '沙箱文件', description: '打开沙箱文件管理' },
    { name: '/skills', label: 'List Skills', description: '浏览所有技能' },
    { name: '/mcps', label: 'List MCPs', description: '浏览 MCP 服务' },
    { name: '/model', label: '切换模型', description: '切换 AI 模型' },
    { name: '/compact', label: '压缩上下文', description: '压缩对话历史' },
    { name: '/export', label: '导出对话', description: '导出当前对话' },
    { name: '/theme', label: '切换主题', description: '切换深色/浅色主题' },
  ]
  
  // 加载技能列表
  try {
    const { getSkillList } = await import('@/api/skills')
    const res: any = await getSkillList({ page: 1, page_size: 100 })
    const skills = res.items || []
    skills.forEach((skill: any) => {
      commands.push({
        name: `/${skill.name}`,
        label: skill.name,
        description: skill.description || '切换到此技能',
        data: skill
      })
    })
  } catch (error) {
    console.error('加载技能列表失败:', error)
  }
  
  allCommands.value = commands
}

// 导出弹窗
const exportVisible = ref(false)
const exportForm = ref({ format: 'md' as 'md' | 'docx', scope: 'last' as 'last' | 'all' })
const exporting = ref(false)
const inputExpanded = ref(false)
const inputKey = ref(0)
const isComposing = ref(false)

function toggleExpand() {
  inputExpanded.value = !inputExpanded.value
  inputKey.value++
}

async function handleExport() {
  if (!currentConvId.value) return
  exporting.value = true
  try {
    await exportConversation(currentConvId.value, exportForm.value.format, exportForm.value.scope)
    exportVisible.value = false
  } finally {
    exporting.value = false
  }
}

async function handleExportMessage(messageId: number, format: 'md' | 'docx') {
  if (!currentConvId.value) return
  acknowledgeExportHint(messageId)
  await exportConversation(currentConvId.value, format, 'message', messageId)
}

// 评分反馈
const {
  feedbackVisible,
  feedbackForm,
  feedbackSubmitting,
  currentFeedback,
  starHover,
  loadFeedback,
  openFeedback,
  handleFeedback,
  clearFeedbackState,
} = useConversationFeedback({
  getCurrentConversationId: () => currentConvId.value,
  fetchFeedback: async (conversationId) => {
    return await getFeedback(conversationId) as any
  },
  submitFeedback,
  showSuccess: (message) => ElMessage.success(message),
})

const convIdFromRoute = computed(() => route.params.id ? Number(route.params.id) : null)
const skillIdFromQuery = computed(() => route.query.skill_id ? Number(route.query.skill_id) : null)
const adminViewFromQuery = computed(() => route.query.admin_view === '1' || route.query.admin_view === 'true')

function buildChatRoute(conversationId?: number | null, extraQuery?: Record<string, string | undefined>) {
  const query: Record<string, string> = {}

  Object.entries(route.query).forEach(([key, value]) => {
    if (typeof value === 'string') {
      query[key] = value
    }
  })

  if (extraQuery) {
    Object.entries(extraQuery).forEach(([key, value]) => {
      if (value === undefined) {
        delete query[key]
      } else {
        query[key] = value
      }
    })
  }

  return {
    name: 'Chat' as const,
    params: conversationId ? { id: conversationId } : {},
    query,
  }
}

const {
  sandboxPanelVisible,
  sandboxLauncherVisible,
  sandboxLauncherTop,
  sandboxLauncherDragging,
  sandboxLauncherStyle,
  syncSandboxLauncherTop,
  handleSandboxLauncherResize,
  openSandboxPanel,
  closeSandboxPanel,
  handleSandboxDrawerClosed,
  handleSandboxLauncherPointerDown,
  handleSandboxLauncherPointerMove,
  handleSandboxLauncherPointerUp,
  handleSandboxLauncherPointerCancel,
  syncSandboxPanelFromRoute,
} = useSandboxLauncher({
  getCurrentConversationId: () => currentConvId.value,
  onOpenPanel: () => {
    void router.replace(buildChatRoute(currentConvId.value, { panel: 'sandbox' }))
  },
  onClosePanel: () => {
    void router.replace(buildChatRoute(currentConvId.value, { panel: undefined }))
  },
  onNoConversation: () => {
    ElMessage.warning('请先创建或选择一个对话')
  },
})

function isActiveConversationRoute(convId: number) {
  return convIdFromRoute.value === convId
}

function shouldApplyConversationLoad(convId: number, requestSeq: number) {
  return requestSeq === conversationLoadRequestSeq && isActiveConversationRoute(convId)
}

function _findToolResult(
  allMsgs: Array<Record<string, unknown>>,
  toolCallId: string,
): { content: string; isError: boolean; isPending: boolean; files: GeneratedFile[] } {
  const toolMsg = allMsgs.find((m) => m.role === 'tool' && m.tool_call_id === toolCallId) as
    | { content?: string; generated_files?: Array<{ file_id: number; original_name: string; file_size: number }> }
    | undefined
  if (!toolMsg) return { content: '', isError: false, isPending: true, files: [] }
  const raw = toolMsg.content || ''
  let isError = false
  try {
    const parsed = JSON.parse(raw)
    if (parsed.error === true) isError = true
  } catch { /* not JSON, treat as success */ }
  const files = (toolMsg.generated_files || []).map((f) => ({
    fileId: f.file_id, filename: f.original_name, fileSize: f.file_size,
  }))
  return { content: raw.substring(0, 200), isError, isPending: false, files }
}

function shouldKeepPendingToolCallState(
  liveExecution?: LiveExecutionState | null,
): boolean {
  const status = liveExecution?.status
  return status === 'running' || status === 'waiting_skill_confirmation'
}

function getIncompleteToolCallErrorText(
  liveExecution?: LiveExecutionState | null,
): string {
  const status = liveExecution?.status
  if (status === 'cancelled') return '⚠️ 工具调用已取消（本轮任务已停止）。'
  if (status === 'error') return getLiveExecutionErrorText(liveExecution)
  return '⚠️ 工具调用未完成（任务已结束）。'
}

function normalizeIncompleteToolCallTimeline(
  target: Msg[],
  liveExecution?: LiveExecutionState | null,
): Msg[] {
  if (!Array.isArray(target) || !target.length) return target
  if (shouldKeepPendingToolCallState(liveExecution)) return target

  const fallbackError = getIncompleteToolCallErrorText(liveExecution)
  let changed = false
  const next = target.map((message) => {
    if (!message.timeline?.length) return message
    let timelineChanged = false
    const nextTimeline = message.timeline.map((item) => {
      if (item.type !== 'tool_call' || item.status !== 'calling') return item
      timelineChanged = true
      changed = true
      return {
        ...item,
        status: 'error' as const,
        errorMessage: item.errorMessage || fallbackError,
        resultPreview: undefined,
      }
    })
    if (!timelineChanged) return message
    return {
      ...message,
      timeline: nextTimeline,
    }
  })

  return changed ? next : target
}

function syncConversationLiveState(conversationId: number, liveExecution?: LiveExecutionState | null) {
  conversationExecution.syncLiveState(conversationId, liveExecution)
}

function syncSidebarConversationLiveState(
  conversationId: number,
  liveExecution?: LiveExecutionState | null,
  sidebarSignal?: SidebarSignal | null,
) {
  syncSidebarConversationFromDetail({
    id: conversationId,
    live_execution: liveExecution,
    sidebar_signal: sidebarSignal,
  })
}

function applyConversationSyncEvent(event: ConversationSyncEvent) {
  const conversationId = Number(event.conversation_id || 0)
  if (!conversationId) return

  if (event.type === 'conversation.deleted') {
    const index = conversations.value.findIndex((conv) => conv.id === conversationId)
    if (index >= 0) {
      conversations.value.splice(index, 1)
      conversations.value = [...conversations.value]
    }
    if (currentConvId.value === conversationId) {
      void router.replace(buildChatRoute(null, { panel: undefined }))
    }
    return
  }

  const patch = event.patch || {}
  const nextLiveExecution = patch.live_execution
  const nextSidebarSignal = patch.sidebar_signal
  const nextTitle = typeof patch.title === 'string' ? patch.title : undefined
  const nextUnreadCount = Number(patch.sandbox_unread_change_count || 0)

  syncSidebarConversationFromDetail({
    id: conversationId,
    title: nextTitle,
    live_execution: nextLiveExecution,
    sidebar_signal: nextSidebarSignal,
  })

  if (currentConvId.value !== conversationId) return

  if (nextLiveExecution) {
    syncConversationLiveState(conversationId, nextLiveExecution)
    const normalizedTimeline = normalizeIncompleteToolCallTimeline(messages.value, nextLiveExecution)
    const normalized = applyLiveExecutionErrorToMessages(normalizedTimeline, nextLiveExecution)
    if (normalized !== messages.value) {
      messages.value = normalized
    }
  }

  if (nextTitle) {
    currentTitle.value = nextTitle
  }
  if (Number.isFinite(nextUnreadCount)) {
    sandboxUnreadChangeCount.value = nextUnreadCount
  }

  const nextVersion = patch.detail_version || ''
  if (nextVersion) {
    const prevVersion = currentConversationLiveStateVersion.value
    currentConversationLiveStateVersion.value = nextVersion
    if (prevVersion && prevVersion !== nextVersion) {
      void loadConversation(conversationId, { skipCache: true, silent: true })
    }
  }
}

function syncSidebarConversationFromDetail(detail: {
  id: number
  title?: string
  skill_id?: number | null
  skill_name?: string
  active_skills?: ActiveSkillLite[]
  tags?: TagInfo[]
  live_execution?: LiveExecutionState | null
  sidebar_signal?: SidebarSignal | null
}) {
  const index = conversations.value.findIndex((conv) => conv.id === detail.id)
  if (index < 0) return

  const current = conversations.value[index]
  if (!current) return
  const nextLiveExecution = detail.live_execution ?? current.live_execution ?? null
  const nextSidebarSignal = detail.sidebar_signal ?? current.sidebar_signal ?? null
  const nextTitle = detail.title ?? current.title
  const nextSkillId = detail.skill_id ?? current.skill_id
  const nextActiveSkills = Array.isArray(detail.active_skills) ? detail.active_skills : current.active_skills
  const nextSkillName = detail.skill_name
    ?? (Array.isArray(nextActiveSkills) ? formatSkillDisplayName(nextActiveSkills) : current.skill_name)
  const nextTags = Array.isArray(detail.tags) ? detail.tags : current.tags

  const hasChanged = current.title !== nextTitle
    || current.skill_id !== nextSkillId
    || current.skill_name !== nextSkillName
    || !areActiveSkillsEqual(current.active_skills, nextActiveSkills)
    || !areTagsEqual(current.tags, nextTags)
    || JSON.stringify(current.live_execution ?? null) !== JSON.stringify(nextLiveExecution)
    || JSON.stringify(current.sidebar_signal ?? null) !== JSON.stringify(nextSidebarSignal)

  if (!hasChanged) return

  conversations.value[index] = {
    ...current,
    title: nextTitle,
    skill_id: nextSkillId,
    skill_name: nextSkillName,
    active_skills: nextActiveSkills,
    tags: nextTags,
    live_execution: nextLiveExecution ?? undefined,
    sidebar_signal: nextSidebarSignal ?? undefined,
  }
}

function syncConversationTitleLocally(conversationId: number, title?: string | null) {
  const nextTitle = (title || '').trim()
  if (!nextTitle) return
  if (currentConvId.value === conversationId) {
    currentTitle.value = nextTitle
  }
  syncSidebarConversationFromDetail({
    id: conversationId,
    title: nextTitle,
  })
}

function parseConversationDetailVersion(
  version: string,
): ConversationDetailVersionPayload | null {
  if (!version) return null
  try {
    return JSON.parse(version) as ConversationDetailVersionPayload
  } catch {
    return null
  }
}

function isTitleOnlyDetailVersionChange(
  previousVersion: string,
  nextVersion: string,
) {
  const previous = parseConversationDetailVersion(previousVersion)
  const next = parseConversationDetailVersion(nextVersion)
  if (!previous || !next) return false

  return previous.status === next.status
    && previous.message_id === next.message_id
    && previous.error_message === next.error_message
    && previous.stage === next.stage
    && previous.stage_detail === next.stage_detail
    && previous.round_no === next.round_no
    && previous.active_skill_ids === next.active_skill_ids
    && previous.current_provider_id === next.current_provider_id
    && previous.current_model_name === next.current_model_name
    && previous.sandbox_unread_change_count === next.sandbox_unread_change_count
    && previous.live_updated_at === next.live_updated_at
    && previous.title !== next.title
}

function buildConversationFingerprint(detail: any): string {
  const messageFingerprints = Array.isArray(detail?.messages)
    ? detail.messages.map((message: any) => ({
        id: message.id,
        role: message.role,
        content: message.content || '',
        reasoning_content: message.reasoning_content || '',
        parent_id: message.parent_id ?? null,
        branch_index: message.branch_index ?? 0,
        sibling_count: message.sibling_count ?? 0,
        child_branch_count: message.child_branch_count ?? 0,
        active_child_branch_index: message.active_child_branch_index ?? 0,
        tool_calls: Array.isArray(message.tool_calls)
          ? message.tool_calls.map((toolCall: any) => ({
              tool_call_id: toolCall.tool_call_id,
              tool_name: toolCall.tool_name,
              arguments: toolCall.arguments,
            }))
          : [],
      }))
    : []

  return JSON.stringify({
    id: detail?.id ?? null,
    title: detail?.title || '',
    current_provider_id: detail?.current_provider_id ?? null,
    current_model_name: detail?.current_model_name ?? null,
    active_skills: Array.isArray(detail?.active_skills)
      ? detail.active_skills.map((skill: any) => ({
          id: skill.id,
          name: skill.name,
        }))
      : [],
    live_execution: {
      status: detail?.live_execution?.status || 'idle',
      message_id: detail?.live_execution?.message_id ?? null,
      error_message: detail?.live_execution?.error_message ?? null,
      stage: detail?.live_execution?.stage ?? null,
      stage_detail: detail?.live_execution?.stage_detail ?? null,
      round_no: detail?.live_execution?.round_no ?? null,
      updated_at: detail?.live_execution?.updated_at ?? null,
    },
    sidebar_signal: {
      state: detail?.sidebar_signal?.state ?? 'none',
      updated_at: detail?.sidebar_signal?.updated_at ?? null,
      read_at: detail?.sidebar_signal?.read_at ?? null,
    },
    messages: messageFingerprints,
  })
}

async function loadConversation(
  convId: number,
  options: { skipCache?: boolean; silent?: boolean } = {},
) {
  const { skipCache = false, silent = false } = options
  const requestSeq = ++conversationLoadRequestSeq

  if (!isActiveConversationRoute(convId)) {
    return
  }

  async function acknowledgeSidebarSignalRead() {
    if (adminViewFromQuery.value) return
    try {
      const response: any = await markConversationSidebarSignalRead(convId)
      const sidebarSignal = response?.data?.sidebar_signal
      if (sidebarSignal) {
        syncSidebarConversationFromDetail({
          id: convId,
          sidebar_signal: sidebarSignal,
        })
      }
    } catch {
      // ignore acknowledge errors
    }
  }

  // 如果该对话正在生成中，从缓存恢复
  const cached = skipCache ? undefined : chatStore.getCachedConversationMessages(convId)
  if (cached) {
    if (!shouldApplyConversationLoad(convId, requestSeq)) {
      return
    }
    currentConvId.value = convId
    chatStore.markConversationSeen(convId)
    if (!silent) {
      void acknowledgeSidebarSignalRead()
    }
    const cachedConv = conversations.value.find((conv) => conv.id === convId)
    if (cachedConv) {
      currentTitle.value = cachedConv.title
      applyCurrentActiveSkills(cachedConv.active_skills || [])
    }
    messages.value = applyMessageUiState(messages.value, cached)
    if (silent) {
      maybeActivateExportHintForLatestAssistant()
    }
    await loadCompressionSummary({ silent })
    if (!silent) {
      scrollToBottom(true)
    }
    if (shouldForceRefreshConversationDetailFromCache({
      cachedMessages: cached,
      isConversationGenerating: chatStore.isConversationGenerating(convId),
      isStreamOwnedByView: isConversationStreamOwnedByView(convId),
      hasSidebarSignal: Boolean(cachedConv?.sidebar_signal && cachedConv.sidebar_signal.state !== 'none'),
    })) {
      void loadConversation(convId, { skipCache: true, silent: true })
    }
    return
  }

  if (!silent) {
    loadingConv.value = true
  }
  try {
    const res: any = await getConversationDetail(
      convId,
      adminViewFromQuery.value ? { admin_view: true } : undefined,
      silent ? { _silent: true } : undefined,
    )
    const d = res.data
    if (!shouldApplyConversationLoad(convId, requestSeq) || d.id !== convId) {
      return
    }
    const nextFingerprint = buildConversationFingerprint(d)
    if (
      silent &&
      currentConvId.value === d.id &&
      currentConversationFingerprint.value === nextFingerprint
    ) {
      return
    }

    currentConvId.value = d.id
    chatStore.markConversationSeen(d.id)
    syncConversationLiveState(d.id, d.live_execution)
    syncSidebarConversationFromDetail(d)
    if (!silent) {
      void acknowledgeSidebarSignalRead()
    }
    currentConversationLiveStateVersion.value = d.detail_version || ''
    sandboxUnreadChangeCount.value = Number(d.sandbox_unread_change_count || 0)
    currentConversationFingerprint.value = nextFingerprint
    currentTitle.value = d.title
    applyCurrentActiveSkills(Array.isArray(d.active_skills) ? d.active_skills : [])
    isChatMode.value = true
    const previousClientKeysById = new Map<number, string>()
    messages.value.forEach((message) => {
      if (typeof message.id === 'number') {
        previousClientKeysById.set(message.id, message.clientKey)
      }
    })
    const rawMsgs = d.messages.filter((m: any) => m.role !== 'tool')
    const merged: Msg[] = []

    for (const m of rawMsgs) {
      const msg: Msg = {
        clientKey: buildMessageClientKey(m.id, m.role, previousClientKeysById),
        id: m.id,
        role: m.role,
        content: m.content,
        files: m.files || [],
        parentId: m.parent_id ?? null,
        branchIndex: m.branch_index ?? 0,
        siblingCount: m.sibling_count ?? 1,
        childBranchCount: m.child_branch_count ?? 0,
        activeChildBranchIndex: m.active_child_branch_index ?? 0,
        referencedMessageIds: m.referenced_message_ids || undefined,
      }
      if (m.role === 'assistant' && m.tool_calls && m.tool_calls.length > 0) {
        msg.timeline = m.tool_calls.map((tc: any) => {
          const result = _findToolResult(d.messages, tc.tool_call_id)
          const keepPending = shouldKeepPendingToolCallState(d.live_execution)
          const isPending = result.isPending && keepPending
          const isError = !isPending && (result.isError || result.isPending)
          return {
            type: 'tool_call' as const,
            toolCallId: tc.tool_call_id,
            toolName: tc.tool_name,
            arguments: tc.arguments,
            status: isPending ? 'calling' as const : isError ? 'error' as const : 'success' as const,
            resultPreview: isPending || isError ? undefined : result.content,
            errorMessage: isPending
              ? undefined
              : result.isPending
                ? getIncompleteToolCallErrorText(d.live_execution)
                : result.isError
                  ? result.content
                  : undefined,
            files: result.files.length > 0 ? result.files : undefined,
          }
        })
      }
      if (m.role === 'assistant' && m.reasoning_content) {
        if (!msg.timeline) msg.timeline = []
        msg.timeline.unshift({ type: 'thinking' as const, content: m.reasoning_content, isThinking: false })
      }
      merged.push(msg)
    }

    const normalizedTimeline = normalizeIncompleteToolCallTimeline(
      merged,
      d.live_execution,
    )
    const nextMessages = applyMessageUiState(
      messages.value,
      applyLiveExecutionErrorToMessages(normalizedTimeline, d.live_execution),
    )
    if (silent && areMessagesRenderEqual(messages.value, nextMessages)) {
      maybeActivateExportHintForLatestAssistant()
      return
    }
    if (silent && canPatchLatestAssistantOnly(messages.value, nextMessages)) {
      const currentLastAssistantIndex = [...messages.value]
        .map((item, index) => ({ item, index }))
        .reverse()
        .find(({ item }) => item.role === 'assistant')?.index
      if (typeof currentLastAssistantIndex === 'number') {
        const patched = [...messages.value]
        patched[currentLastAssistantIndex] = nextMessages[currentLastAssistantIndex]!
        messages.value = patched
      } else {
        messages.value = nextMessages
      }
    } else {
      messages.value = nextMessages
    }
  recoverSkillActivationPromptIfMissing(convId, d.live_execution)
  recoverPendingSkillResumeIfResolved(convId, d.live_execution)
  if (silent) {
    maybeActivateExportHintForLatestAssistant()
  }
    currentProviderId.value = d.current_provider_id ?? null
    currentModelName.value = d.current_model_name ?? null
    // 仅当对话有明确模型绑定时才覆盖用户已选模型
    if (d.current_provider_id && d.current_model_name) {
      selectedProviderId.value = d.current_provider_id
      selectedModelName.value = d.current_model_name
    }
    await loadCompressionSummary({ silent })
    if (!silent) {
      scrollToBottom(true)
    }
    if (!adminViewFromQuery.value) {
      loadFeedback(convId)
      await loadCurrentTemplate(convId)
    } else {
      clearFeedbackState()
      currentTemplateId.value = null
    }
  } finally {
    if (!silent) {
      loadingConv.value = false
    }
  }
}

function stopConversationPolling() {
  conversationLiveState.stopPolling()
}

function bindConversationStream(
  convId: number,
  controller: AbortController,
  actionType: Parameters<typeof conversationExecution.runConversationAction>[0]['actionType'] = 'send',
) {
  return conversationExecution.runConversationAction({
    conversationId: convId,
    actionType,
    abortController: controller,
  })
}

function releaseConversationStream(
  convId: number,
  streamSessionId?: string,
  options: Parameters<typeof conversationExecution.releaseConversationStream>[2] = {},
) {
  conversationExecution.releaseConversationStream(convId, streamSessionId, options)
}

function isConversationStreamOwnedByView(convId: number | null) {
  return conversationExecution.isConversationStreamOwnedByView(convId)
}

const conversationLiveState = useConversationLiveState({
  intervalMs: 1000,
  shouldSkipPoll: () => !currentConvId.value,
  poll: async () => {
    const convId = currentConvId.value
    if (!convId) return
    await refreshConversationFromLiveState(convId)
  },
})

const pollingHealth = conversationLiveState.pollingHealth
const lastLiveSyncErrorMessage = conversationLiveState.lastPollErrorMessage

const conversationEvents = useConversationEvents({
  onEvent: (event) => {
    applyConversationSyncEvent(event)
  },
})

const isEventStreamConnected = computed(() => conversationEvents.connectionState.value === 'connected')

async function refreshConversationFromLiveState(convId: number) {
  const res: any = await getConversationLiveState(
    convId,
    adminViewFromQuery.value ? { admin_view: true } : undefined,
    { _silent: true },
  )
  if (currentConvId.value !== convId) return

  const snapshot = res.data as ConversationLiveStateSnapshot
  syncConversationLiveState(convId, snapshot.live_execution)
  syncSidebarConversationLiveState(convId, snapshot.live_execution, snapshot.sidebar_signal)
  const liveStatus = snapshot.live_execution?.status || 'idle'
  if (liveStatus !== 'running' && liveStatus !== 'waiting_skill_confirmation') {
    if (removeTrailingEmptyAssistantPlaceholder(messages.value)) {
      messages.value = [...messages.value]
    }
  }
  sandboxUnreadChangeCount.value = Number(snapshot.sandbox_unread_change_count || 0)
  const normalizedTimeline = normalizeIncompleteToolCallTimeline(
    messages.value,
    snapshot.live_execution,
  )
  const normalized = applyLiveExecutionErrorToMessages(
    normalizedTimeline,
    snapshot.live_execution,
  )
  if (normalized !== messages.value) {
    messages.value = normalized
  }
  recoverSkillActivationPromptIfMissing(convId, snapshot.live_execution)
  recoverPendingSkillResumeIfResolved(convId, snapshot.live_execution)

  const nextVersion = snapshot.detail_version || ''
  const prevVersion = currentConversationLiveStateVersion.value
  currentConversationLiveStateVersion.value = nextVersion

  if (prevVersion && prevVersion !== nextVersion) {
    if (isTitleOnlyDetailVersionChange(prevVersion, nextVersion)) {
      syncConversationTitleLocally(convId, parseConversationDetailVersion(nextVersion)?.title)
      return
    }
    await loadConversation(convId, { skipCache: true, silent: true })
  }
}

function startConversationPolling() {
  conversationLiveState.startPolling()
}

async function markSandboxChangesReadForCurrentConversation(conversationId: number) {
  if (!conversationId) return
  sandboxUnreadChangeCount.value = 0
  try {
    await markSandboxChangesRead(conversationId)
  } catch {
    // 忽略已读上报异常，避免影响抽屉打开
  }
}

async function startNewConversation(skillId: number) {
  loadingConv.value = true
  try {
    const res: any = await createConversation(skillId)
    const d = res.data
    currentConvId.value = d.conversation_id
    currentConversationLiveStateVersion.value = ''
    sandboxUnreadChangeCount.value = 0
    currentTitle.value = d.skill_name || '新对话'
    applyCurrentActiveSkills(Array.isArray(d.active_skills) ? d.active_skills : [])
    currentProviderId.value = d.model_provider_id ?? null
    currentModelName.value = d.model_name ?? null
    if (d.model_provider_id && d.model_name) {
      selectedProviderId.value = d.model_provider_id
      selectedModelName.value = d.model_name
    }
    messages.value = d.messages.map((m: any) => ({
      clientKey: m.id ? `server-${m.id}` : nextMessageClientKey(m.role),
      id: m.id,
      role: m.role,
      content: m.content,
    }))
    router.replace(buildChatRoute(d.conversation_id, { skill_id: undefined, panel: undefined }))
    await loadConversationList()
    await loadCompressionSummary()
    await loadCurrentTemplate(d.conversation_id)
    scrollToBottom(true)
  } finally {
    loadingConv.value = false
  }
}

const isGenerating = computed(() =>
  chatStore.isConversationGenerating(currentConvId.value)
)

const currentExecutionSnapshot = computed(() => {
  const convId = currentConvId.value
  if (!convId) return null
  return conversationExecutionStates.value.get(convId) || null
})
const currentLiveExecution = computed<LiveExecutionState | null>(() => {
  const convId = currentConvId.value
  if (!convId) return null
  const conversation = conversations.value.find((item) => item.id === convId)
  return conversation?.live_execution ?? null
})

const currentStatusState = computed(() => {
  const snapshotState = currentExecutionSnapshot.value?.state || null
  if (
    isGenerating.value
    && (snapshotState == null || snapshotState === 'idle' || snapshotState === 'completed' || snapshotState === 'failed')
  ) {
    return 'streaming'
  }
  return snapshotState
})
const currentStatusReason = computed(() => {
  if (
    currentStatusState.value === 'streaming'
    || currentStatusState.value === 'preparing'
    || currentStatusState.value === 'waiting_skill_confirmation'
  ) {
    return null
  }
  return currentExecutionSnapshot.value?.lastTerminalReason || null
})
const currentStatusErrorMessage = computed(() => {
  return currentExecutionSnapshot.value?.lastErrorMessage || lastLiveSyncErrorMessage.value || null
})

watch(
  [currentConvId, isGenerating, isEventStreamConnected],
  ([convId, generating, eventConnected]) => {
    if (!eventConnected && convId && (!generating || !isConversationStreamOwnedByView(convId))) {
      startConversationPolling()
      return
    }
    stopConversationPolling()
  },
  { immediate: true },
)

watch(isGenerating, (generating) => {
  if (!generating && pendingSkillResume.value) {
    void runPendingSkillResume()
  }
})

watch(
  isEventStreamConnected,
  (connected) => {
    if (connected) {
      stopConversationListAutoRefresh()
      return
    }
    startConversationListAutoRefresh(15000)
    void loadConversationList(false, { silent: true })
    if (currentConvId.value) {
      void refreshConversationFromLiveState(currentConvId.value)
    }
  },
  { immediate: true },
)

watch(currentConvId, (convId) => {
  conversationLiveState.resetHealth()
  if (convId) {
    hydrateHandledWaitingPromptKeys(convId)
  }
  pendingSkillResume.value = convId ? loadPersistedPendingSkillResume(convId) : null
  void loadReferenceState(convId)
  if (convId && pendingSkillResume.value && !isGenerating.value) {
    void runPendingSkillResume()
  }
})

function handlePageResume() {
  if (document.visibilityState === 'hidden') return
  if (!currentConvId.value) return
  if (!pendingSkillResume.value) {
    pendingSkillResume.value = loadPersistedPendingSkillResume(currentConvId.value)
  }
  if (!pendingSkillResume.value) return
  void runPendingSkillResume({ force: true })
}

async function handleStatusRefresh() {
  const convId = currentConvId.value
  if (!convId) return
  try {
    await loadConversation(convId, { skipCache: true, silent: true })
    conversationLiveState.resetHealth()
  } catch {
    // 保持状态条可见
  }
}

async function handleStatusRetry() {
  if (pendingSkillResume.value) {
    await runPendingSkillResume({ force: true })
    return
  }
  const terminalReason = currentStatusReason.value
  const shouldRetryGeneration = terminalReason === 'stream_disconnected'
    || terminalReason === 'error'
    || terminalReason === 'throw'

  if (shouldRetryGeneration) {
    const retryMessageId = getLatestRetryableAssistantMessageId(messages.value)
    if (retryMessageId !== null) {
      await handleRegenerate(retryMessageId)
      return
    }
  }

  await handleStatusRefresh()
}

function handleStatusDetails() {
  const detail = currentStatusErrorMessage.value || '暂无可用错误详情'
  void ElMessageBox.alert(detail, '错误详情', {
    confirmButtonText: '知道了',
    customClass: 'app-error-detail-dialog',
    confirmButtonClass: 'app-error-detail__confirm',
  })
}

function markStreamDisconnected(
  conversationId: number,
  streamSessionId: string,
) {
  if (!chatStore.isStreamOwnedBy(conversationId, streamSessionId)) return
  conversationExecution.finalizeConversationAction({
    conversationId,
    streamSessionId,
    reason: 'stream_disconnected',
    errorMessage: '连接已中断，请重试',
  })
}

function handleModelBSelected(providerId: number, modelName: string) {
  compareModelBProviderId.value = providerId
  compareModelBName.value = modelName
}

function handleCommandExecute(command: any) {
  executeCommand(command)
}

function buildQuotedMessagesFromIds(referencedIds: number[] = []) {
  return referencedIds
    .map((id) => {
      const matched = messages.value.find((message) => message.id === id)
      if (!matched) {
        return {
          id,
          role: 'assistant',
          content: `引用消息 #${id}`,
          created_at: new Date().toISOString(),
        }
      }
      return {
        id,
        role: matched.role,
        content: matched.content,
        created_at: new Date().toISOString(),
      }
    })
    .slice(0, 3)
}

function hasDraftContent() {
  const pendingFiles = fileUploaderRef.value?.getFiles() || []
  return Boolean(
    inputText.value.trim()
    || quotedMessages.value.length > 0
    || fileIds.value.length > 0
    || pendingFiles.length > 0,
  )
}

async function startMessageEdit(messageId: number) {
  const message = messages.value.find((item) => item.id === messageId && item.role === 'user')
  if (!message) {
    ElMessage.warning('仅支持编辑用户消息')
    return
  }

  if (hasDraftContent()) {
    try {
      await showDangerConfirm({
        title: '覆盖当前输入内容',
        subject: '输入框草稿',
        detail: '继续后将覆盖当前输入框中的文本、引用消息和附件。你可以在编辑模式中点击取消恢复。',
        confirmText: '继续覆盖',
        confirmType: 'danger',
      })
    } catch {
      return
    }
  }

  editDraftBackup.value = {
    draft: snapshotDraft(),
    files: (fileUploaderRef.value?.getFiles() || []).map((item: any) => ({ ...item })),
  }

  editingMessageId.value = messageId
  inputText.value = message.content || ''
  const referencedIds = (message.referencedMessageIds || [])
    .map((id) => Number(id))
    .filter((id) => Number.isFinite(id))
  quotedMessages.value = buildQuotedMessagesFromIds(referencedIds)

  const messageFiles = Array.isArray(message.files) ? message.files : []
  fileIds.value = messageFiles
    .map((file) => Number(file.file_id))
    .filter((id) => Number.isFinite(id))

  await nextTick()
  fileUploaderRef.value?.setFiles(messageFiles as any)
  const textarea = document.querySelector('.input-box textarea') as HTMLTextAreaElement | null
  textarea?.focus()
  scrollToBottom(true)
}

async function cancelMessageEdit() {
  if (editingMessageId.value === null) return

  const backup = editDraftBackup.value
  editingMessageId.value = null
  editDraftBackup.value = null

  if (backup) {
    restoreDraft(backup.draft)
    await nextTick()
    if (backup.files.length > 0) {
      fileUploaderRef.value?.setFiles(backup.files)
    } else {
      fileUploaderRef.value?.clear()
    }
    return
  }

  clearDraft()
  await nextTick()
  fileUploaderRef.value?.clear()
}

function handleQuote(messageId: number) {
  // 最多引用3条消息
  if (quotedMessages.value.length >= 3) {
    ElMessage.warning('最多只能引用3条消息')
    return
  }
  
  // 查找消息
  const message = messages.value.find(m => m.id === messageId)
  if (!message) return
  
  // 避免重复引用
  if (quotedMessages.value.some(m => m.id === messageId)) {
    ElMessage.info('该消息已被引用')
    return
  }
  
  quotedMessages.value.push({
    id: messageId,
    role: message.role,
    content: message.content,
    created_at: new Date().toISOString() // 使用当前时间作为占位
  })
}

function handleRemoveQuote(messageId: number) {
  quotedMessages.value = quotedMessages.value.filter(m => m.id !== messageId)
}


async function handleCompressConversation() {
  if (!currentConvId.value) {
    ElMessage.warning('请先选择一个对话')
    return
  }
  
  const loading = ElLoading.service({
    lock: true,
    text: '正在压缩对话上下文...',
    background: 'rgba(0, 0, 0, 0.7)'
  })
  
  try {
    const result = await compressConversation(currentConvId.value)
    loading.close()
    
    if (result.saved_tokens > 0) {
      ElMessage.success({
        message: `压缩完成！节省了 ${result.saved_tokens} tokens`,
        duration: 3000
      })
    } else {
      ElMessage.warning({
        message: `压缩完成，但摘要比原文更长，未能节省 Token`,
        duration: 3000
      })
    }
    
    // 加载压缩摘要
    await loadCompressionSummary()
  } catch (error: any) {
    loading.close()
    // 全局拦截器已经显示了错误，这里不再重复显示
  }
}

async function loadCompressionSummary(options: { silent?: boolean } = {}) {
  if (!currentConvId.value) return
  const { silent = false } = options
  
  try {
    const result = await getCompressionSummary(currentConvId.value)
    const nextSummary = result.summary || ''
    const nextSavedTokens = Number(result.saved_tokens || 0)
    const nextSplitMsgId = result.split_message_id ?? null
    const hasChanged = compressionSummary.value !== nextSummary
      || compressionSavedTokens.value !== nextSavedTokens
      || compressionSplitMsgId.value !== nextSplitMsgId
    if (!silent || hasChanged) {
      compressionSummary.value = nextSummary
      compressionSavedTokens.value = nextSavedTokens
      compressionSplitMsgId.value = nextSplitMsgId
    }
  } catch (error) {
    if (!silent) {
      compressionSummary.value = ''
      compressionSavedTokens.value = 0
      compressionSplitMsgId.value = null
    }
  }
}

async function regenerateTitleWithLLM() {
  const convId = currentConvId.value
  if (!convId || regeneratingTitle.value) return
  regeneratingTitle.value = true
  try {
    const response: any = await regenerateConversationTitle(convId)
    const nextTitle = response?.data?.title || response?.title || ''
    if (!nextTitle) {
      ElMessage.warning('标题生成失败，请稍后重试')
      return
    }
    syncConversationTitleLocally(convId, nextTitle)
    ElMessage.success('标题已重新生成')
  } finally {
    regeneratingTitle.value = false
  }
}

function startEditSidebarTitle(convId: number, title: string) {
  editingHeaderTitle.value = false
  editingSidebarTitleConvId.value = convId
  editingSidebarTitleText.value = title || ''
  nextTick(() => {
    const input = sidebarTitleInputRefs.get(convId)
    input?.focus()
    input?.select()
  })
}

function startEditHeaderTitle() {
  const convId = currentConvId.value
  if (!convId) return
  editingSidebarTitleConvId.value = null
  editingHeaderTitle.value = true
  editingHeaderTitleText.value = currentTitle.value || currentSkillName.value || '新对话'
  nextTick(() => {
    headerTitleInputRef.value?.focus()
    headerTitleInputRef.value?.select()
  })
}

async function persistConversationTitle(convId: number, title: string) {
  try {
    await updateConversationTitle(convId, title)
    syncConversationTitleLocally(convId, title)
  } catch {}
}

async function saveSidebarEditTitle() {
  const convId = editingSidebarTitleConvId.value
  const title = editingSidebarTitleText.value.trim()
  editingSidebarTitleConvId.value = null
  if (!convId || !title) return
  await persistConversationTitle(convId, title)
}

async function saveHeaderEditTitle() {
  const convId = currentConvId.value
  const title = editingHeaderTitleText.value.trim()
  editingHeaderTitle.value = false
  if (!convId || !title) return
  await persistConversationTitle(convId, title)
}

function cancelSidebarEditTitle() {
  editingSidebarTitleConvId.value = null
}

function cancelHeaderEditTitle() {
  editingHeaderTitle.value = false
}

async function handleSend() {
  const text = inputText.value.trim()
  acknowledgeAllExportHints()

  if (editingMessageId.value && text) {
    const editingTargetMessageId = editingMessageId.value
    const sendFileIds = [...fileIds.value]
    const referencedIds = quotedMessages.value
      .map((item) => Number(item.id))
      .filter((id) => Number.isFinite(id))

    clearDraft()
    fileUploaderRef.value?.clear()
    editingMessageId.value = null
    editDraftBackup.value = null

    await submitEditedMessage(editingTargetMessageId, text, sendFileIds, referencedIds)
    return
  }

  if (forkFromMessageId.value && text) {
    inputText.value = ''
    await handleSendFork(text)
    return
  }

  let convId: number | null = currentConvId.value

  if (!convId) {
    try {
      const res: any = await createConversation(skillIdFromQuery.value)
      convId = res.data.conversation_id
      currentConvId.value = convId
      currentConversationLiveStateVersion.value = ''
      currentTitle.value = '新对话'
      applyCurrentActiveSkills(Array.isArray(res.data?.active_skills) ? res.data.active_skills : [])
      router.replace(buildChatRoute(convId, { skill_id: undefined, panel: undefined }))
      
      loadConversationList()
    } catch {
      return
    }
  }

  if (!text || !convId || chatStore.isConversationGenerating(convId)) return
  const convIdNum = convId as number
  let sendPreparingMarked = false
  const markSendPreparing = () => {
    if (sendPreparingMarked) return
    sendPreparingMarked = conversationExecution.markActionPreparing(convIdNum, 'send')
  }
  const clearSendPreparing = () => {
    if (!sendPreparingMarked) return
    conversationExecution.clearActionPreparing(convIdNum, 'send')
    sendPreparingMarked = false
  }
  markSendPreparing()

  // 确保对话绑定的模型与用户选择一致
  if (!autoRouteEnabled.value && selectedProviderId.value && selectedModelName.value) {
    if (selectedProviderId.value !== currentProviderId.value || selectedModelName.value !== currentModelName.value) {
      try {
        await switchConversationModel(convId, selectedProviderId.value, selectedModelName.value)
        currentProviderId.value = selectedProviderId.value
        currentModelName.value = selectedModelName.value
      } catch (e) {
        console.error('切换模型失败:', e)
      }
    }
  }

  // 对比模式
  if (compareMode.value) {
    if (!selectedProviderId.value || !selectedModelName.value || !compareModelBProviderId.value || !compareModelBName.value) {
      clearSendPreparing()
      ElMessage.warning('请选择两个模型进行对比')
      return
    }
    clearSendPreparing()
    await handleCompare(convId, text)
    return
  }

  const referenceModeForThisTurn = nextTurnReferenceMode.value

  // 模型兼容性校验 — 检查是否有图片且模型不支持多模态
  const sendFiles = fileUploaderRef.value?.getFiles() || []
  try {
    const effectiveProviderId = selectedProviderId.value || currentProviderId.value
    const effectiveModelName = selectedModelName.value || currentModelName.value
    const allowed = await ensureMultimodalSupport({
      hasImages: sendFiles.some((file: any) => file.is_image),
      autoRouteEnabled: autoRouteEnabled.value,
      providerId: effectiveProviderId,
      modelName: effectiveModelName,
      modelList,
      loadModelList,
      showWarning: (message) => ElMessage.warning(message),
      showConfirm: showDangerConfirm,
      onUnsupportedConfirmed: () => {
        const imageFileIds = sendFiles
          .filter((file: any) => file.is_image)
          .map((file: any) => file.file_id)
        fileIds.value = fileIds.value.filter((id) => !imageFileIds.includes(id))
      },
    })
    if (!allowed) {
      clearSendPreparing()
      return
    }
  } catch {
    clearSendPreparing()
    return
  }

  const sendFileIds = [...fileIds.value]
  const referencedIds = quotedMessages.value
    .map(m => Number(m.id))
    .filter((id) => Number.isFinite(id))
  const draftSnapshot = snapshotDraft()
  
  clearDraft()
  fileUploaderRef.value?.clear()

  messages.value.push(createLocalMessage({
    role: 'user',
    content: text,
    files: sendFiles.map((f) => ({
      file_id: f.file_id,
      original_name: f.original_name,
      file_type: f.file_type,
      file_size: f.file_size,
    })),
  }))
  messages.value.push(createLocalMessage({ role: 'assistant', content: '', timeline: [] }))
  // 保存当前消息到缓存
  chatStore.cacheConversationMessages(convIdNum, [...messages.value])
  scrollToBottom(true)

  const abortCtrl = new AbortController()
  const streamSessionId = bindConversationStream(convIdNum, abortCtrl, 'send')

  await conversationExecution.sendMessage({
    conversationId: convIdNum,
    content: text,
    fileIds: sendFileIds,
    callbacks: {
    onChunk: (content) => {
      const cached = msgCache.value.get(convIdNum)
      if (!cached) return
      const last = cached[cached.length - 1]
      if (last && last.role === 'assistant') {
        last.content += content
      }
      if (currentConvId.value === convIdNum) {
        messages.value = [...cached]
        scrollToBottom()
      }
    },
    onThinkingDelta: (content) => {
      const cached = msgCache.value.get(convIdNum)
      if (!cached) return
      const last = cached[cached.length - 1]
      if (last && last.role === 'assistant') {
        if (!last.timeline) last.timeline = []
        const tl = last.timeline
        const cur = tl[tl.length - 1]
        if (cur && cur.type === 'thinking' && cur.isThinking) {
          cur.content += content
        } else {
          tl.push({ type: 'thinking', content, isThinking: true })
        }
        last.timeline = [...tl]
      }
      if (currentConvId.value === convIdNum) {
        messages.value = [...cached]
        scrollToBottom()
      }
    },
    onThinkingDone: () => {
      const cached = msgCache.value.get(convIdNum)
      if (!cached) return
      const last = cached[cached.length - 1]
      if (last && last.role === 'assistant' && last.timeline?.length) {
        const cur = last.timeline[last.timeline.length - 1]
        if (cur && cur.type === 'thinking') cur.isThinking = false
        last.timeline = [...last.timeline]
      }
      if (currentConvId.value === convIdNum) {
        messages.value = [...cached]
      }
    },
    onToolCallStart: (data) => {
      const cached = msgCache.value.get(convIdNum)
      if (!cached) return
      let last = cached[cached.length - 1]
      if (!last || last.role !== 'assistant') {
        cached.push(createLocalMessage({ role: 'assistant', content: '', timeline: [] }))
        last = cached[cached.length - 1]
      }
      if (!last) return
      if (!last.timeline) last.timeline = []
      last.timeline = [...last.timeline, {
        type: 'tool_call',
        toolCallId: data.toolCallId,
        toolName: data.toolName,
        arguments: data.arguments,
        status: 'calling' as const,
      }]
      if (currentConvId.value === convIdNum) {
        messages.value = [...cached]
        scrollToBottom()
      }
    },
    onToolCallProgress: (data) => {
      const cached = msgCache.value.get(convIdNum)
      if (!cached) return
      for (const m of cached) {
        const tc = m.timeline?.find((t: any) => t.type === 'tool_call' && t.toolCallId === data.toolCallId)
        if (tc) {
          tc.status = 'calling'
          tc.progressTick = data.progressTick
          tc.elapsedMs = data.elapsedMs
          tc.elapsedSeconds = data.elapsedSeconds
          m.timeline = [...m.timeline!]
          break
        }
      }
      if (currentConvId.value === convIdNum) {
        messages.value = [...cached]
      }
    },
    onToolCallResult: (data) => {
      const cached = msgCache.value.get(convIdNum)
      if (!cached) return
      for (const m of cached) {
        const tc = m.timeline?.find((t: any) => t.type === 'tool_call' && t.toolCallId === data.toolCallId)
        if (tc) {
          tc.status = 'success'
          tc.progressTick = undefined
          tc.elapsedMs = undefined
          tc.elapsedSeconds = undefined
          tc.resultPreview = data.resultPreview
          m.timeline = [...m.timeline!]
          break
        }
      }
      if (currentConvId.value === convIdNum) {
        messages.value = [...cached]
      }
    },
    onToolCallError: (data) => {
      const cached = msgCache.value.get(convIdNum)
      if (!cached) return
      for (const m of cached) {
        const tc = m.timeline?.find((t: any) => t.type === 'tool_call' && t.toolCallId === data.toolCallId)
        if (tc) {
          tc.status = 'error'
          tc.progressTick = undefined
          tc.elapsedMs = undefined
          tc.elapsedSeconds = undefined
          tc.errorMessage = data.errorMessage
          m.timeline = [...m.timeline!]
          break
        }
      }
      if (currentConvId.value === convIdNum) {
        messages.value = [...cached]
      }
    },
    onToolCallFiles: (data) => {
      const cached = msgCache.value.get(convIdNum)
      if (!cached) return
      for (const m of cached) {
        const tc = m.timeline?.find((t: any) => t.type === 'tool_call' && t.toolCallId === data.toolCallId)
        if (tc) {
          tc.files = data.files.map(f => ({ fileId: f.file_id, filename: f.filename, fileSize: f.file_size }))
          m.timeline = [...m.timeline!]
          break
        }
      }
      if (currentConvId.value === convIdNum) {
        messages.value = [...cached]
      }
    },
    onDone: (doneData) => {
      if (!chatStore.isStreamOwnedBy(convIdNum, streamSessionId)) return
      releaseConversationStream(convIdNum, streamSessionId, { terminalReason: 'done' })
      if (currentConvId.value === convIdNum) {
        finalizeVisibleConversationStream(convIdNum, doneData.message_id)
      } else {
        chatStore.clearCachedConversationMessages(convIdNum)
      }
      loadConversationList()
    },
    onCancelled: () => {
      if (!chatStore.isStreamOwnedBy(convIdNum, streamSessionId)) return
      releaseConversationStream(convIdNum, streamSessionId, { terminalReason: 'cancelled' })
      chatStore.clearCachedConversationMessages(convIdNum)
      void loadConversation(convIdNum, { skipCache: true })
      loadConversationList()
    },
    onTitleUpdated: (title) => {
      syncConversationTitleLocally(convIdNum, title)
      loadConversationList()
    },
    onContextWarning: (msg) => {
      if (currentConvId.value === convId) {
        ElMessage.warning(msg)
      }
    },
    onFallbackTriggered: (data) => {
      if (currentConvId.value === convId) {
        ElMessage.warning({
          message: data.message,
          duration: 3000,
        })
      }
    },
    onFallbackSwitched: (data) => {
      if (currentConvId.value === convId) {
        ElMessage.success({
          message: data.message,
          duration: 2000,
        })
      }
    },
    onSkillMatched: (data) => {
      if (currentConvId.value === convIdNum) {
        currentTitle.value = data.skill_name
        if (data.model_provider_id && data.model_name) {
          selectedProviderId.value = data.model_provider_id
          selectedModelName.value = data.model_name
          currentProviderId.value = data.model_provider_id
          currentModelName.value = data.model_name
        }
        ElMessage.success({ message: `已自动加载技能「${data.skill_name}」`, duration: 3000 })
        refreshCurrentConversationActiveSkills()
        loadConversationList()
      }
    },
    onSkillActivationRequest: async (data) => {
      if (!chatStore.isStreamOwnedBy(convIdNum, streamSessionId)) return
      // skill 激活确认请求到达后，该轮流式应切到等待确认态并释放当前流 owner。
      conversationExecution.releaseConversationStream(convIdNum, streamSessionId, {
        clearGenerating: true,
      })
      conversationExecution.markWaitingSkillConfirmation(convIdNum)
      await handleSkillActivationRequest(data)
    },
    onRouteSelected: (data) => {
      if (currentConvId.value === convIdNum) {
        // 切换到路由选中的模型
        currentProviderId.value = data.provider_id
        currentModelName.value = data.model_name
        selectedProviderId.value = data.provider_id
        selectedModelName.value = data.model_name
        // 关闭智能路由
        void disableAutoRoute()
        // 插入路由提示
        const cached = msgCache.value.get(convIdNum)
        if (cached) {
          const idx = cached.length - 1
          const lastMsg = idx >= 0 ? cached[idx] : undefined
          if (lastMsg && lastMsg.role === 'assistant') {
            cached.splice(idx, 0, createLocalMessage({
              role: 'system_notice',
              content: `已自动选择 ${data.model_name} 模型（原因：检测到${data.reason}）`,
            }))
            messages.value = [...cached]
            scrollToBottom()
          }
        }
        ElMessage.success({ message: `智能路由已为您选择 ${data.model_name}（${data.reason}）`, duration: 4000 })
      }
    },
    onStreamDisconnected: () => {
      markStreamDisconnected(convIdNum, streamSessionId)
    },
    onError: (msg) => {
      if (!chatStore.isStreamOwnedBy(convIdNum, streamSessionId)) return
      conversationExecution.handleActionErrorTerminal(convIdNum, streamSessionId, msg)
      const cached = msgCache.value.get(convIdNum)
      if (cached) {
        removeTrailingEmptyAssistantPlaceholder(cached)
        if (currentConvId.value === convIdNum) {
          messages.value = [...cached]
        }
      }
      if (currentConvId.value === convIdNum) {
        restoreDraft(draftSnapshot)
        fileUploaderRef.value?.setFiles(sendFiles as any)
      }
      chatStore.clearCachedConversationMessages(convIdNum)
      ElMessage.error(msg)
    },
    },
    abortSignal: abortCtrl.signal,
    referencedMessageIds: referencedIds,
    providerId: selectedProviderId.value,
    modelName: selectedModelName.value,
    referenceMode: referenceModeForThisTurn,
  }).catch((err: any) => {
    if (!chatStore.isStreamOwnedBy(convIdNum, streamSessionId)) return
    if (err?.name === 'AbortError') {
      releaseConversationStream(convIdNum, streamSessionId, { terminalReason: 'cancelled' })
      chatStore.clearCachedConversationMessages(convIdNum)
      loadConversationList()
    } else if (currentConvId.value === convIdNum) {
      restoreDraft(draftSnapshot)
      fileUploaderRef.value?.setFiles(sendFiles as any)
    }
  })
  nextTurnReferenceMode.value = null
}

async function handleStop() {
  const convId = currentConvId.value
  if (!convId) return
  const stopped = await conversationExecution.cancelConversationAction(convId, {
    reason: 'user_stop',
  })
  if (!stopped) return

  void cancelConversationGenerationWithMeta(convId, {
    reason: 'user_stop',
    source: 'chat_stop',
  }).catch(() => {
    // 忽略取消接口失败，前端已完成本地终态收尾
  })

  chatStore.clearCachedConversationMessages(convId)
  await loadConversation(convId, { skipCache: true })
  await loadConversationList()
  ElMessage.info('已停止生成')
}

async function handleCompare(convId: number, text: string) {
  if (!selectedProviderId.value || !selectedModelName.value || !compareModelBProviderId.value || !compareModelBName.value) {
    return
  }
  
  comparingConvId.value = convId
  comparisonResults.value = [
    { side: 'a', content: '' },
    { side: 'b', content: '' }
  ]
  comparisonId.value = null
  comparisonDone.value = false
  
  // 添加用户消息
  messages.value.push(createLocalMessage({ role: 'user', content: text }))
  inputText.value = ''
  
  try {
    const token = localStorage.getItem('access_token')
    const response = await fetch(`/api/conversations/${convId}/messages/compare`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        content: text,
        model_a_provider_id: selectedProviderId.value,
        model_a_name: selectedModelName.value,
        model_b_provider_id: compareModelBProviderId.value,
        model_b_name: compareModelBName.value
      })
    })
    
    if (!response.ok || !response.body) {
      ElMessage.error('对比请求失败')
      return
    }
    
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let _cmpId: number | null = null
    
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            
            if (data.side === 'a' && data.type === 'chunk') {
              const sideA = comparisonResults.value[0]
              if (sideA) sideA.content += data.content
            } else if (data.side === 'b' && data.type === 'chunk') {
              const sideB = comparisonResults.value[1]
              if (sideB) sideB.content += data.content
            } else if (data.type === 'done' && data.comparison_id) {
              _cmpId = data.comparison_id
            }
          } catch (e) {
            console.error('解析 SSE 数据失败:', e)
          }
        }
      }
    }
    
    // 显示内联选择卡片
    if (_cmpId) {
      comparisonId.value = _cmpId
      comparisonDone.value = true
      scrollToBottom(true)
    }
    
  } catch (e: any) {
    ElMessage.error(e?.message || '对比失败')
  } finally {
    comparingConvId.value = null
  }
}

async function handleChooseWinner(choice: 'a' | 'b') {
  const convId = currentConvId.value
  if (!convId || !comparisonId.value || choosingWinner.value) return
  choosingWinner.value = true
  try {
    const { chooseComparisonWinner } = await import('@/api/conversations')
    await chooseComparisonWinner(convId, comparisonId.value, choice)
    ElMessage.success('已选择优胜模型')
    compareMode.value = false
    comparisonDone.value = false
    comparisonId.value = null
    await loadConversation(convId)
    comparisonResults.value = []
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '选择失败')
  } finally {
    choosingWinner.value = false
  }
}

const { handleEdit: submitEditedMessage, handleRegenerate, handleSendFork, handleContinueAfterSkillActivation } = useConversationMessageActions({
  messages,
  isGenerating,
  getCurrentConversationId: () => currentConvId.value,
  getForkFromMessageId: () => forkFromMessageId.value,
  clearForkState: () => {
    forkFromMessageId.value = null
    messagesBeforeFork.value = null
  },
  acknowledgeAllExportHints,
  createLocalMessage,
  bindConversationStream,
  releaseConversationStream,
  isStreamOwnedBy: (conversationId, streamSessionId) => chatStore.isStreamOwnedBy(conversationId, streamSessionId),
  appendRunningToolCall,
  updateToolCallTimeline,
  markStreamDisconnected,
  onActionError: (conversationId, streamSessionId, errorMessage) => {
    conversationExecution.handleActionErrorTerminal(conversationId, streamSessionId, errorMessage)
  },
  editMessage: conversationExecution.editMessage,
  regenerateMessage: conversationExecution.regenerateMessage,
  continueFromMessage: conversationExecution.continueFromMessage,
  forkConversation: conversationExecution.forkConversation,
  loadConversation: async (conversationId) => {
    await loadConversation(conversationId)
  },
  loadConversationSkipCache: async (conversationId) => {
    await loadConversation(conversationId, { skipCache: true })
  },
  loadConversationList: async () => {
    await loadConversationList()
  },
  finalizeVisibleConversationStream,
  loadActiveSkills: () => {
    skillManagerRef.value?.loadActiveSkills?.()
  },
  markWaitingSkillConfirmation: (conversationId, streamSessionId) => {
    conversationExecution.markWaitingSkillConfirmation(conversationId, streamSessionId)
  },
  onSkillActivationRequest: (payload) => {
    void handleSkillActivationRequest(payload)
  },
  scrollToBottom,
  showWarning: (message) => ElMessage.warning(message),
  showError: (message) => ElMessage.error(message),
})

const isForkMode = computed(() => forkFromMessageId.value !== null)

function handleForkByIndex(index: number) {
  const msg = messages.value[index]
  if (!msg?.id) {
    ElMessage.warning('请等待回复完成后再操作')
    return
  }
  messagesBeforeFork.value = [...messages.value]
  forkFromMessageId.value = msg.id

  messages.value = messages.value.slice(0, index + 1)

  nextTick(() => {
    scrollToBottom(true)
    const textarea = document.querySelector('.input-box textarea') as HTMLTextAreaElement
    textarea?.focus()
  })
}

function cancelFork() {
  if (messagesBeforeFork.value) {
    messages.value = messagesBeforeFork.value
  }
  forkFromMessageId.value = null
  messagesBeforeFork.value = null
  inputText.value = ''
}

// 分支切换（同级分支：编辑/重新生成产生的）
async function handleSwitchBranch(messageId: number, branchIndex: number) {
  const convId = currentConvId.value
  if (!convId) return
  try {
    await switchBranch(convId, messageId, branchIndex)
    await loadConversation(convId)
  } catch {
    ElMessage.error('切换分支失败')
  }
}

// 子分支切换（从这里继续产生的）— parentMessageId 是分叉点，branchIndex 是目标子分支
async function handleSwitchChildBranch(parentMessageId: number, branchIndex: number) {
  const convId = currentConvId.value
  if (!convId) return
  try {
    await switchBranch(convId, parentMessageId, branchIndex, parentMessageId)
    await loadConversation(convId)
  } catch {
    ElMessage.error('切换分支失败')
  }
}

async function reloadAfterModelChange() {
  if (!currentConvId.value) return
  await loadConversation(currentConvId.value)
  await loadConversationList()
}

function handleModelSelected(providerId: number, modelName: string) {
  selectedProviderId.value = providerId
  selectedModelName.value = modelName
}

// 持久化上次使用的模型
watch([selectedProviderId, selectedModelName], ([pid, name]) => {
  if (pid && name) localStorage.setItem('last_model', JSON.stringify({ pid, name }))
})

async function handleAutoRouteToggle(val: boolean) {
  await setAutoRouteEnabled(val)
}

async function ensureConversation(): Promise<number | null> {
  if (currentConvId.value) return currentConvId.value
  try {
    const res: any = await createConversation(skillIdFromQuery.value)
    const convId = res.data.conversation_id
    currentConvId.value = convId
    currentTitle.value = '新对话'
    applyCurrentActiveSkills(Array.isArray(res.data?.active_skills) ? res.data.active_skills : [])
    isChatMode.value = true
    router.replace(buildChatRoute(convId, { skill_id: undefined, panel: undefined }))
    loadConversationList()
    return convId
  } catch {
    ElMessage.error('创建对话失败')
    return null
  }
}

const isChatMode = ref(false)

async function startFreeChat() {
  currentConvId.value = null
  currentTitle.value = '新对话'
  applyCurrentActiveSkills([])
  messages.value = []
  currentTemplateId.value = null
  isChatMode.value = true
  router.push(buildChatRoute(null, { skill_id: undefined, panel: undefined }))
  // 清空模板列表并重新加载，以设置全局默认提示词
  templateList.value = []
  await loadTemplateList()
  nextTick(() => {
    const textarea = document.querySelector('.input-box textarea') as HTMLTextAreaElement
    textarea?.focus()
  })
}

function switchConversation(conv: ConvItem) {
  if (conv.id === currentConvId.value) return
  chatStore.markConversationSeen(conv.id)
  router.push(buildChatRoute(conv.id, { skill_id: undefined, panel: sandboxPanelVisible.value ? 'sandbox' : undefined }))
}

function handleSidebarConversationClick(conv: ConvItem) {
  if (isSelectMode.value) {
    toggleSelect(conv.id)
    return
  }
  switchConversation(conv)
}

function handleSidebarConversationsUpdate(items: ConvItem[]) {
  conversations.value = items
}

async function handleDeleteConv(conv: ConvItem) {
  await showDangerConfirm({
    title: '删除对话',
    subject: conv.title,
    detail: '删除后该对话将无法恢复。',
    confirmText: '删除对话',
  })
  await deleteConversation(conv.id)
  ElMessage.success('对话已删除')
  if (conv.id === currentConvId.value) {
    currentConvId.value = null
    messages.value = []
    currentTitle.value = ''
    currentTemplateId.value = null
    // 清空模板列表并重新加载，以设置全局默认提示词
    templateList.value = []
    await loadTemplateList()
    router.replace(buildChatRoute(null, { skill_id: undefined, panel: undefined }))
  }
  await loadConversationList()
}

function handleComposerDrop(e: DragEvent) {
  void handleDrop(e)
}

function handleComposerAddAttachment() {
  ensureConversation().then((id) => {
    if (id) fileUploaderRef.value?.triggerUpload()
  })
}

async function selectModel(model: any) {
  showModelList.value = false
  inputText.value = ''

  await disableAutoRoute()

  if (currentConvId.value) {
    // 已有对话，切换模型
    try {
      await switchConversationModel(currentConvId.value, model.provider_id, model.model_name)
      currentProviderId.value = model.provider_id
      currentModelName.value = model.model_name
      ElMessage.success(`已切换到 ${model.display_name}`)
    } catch (error: any) {
      console.error('switch error:', error)
      ElMessage.error(error.response?.data?.message || '切换模型失败')
    }
  } else {
    // 新建对话，选择模型
    selectedProviderId.value = model.provider_id
    selectedModelName.value = model.model_name
    currentProviderId.value = model.provider_id
    currentModelName.value = model.model_name
    ElMessage.success(`已选择 ${model.display_name}`)
  }
}

async function selectSkill(skill: any) {
  showSkillList.value = false
  inputText.value = ''

  if (currentConvId.value) {
    try {
      const res: any = await activateConversationSkill(currentConvId.value, skill.id)
      if (res?.data?.success === false) {
        throw new Error(res?.data?.message || '加载技能失败')
      }
      await refreshCurrentConversationActiveSkills()
      await loadConversationList()
      skillManagerRef.value?.loadActiveSkills?.()
    } catch (error: any) {
      ElMessage.error(error?.message || '加载技能失败')
      return
    }
  } else {
    applyCurrentActiveSkills([{ id: skill.id, name: skill.name }])
    // 更新 URL query 参数（新对话场景）
    router.replace({ query: { skill_id: skill.id } })
  }

  // 自动切换到技能绑定的模型
  if (skill.model_provider_id && skill.model_name) {
    selectedProviderId.value = skill.model_provider_id
    selectedModelName.value = skill.model_name
    if (currentConvId.value) {
      try {
        await switchConversationModel(currentConvId.value, skill.model_provider_id, skill.model_name)
        currentProviderId.value = skill.model_provider_id
        currentModelName.value = skill.model_name
      } catch (e) {
        console.error('切换模型失败:', e)
      }
    } else {
      currentProviderId.value = skill.model_provider_id
      currentModelName.value = skill.model_name
    }
  }

  ElMessage.success(`已加载技能：${skill.name}`)
}

function resolveTemplateId(templateOrId: any): number | null {
  if (templateOrId == null) return null
  if (typeof templateOrId === 'number') return templateOrId
  if (typeof templateOrId === 'object' && 'id' in templateOrId) {
    return templateOrId.id ?? null
  }
  return null
}

async function selectTemplate(templateOrId: any) {
  showTemplateList.value = false
  await handleTemplateSelect(resolveTemplateId(templateOrId))
}

function handlePaletteCommandSelect(command: any) {
  void executeCommand(command)
  inputText.value = ''
  showCommandSuggestions.value = false
}

const { executeCommand } = useCommandDispatcher({
  openModelList,
  openSkillList,
  openMcpList,
  openTemplateList,
  toggleTheme: () => {
    const themeToggle = document.querySelector('.theme-toggle') as HTMLElement
    themeToggle?.click()
  },
  onNewChat: () => {
    router.push(buildChatRoute(null, { skill_id: undefined, panel: undefined }))
  },
  onExport: () => {
    if (currentConvId.value) {
      return handleExport()
    }
    ElMessage.warning('请先选择一个对话')
  },
  onCompact: async () => {
    if (currentConvId.value) {
      await handleCompressConversation()
      return
    }
    ElMessage.warning('请先选择一个对话')
  },
  onSandbox: () => {
    openSandboxPanel()
  },
  onSkillCommand: (skillData: any) => {
    if (!skillData?.id) return
    router.push(buildChatRoute(null, { skill_id: String(skillData.id), panel: undefined }))
  },
})

const { handleKeyDown } = useConversationKeydown({
  showMcpList,
  selectedMcpIndex,
  filteredMcpList,
  showSkillList,
  selectedSkillIndex,
  filteredSkillList,
  selectSkill,
  showModelList,
  selectedModelIndex,
  filteredModelList,
  selectModel,
  showTemplateList,
  selectedTemplateIndex,
  filteredTemplateList,
  selectTemplate,
  showCommandSuggestions,
  selectedCommandIndex,
  commandSuggestions,
  executeCommand,
  inputText,
  isForkMode,
  cancelFork,
  isMessageEditMode: computed(() => editingMessageId.value !== null),
  cancelMessageEdit,
  isComposing,
  isGenerating,
  handleSend,
})

function isNearBottom(): boolean {
  const el = messagesRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 150
}

function scrollToBottom(force = false) {
  nextTick(() => {
    if (messagesRef.value && (force || isNearBottom())) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

function formatTime(val: string) {
  if (!val) return ''
  const d = new Date(val)
  const now = new Date()

  const toDateStr = (dt: Date) => `${dt.getFullYear()}-${dt.getMonth()}-${dt.getDate()}`
  const todayStr = toDateStr(now)
  const targetStr = toDateStr(d)

  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  const yesterdayStr = toDateStr(yesterday)

  const dayBefore = new Date(now)
  dayBefore.setDate(dayBefore.getDate() - 2)
  const dayBeforeStr = toDateStr(dayBefore)

  const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })

  if (targetStr === todayStr) return time
  if (targetStr === yesterdayStr) return `昨天 ${time}`
  if (targetStr === dayBeforeStr) return `前天 ${time}`

  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function handleGlobalKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isGenerating.value) {
    e.preventDefault()
    handleStop()
  }
}

// ────── 标签筛选 ──────
const tagManagerRef = ref<InstanceType<typeof TagManager>>()
const {
  allTags,
  loadTags,
  handleTagFilter,
  convHasTag,
  handleTagCommand,
} = useConversationTagging<ConvItem>({
  conversations,
  activeTagFilter,
  fetchTagList: async () => {
    return await getTagList() as any
  },
  addConversationTag,
  removeConversationTag,
  resetPagination,
  reloadConversationList: async (append?: boolean) => {
    await loadConversationList(append)
  },
  showError: (message) => ElMessage.error(message),
})

// ────── 批量操作 ──────
const {
  isSelectMode,
  selectedConvIds,
  batchTagVisible,
  batchTagFloatingStyle,
  toggleSelectMode,
  toggleSelect,
  selectAll,
  handleBatchDelete,
  handleBatchExport,
  handleBatchTag,
  confirmBatchTag,
  handleBatchTagOutsideClick,
  handleBatchTagWindowResize,
  handleBatchTagWindowScroll,
} = useConversationBatchActions({
  getConversations: () => conversations.value,
  getAllTags: () => allTags.value,
  showDangerConfirm,
  showSuccess: (message) => ElMessage.success(message),
  showError: (message) => ElMessage.error(message),
  showInfo: (message) => ElMessage.info(message),
  reloadConversationList: async () => {
    await loadConversationList()
  },
  onDeletedConversations: (ids) => {
    if (currentConvId.value && ids.includes(currentConvId.value)) {
      currentConvId.value = null
      messages.value = []
      void router.replace(buildChatRoute(null, { skill_id: undefined, panel: undefined }))
    }
  },
  batchDeleteConversations,
  batchExportConversations,
  batchTagConversations,
})

function handleCommandSuggestionsOutsideClick(e: MouseEvent) {
  if (!showCommandSuggestions.value && !showTemplateList.value && !showSkillList.value && !showMcpList.value && !showModelList.value) return
  const target = e.target as Node | null
  if (!target) return
  if (chatInputAreaRef.value?.contains(target)) return
  closeCommandPanels()
}

function finalizeVisibleConversationStream(convId: number, messageId?: number) {
  chatStore.setConversationExecutionState(convId, {
    state: 'completed',
    streamSessionId: null,
    lastTerminalReason: 'done',
    lastErrorMessage: null,
  })
  const cached = msgCache.value.get(convId)
  if (cached) {
    let targetMessageId: number | null = null
    let targetMessageContent = ''
    if (messageId) {
      const last = cached[cached.length - 1]
      if (last && last.role === 'assistant') {
        last.id = messageId
        targetMessageId = messageId
        targetMessageContent = last.content || ''
      }
    }
    if (currentConvId.value === convId) {
      messages.value = [...cached]
      chatStore.markConversationSeen(convId)
      if (targetMessageId) {
        maybeActivateExportHintForMessage(targetMessageId, targetMessageContent)
      }
    }
  }
  chatStore.clearCachedConversationMessages(convId)
}

onMounted(async () => {
  document.addEventListener('keydown', handleGlobalKeyDown, true)
  document.addEventListener('mousedown', handleBatchTagOutsideClick)
  document.addEventListener('mousedown', handleCommandSuggestionsOutsideClick)
  document.addEventListener('visibilitychange', handlePageResume)
  window.addEventListener('focus', handlePageResume)
  window.addEventListener('pageshow', handlePageResume)
  window.addEventListener('resize', handleBatchTagWindowResize)
  window.addEventListener('resize', handleSandboxLauncherResize)
  window.addEventListener('scroll', handleBatchTagWindowScroll, true)
  syncSandboxLauncherTop(sandboxLauncherTop.value)
  // 立即设置模式，避免闪烁空状态
  isChatMode.value = true
  if (convIdFromRoute.value) {
    loadingConv.value = true
  }
  await loadTags()
  await loadConversationList()
  conversationEvents.start()
  await loadAllCommands()
  await loadTemplateList()
  await initAutoRoutePreference()
  if (convIdFromRoute.value) {
    await loadConversation(convIdFromRoute.value)
    // 从首页跳转过来，恢复待发送文本/附件
    const pendingMsgRaw = route.query.msg
    const pendingMsg = typeof pendingMsgRaw === 'string' ? pendingMsgRaw : ''
    const pendingFileIds = route.query.file_ids
      ? String(route.query.file_ids).split(',').map(Number).filter((id) => Number.isFinite(id) && id > 0)
      : []
    const pendingFilesMeta = JSON.parse(sessionStorage.getItem('pending_files') || '[]')
    const normalizedPendingFilesMeta = Array.isArray(pendingFilesMeta)
      ? pendingFilesMeta.filter(
        (item: any) => item && Number.isFinite(item.file_id) && typeof item.original_name === 'string',
      )
      : []
    const hasPendingPayload = route.query.msg != null || pendingFileIds.length > 0 || normalizedPendingFilesMeta.length > 0
    const hasPendingMsg = pendingMsg.trim().length > 0
    if (hasPendingPayload) {
      sessionStorage.removeItem('pending_files')
      router.replace({ path: route.path, query: {} })
    }
    isChatMode.value = true

    if (!hasPendingMsg && (pendingFileIds.length > 0 || normalizedPendingFilesMeta.length > 0)) {
      const fallbackMeta = pendingFileIds.map((id) => ({
        file_id: id,
        original_name: `附件 #${id}`,
        file_type: 'file',
        file_size: 0,
      }))
      const filesToRestore = normalizedPendingFilesMeta.length > 0 ? normalizedPendingFilesMeta : fallbackMeta
      fileIds.value = pendingFileIds.length > 0 ? pendingFileIds : filesToRestore.map((item: any) => item.file_id)
      await nextTick()
      fileUploaderRef.value?.setFiles(filesToRestore)
    }

    // 首页已输入文本时自动发送
    if (hasPendingMsg) {
      const convId = currentConvId.value!
      messages.value.push(createLocalMessage({ role: 'user', content: pendingMsg, files: normalizedPendingFilesMeta }))
      messages.value.push(createLocalMessage({ role: 'assistant', content: '', timeline: [] }))
      chatStore.cacheConversationMessages(convId, [...messages.value])
      scrollToBottom(true)
      const abortCtrl = new AbortController()
      const streamSessionId = bindConversationStream(convId, abortCtrl, 'landing_send')

      conversationExecution.sendMessage({
        conversationId: convId,
        content: pendingMsg,
        fileIds: pendingFileIds,
        callbacks: {
        onChunk: (content) => {
          const cached = msgCache.value.get(convId)
          if (!cached) return
          const last = cached[cached.length - 1]
          if (last?.role === 'assistant') last.content += content
          if (currentConvId.value === convId) { messages.value = [...cached]; scrollToBottom() }
        },
        onThinkingDelta: (content) => {
          const cached = msgCache.value.get(convId)
          if (!cached) return
          const last = cached[cached.length - 1]
          if (last?.role === 'assistant') {
            if (!last.timeline) last.timeline = []
            const cur = last.timeline[last.timeline.length - 1]
            if (cur && cur.type === 'thinking' && cur.isThinking) { cur.content += content } else { last.timeline.push({ type: 'thinking', content, isThinking: true }) }
            last.timeline = [...last.timeline]
          }
          if (currentConvId.value === convId) { messages.value = [...cached]; scrollToBottom() }
        },
        onThinkingDone: () => {
          const cached = msgCache.value.get(convId)
          if (!cached) return
          const last = cached[cached.length - 1]
          if (last?.role === 'assistant' && last.timeline?.length) { const cur = last.timeline[last.timeline.length - 1]; if (cur?.type === 'thinking') cur.isThinking = false; last.timeline = [...last.timeline] }
          if (currentConvId.value === convId) messages.value = [...cached]
        },
        onToolCallStart: (data) => {
          const cached = msgCache.value.get(convId)
          if (!cached) return
          let last = cached[cached.length - 1]
          if (!last || last.role !== 'assistant') {
            cached.push(createLocalMessage({ role: 'assistant', content: '', timeline: [] }))
            last = cached[cached.length - 1]
          }
          if (!last) return
          if (!last.timeline) last.timeline = []
          last.timeline = [...last.timeline, { type: 'tool_call', toolCallId: data.toolCallId, toolName: data.toolName, arguments: data.arguments, status: 'calling' as const }]
          if (currentConvId.value === convId) { messages.value = [...cached]; scrollToBottom() }
        },
        onToolCallProgress: (data) => {
          const cached = msgCache.value.get(convId)
          if (!cached) return
          for (const m of cached) {
            const tc = m.timeline?.find((t: any) => t.type === 'tool_call' && t.toolCallId === data.toolCallId)
            if (tc) {
              tc.status = 'calling'
              tc.progressTick = data.progressTick
              tc.elapsedMs = data.elapsedMs
              tc.elapsedSeconds = data.elapsedSeconds
              m.timeline = [...m.timeline!]
              break
            }
          }
          if (currentConvId.value === convId) messages.value = [...cached]
        },
        onToolCallResult: (data) => {
          const cached = msgCache.value.get(convId)
          if (!cached) return
          for (const m of cached) { const tc = m.timeline?.find((t: any) => t.type === 'tool_call' && t.toolCallId === data.toolCallId); if (tc) { tc.status = 'success'; tc.progressTick = undefined; tc.elapsedMs = undefined; tc.elapsedSeconds = undefined; tc.resultPreview = data.resultPreview; m.timeline = [...m.timeline!]; break } }
          if (currentConvId.value === convId) messages.value = [...cached]
        },
        onToolCallError: (data) => {
          const cached = msgCache.value.get(convId)
          if (!cached) return
          for (const m of cached) { const tc = m.timeline?.find((t: any) => t.type === 'tool_call' && t.toolCallId === data.toolCallId); if (tc) { tc.status = 'error'; tc.progressTick = undefined; tc.elapsedMs = undefined; tc.elapsedSeconds = undefined; tc.errorMessage = data.errorMessage; m.timeline = [...m.timeline!]; break } }
          if (currentConvId.value === convId) messages.value = [...cached]
        },
        onToolCallFiles: (data) => {
          const cached = msgCache.value.get(convId)
          if (!cached) return
          for (const m of cached) { const tc = m.timeline?.find((t: any) => t.type === 'tool_call' && t.toolCallId === data.toolCallId); if (tc) { tc.files = data.files.map(f => ({ fileId: f.file_id, filename: f.filename, fileSize: f.file_size })); m.timeline = [...m.timeline!]; break } }
          if (currentConvId.value === convId) messages.value = [...cached]
        },
        onDone: (doneData) => {
          if (!chatStore.isStreamOwnedBy(convId, streamSessionId)) return
          releaseConversationStream(convId, streamSessionId, { terminalReason: 'done' })
          if (currentConvId.value === convId) {
            finalizeVisibleConversationStream(convId, doneData.message_id)
          } else {
            chatStore.clearCachedConversationMessages(convId)
          }
          loadConversationList()
        },
        onCancelled: () => {
          if (!chatStore.isStreamOwnedBy(convId, streamSessionId)) return
          releaseConversationStream(convId, streamSessionId, { terminalReason: 'cancelled' })
          chatStore.clearCachedConversationMessages(convId)
          void loadConversation(convId, { skipCache: true })
          loadConversationList()
        },
        onTitleUpdated: (title) => { syncConversationTitleLocally(convId, title) },
        onContextWarning: (msg) => { if (!chatStore.isStreamOwnedBy(convId, streamSessionId)) return; if (currentConvId.value === convId) ElMessage.warning(msg) },
        onSkillMatched: (data) => { if (!chatStore.isStreamOwnedBy(convId, streamSessionId)) return; if (currentConvId.value === convId) { currentTitle.value = data.skill_name; if (data.model_provider_id && data.model_name) { selectedProviderId.value = data.model_provider_id; selectedModelName.value = data.model_name; currentProviderId.value = data.model_provider_id; currentModelName.value = data.model_name }; ElMessage.success({ message: `已自动加载技能「${data.skill_name}」`, duration: 3000 }); refreshCurrentConversationActiveSkills(); loadConversationList() } },
        onSkillActivationRequest: async (data) => {
          if (!chatStore.isStreamOwnedBy(convId, streamSessionId)) return
          conversationExecution.releaseConversationStream(convId, streamSessionId, {
            clearGenerating: true,
          })
          conversationExecution.markWaitingSkillConfirmation(convId)
          await handleSkillActivationRequest(data)
        },
        onRouteSelected: () => {},
        onStreamDisconnected: () => {
          markStreamDisconnected(convId, streamSessionId)
        },
        onError: (msg) => {
          if (!chatStore.isStreamOwnedBy(convId, streamSessionId)) return
          conversationExecution.handleActionErrorTerminal(convId, streamSessionId, msg)
          const cached = msgCache.value.get(convId)
          if (cached) {
            removeTrailingEmptyAssistantPlaceholder(cached)
            if (currentConvId.value === convId) {
              messages.value = [...cached]
            }
          }
          chatStore.clearCachedConversationMessages(convId)
          ElMessage.error(msg)
        },
        },
        abortSignal: abortCtrl.signal,
        referencedMessageIds: undefined,
        providerId: selectedProviderId.value,
        modelName: selectedModelName.value,
      }).catch(() => { if (!chatStore.isStreamOwnedBy(convId, streamSessionId)) return; releaseConversationStream(convId, streamSessionId, { terminalReason: 'cancelled' }); chatStore.clearCachedConversationMessages(convId) })
    }
  } else if (skillIdFromQuery.value) {
    await startNewConversation(skillIdFromQuery.value)
  } else if (route.path === '/chat') {
    // 直接访问 /chat 路由，启用聊天模式
    isChatMode.value = true
  }
})

onUnmounted(() => {
  conversationEvents.stop()
  stopConversationListAutoRefresh()
  stopConversationPolling()
  clearPendingSkillResumeRecoveryTimer()
  resetExportHints()
  void conversationExecution.cancelAllOwnedActions('unmount')
  document.removeEventListener('keydown', handleGlobalKeyDown, true)
  document.removeEventListener('mousedown', handleBatchTagOutsideClick)
  document.removeEventListener('mousedown', handleCommandSuggestionsOutsideClick)
  document.removeEventListener('visibilitychange', handlePageResume)
  window.removeEventListener('focus', handlePageResume)
  window.removeEventListener('pageshow', handlePageResume)
  window.removeEventListener('resize', handleBatchTagWindowResize)
  window.removeEventListener('resize', handleSandboxLauncherResize)
  window.removeEventListener('scroll', handleBatchTagWindowScroll, true)
})

// 监听输入变化，显示指令建议
watch(listSearchQuery, () => {
  resetListSelectionIndices()
})

watch(inputText, (newVal) => {
  // 监听 @ 字符触发文件上传
  if (newVal === '@') {
    inputText.value = ''
    ensureConversation().then((id) => { if (id) fileUploaderRef.value?.triggerUpload() })
    return
  }

  updateCommandSuggestionsByInput(newVal)
})

watch(convIdFromRoute, async (newId) => {
  const oldId = currentConvId.value
  if (newId !== oldId) {
    resetExportHints()
  }
  // 离开正在生成的对话时，保存当前消息到缓存
  if (oldId && chatStore.isConversationGenerating(oldId)) {
    chatStore.cacheConversationMessages(oldId, [...messages.value])
    const shouldRequestRemoteCancel = shouldRequestRemoteCancelOnRouteSwitch(
      isConversationStreamOwnedByView(oldId),
    )
    await conversationExecution.cancelConversationAction(oldId, {
      reason: 'route_switch',
      requestRemoteCancel: shouldRequestRemoteCancel
        ? (conversationId) =>
            cancelConversationGenerationWithMeta(conversationId, {
              reason: 'route_switch',
              source: 'chat_route_switch',
            })
        : undefined,
      suppressRemoteError: true,
    })
  }

  if (newId && newId !== oldId) {
    await loadConversation(newId)
  } else if (!newId) {
    currentConvId.value = null
    currentConversationFingerprint.value = ''
    currentConversationLiveStateVersion.value = ''
    sandboxUnreadChangeCount.value = 0
    currentTitle.value = isChatMode.value ? '新对话' : ''
    applyCurrentActiveSkills([])
    messages.value = []
  }
})

watch(
  [() => route.query.panel, currentConvId],
  ([panel, convId]) => {
    if (panel === 'sandbox' && !convId && !convIdFromRoute.value) {
      void router.replace(buildChatRoute(null, { panel: undefined }))
      return
    }

    const shouldOpen = panel === 'sandbox' && !!convId
    syncSandboxPanelFromRoute(shouldOpen)
  },
  { immediate: true },
)

watch(
  [sandboxPanelVisible, currentConvId],
  ([panelVisible, convId]) => {
    if (!panelVisible || !convId) return
    void markSandboxChangesReadForCurrentConversation(convId)
  },
  { immediate: true },
)

onBeforeRouteLeave(async (_, __, next) => {
  try {
    await conversationExecution.cancelAllOwnedActions('route_switch')
    if (skillManagerRef.value?.hasPendingSkillActivation?.()) {
      await skillManagerRef.value.rejectPendingSkillActivation?.()
    }
  } finally {
    next()
  }
})

async function focusConversationInSidebar(convId: number) {
  const convExists = conversations.value.some(c => c.id === convId)

  if (!convExists) {
    let attempts = 0
    const maxAttempts = 5

    while (!conversations.value.some(c => c.id === convId) && attempts < maxAttempts && hasMoreConversations.value) {
      await loadMoreConversations()
      attempts++
    }
  }

  await nextTick()
  setTimeout(() => {
    const wrapper = document.querySelector('.conv-list-wrapper') as HTMLElement | null
    const convItem = document.querySelector(`.conv-item[data-conv-id="${convId}"]`)
    if (!(convItem instanceof HTMLElement) || !wrapper) return
    const targetTop = Math.max(0, convItem.offsetTop - (wrapper.clientHeight - convItem.offsetHeight) / 2)
    wrapper.scrollTo({ top: targetTop, behavior: 'smooth' })
    convItem.classList.add('highlight-flash')
    setTimeout(() => convItem.classList.remove('highlight-flash'), 2000)
  }, 100)
}

watch([() => chatStore.pendingFocusConversationId, currentConvId], async ([pendingConvId, activeConvId]) => {
  if (!pendingConvId || activeConvId !== pendingConvId) return
  try {
    await focusConversationInSidebar(pendingConvId)
  } finally {
    chatStore.clearPendingFocusConversation(pendingConvId)
  }
}, { immediate: true })
</script>

<template>
  <div class="chat-page">
    <!-- 左侧对话列表 -->
    <ConversationSidebar
      :conversations="conversations"
      :all-tags="allTags"
      :active-tag-filter="activeTagFilter"
      :is-select-mode="isSelectMode"
      :selected-conv-ids="selectedConvIds"
      :current-conv-id="currentConvId"
      :editing-sidebar-title-conv-id="editingSidebarTitleConvId"
      :editing-sidebar-title-text="editingSidebarTitleText"
      :generating-conv-ids="generatingConvIds"
      :conversation-execution-states="conversationExecutionStates"
      :polling-health="pollingHealth"
      :loading-more-conversations="loadingMoreConversations"
      :has-more-conversations="hasMoreConversations"
      :get-tag-filter-item-style="getTagFilterItemStyle"
      :format-time="formatTime"
      :conv-has-tag="convHasTag"
      :set-sidebar-title-input-ref="setSidebarTitleInputRef"
      @update:conversations="handleSidebarConversationsUpdate"
      @update:editing-sidebar-title-text="(value) => (editingSidebarTitleText = value)"
      @new-chat="startFreeChat"
      @toggle-select-mode="toggleSelectMode"
      @open-tag-manager="tagManagerRef?.open()"
      @tag-filter="handleTagFilter"
      @select-all="selectAll"
      @conv-list-scroll="handleConvListScroll"
      @conv-drag-end="handleConvDragEnd"
      @conv-click="handleSidebarConversationClick"
      @toggle-select="toggleSelect"
      @start-edit-sidebar-title="startEditSidebarTitle"
      @save-sidebar-edit-title="saveSidebarEditTitle"
      @cancel-sidebar-edit-title="cancelSidebarEditTitle"
      @tag-command="handleTagCommand"
      @delete-conv="handleDeleteConv"
      @batch-delete="handleBatchDelete"
      @batch-export="handleBatchExport"
      @batch-tag="handleBatchTag"
    />

    <!-- 标签管理抽屉 -->
    <TagManager ref="tagManagerRef" @updated="loadTags(); loadConversationList()" />

    <!-- 批量打标签浮层（左下角，无全屏遮罩） -->
    <Transition name="batch-tag-float">
      <div v-if="batchTagVisible" class="batch-tag-floating" :style="batchTagFloatingStyle">
        <div class="batch-tag-list">
          <div
            v-for="tag in allTags"
            :key="tag.id"
            class="tag-picker-item"
            @click="confirmBatchTag(tag.id)"
          >
            <span class="tag-picker-dot" :style="{ background: tag.color }" />
            <span class="tag-picker-name">{{ tag.name }}</span>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 右侧对话区域 -->
    <ChatWorkspace :loading="loadingConv" :show-workspace="Boolean(currentConvId || isChatMode)">
      <template #header>
        <ChatHeader
          :loading="loadingConv"
          :editing-header-title="editingHeaderTitle"
          :editing-header-title-text="editingHeaderTitleText"
          :current-conv-id="currentConvId"
          :current-title="currentTitle"
          :current-skill-name="currentSkillName"
          :is-generating="isGenerating"
          :regenerating-title="regeneratingTitle"
          :admin-view="adminViewFromQuery"
          :message-count="messages.length"
          :current-feedback="currentFeedback"
          :set-header-title-input-ref="setHeaderTitleInputRef"
          @update:editing-header-title-text="(value) => (editingHeaderTitleText = value)"
          @start-edit-header-title="startEditHeaderTitle"
          @save-header-edit-title="saveHeaderEditTitle"
          @cancel-header-edit-title="cancelHeaderEditTitle"
          @regenerate-title="regenerateTitleWithLLM"
          @open-feedback="openFeedback"
          @open-export="exportVisible = true"
        />
      </template>
      <template #status>
        <ChatStatusBar
          :state="currentStatusState"
          :polling-health="pollingHealth"
          :last-terminal-reason="currentStatusReason"
          :last-error-message="currentStatusErrorMessage"
          :live-execution="currentLiveExecution"
          @retry="handleStatusRetry"
          @refresh="handleStatusRefresh"
          @details="handleStatusDetails"
        />
      </template>
      <template #messages>
        <ChatMessageList
          :messages="messages"
          :conversation-id="currentConvId"
          :set-messages-area-ref="setMessagesAreaRef"
          :is-generating="isGenerating"
          :compression-summary="compressionSummary"
          :compression-saved-tokens="compressionSavedTokens"
          :compression-split-message-id="compressionSplitMsgId"
          :comparison-results="comparisonResults"
          :selected-model-name="selectedModelName"
          :compare-model-b-name="compareModelBName"
          :comparison-done="comparisonDone"
          :comparison-id="comparisonId"
          :choosing-winner="choosingWinner"
          @edit="startMessageEdit"
          @regenerate="handleRegenerate"
          @fork="handleForkByIndex"
          @quote="handleQuote"
          @export-message="handleExportMessage"
          @export-hint-acknowledge="acknowledgeExportHint"
          @skill-decision="handleToolSkillDecision"
          @switch-branch="handleSwitchBranch"
          @switch-child-branch="handleSwitchChildBranch"
          @choose-winner="handleChooseWinner"
        />
      </template>
      <template #composer>
        <ChatComposer
          :set-chat-input-area-ref="setChatInputAreaRef"
          :set-file-uploader-ref="setFileUploaderComponentRef"
          :set-skill-manager-ref="setSkillManagerComponentRef"
          :current-conv-id="currentConvId"
          :quoted-messages="quotedMessages"
          :show-reference-composer-bar="showReferenceComposerBar"
          :reference-empty-mode="referenceState.empty_mode"
          :reference-selected-count="referenceSelectedCount"
          :clear-reference-disabled="isGenerating || (referenceSelectedCount === 0 && referenceState.empty_mode === 'none')"
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
          :is-fork-mode="isForkMode"
          :is-message-edit-mode="editingMessageId !== null"
          :is-dragging="isDragging"
          :is-generating="isGenerating"
          :optimizing="optimizing"
          :input-text="inputText"
          :input-key="inputKey"
          :input-expanded="inputExpanded"
          :is-composing="isComposing"
          :template-popover-visible="templatePopoverVisible"
          :current-template-label="currentTemplateLabel"
          :current-template-id="currentTemplateId"
          :visible-template-list="visibleTemplateList"
          :loading-template="loadingTemplate"
          :auto-route-enabled="autoRouteEnabled"
          :compare-mode="compareMode"
          :selected-provider-id="selectedProviderId"
          :selected-model-name="selectedModelName"
          :compare-model-b-provider-id="compareModelBProviderId"
          :compare-model-b-name="compareModelBName"
          :current-provider-id="currentProviderId"
          :current-model-name="currentModelName"
          @update:file-ids="(ids) => (fileIds = ids)"
          @remove-quote="handleRemoveQuote"
          @skill-activated="handleSkillActivated"
          @skill-rejected="handleSkillRejected"
          @skill-deactivated="handleSkillDeactivated"
          @update:list-search-query="(value) => (listSearchQuery = value)"
          @list-keydown="handleKeyDown"
          @command-select="handlePaletteCommandSelect"
          @template-select="selectTemplate"
          @skill-select="selectSkill"
          @model-select="selectModel"
          @open-reference-dialog="openReferenceDialog()"
          @clear-reference="handleClearReference"
          @dragenter="handleComposerDragEnter"
          @dragleave="handleComposerDragLeave"
          @drop="handleComposerDrop"
          @optimize-prompt="handleOptimizePrompt"
          @update:input-text="(value) => (inputText = value)"
          @keydown="handleKeyDown"
          @update:is-composing="(value) => (isComposing = value)"
          @paste="handlePaste"
          @update:template-popover-visible="(value) => (templatePopoverVisible = value)"
          @template-popover-visible="handleTemplatePopoverVisible"
          @add-attachment="handleComposerAddAttachment"
          @toggle-expand="toggleExpand"
          @update:auto-route-enabled="(value) => (autoRouteEnabled = value)"
          @auto-route-toggle="handleAutoRouteToggle"
          @update:compare-mode="(value) => (compareMode = value)"
          @reload-after-model-change="reloadAfterModelChange"
          @model-selected="handleModelSelected"
          @model-b-selected="handleModelBSelected"
          @stop="handleStop"
          @send="handleSend"
          @cancel-fork="cancelFork"
          @cancel-message-edit="cancelMessageEdit"
        />
      </template>
      <template #empty>
        <ChatEmptyState @browse="router.push('/skills')" />
      </template>
    </ChatWorkspace>

    <SandboxPanelLauncher
      :current-conv-id="currentConvId"
      :sandbox-launcher-visible="sandboxLauncherVisible"
      :sandbox-panel-visible="sandboxPanelVisible"
      :unread-change-count="sandboxUnreadChangeCount"
      :sandbox-launcher-dragging="sandboxLauncherDragging"
      :sandbox-launcher-style="sandboxLauncherStyle"
      @update:sandbox-panel-visible="(value) => (sandboxPanelVisible = value)"
      @launcher-pointerdown="handleSandboxLauncherPointerDown"
      @launcher-pointermove="handleSandboxLauncherPointerMove"
      @launcher-pointerup="handleSandboxLauncherPointerUp"
      @launcher-pointercancel="handleSandboxLauncherPointerCancel"
      @drawer-close="closeSandboxPanel"
      @drawer-closed="handleSandboxDrawerClosed"
    />

    <ConversationReferenceDialog
      :visible="referenceDialogVisible"
      :loading="referenceDialogLoading"
      :selected-ids="referenceSelectedIds"
      :all-files="referenceAllFiles"
      :tree-items="referenceTreeItems"
      :focused-file-id="referenceFocusedFileId"
      :focused-file="focusedReferenceFile"
      :inspector-tags="focusedReferenceInspectorTags"
      :inspector-fields="focusedReferenceInspectorFields"
      :inspector-summary="focusedReferenceInspectorSummary"
      :binding-summary="referenceBindingSummary"
      :format-reference-display-path="formatReferenceDisplayPath"
      :reference-file-preview="referenceFilePreview"
      @update:visible="(value) => (referenceDialogVisible = value)"
      @cancel="cancelReferenceDialog"
      @update:selected-ids="updateReferenceSelectedIds"
      @file-click="handleReferenceTreeItemClick"
      @file-dblclick="handleReferenceTreeItemDblClick"
      @inspector-action="handleReferenceInspectorAction"
      @apply-mode="applyReferenceMode"
    />

    <ConversationExportDialog
      :visible="exportVisible"
      :format="exportForm.format"
      :scope="exportForm.scope"
      :exporting="exporting"
      @update:visible="(value) => (exportVisible = value)"
      @update:format="(value) => (exportForm.format = value)"
      @update:scope="(value) => (exportForm.scope = value)"
      @submit="handleExport"
    />

    <ConversationFeedbackDialog
      :visible="feedbackVisible"
      :rating="feedbackForm.rating"
      :comment="feedbackForm.comment"
      :submitting="feedbackSubmitting"
      :star-hover="starHover"
      @update:visible="(value) => (feedbackVisible = value)"
      @update:rating="(value) => (feedbackForm.rating = value)"
      @update:comment="(value) => (feedbackForm.comment = value)"
      @update:star-hover="(value) => (starHover = value)"
      @submit="handleFeedback"
    />

    <OptimizedPromptDialog
      :visible="showOptimizedDialog"
      :optimizing="optimizing"
      :optimized-prompt="optimizedPrompt"
      :should-auto-scroll-optimized-prompt="shouldAutoScrollOptimizedPrompt"
      :set-optimized-prompt-container-ref="setOptimizedPromptContainerRef"
      @update:visible="(value) => (showOptimizedDialog = value)"
      @close="stopOptimizing"
      @stop="stopOptimizing"
      @apply="applyOptimizedPrompt"
      @scroll="updateOptimizedPromptAutoScroll"
      @scroll-bottom="scrollOptimizedPromptToBottom"
    />
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - 76px); /* 减小高度，留出上下对称的间距 */
  margin: -24px;
  margin-top: -76px; /* 精确抵消，只留 8px 间距 */
  margin-bottom: -16px; /* 减小底部间距，与顶部对称 */
  background: var(--bg-card, #fff);
}

/* ── Styled Dialog ── */
.tag-picker-title {
  font-size: 12px;
  color: var(--text-muted, #909399);
  margin-bottom: 6px;
  font-weight: 500;
}

.tag-picker-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: color 0.14s ease;
}

.tag-picker-item:hover {
  background: transparent;
}

.tag-picker-item.is-selected {
  background: rgba(64, 158, 255, 0.08);
}

.tag-picker-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
}

.tag-picker-name {
  font-size: 13px;
  color: var(--text-primary, #303133);
  max-width: 72px;
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

.tag-picker-empty {
  font-size: 12px;
  color: var(--text-muted, #909399);
  text-align: center;
  padding: 8px 0;
}

/* Tag dropdown popper skin */
:deep(.tag-picker-dropdown.el-popper) {
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 14px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.12);
  overflow: hidden;
  min-width: 0 !important;
  width: fit-content;
}

:deep(.tag-picker-dropdown .el-popper__arrow::before) {
  border-color: rgba(0, 0, 0, 0.08);
  background: var(--bg-card, #fff);
}

:deep(.tag-picker-dropdown .el-dropdown-menu) {
  min-width: 0;
  width: fit-content;
  padding: 3px 4px;
  border: none;
  background: var(--bg-card, #fff);
}

:deep(.tag-picker-dropdown .el-dropdown-menu__item) {
  padding: 0;
  margin: 0;
  line-height: normal;
  border-radius: 6px;
}

:deep(.tag-picker-dropdown .el-dropdown-menu__item:not(.is-disabled):hover),
:deep(.tag-picker-dropdown .el-dropdown-menu__item:not(.is-disabled):focus) {
  background: transparent;
}

html.dark :deep(.tag-picker-dropdown.el-popper) {
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.45);
}

html.dark :deep(.tag-picker-dropdown .el-popper__arrow::before) {
  border-color: rgba(255, 255, 255, 0.1);
  background: var(--bg-card, #1f2937);
}

html.dark :deep(.tag-picker-dropdown .el-dropdown-menu) {
  background: var(--bg-card, #1f2937);
}

.batch-tag-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.batch-tag-floating {
  position: fixed;
  transform: translate(-50%, -100%);
  z-index: 1800;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 14px;
  background: var(--bg-card, #fff);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.12);
  padding: 4px;
  min-width: 0;
  width: fit-content;
}

.batch-tag-float-enter-active,
.batch-tag-float-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease;
}

.batch-tag-float-enter-from,
.batch-tag-float-leave-to {
  opacity: 0;
  transform: translate(-50%, calc(-100% + 4px)) scale(0.98);
}

html.dark .batch-tag-floating {
  border-color: rgba(255, 255, 255, 0.1);
  background: var(--bg-card, #1f2937);
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.45);
}

</style>

<style scoped>
:global(.chat-confirm-dialog.el-message-box),
:global(.chat-confirm-dialog .el-message-box) {
  width: min(460px, calc(100vw - 32px));
  padding: 0;
  border: 1px solid #e5e7eb;
  border-radius: 24px;
  background: #ffffff;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

:global(.chat-confirm-dialog.el-message-box .el-message-box__header),
:global(.chat-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.chat-confirm-dialog.el-message-box .el-message-box__title),
:global(.chat-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.chat-confirm-dialog.el-message-box .el-message-box__headerbtn),
:global(.chat-confirm-dialog .el-message-box__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.chat-confirm-dialog.el-message-box .el-message-box__headerbtn .el-message-box__close),
:global(.chat-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.chat-confirm-dialog.el-message-box .el-message-box__content),
:global(.chat-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.chat-confirm-dialog.el-message-box .el-message-box__message),
:global(.chat-confirm-dialog .el-message-box__message) {
  margin: 0;
}

:global(.danger-confirm-content) {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

:global(.danger-confirm-badge) {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: #fef2f2;
  color: #dc2626;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

:global(.danger-confirm-subject) {
  font-size: 18px;
  line-height: 1.5;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
  word-break: break-word;
}

:global(.danger-confirm-detail) {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-secondary, #64748b);
}

:global(.chat-confirm-dialog.el-message-box .el-message-box__btns),
:global(.chat-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.chat-confirm-dialog.el-message-box .el-message-box__btns .el-button),
:global(.chat-confirm-dialog .el-message-box__btns .el-button) {
  min-width: 108px;
  height: 42px;
  border-radius: 14px;
  font-weight: 600;
}

:global(.chat-confirm-dialog .el-message-box__btns .chat-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.chat-confirm-dialog .el-message-box__btns .chat-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.chat-confirm-dialog .el-message-box__btns .chat-confirm-primary) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.chat-confirm-dialog .el-message-box__btns .chat-confirm-primary:hover) {
  border-color: #fca5a5;
  background: #fef2f2;
  color: #b91c1c;
}

:global(.chat-confirm-dialog .el-message-box__btns .chat-confirm-accent) {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  color: #2563eb;
  box-shadow: none;
}

:global(.chat-confirm-dialog .el-message-box__btns .chat-confirm-accent:hover) {
  border-color: #bfdbfe;
  background: #dbeafe;
  color: #1d4ed8;
}

:global(html.dark .chat-confirm-dialog.el-message-box),
:global(html.dark .chat-confirm-dialog .el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .chat-confirm-dialog.el-message-box .el-message-box__title),
:global(html.dark .chat-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}

:global(html.dark .chat-confirm-dialog.el-message-box .el-message-box__headerbtn .el-message-box__close),
:global(html.dark .chat-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: #94a3b8;
}

:global(html.dark .danger-confirm-badge) {
  background: rgba(248, 113, 113, 0.14);
  color: #fca5a5;
}

:global(html.dark .danger-confirm-subject) {
  color: #f8fafc;
}

:global(html.dark .danger-confirm-detail) {
  color: #94a3b8;
}

:global(html.dark .chat-confirm-dialog .el-message-box__btns .chat-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .chat-confirm-dialog .el-message-box__btns .chat-confirm-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}

/* SkillManage confirm styles: copied for exact visual parity */
:global(.skill-manage-confirm-dialog.el-message-box) {
  width: min(460px, calc(100vw - 32px));
  padding: 0;
  border: 1px solid #e5e7eb;
  border-radius: 24px;
  background: #ffffff;
  box-shadow:
    0 20px 48px rgba(15, 23, 42, 0.08),
    0 4px 14px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

:global(.skill-manage-confirm-dialog .el-message-box) {
  border-radius: 24px;
  overflow: hidden;
}

:global(.skill-manage-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.skill-manage-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.skill-manage-confirm-dialog .el-message-box__headerbtn) {
  top: 18px;
  right: 18px;
}

:global(.skill-manage-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: var(--text-secondary, #94a3b8);
}

:global(.skill-manage-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.skill-manage-confirm-dialog .el-message-box__message) {
  margin: 0;
}

:global(.skill-manage-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.skill-manage-confirm-dialog .el-message-box__btns .el-button) {
  min-width: 108px;
  height: 42px;
  border-radius: 14px;
  font-weight: 600;
}

:global(.skill-manage-confirm-dialog.el-message-box),
:global(.skill-manage-confirm-dialog .el-message-box) {
  border-radius: 24px !important;
}

:global(.skill-manage-confirm-dialog .skill-manage-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.skill-manage-confirm-dialog .skill-manage-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.skill-manage-confirm-dialog .skill-manage-confirm-primary) {
  border: 1px solid #fecaca;
  background: #fff5f5;
  color: #dc2626;
  box-shadow: none;
}

:global(.skill-manage-confirm-dialog .skill-manage-confirm-primary:hover) {
  border-color: #fca5a5;
  background: #fef2f2;
  color: #b91c1c;
}

/* Keep multimodal confirmation as blue accent */
:global(.chat-confirm-accent-mode .skill-manage-confirm-primary) {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  color: #2563eb;
}

:global(.chat-confirm-accent-mode .skill-manage-confirm-primary:hover) {
  border-color: #bfdbfe;
  background: #dbeafe;
  color: #1d4ed8;
}

:global(html.dark .skill-manage-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background:
    linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .skill-manage-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}

:global(html.dark .skill-manage-confirm-dialog .el-message-box__headerbtn .el-message-box__close) {
  color: #94a3b8;
}

:global(html.dark .skill-manage-confirm-dialog .skill-manage-confirm-secondary) {
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.06);
  color: #cbd5e1;
}

:global(html.dark .skill-manage-confirm-dialog .skill-manage-confirm-secondary:hover) {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.1);
  color: #f8fafc;
}
</style>
