<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  getAdminSkillDetail, createSkill, updateSkill,
  parseSkillPackage, getTempFileContent,
  uploadSkillPackage, getPackageFiles, getPackageFileContent, uploadSkillIcon,
} from '@/api/admin/skills'
import { getSceneTagList } from '@/api/admin/sceneTags'
import { getAvailableModels } from '@/api/admin/modelProviders'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: true, linkify: true, breaks: true })

interface FileNode {
  name: string
  path: string
  type: 'file' | 'directory'
  extension?: string
  children?: FileNode[]
}

const router = useRouter()
const route = useRoute()
const skillId = computed(() => route.params.id ? Number(route.params.id) : null)
const isEdit = computed(() => !!skillId.value)

const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const formRef = ref<FormInstance>()
const allTags = ref<{ id: number; name: string }[]>([])
const availableModels = ref<{ provider_id: number; provider_name: string; model_name: string; display_name: string }[]>([])
const availableMcps = ref<{ id: number; name: string }[]>([])

// 步骤控制：新建时 step=0 表示"待上传"，上传后或手动跳过后 step=1 表示"编辑表单"
const step = ref(0)

const form = ref({
  name: '',
  icon_emoji: '',
  brief_desc: '',
  detail_desc: '',
  tag_ids: [] as number[],
  system_prompt: '',
  welcome_message: '',
  model_provider_id: null as number | null,
  model_name: '',
  usage_example: '',
  mcp_load_mode: 'all',
  mcp_ids: [] as number[],
})
const iconUrl = ref('')
const selectedModelKey = ref('')
const emojiDialogVisible = ref(false)
const emojiActiveTab = ref('办公学习')
const emojiSearch = ref('')
const iconFileInputRef = ref<HTMLInputElement | null>(null)
const iconCropDialogVisible = ref(false)
const cropImageSrc = ref('')
const cropScale = ref(1)
const cropMinScale = ref(1)
const cropMaxScale = ref(4)
const cropX = ref(0)
const cropY = ref(0)
const iconCropImageRef = ref<HTMLImageElement | null>(null)
const sourceImageNaturalWidth = ref(0)
const sourceImageNaturalHeight = ref(0)
const draggingCrop = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const dragOriginX = ref(0)
const dragOriginY = ref(0)
const cropSize = 240
const uploadingIcon = ref(false)

import { emojiCategories } from '@/utils/emojis'

function selectEmoji(e: string) {
  form.value.icon_emoji = e
  emojiDialogVisible.value = false
}

const iconPreviewSrc = computed(() => iconUrl.value || '')
const cropImageStyle = computed(() => ({
  width: `${sourceImageNaturalWidth.value * cropScale.value}px`,
  height: `${sourceImageNaturalHeight.value * cropScale.value}px`,
  transform: `translate(${cropX.value}px, ${cropY.value}px)`,
}))

function getFilteredEmojis(emojis: string[]): string[] {
  const q = emojiSearch.value.trim().toLowerCase()
  if (!q) return emojis
  const normalized = q.replace(/^u\+/, '')
  return emojis.filter((emoji) => {
    if (emoji.includes(q)) return true
    const cp = emoji.codePointAt(0)?.toString(16).toLowerCase() || ''
    return cp.includes(normalized)
  })
}

watch(emojiDialogVisible, (v) => {
  if (!v) emojiSearch.value = ''
})

function openIconFilePicker() {
  if (!isEdit.value) {
    ElMessage.warning('请先创建 Skill，再上传图片图标')
    return
  }
  iconFileInputRef.value?.click()
}

function resetCropState() {
  cropImageSrc.value = ''
  cropScale.value = 1
  cropMinScale.value = 1
  cropMaxScale.value = 4
  cropX.value = 0
  cropY.value = 0
  sourceImageNaturalWidth.value = 0
  sourceImageNaturalHeight.value = 0
  draggingCrop.value = false
}

