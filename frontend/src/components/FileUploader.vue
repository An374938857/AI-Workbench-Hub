<script setup lang="ts">
import { ref } from 'vue'
import { uploadFile as uploadFileApi } from '@/api/files'
import { ElMessage } from 'element-plus'
import UnifiedFilePreviewDialog from '@/components/common/UnifiedFilePreviewDialog.vue'
import { useFilePreview } from '@/composables/useFilePreview'

interface UploadedItem {
  file_id: number
  original_name: string
  file_type: string
  file_size: number
  is_image: boolean
  thumbnail_url?: string
}

const IMAGE_TYPES = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg']
const MAX_FILES = 10
const ACCEPT_TYPES = '.txt,.md,.docx,.xlsx,.csv,.pdf,.jpg,.jpeg,.png,.gif,.webp,.bmp,.svg'

const props = defineProps<{ conversationId: number | null; disabled?: boolean }>()
const emit = defineEmits<{ change: [fileIds: number[]] }>()

const files = ref<UploadedItem[]>([])
const uploading = ref(false)
const uploadRef = ref()
const filePreview = useFilePreview()

async function openPreview(file: UploadedItem) {
  if (!props.conversationId) {
    ElMessage.warning('请先创建对话后再预览文件')
    return
  }
  await filePreview.openPreview({
    label: file.original_name,
    fileType: file.file_type,
    fileSize: file.file_size,
    source: 'sandbox',
    conversationId: props.conversationId,
    fileId: file.file_id,
  })
}

async function handleUpload(options: any) {
  await uploadFile(options.file)
  return false
}

async function uploadFile(file: File) {
  if (!props.conversationId) {
    ElMessage.warning('请先创建对话后再上传文件')
    return
  }
  if (files.value.length >= MAX_FILES) {
    ElMessage.warning(`单次消息最多上传 ${MAX_FILES} 个文件`)
    return
  }
  uploading.value = true
  try {
    const res: any = await uploadFileApi(file, props.conversationId)
    const item: UploadedItem = {
      file_id: res.data.file_id,
      original_name: res.data.original_name,
      file_type: res.data.file_type,
      file_size: res.data.file_size,
      is_image: res.data.is_image ?? IMAGE_TYPES.includes(res.data.file_type),
    }
    if (item.is_image) {
      item.thumbnail_url = `/api/files/image/${res.data.file_id}`
    }
    files.value.push(item)
    emit('change', files.value.map((f) => f.file_id))
    ElMessage.success(`${res.data.original_name} 上传成功`)
  } catch (e: any) {
    ElMessage.error(e?.message || '文件上传失败')
  } finally {
    uploading.value = false
  }
}

function removeFile(index: number) {
  files.value.splice(index, 1)
  emit('change', files.value.map((f) => f.file_id))
}

function clear() {
  files.value = []
  filePreview.close()
  emit('change', [])
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

function getFiles(): UploadedItem[] {
  return [...files.value]
}

function setFiles(items: Array<Partial<UploadedItem> & Pick<UploadedItem, 'file_id' | 'original_name' | 'file_type' | 'file_size'>>) {
  files.value = items.map((item) => {
    const isImage = item.is_image ?? IMAGE_TYPES.includes(String(item.file_type || '').toLowerCase())
    return {
      file_id: item.file_id,
      original_name: item.original_name,
      file_type: item.file_type,
      file_size: item.file_size,
      is_image: isImage,
      thumbnail_url: isImage ? `/api/files/image/${item.file_id}` : undefined,
    }
  })
  emit('change', files.value.map((f) => f.file_id))
}

function triggerUpload() {
  uploadRef.value?.$el?.querySelector('input[type="file"]')?.click()
}

defineExpose({ clear, getFiles, setFiles, triggerUpload, uploadFile })
</script>

<template>
  <div class="file-uploader">
    <div v-if="files.length > 0" class="file-list">
      <div
        v-for="(f, i) in files"
        :key="f.file_id"
        class="file-item"
        :class="{ 'is-disabled': disabled }"
        role="button"
        :tabindex="disabled ? -1 : 0"
        :title="`预览 ${f.original_name}`"
        @click="!disabled && openPreview(f)"
        @keydown.enter.prevent="!disabled && openPreview(f)"
        @keydown.space.prevent="!disabled && openPreview(f)"
      >
        <template v-if="f.is_image">
          <img :src="f.thumbnail_url" :alt="f.original_name" class="file-thumbnail" />
        </template>
        <template v-else>
          <el-icon color="#409eff" :size="14"><Document /></el-icon>
          <span class="file-name">{{ f.original_name }}</span>
          <span class="file-size">{{ formatSize(f.file_size) }}</span>
        </template>
        <el-button link type="danger" size="small" @click.stop="removeFile(i)" :disabled="disabled" class="file-remove">
          <el-icon :size="12"><Close /></el-icon>
        </el-button>
      </div>
    </div>
    <el-upload
      ref="uploadRef"
      :http-request="handleUpload"
      :show-file-list="false"
      :disabled="disabled || uploading"
      :accept="ACCEPT_TYPES"
      multiple
      class="file-upload-hidden"
    >
      <span></span>
    </el-upload>
    <UnifiedFilePreviewDialog
      v-model="filePreview.visible.value"
      :loading="filePreview.loading.value"
      :title="filePreview.title.value"
      :file-type="filePreview.fileType.value"
      :file-size="filePreview.fileSize.value"
      :mode="filePreview.mode.value"
      :can-edit="filePreview.canEdit.value"
      :saving="filePreview.saving.value"
      :can-download="filePreview.canDownload.value"
      :content="filePreview.content.value"
      :preview-notice="filePreview.previewNotice.value"
      :preview-url="filePreview.previewUrl.value"
      :sheets="filePreview.sheets.value"
      :active-sheet-name="filePreview.activeSheetName.value"
      @update:active-sheet-name="(name) => (filePreview.activeSheetName.value = name)"
      @open-external="filePreview.openCurrentInNewWindow"
      @download="filePreview.downloadCurrent"
      @save-edit="filePreview.saveMarkdownEdit"
    />
  </div>
</template>

<style scoped>
.file-uploader { position: relative; }

.file-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
  align-items: center;
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
  height: 48px;
  box-sizing: border-box;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  outline: none;
  cursor: pointer;
}

.file-item.is-disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.file-item:focus-visible {
  border-color: rgba(64, 158, 255, 0.5);
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.15);
}

.file-thumbnail {
  height: 40px;
  width: 56px;
  object-fit: cover;
  border-radius: 8px;
  cursor: pointer;
  flex-shrink: 0;
}
.file-thumbnail:hover { opacity: 0.8; }

.file-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  color: var(--text-muted, #c0c4cc);
  font-size: 11px;
  flex-shrink: 0;
}

.file-remove { flex-shrink: 0; }

.file-upload-hidden {
  position: absolute;
  width: 0; height: 0;
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
}
</style>
