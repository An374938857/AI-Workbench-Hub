<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { createConversation, switchConversationModel, switchPromptTemplate } from '@/api/conversations'
import { uploadFile as uploadFileApi } from '@/api/files'
import { useAuthStore } from '@/stores/auth'
import { showDangerConfirm } from '@/composables/useDangerConfirm'
import { useComposerCatalogs } from '@/composables/useComposerCatalogs'
import { usePromptOptimizer } from '@/composables/usePromptOptimizer'
import { useAutoRoutePreference } from '@/composables/useAutoRoutePreference'
import { useMultimodalGuard } from '@/composables/useMultimodalGuard'
import { useCommandDispatcher } from '@/composables/useCommandDispatcher'
import { useCommandPanelKeydown } from '@/composables/useCommandPanelKeydown'
import ModelSelector from '@/components/ModelSelector.vue'
import PromptTemplateSelector from '@/components/common/PromptTemplateSelector.vue'
import ConversationCommandPalette from '@/components/chat/ConversationCommandPalette.vue'
import OptimizedPromptDialog from '@/components/chat/OptimizedPromptDialog.vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()
const inputText = ref('')
const sending = ref(false)
const isComposing = ref(false)
const inputExpanded = ref(false)
const inputKey = ref(0)

// 模型选择
const selectedProviderId = ref<number | null>(null)
const selectedModelName = ref<string | null>(null)
const autoRouteEnabled = ref(false)

// 提示词模板
const templateList = ref<any[]>([])
const currentTemplateId = ref<number | null>(null)
const loadingTemplate = ref(false)
const templatePopoverVisible = ref(false)

// 技能选择
const selectedSkillId = ref<number | null>(null)
const selectedSkillName = ref<string | null>(null)

// 斜杠指令
const showCommandSuggestions = ref(false)
const commandSuggestions = ref<any[]>([])
const selectedCommandIndex = ref(0)
const allCommands = ref<any[]>([])

// /model 列表
const showModelList = ref(false)
const modelList = ref<any[]>([])
const selectedModelIndex = ref(0)

// /prompt 列表
const showTemplateList = ref(false)
const selectedTemplateIndex = ref(0)

// /skills 列表
const showSkillList = ref(false)
const skillList = ref<any[]>([])
const selectedSkillIndex = ref(0)

// /mcps 列表
const showMcpList = ref(false)
const mcpList = ref<any[]>([])
const selectedMcpIndex = ref(0)
const homeInputAreaRef = ref<HTMLElement | null>(null)

// 列表搜索
const listSearchQuery = ref('')
const filteredModelList = computed(() => {
  const q = listSearchQuery.value.toLowerCase()
  return q ? modelList.value.filter(m => (m.display_name || '').toLowerCase().includes(q) || (m.provider_name || '').toLowerCase().includes(q)) : modelList.value
})
const filteredSkillList = computed(() => {
  const q = listSearchQuery.value.toLowerCase()
  return q ? skillList.value.filter(s => (s.name || '').toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q)) : skillList.value
})
const filteredMcpList = computed(() => {
  const q = listSearchQuery.value.toLowerCase()
  return q ? mcpList.value.filter(m => (m.name || '').toLowerCase().includes(q) || (m.description || '').toLowerCase().includes(q)) : mcpList.value
})
const globalDefaultTemplateId = computed<number | null>(() => {
  const globalDefault = templateList.value.find((tpl: any) => tpl.is_global_default || tpl.is_default)
  return globalDefault?.id ?? null
})
const isFreeTemplateGlobalDefault = computed(() => {
  if (globalDefaultTemplateId.value == null) return true
  const globalDefault = templateList.value.find((tpl: any) => tpl.id === globalDefaultTemplateId.value)
  return (globalDefault?.name || '').trim() === '自由对话'
})
function buildTemplatePreview(content: string): string {
  const normalized = content.replace(/\s+/g, ' ').trim()
  const maxLen = 60
  return normalized.length > maxLen ? `${normalized.slice(0, maxLen)}...` : normalized
}
const templateCommandList = computed(() => visibleTemplateList.value)
function getTemplatePreview(template: any): string {
  const raw = typeof template?.content === 'string' ? template.content : ''
  const preview = buildTemplatePreview(raw)
  if (!preview) return template?.is_favorited ? '收藏模板' : template?.id === globalDefaultTemplateId.value ? '默认模板' : '提示词模板'
  return preview
}
const filteredTemplateList = computed(() => {
  const q = listSearchQuery.value.toLowerCase()
  return q ? templateCommandList.value.filter(t =>
    (t.name || '').toLowerCase().includes(q) ||
    (t.description || '').toLowerCase().includes(q) ||
    getTemplatePreview(t).toLowerCase().includes(q)
  ) : templateCommandList.value
})
const currentTemplateLabel = computed(() => {
  if (!currentTemplateId.value) {
    const globalDefault = templateList.value.find((tpl: any) => tpl.is_global_default || tpl.is_default)
    return globalDefault?.name || '选择模板'
  }
  const current = templateList.value.find((tpl: any) => tpl.id === currentTemplateId.value)
  return current?.name || '选择模板'
})