function clampCropPosition() {
  const imageWidth = sourceImageNaturalWidth.value * cropScale.value
  const imageHeight = sourceImageNaturalHeight.value * cropScale.value
  const minX = imageWidth <= cropSize ? 0 : cropSize - imageWidth
  const maxX = imageWidth <= cropSize ? cropSize - imageWidth : 0
  const minY = imageHeight <= cropSize ? 0 : cropSize - imageHeight
  const maxY = imageHeight <= cropSize ? cropSize - imageHeight : 0
  cropX.value = Math.min(maxX, Math.max(minX, cropX.value))
  cropY.value = Math.min(maxY, Math.max(minY, cropY.value))
}

function updateScale(nextScale: number) {
  const prevScale = cropScale.value
  if (nextScale === prevScale) return
  const focalX = (cropSize / 2 - cropX.value) / prevScale
  const focalY = (cropSize / 2 - cropY.value) / prevScale
  cropScale.value = nextScale
  cropX.value = cropSize / 2 - focalX * nextScale
  cropY.value = cropSize / 2 - focalY * nextScale
  clampCropPosition()
}

function handleCropScaleChange(val: number) {
  updateScale(val)
}

function handleIconFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  const isSupportedType = ['image/png', 'image/jpeg', 'image/jpg', 'image/svg+xml'].includes(file.type)
  if (!isSupportedType) {
    ElMessage.error('仅支持 png/jpg/svg 格式')
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.error('图标文件不能超过 2MB')
    return
  }

  const reader = new FileReader()
  reader.onload = async () => {
    cropImageSrc.value = String(reader.result || '')
    iconCropDialogVisible.value = true
    await nextTick()
  }
  reader.readAsDataURL(file)
}

function handleCropImageLoad() {
  const image = iconCropImageRef.value
  if (!image) return
  sourceImageNaturalWidth.value = image.naturalWidth || 1
  sourceImageNaturalHeight.value = image.naturalHeight || 1
  const fitScale = Math.min(
    cropSize / sourceImageNaturalWidth.value,
    cropSize / sourceImageNaturalHeight.value,
  )
  cropMinScale.value = Math.max(fitScale * 0.2, 0.05)
  cropMaxScale.value = Math.max(fitScale * 8, fitScale + 1)
  cropScale.value = fitScale
  const imageWidth = sourceImageNaturalWidth.value * fitScale
  const imageHeight = sourceImageNaturalHeight.value * fitScale
  cropX.value = (cropSize - imageWidth) / 2
  cropY.value = (cropSize - imageHeight) / 2
  clampCropPosition()
}

function handleCropMouseDown(event: MouseEvent) {
  if (!cropImageSrc.value) return
  draggingCrop.value = true
  dragStartX.value = event.clientX
  dragStartY.value = event.clientY
  dragOriginX.value = cropX.value
  dragOriginY.value = cropY.value
}

function handleCropMouseMove(event: MouseEvent) {
  if (!draggingCrop.value) return
  const deltaX = event.clientX - dragStartX.value
  const deltaY = event.clientY - dragStartY.value
  cropX.value = dragOriginX.value + deltaX
  cropY.value = dragOriginY.value + deltaY
  clampCropPosition()
}

function handleCropMouseUp() {
  draggingCrop.value = false
}

function handleCropWheel(event: WheelEvent) {
  event.preventDefault()
  const direction = event.deltaY > 0 ? -0.05 : 0.05
  const next = Math.min(cropMaxScale.value, Math.max(cropMinScale.value, cropScale.value + direction))
  updateScale(next)
}

async function saveCroppedIcon() {
  if (!skillId.value || !iconCropImageRef.value) return
  uploadingIcon.value = true
  try {
    const canvas = document.createElement('canvas')
    const outputSize = 256
    canvas.width = outputSize
    canvas.height = outputSize
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('无法初始化图标画布')
    const ratio = outputSize / cropSize
    ctx.clearRect(0, 0, outputSize, outputSize)
    ctx.drawImage(
      iconCropImageRef.value,
      cropX.value * ratio,
      cropY.value * ratio,
      sourceImageNaturalWidth.value * cropScale.value * ratio,
      sourceImageNaturalHeight.value * cropScale.value * ratio,
    )
    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob((result) => resolve(result), 'image/png')
    })
    if (!blob) throw new Error('图标生成失败，请重试')
    const iconFile = new File([blob], `skill-icon-${skillId.value}.png`, { type: 'image/png' })
    const res: any = await uploadSkillIcon(skillId.value, iconFile)
    iconUrl.value = `${res.data.icon_url}?t=${Date.now()}`
    iconCropDialogVisible.value = false
    ElMessage.success('图标上传成功')
  } finally {
    uploadingIcon.value = false
  }
}

watch(iconCropDialogVisible, (visible) => {
  if (!visible) resetCropState()
})

// 草稿状态
const hasDraft = ref(false)

// 技能包相关
const tempPackageId = ref('')
const fileTree = ref<FileNode[]>([])
const hasPackage = ref(false)
const previewFile = ref<{ path: string; content: string; extension: string } | null>(null)
const previewLoading = ref(false)
const uploadedFileName = ref('')

const rules: FormRules = {
  name: [{ required: true, message: '请输入 Skill 名称', trigger: 'blur' }],
  brief_desc: [
    { required: true, message: '请输入描述', trigger: 'blur' },
    { max: 1000, message: '不超过 1000 个字符', trigger: 'blur' },
  ],
  detail_desc: [{ required: true, message: '请输入详细说明', trigger: 'blur' }],
  tag_ids: [{ required: true, type: 'array', min: 1, message: '请选择至少一个标签', trigger: 'change' }],
  system_prompt: [{ required: true, message: '请输入系统 Prompt', trigger: 'blur' }],
  welcome_message: [{ required: true, message: '请输入开场白', trigger: 'blur' }],
}

function onModelChange(key: string) {
  const m = availableModels.value.find((x) => `${x.provider_id}::${x.model_name}` === key)
  if (m) {
    form.value.model_provider_id = m.provider_id
    form.value.model_name = m.model_name
  }
}

async function loadOptions() {
  const { getMcpList } = await import('@/api/admin/mcps')
  const [tagRes, modelRes, mcpRes]: any[] = await Promise.all([getSceneTagList(), getAvailableModels(), getMcpList({ is_enabled: true })])
  allTags.value = tagRes.data.filter((t: any) => t.is_active)
  availableModels.value = modelRes.data
  availableMcps.value = (mcpRes.data.items || []).map((m: any) => ({ id: m.id, name: m.name }))
}

async function loadSkill() {
  if (!skillId.value) return
  loading.value = true
  try {
    const res: any = await getAdminSkillDetail(skillId.value)
    const d = res.data
    hasDraft.value = !!d.draft_version_detail
    const v = d.draft_version_detail || d.published_version_detail
    if (v) {
      form.value = {
        name: d.name,
        icon_emoji: d.icon_emoji || '',
        brief_desc: v.brief_desc,
        detail_desc: v.detail_desc,
        tag_ids: (d.tags || []).map((t: any) => t.id),
        system_prompt: v.system_prompt,
        welcome_message: v.welcome_message,
        model_provider_id: v.model_provider_id,
        model_name: v.model_name,
        usage_example: v.usage_example || '',
        mcp_load_mode: v.mcp_load_mode || 'all',
        mcp_ids: v.mcp_ids || [],
      }
      iconUrl.value = d.icon_url || ''
      selectedModelKey.value = `${v.model_provider_id}::${v.model_name}`
      if (v.has_package) {
        await loadPackageFiles()
      }
    }
    step.value = 1
  } finally {
    loading.value = false
  }
}

async function loadPackageFiles() {
  if (!skillId.value) return
  try {
    let res: any = await getPackageFiles(skillId.value, 'draft')
    if (!res.data.has_package) {
      res = await getPackageFiles(skillId.value, 'published')
    }
    fileTree.value = res.data.file_tree
    hasPackage.value = res.data.has_package
  } catch { /* ignore */ }
}