const {
  loadModelList,
  loadSkillList,
  loadMcpList,
  loadTemplateList,
  visibleTemplateList,
} = useComposerCatalogs({
  modelList,
  skillList,
  mcpList,
  templateList,
  currentTemplateId,
  loadingTemplate,
  shouldApplyTemplateDefault: () => true,
})

// 附件（暂存 File 对象，创建对话后再上传）
interface PendingFile {
  file: File
  isImage: boolean
  previewUrl?: string
}
const pendingFiles = ref<PendingFile[]>([])
const fileInputRef = ref<HTMLInputElement>()

// 拖拽上传
const isDragging = ref(false)
const dragCounter = ref(0)
const ALLOWED_EXTENSIONS = new Set(['txt', 'md', 'docx', 'xlsx', 'csv', 'pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'])

// 图片预览
const showPreview = ref(false)
const previewIndex = ref(0)
const previewScale = ref(1)
const imageFiles = computed(() => pendingFiles.value.filter(pf => pf.isImage))

function openPreview(index: number) {
  // index 是在 imageFiles 中的索引
  previewIndex.value = index
  previewScale.value = 1
  showPreview.value = true
}
function handlePreviewKeydown(e: KeyboardEvent) {
  if (!showPreview.value) return
  if (e.key === 'Escape') showPreview.value = false
  else if (e.key === 'ArrowLeft' && previewIndex.value > 0) { previewIndex.value--; previewScale.value = 1 }
  else if (e.key === 'ArrowRight' && previewIndex.value < imageFiles.value.length - 1) { previewIndex.value++; previewScale.value = 1 }
}
function handlePreviewWheel(e: WheelEvent) {
  e.preventDefault()
  previewScale.value = Math.min(5, Math.max(0.2, previewScale.value * (e.deltaY < 0 ? 1.1 : 0.9)))
}
watch(showPreview, (v) => {
  if (v) document.addEventListener('keydown', handlePreviewKeydown)
  else document.removeEventListener('keydown', handlePreviewKeydown)
})
onUnmounted(() => document.removeEventListener('keydown', handlePreviewKeydown))

// 提示词优化
const optimizing = ref(false)
const showOptimizedDialog = ref(false)

const optimizedPrompt = ref('')
const optimizeAbortController = ref<AbortController | null>(null)
const optimizedPromptContainerRef = ref<HTMLElement | null>(null)
const shouldAutoScrollOptimizedPrompt = ref(true)

function toggleExpand() {
  inputExpanded.value = !inputExpanded.value
  inputKey.value++
}

// ── 附件 ──
function triggerFileUpload() {
  fileInputRef.value?.click()
}