// 新建模式：上传并解析技能包
async function handleParsePackage(uploadFile: any) {
  uploading.value = true
  try {
    const res: any = await parseSkillPackage(uploadFile.file)
    const { temp_package_id, parsed_info, file_tree: tree } = res.data

    tempPackageId.value = temp_package_id
    fileTree.value = tree
    hasPackage.value = true
    uploadedFileName.value = uploadFile.file.name
    previewFile.value = null

    // 自动填充表单
    if (parsed_info.name) form.value.name = parsed_info.name
    if (parsed_info.brief_desc) form.value.brief_desc = parsed_info.brief_desc
    if (parsed_info.detail_desc) form.value.detail_desc = parsed_info.detail_desc
    if (parsed_info.system_prompt) form.value.system_prompt = parsed_info.system_prompt
    if (parsed_info.welcome_message) form.value.welcome_message = parsed_info.welcome_message

    // 自动选择第一个可用模型
    const first = availableModels.value[0]
    if (first && !selectedModelKey.value) {
      selectedModelKey.value = `${first.provider_id}::${first.model_name}`
      form.value.model_provider_id = first.provider_id
      form.value.model_name = first.model_name
    }

    step.value = 1
    ElMessage.success('技能包解析成功，已自动填充表单，请检查并补充信息')
  } catch {
    // error handled by interceptor
  } finally {
    uploading.value = false
  }
  return false
}

// 编辑模式：重新上传技能包
async function handleReUploadPackage(uploadFile: any) {
  if (!skillId.value) return false
  uploading.value = true
  try {
    const res: any = await uploadSkillPackage(skillId.value, uploadFile.file)
    fileTree.value = res.data.file_tree
    hasPackage.value = true
    previewFile.value = null
    uploadedFileName.value = uploadFile.file.name
    ElMessage.success('技能包更新成功')
    await loadSkill()
  } finally {
    uploading.value = false
  }
  return false
}

async function handleFileClick(node: FileNode) {
  if (node.type !== 'file') return
  previewLoading.value = true
  try {
    let res: any
    if (tempPackageId.value && !skillId.value) {
      // 新建模式用临时包接口
      res = await getTempFileContent(tempPackageId.value, node.path)
    } else if (skillId.value) {
      // 先尝试 draft，再尝试 published，用原始 axios 避免拦截器弹错误提示
      const token = localStorage.getItem('access_token')
      const headers = { Authorization: `Bearer ${token}` }
      const baseUrl = `/api/admin/skills/${skillId.value}/package-files/content?file_path=${encodeURIComponent(node.path)}`
      let raw = await fetch(`${baseUrl}&version_type=draft`, { headers })
      let json = await raw.json()
      if (!raw.ok || json.code !== 0) {
        raw = await fetch(`${baseUrl}&version_type=published`, { headers })
        json = await raw.json()
      }
      res = json
    } else {
      return
    }
    const d = res.data
    if (d.is_text) {
      previewFile.value = { path: d.file_path, content: d.content, extension: d.extension }
    } else {
      previewFile.value = { path: d.file_path, content: d.message || '不支持预览此文件格式', extension: '' }
    }
  } finally {
    previewLoading.value = false
  }
}

function skipUpload() {
  step.value = 1
  const first = availableModels.value[0]
  if (first && !selectedModelKey.value) {
    selectedModelKey.value = `${first.provider_id}::${first.model_name}`
    form.value.model_provider_id = first.provider_id
    form.value.model_name = first.model_name
  }
}

async function handleDownloadPackage() {
  if (!skillId.value) return
  const token = localStorage.getItem('access_token')
  const url = `/api/admin/skills/${skillId.value}/download-package?version_type=draft`
  try {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    const contentType = res.headers.get('Content-Type') || ''

    if (!res.ok) {
      const text = await res.text()
      try {
        const json = JSON.parse(text)
        ElMessage.error(json.detail || json.message || '下载失败')
      } catch {
        ElMessage.error(`下载失败 (${res.status})`)
      }
      return
    }

    if (contentType.includes('application/zip') || contentType.includes('application/octet-stream')) {
      const blob = await res.blob()
      const disposition = res.headers.get('Content-Disposition') || ''
      const starMatch = disposition.match(/filename\*=UTF-8''([^\s;]+)/)
      const plainMatch = disposition.match(/filename="?([^";\s]+)"?/)
      const rawName = starMatch ? starMatch[1] : plainMatch ? plainMatch[1] : ''
      const filename = rawName ? decodeURIComponent(rawName) : `skill_${skillId.value}.zip`
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = filename
      a.click()
      URL.revokeObjectURL(a.href)
    } else {
      const json = await res.json()
      ElMessage.error(json.message || '下载失败')
    }
  } catch (e: any) {
    console.error('Download error:', e)
    ElMessage.error('下载失败，请稍后重试')
  }
}