function addPendingFile(file: File) {
  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'].includes(ext) || file.type.startsWith('image/')
  const item: PendingFile = { file, isImage }
  if (isImage) item.previewUrl = URL.createObjectURL(file)
  pendingFiles.value.push(item)
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files) return
  for (const f of Array.from(input.files)) addPendingFile(f)
  input.value = ''
}

function removePendingFile(index: number) {
  const item = pendingFiles.value[index]
  if (!item) return
  if (item.previewUrl) URL.revokeObjectURL(item.previewUrl)
  pendingFiles.value.splice(index, 1)
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  dragCounter.value = 0
  const files = e.dataTransfer?.files
  if (!files?.length) return
  for (const file of Array.from(files)) {
    const ext = file.name.split('.').pop()?.toLowerCase() || ''
    if (!ALLOWED_EXTENSIONS.has(ext)) {
      ElMessage.warning(`不支持的文件格式: ${file.name}`)
      continue
    }
    addPendingFile(file)
  }
}

function handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of Array.from(items)) {
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      const blob = item.getAsFile()
      if (!blob) continue
      const now = new Date()
      const ts = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`
      const file = new File([blob], `clipboard_${ts}.png`, { type: 'image/png' })
      addPendingFile(file)
      return
    }
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

// ── 加载指令 ──
async function loadAllCommands() {
  if (allCommands.value.length > 0) return
  const commands: any[] = [
    { name: '/skills', label: 'List Skills', description: '浏览所有技能' },
    { name: '/mcps', label: 'List MCPs', description: '浏览 MCP 服务' },
    { name: '/prompt', label: '选择模板', description: '选择提示词模板' },
    { name: '/model', label: '切换模型', description: '切换 AI 模型' },
    { name: '/theme', label: '切换主题', description: '切换深色/浅色主题' },
  ]
  try {
    const { getSkillList } = await import('@/api/skills')
    const res: any = await getSkillList({ page: 1, page_size: 100 })
    const skills = res.items || []
    skills.forEach((skill: any) => {
      commands.push({
        name: `/${skill.name}`,
        label: skill.name,
        description: skill.description || '使用此技能开始对话',
        data: skill,
      })
    })
  } catch {}
  allCommands.value = commands
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

function handleTemplateSelect(templateId: number | null) {
  currentTemplateId.value = templateId
  templatePopoverVisible.value = false
}

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

async function handleSkillCommandSelection(skillData: any) {
  if (!skillData?.id) return
  selectedSkillId.value = skillData.id
  selectedSkillName.value = skillData.name
  if (skillData.model_provider_id && skillData.model_name) {
    selectedProviderId.value = skillData.model_provider_id
    selectedModelName.value = skillData.model_name
  }
  ElMessage.success(`已选择技能：${skillData.name}`)
}

const { executeCommand } = useCommandDispatcher({
  openModelList,
  openSkillList,
  openMcpList,
  openTemplateList,
  toggleTheme: () => {
    const btn = document.querySelector('.theme-toggle') as HTMLElement
    btn?.click()
  },
  onSkillCommand: handleSkillCommandSelection,
})

function selectModel(model: any) {
  showModelList.value = false
  inputText.value = ''
  void disableAutoRoute()
  selectedProviderId.value = model.provider_id
  selectedModelName.value = model.model_name
  ElMessage.success(`已选择 ${model.display_name}`)
}

function selectSkill(skill: any) {
  showSkillList.value = false
  inputText.value = ''
  selectedSkillId.value = skill.id
  selectedSkillName.value = skill.name
  if (skill.model_provider_id && skill.model_name) {
    selectedProviderId.value = skill.model_provider_id
    selectedModelName.value = skill.model_name
  }
  ElMessage.success(`已选择技能：${skill.name}`)
}

function selectTemplate(template: any) {
  showTemplateList.value = false
  inputText.value = ''
  handleTemplateSelect(template.id ?? null)
}

function handleModelSelected(providerId: number, modelName: string) {
  selectedProviderId.value = providerId
  selectedModelName.value = modelName
}

const {
  initAutoRoutePreference,
  setAutoRouteEnabled,
  disableAutoRoute,
} = useAutoRoutePreference({
  autoRouteEnabled,
})

async function handleAutoRouteToggle(val: boolean) {
  await setAutoRouteEnabled(val)
}

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

const { ensureMultimodalSupport } = useMultimodalGuard()

async function ensureHomeMultimodalSupport(): Promise<boolean> {
  try {
    return await ensureMultimodalSupport({
      hasImages: pendingFiles.value.some((file) => file.isImage),
      autoRouteEnabled: autoRouteEnabled.value,
      providerId: selectedProviderId.value,
      modelName: selectedModelName.value,
      modelList,
      loadModelList,
      showWarning: (message) => ElMessage.warning(message),
      showConfirm: showDangerConfirm,
      onUnsupportedConfirmed: () => {
        pendingFiles.value = pendingFiles.value.filter((file) => {
          if (file.isImage && file.previewUrl) {
            URL.revokeObjectURL(file.previewUrl)
          }
          return !file.isImage
        })
      },
    })
  } catch {
    return false
  }
}

// ── 发送 ──
async function handleSend() {
  const text = inputText.value.trim()
  if (!text || sending.value) return
  sending.value = true
  try {
    // 1. 创建对话
    const res: any = await createConversation(selectedSkillId.value)
    const convId = res.data.conversation_id

    // 1.5 切换提示词模板（如果已选择）
    if (currentTemplateId.value) {
      try { await switchPromptTemplate(convId, currentTemplateId.value) } catch {}
    }

    // 2. 切换模型（如果用户手动选了且未开启智能路由）
    if (!autoRouteEnabled.value && selectedProviderId.value && selectedModelName.value) {
      try { await switchConversationModel(convId, selectedProviderId.value, selectedModelName.value) } catch {}
    }

    // 2.5 多模态校验
    if (!(await ensureHomeMultimodalSupport())) {
      sending.value = false
      return
    }

    // 3. 上传附件
    const uploadedFileIds: number[] = []
    const uploadedFiles: { file_id: number; original_name: string; file_type: string; file_size: number }[] = []
    for (const pf of pendingFiles.value) {
      try {
        const uploadRes: any = await uploadFileApi(pf.file, convId)
        uploadedFileIds.push(uploadRes.data.file_id)
        uploadedFiles.push({ file_id: uploadRes.data.file_id, original_name: uploadRes.data.original_name, file_type: uploadRes.data.file_type, file_size: uploadRes.data.file_size })
      } catch {}
    }

    // 4. 立即跳转，让 Chat.vue 负责发送消息
    const savedText = text
    inputText.value = ''
    // 清理预览 URL
    pendingFiles.value.forEach(pf => { if (pf.previewUrl) URL.revokeObjectURL(pf.previewUrl) })
    pendingFiles.value = []
    selectedSkillId.value = null
    selectedSkillName.value = null

    if (uploadedFiles.length) {
      sessionStorage.setItem('pending_files', JSON.stringify(uploadedFiles))
    }
    router.push({ path: `/chat/${convId}`, query: { msg: savedText, file_ids: uploadedFileIds.length ? uploadedFileIds.join(',') : undefined } })
  } catch {
    ElMessage.error('创建对话失败')
    sending.value = false
  }
}

const { handleKeyDown } = useCommandPanelKeydown({
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
  isComposing,
  isGenerating: computed(() => sending.value),
  handleSend,
})

// ── 输入监听 ──
watch(listSearchQuery, () => {
  selectedTemplateIndex.value = 0
  selectedModelIndex.value = 0
  selectedSkillIndex.value = 0
  selectedMcpIndex.value = 0
})

watch(inputText, (val) => {
  if (val === '@') {
    inputText.value = ''
    triggerFileUpload()
    return
  }
  if (val.startsWith('/')) {
    const query = val.slice(1).toLowerCase()
    commandSuggestions.value = (query === '' ? allCommands.value.slice(0, 8) : allCommands.value.filter(c =>
      c.name.toLowerCase().includes(query) || c.label.toLowerCase().includes(query) || c.description.toLowerCase().includes(query)
    ).slice(0, 8))
    showCommandSuggestions.value = commandSuggestions.value.length > 0
    selectedCommandIndex.value = 0
  } else {
    showCommandSuggestions.value = false
  }
})

function handleCommandSuggestionsOutsideClick(e: MouseEvent) {
  if (!showCommandSuggestions.value && !showTemplateList.value && !showSkillList.value && !showMcpList.value && !showModelList.value) return
  const target = e.target as Node | null
  if (!target) return
  if (homeInputAreaRef.value?.contains(target)) return
  showCommandSuggestions.value = false
  showTemplateList.value = false
  showSkillList.value = false
  showMcpList.value = false
  showModelList.value = false
}

onMounted(async () => {
  document.addEventListener('mousedown', handleCommandSuggestionsOutsideClick)
  await loadAllCommands()
  if (!authStore.user) await authStore.fetchUser()
  try {
    await loadTemplateList()
  } catch {}
  await initAutoRoutePreference()
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleCommandSuggestionsOutsideClick)
})

function clearSkill() {
  selectedSkillId.value = null
  selectedSkillName.value = null
}

// 快捷操作
const quickActions = [
  { label: '浏览技能', icon: '🎯', action: openSkillList },
  { label: '查看 MCP', icon: '🔌', action: openMcpList },
  { label: '选择模型', icon: '🤖', action: openModelList },
  { label: '历史对话', icon: '💬', action: () => router.push('/chat') },
]
</script>

<template>
  <div class="home-page">
    <div class="home-center">
      <!-- Greeting -->
      <div class="home-greeting">
        <span class="greeting-line anim-item" style="animation-delay: 0.1s">✨ {{ authStore.user?.display_name || '' }}，你好</span>
        <h1 class="home-title anim-item" style="animation-delay: 0.25s">需要我为你做些什么？</h1>
      </div>

      <!-- 已选技能 -->
      <Transition name="badge-fade">
        <div v-if="selectedSkillName" class="skill-badge-bar">
          <span class="skill-badge">
            <el-icon :size="13"><MagicStick /></el-icon>
            {{ selectedSkillName }}
            <el-icon class="skill-badge-close" :size="12" aria-label="清除技能" @click="clearSkill"><Close /></el-icon>
          </span>
        </div>
      </Transition>

      <!-- 输入卡片 -->
      <div ref="homeInputAreaRef" class="home-input-area">
        <!-- 暂存附件 -->
        <div v-if="pendingFiles.length > 0" class="pending-files">
          <div v-for="(pf, i) in pendingFiles" :key="i" class="file-item">
            <template v-if="pf.isImage">
              <img :src="pf.previewUrl" :alt="pf.file.name" class="file-thumbnail" loading="lazy" decoding="async" @click.stop="openPreview(imageFiles.indexOf(pf))" />
            </template>
            <template v-else>
              <el-icon color="#409eff"><Document /></el-icon>
              <span class="file-name">{{ pf.file.name }}</span>
              <span class="file-size">{{ formatSize(pf.file.size) }}</span>
            </template>
            <el-button link type="danger" size="small" @click="removePendingFile(i)"><el-icon><Close /></el-icon></el-button>
          </div>
        </div>
        <input ref="fileInputRef" type="file" accept=".txt,.md,.docx,.xlsx,.csv,.pdf,.jpg,.jpeg,.png,.gif,.webp,.bmp,.svg" multiple style="display:none" @change="handleFileSelect" />

        <!-- 弹出列表 -->
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
          @update:list-search-query="(value) => (listSearchQuery = value)"
          @list-keydown="handleKeyDown"
          @command-select="async (command) => { await executeCommand(command); inputText = ''; showCommandSuggestions = false }"
          @template-select="selectTemplate"
          @skill-select="selectSkill"
          @model-select="selectModel"
        />

        <!-- 输入框卡片 -->
        <div class="input-card" :class="{ sending }" @dragenter.prevent="dragCounter++; isDragging = true" @dragleave.prevent="dragCounter--; if (dragCounter <= 0) { isDragging = false; dragCounter = 0 }" @dragover.prevent @drop.prevent="handleDrop">
          <div v-if="isDragging" class="drop-overlay">
            <div class="drop-hint">
              <el-icon :size="24"><Paperclip /></el-icon>
              <span>将文件拖放到此处</span>
            </div>
          </div>
          <button v-if="!sending" type="button" class="optimize-icon-btn" title="优化提示词" aria-label="优化提示词" :disabled="optimizing || !inputText.trim()" @click="handleOptimizePrompt">
            <el-icon :class="{ 'is-loading': optimizing }"><MagicStick /></el-icon>
          </button>
          <label for="home-input" class="sr-only">输入消息</label>
          <el-input id="home-input" :key="inputKey" v-model="inputText" type="textarea" :autosize="inputExpanded ? { minRows: 11, maxRows: 22 } : { minRows: 3, maxRows: 7 }" placeholder="你想要的一切，从这里开始" :disabled="sending" @keydown="handleKeyDown" @compositionstart="isComposing = true" @compositionend="isComposing = false" @paste="handlePaste" />
          <div class="input-toolbar">
            <div class="toolbar-left">
              <PromptTemplateSelector
                :popover-visible="templatePopoverVisible"
                :current-template-label="currentTemplateLabel"
                :current-template-id="currentTemplateId"
                :is-free-template-global-default="isFreeTemplateGlobalDefault"
                :global-default-template-id="globalDefaultTemplateId"
                :visible-template-list="visibleTemplateList"
                :loading="loadingTemplate"
                @update:popover-visible="(value) => (templatePopoverVisible = value)"
                @visible-change="handleTemplatePopoverVisible"
                @select="handleTemplateSelect"
              />
              <button type="button" class="tool-btn" title="添加附件" aria-label="添加附件" @click="triggerFileUpload">
                <el-icon :size="18"><Plus /></el-icon>
              </button>
            </div>
            <div class="toolbar-right">
              <el-tooltip content="根据提问内容自动选择最佳模型" placement="top">
                <el-switch v-model="autoRouteEnabled" active-text="智能选择" size="small" @change="handleAutoRouteToggle" />
              </el-tooltip>
              <ModelSelector v-if="!autoRouteEnabled" :conversation-id="null" :current-provider-id="selectedProviderId" :current-model-name="selectedModelName" @model-selected="handleModelSelected" />
              <el-button v-if="sending" type="primary" size="small" class="send-btn" disabled loading round>创建中...</el-button>
              <el-button v-else type="primary" size="small" :disabled="!inputText.trim()" @click="handleSend" class="send-btn" round>发送 ↵</el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 快捷操作 chips -->
      <div class="quick-actions anim-item" style="animation-delay: 0.55s">
        <button v-for="qa in quickActions" :key="qa.label" class="quick-chip" @click="qa.action">
          <span class="chip-icon">{{ qa.icon }}</span>
          <span>{{ qa.label }}</span>
        </button>
      </div>
    </div>

    <!-- 优化提示词对话框 -->
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

    <!-- 图片预览 -->
    <Teleport to="body">
      <div v-if="showPreview && imageFiles.length > 0" class="home-preview-overlay" @wheel.prevent="handlePreviewWheel">
        <div class="home-preview-counter">{{ previewIndex + 1 }} / {{ imageFiles.length }}</div>
        <img :src="imageFiles[previewIndex]?.previewUrl" :alt="imageFiles[previewIndex]?.file.name" class="home-preview-image" :style="{ transform: `scale(${previewScale})` }" />
        <button v-if="imageFiles.length > 1 && previewIndex > 0" class="home-preview-nav home-prev" aria-label="上一张图片" @click.stop="previewIndex--; previewScale = 1">&lt;</button>
        <button v-if="imageFiles.length > 1 && previewIndex < imageFiles.length - 1" class="home-preview-nav home-next" aria-label="下一张图片" @click.stop="previewIndex++; previewScale = 1">&gt;</button>
        <button class="home-preview-close" aria-label="关闭预览" @click="showPreview = false">&times;</button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.home-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 60px);
  background: var(--bg-page, #f5f7fa);
  padding-bottom: 60px;
}

/* ── Drop overlay ── */
.drop-overlay {
  position: absolute;
  inset: 0;
  background: rgba(219, 228, 243, 0.45);
  border: 1.5px dashed #7cacf8;
  border-radius: 24px;
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
.home-center {
  width: 100%;
  max-width: var(--container-lg);
  padding: 0 32px;
}

/* ── Greeting ── */
.home-greeting {
  margin-bottom: 40px;
  padding-left: 24px;
  overflow: hidden;
}

/* sr-only for accessibility */
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

/* ── Staggered entrance animation (Gemini-style) ── */
.anim-item {
  animation: slide-up-fade 0.9s cubic-bezier(0.25, 0.46, 0.45, 0.94) both;
}
@keyframes slide-up-fade {
  from {
    opacity: 0;
    transform: translateY(24px);
    filter: blur(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
    filter: blur(0);
  }
}

.greeting-line {
  display: block;
  font-size: 18px;
  color: var(--text-secondary, #606266);
  margin-bottom: 6px;
  letter-spacing: 0.3px;
}
.home-title {
  font-size: 36px;
  font-weight: 700;
  color: var(--text-primary, #1d1d1f);
  margin: 0;
  line-height: 1.25;
  letter-spacing: -0.5px;
}

/* ── Skill badge ── */
.skill-badge-bar {
  padding-left: 24px;
  margin-bottom: 16px;
}
.skill-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  color: #8b7bc6;
  background: rgba(139, 123, 198, 0.08);
  border: 1px solid rgba(139, 123, 198, 0.18);
}
.skill-badge-close {
  cursor: pointer;
  opacity: 0.45;
  transition: opacity 0.15s;
}
.skill-badge-close:hover { opacity: 1; }

.badge-fade-enter-active { transition: all 0.25s ease-out; }
.badge-fade-leave-active { transition: all 0.15s ease-in; }
.badge-fade-enter-from, .badge-fade-leave-to { opacity: 0; transform: translateY(-4px); }

/* ── Input area ── */
.home-input-area {
  position: relative;
}

.pending-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-left: 24px;
  margin-bottom: 10px;
}
.file-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  background: var(--bg-card, #fff);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  font-size: 12px;
  color: var(--text-secondary, #606266);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.file-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-size {
  color: var(--text-muted, #c0c4cc);
  font-size: 11px;
}
.file-thumbnail {
  height: 40px;
  width: 56px;
  object-fit: cover;
  border-radius: 8px;
  flex-shrink: 0;
  cursor: pointer;
}
.file-thumbnail:hover { opacity: 0.8; }

/* ── Input card (Gemini style) ── */
.input-card {
  position: relative;
  background: var(--bg-card, #fff);
  border-radius: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 4px 16px rgba(0, 0, 0, 0.04);
  transition: box-shadow 0.25s;
  overflow: hidden;
}
.input-card:focus-within {
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 8px 32px rgba(0, 0, 0, 0.08);
}
.input-card.sending {
  opacity: 0.6;
  pointer-events: none;
}
.input-card :deep(.el-textarea__inner) {
  resize: none;
  border: none !important;
  box-shadow: none !important;
  padding: 24px 24px 12px;
  font-size: 16px;
  line-height: 1.65;
  background: transparent;
  color: var(--text-primary, #303133);
  transition: height 0.4s ease;
}
.input-card :deep(.el-textarea__inner)::placeholder {
  color: var(--text-muted, #c0c4cc);
}

/* ── Toolbar ── */
.input-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 14px 14px;
}
.toolbar-left {
  display: flex;
  gap: 4px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.tool-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  color: var(--text-muted, #909399);
  transition: background 0.15s, color 0.15s;
}
.tool-btn:hover {
  background: var(--bg-hover, #f0f2f5);
  color: var(--text-secondary, #606266);
}
.tool-btn .rotate-icon {
  transform: rotate(180deg);
  transition: transform 0.3s ease;
}

.send-btn {
  height: 32px;
  min-width: 76px;
  font-size: 13px;
  border-radius: 10px;
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

/* ── Quick action chips ── */
.quick-actions {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
}
.quick-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border-radius: 20px;
  border: none;
  background: var(--bg-card, #fff);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  font-size: 14px;
  color: var(--text-primary, #303133);
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
  font-family: inherit;
}
.quick-chip:hover {
  background: var(--bg-hover, #f0f2f5);
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.08);
}
.chip-icon {
  font-size: 15px;
}

/* ── Optimize button ── */
.optimize-icon-btn {
  position: absolute;
  top: 22px;
  right: 14px;
  z-index: 10;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-muted, #c0c4cc);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.optimize-icon-btn:hover {
  background: var(--bg-hover, #f0f2f5);
  color: var(--el-color-primary);
}
.optimize-icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.optimize-icon-btn .el-icon { font-size: 16px; }

/* ── Image preview overlay ── */
.home-preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.85);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.home-preview-image {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 4px;
}
.home-preview-counter {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  color: #fff;
  font-size: 14px;
  background: rgba(0,0,0,0.5);
  padding: 4px 12px;
  border-radius: 12px;
}
.home-preview-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255,255,255,0.2);
  border: none;
  color: #fff;
  font-size: 28px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.home-preview-nav:hover { background: rgba(255,255,255,0.4); }
.home-prev { left: 16px; }
.home-next { right: 16px; }
.home-preview-close {
  position: absolute;
  top: 16px;
  right: 16px;
  background: rgba(255,255,255,0.2);
  border: none;
  color: #fff;
  font-size: 24px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.home-preview-close:hover { background: rgba(255,255,255,0.4); }

:global(.home-confirm-dialog.el-message-box) {
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

:global(.home-confirm-dialog .el-message-box__header) {
  padding: 22px 24px 0;
}

:global(.home-confirm-dialog .el-message-box__title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary, #0f172a);
}

:global(.home-confirm-dialog .el-message-box__content) {
  padding: 14px 24px 0;
}

:global(.home-confirm-dialog .el-message-box__message) {
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
  background: #eff6ff;
  color: #2563eb;
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

:global(.home-confirm-dialog .el-message-box__btns) {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 22px 24px 24px;
}

:global(.home-confirm-dialog .home-confirm-secondary) {
  border-color: #e5e7eb;
  background: #ffffff;
  color: var(--text-secondary, #475569);
}

:global(.home-confirm-dialog .home-confirm-secondary:hover) {
  border-color: #dbeafe;
  background: #eff6ff;
  color: var(--text-primary, #0f172a);
}

:global(.home-confirm-dialog .home-confirm-primary) {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  color: #2563eb;
  box-shadow: none;
}

:global(.home-confirm-dialog .home-confirm-primary:hover) {
  border-color: #bfdbfe;
  background: #dbeafe;
  color: #1d4ed8;
}

:global(html.dark .home-confirm-dialog.el-message-box) {
  border-color: rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.96) 0%, rgba(10, 15, 27, 0.98) 100%);
  box-shadow: 0 32px 84px rgba(2, 6, 23, 0.48);
}

:global(html.dark .home-confirm-dialog .el-message-box__title) {
  color: #f8fafc;
}

:global(html.dark .danger-confirm-badge) {
  background: rgba(96, 165, 250, 0.14);
  color: #bfdbfe;
}

:global(html.dark .danger-confirm-subject) {
  color: #f8fafc;
}

:global(html.dark .danger-confirm-detail) {
  color: #94a3b8;
}
</style>