async function handleSave() {
  await formRef.value?.validate()
  if (!form.value.model_provider_id || !form.value.model_name) {
    ElMessage.warning('请选择模型')
    return
  }
  saving.value = true
  try {
    if (isEdit.value) {
      const res: any = await updateSkill(skillId.value!, form.value)
      ElMessage.success(res.data?.is_draft_save ? '已保存为草稿，需要发布后生效' : '保存成功')
      router.push('/admin/skills')
    } else {
      const payload: any = { ...form.value }
      if (tempPackageId.value) {
        payload.temp_package_id = tempPackageId.value
      }
      await createSkill(payload)
      ElMessage.success('Skill 创建成功')
      router.push('/admin/skills')
    }
  } finally {
    saving.value = false
  }
}

function renderMarkdown(content: string): string {
  return md.render(content || '')
}

onMounted(async () => {
  window.addEventListener('mousemove', handleCropMouseMove)
  window.addEventListener('mouseup', handleCropMouseUp)
  await loadOptions()
  if (isEdit.value) {
    await loadSkill()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', handleCropMouseMove)
  window.removeEventListener('mouseup', handleCropMouseUp)
})
</script>

<template>
  <div class="skill-editor" v-loading="loading">
    <div class="page-header">
      <h2>{{ isEdit ? '编辑 Skill' : '新建 Skill' }}</h2>
    </div>

    <!-- 新建模式：步骤 0 - 上传技能包 -->
    <div v-if="!isEdit && step === 0" class="upload-step">
      <el-card shadow="never" class="upload-hero-card">
        <div class="upload-hero">
          <el-icon :size="48" color="#409eff"><UploadFilled /></el-icon>
          <h3>上传 Claude Skills 技能包</h3>
          <p>上传 .zip 格式的技能包，系统将自动解析 SKILL.md 文件并填充表单信息</p>
          <el-upload
            :http-request="handleParsePackage"
            :show-file-list="false"
            :disabled="uploading"
            accept=".zip"
            drag
            class="upload-dragger"
          >
            <div class="dragger-content">
              <el-icon :size="36"><UploadFilled /></el-icon>
              <p v-if="uploading">解析中...</p>
              <p v-else>拖拽 .zip 文件到此处，或<em>点击上传</em></p>
            </div>
          </el-upload>
          <el-divider>或</el-divider>
          <el-button @click="skipUpload">跳过，手动填写信息</el-button>
        </div>
      </el-card>
    </div>

    <!-- 步骤 1 - 编辑表单 -->
    <div v-else>
      <el-alert
        v-if="isEdit && hasDraft"
        type="warning"
        show-icon
        :closable="false"
        class="draft-alert"
      >
        <template #title>
          当前存在未发布的草稿版本（技能包已更新），请到列表页点击「发布」使新版本生效
        </template>
      </el-alert>
      <div class="editor-layout">
      <!-- 左侧：表单 -->
      <el-card shadow="never" class="form-card">
        <template #header><span class="card-title">基本信息</span></template>
        <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
          <el-form-item label="图标">
            <div class="icon-picker">
              <div class="icon-preview" @click="emojiDialogVisible = true">
                <img v-if="iconPreviewSrc" :src="iconPreviewSrc" class="icon-image" alt="图标预览" />
                <span v-else-if="form.icon_emoji" class="icon-emoji">{{ form.icon_emoji }}</span>
                <el-icon v-else :size="24" color="#409eff"><Promotion /></el-icon>
              </div>
              <div class="icon-actions">
                <el-button size="small" @click="emojiDialogVisible = true">选择 Emoji</el-button>
                <el-button size="small" @click="openIconFilePicker">上传图片</el-button>
                <el-button v-if="form.icon_emoji" size="small" link type="info" @click="form.icon_emoji = ''">清除 Emoji</el-button>
                <span v-if="iconPreviewSrc" class="icon-tip">已上传图片，发布后生效</span>
              </div>
            </div>
            <input
              ref="iconFileInputRef"
              type="file"
              accept=".png,.jpg,.jpeg,.svg,image/png,image/jpeg,image/svg+xml"
              style="display: none"
              @change="handleIconFileSelected"
            />
          </el-form-item>
          <el-form-item label="名称" prop="name">
            <el-input v-model="form.name" placeholder="如：PRD 生成" maxlength="100" show-word-limit />
          </el-form-item>
          <el-form-item label="描述" prop="brief_desc">
            <el-input v-model="form.brief_desc" placeholder="卡片展示的描述" maxlength="1000" show-word-limit />
          </el-form-item>
          <el-form-item label="场景标签" prop="tag_ids">
            <el-select v-model="form.tag_ids" multiple placeholder="选择场景标签" style="width: 100%">
              <el-option v-for="t in allTags" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="模型" required>
            <el-select v-model="selectedModelKey" placeholder="选择模型" style="width: 100%" @change="onModelChange">
              <el-option v-for="m in availableModels" :key="`${m.provider_id}::${m.model_name}`" :label="m.display_name" :value="`${m.provider_id}::${m.model_name}`" />
            </el-select>
          </el-form-item>
          <el-form-item label="详细说明" prop="detail_desc">
            <el-input v-model="form.detail_desc" type="textarea" :rows="4" placeholder="详情页展示，支持 Markdown" />
          </el-form-item>
          <el-form-item label="开场白" prop="welcome_message">
            <el-input v-model="form.welcome_message" type="textarea" :rows="3" placeholder="AI 首条消息，引导用户" />
          </el-form-item>
          <el-form-item label="系统 Prompt" prop="system_prompt">
            <el-input v-model="form.system_prompt" type="textarea" :rows="8" placeholder="从 SKILL.md 自动提取，可手动修改" />
            <div v-if="hasPackage" class="field-tip">已从技能包 SKILL.md 自动填充</div>
          </el-form-item>
          <el-form-item label="使用示例">
            <el-input v-model="form.usage_example" type="textarea" :rows="3" placeholder="可选" />
          </el-form-item>
          <el-form-item label="MCP 配置">
            <div style="width:100%">
              <el-radio-group v-model="form.mcp_load_mode">
                <el-radio value="all">加载全部可用 MCP</el-radio>
                <el-radio value="selected">仅加载指定 MCP</el-radio>
              </el-radio-group>
              <div v-if="form.mcp_load_mode === 'selected'" style="margin-top:8px">
                <el-checkbox-group v-model="form.mcp_ids">
                  <el-checkbox v-for="m in availableMcps" :key="m.id" :value="m.id" :label="m.name" />
                </el-checkbox-group>
                <div v-if="availableMcps.length === 0" style="color: var(--text-muted);font-size:12px;margin-top:4px">暂无可用 MCP</div>
              </div>
            </div>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="handleSave">
              {{ isEdit ? '保存' : '创建' }}
            </el-button>
            <el-button @click="router.push('/admin/skills')">取消</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 右侧：技能包 -->
      <div class="package-panel">
        <el-card shadow="never" class="upload-card">
          <template #header><span class="card-title">技能包</span></template>
          <div v-if="hasPackage" class="package-info">
            <el-icon color="#67c23a"><CircleCheckFilled /></el-icon>
            <span>{{ uploadedFileName || '已上传技能包' }}</span>
          </div>
          <el-upload
            :http-request="isEdit ? handleReUploadPackage : handleParsePackage"
            :show-file-list="false"
            :disabled="uploading"
            accept=".zip"
          >
            <el-button size="small" :loading="uploading">
              {{ hasPackage ? '重新上传' : '上传技能包' }}
            </el-button>
          </el-upload>
        </el-card>

        <!-- 文件树 -->
        <el-card v-if="hasPackage" shadow="never" class="tree-card">
          <template #header>
            <div class="tree-card-header">
              <span class="card-title">文件目录</span>
              <el-button v-if="isEdit" link type="primary" size="small" @click="handleDownloadPackage">
                <el-icon><Download /></el-icon> 下载
              </el-button>
            </div>
          </template>
          <div class="file-tree">
            <el-tree
              :data="fileTree"
              :props="{ label: 'name', children: 'children' }"
              node-key="path"
              default-expand-all
              highlight-current
              @node-click="(data: FileNode) => handleFileClick(data)"
            >
              <template #default="{ data }">
                <span class="tree-node">
                  <el-icon v-if="data.type === 'directory'" color="#e6a23c"><Folder /></el-icon>
                  <el-icon v-else color="#409eff"><Document /></el-icon>
                  <span class="tree-node-name">{{ data.name }}</span>
                </span>
              </template>
            </el-tree>
          </div>
        </el-card>

        <!-- 文件预览 -->
        <el-card v-if="previewFile" shadow="never" class="preview-card">
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between">
              <span class="card-title">{{ previewFile.path }}</span>
              <el-button link type="info" @click="previewFile = null"><el-icon><Close /></el-icon></el-button>
            </div>
          </template>
          <div class="preview-content" v-loading="previewLoading">
            <div v-if="previewFile.extension === '.md'" class="md-preview" v-html="renderMarkdown(previewFile.content)" />
            <pre v-else class="code-preview">{{ previewFile.content }}</pre>
          </div>
        </el-card>
      </div>
    </div>
    </div>

    <el-dialog
      v-model="iconCropDialogVisible"
      title="调整图片图标"
      width="520px"
      destroy-on-close
      :close-on-click-modal="false"
    >
      <div class="cropper-wrap">
        <div
          class="crop-area"
          @wheel="handleCropWheel"
        >
          <img
            v-if="cropImageSrc"
            ref="iconCropImageRef"
            :src="cropImageSrc"
            class="crop-image"
            :style="cropImageStyle"
            @load="handleCropImageLoad"
            @mousedown.prevent="handleCropMouseDown"
            draggable="false"
            alt="图标裁剪预览"
          />
        </div>
        <div class="crop-tools">
          <span class="crop-tools-label">缩放</span>
          <el-slider
            :model-value="cropScale"
            :min="cropMinScale"
            :max="cropMaxScale"
            :step="0.01"
            @update:model-value="handleCropScaleChange"
          />
        </div>
        <div class="crop-tip">拖动图片并缩放，系统会按 1:1 输出图标</div>
      </div>
      <template #footer>
        <el-button @click="iconCropDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploadingIcon" @click="saveCroppedIcon">确认上传</el-button>
      </template>
    </el-dialog>

    <!-- Emoji 选择对话框 -->
    <el-dialog v-model="emojiDialogVisible" title="选择图标" width="520px" destroy-on-close>
      <el-input
        v-model="emojiSearch"
        placeholder="搜索 Emoji（可输入图标或 Unicode 码位，如 1f4）"
        clearable
        style="margin-bottom: 12px"
      />
      <el-tabs v-model="emojiActiveTab" class="emoji-tabs">
        <el-tab-pane v-for="cat in emojiCategories" :key="cat.name" :label="cat.name" :name="cat.name">
          <div class="emoji-grid">
            <span
              v-for="e in getFilteredEmojis(cat.emojis)" :key="e"
              class="emoji-item"
              :class="{ selected: form.icon_emoji === e }"
              @click="selectEmoji(e)"
            >{{ e }}</span>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<style scoped>
.skill-editor { width: 100% }
.page-header { margin-bottom: 20px }
.page-header h2 { margin: 0; font-size: 20px; color: var(--text-primary, #303133) }

/* 上传步骤 */
.upload-step { max-width: 640px; margin: 0 auto }
.upload-hero-card { text-align: center }
.upload-hero h3 { margin: 16px 0 8px; font-size: 18px; color: var(--text-primary, #303133) }
.upload-hero > p { color: var(--text-muted, #909399); font-size: 14px; margin-bottom: 24px }
.upload-dragger { width: 100% }
.dragger-content { padding: 24px 0 }
.dragger-content p { margin: 12px 0 0; color: var(--text-muted, #909399); font-size: 14px }
.dragger-content em { color: #409eff; font-style: normal }

/* 草稿提醒 */
.draft-alert { margin-bottom: 16px }

/* 编辑布局 */
.editor-layout { display: flex; gap: 16px; align-items: flex-start }
.form-card { flex: 1; min-width: 0 }
.package-panel { width: 420px; flex-shrink: 0; display: flex; flex-direction: column; gap: 12px }
.card-title { font-weight: 600; font-size: 15px }
.field-tip { font-size: 12px; color: #67c23a; margin-top: 4px }

.icon-picker { display: flex; align-items: center; gap: 14px }
.icon-preview {
  width: 52px; height: 52px; border-radius: 14px; background: var(--bg-hover, #f0f2f5);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; border: 2px dashed var(--border-primary, #dcdfe6); transition: border-color 0.2s;
}
.icon-preview:hover { border-color: #409eff }
.icon-emoji { font-size: 28px; line-height: 1 }
.icon-image { width: 100%; height: 100%; object-fit: cover; border-radius: 12px }
.icon-actions { display: flex; align-items: center; gap: 8px }
.icon-tip { font-size: 12px; color: var(--text-muted, #909399) }
.cropper-wrap { display: flex; flex-direction: column; gap: 12px }
.crop-area {
  width: 240px;
  height: 240px;
  margin: 0 auto;
  position: relative;
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid var(--border-primary, #dcdfe6);
  background: linear-gradient(45deg, #f5f7fa 25%, #ffffff 25%, #ffffff 50%, #f5f7fa 50%, #f5f7fa 75%, #ffffff 75%, #ffffff);
  background-size: 16px 16px;
  cursor: grab;
}
.crop-area:active { cursor: grabbing }
.crop-image {
  position: absolute;
  left: 0;
  top: 0;
  user-select: none;
}
.crop-tools { padding: 0 8px }
.crop-tools-label { display: inline-block; margin-bottom: 4px; color: var(--text-secondary, #606266); font-size: 13px }
.crop-tip { font-size: 12px; color: var(--text-muted, #909399); text-align: center }
.emoji-tabs :deep(.el-tabs__content) { max-height: 360px; overflow-y: auto }
.emoji-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 2px }
.emoji-item {
  font-size: 24px; width: 42px; height: 42px; display: flex; align-items: center;
  justify-content: center; border-radius: 8px; cursor: pointer; transition: all 0.15s;
  border: 2px solid transparent;
}
.emoji-item:hover { background: #ecf5ff; transform: scale(1.15) }
.emoji-item.selected { border-color: #409eff; background: #ecf5ff }

.package-info {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 10px; font-size: 13px; color: var(--text-secondary, #606266);
}

/* 文件树 */
.tree-card-header { display: flex; align-items: center; justify-content: space-between }
.file-tree { max-height: 360px; overflow-y: auto }
.tree-node { display: flex; align-items: center; gap: 6px; font-size: 13px }
.tree-node-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap }

/* 文件预览 */
.preview-card .preview-content { max-height: 500px; overflow-y: auto }
.code-preview {
  margin: 0; padding: 12px; background: var(--bg-code, #fafafa); border-radius: 4px;
  font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-all;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
}
.md-preview { padding: 4px 0; font-size: 14px; line-height: 1.7 }
.md-preview :deep(h1) { font-size: 20px; margin: 16px 0 8px; border-bottom: 1px solid #eee; padding-bottom: 8px }
.md-preview :deep(h2) { font-size: 17px; margin: 14px 0 6px }
.md-preview :deep(h3) { font-size: 15px; margin: 12px 0 4px }
.md-preview :deep(p) { margin: 6px 0 }
.md-preview :deep(ul), .md-preview :deep(ol) { padding-left: 20px; margin: 6px 0 }
.md-preview :deep(code) { background: var(--bg-code, #f5f7fa); padding: 2px 6px; border-radius: 3px; font-size: 13px }
.md-preview :deep(pre) { background: var(--bg-code, #f5f7fa); padding: 12px; border-radius: 6px; overflow-x: auto }
.md-preview :deep(pre code) { background: none; padding: 0 }
.md-preview :deep(blockquote) { border-left: 3px solid #ddd; padding-left: 12px; color: #666; margin: 8px 0 }
.md-preview :deep(table) { border-collapse: collapse; width: 100%; margin: 8px 0 }
.md-preview :deep(th), .md-preview :deep(td) { border: 1px solid #ddd; padding: 6px 10px; text-align: left }
.md-preview :deep(th) { background: var(--bg-code, #f5f7fa) }

@media (max-width: 1200px) {
  .editor-layout { flex-direction: column }
  .package-panel { width: 100% }
}
</style>
