import { ref } from 'vue'

const ALLOWED_EXTENSIONS = new Set(['txt', 'md', 'docx', 'xlsx', 'csv', 'pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'])

interface ConversationFileInputOptions {
  ensureConversation: () => Promise<number | null>
  uploadFile: (file: File) => Promise<void>
  onUnsupportedFile?: (filename: string) => void
}

export function useConversationFileInput(options: ConversationFileInputOptions) {
  const isDragging = ref(false)
  const dragCounter = ref(0)

  function handleDragEnter() {
    dragCounter.value += 1
    isDragging.value = true
  }

  function handleDragLeave() {
    dragCounter.value -= 1
    if (dragCounter.value <= 0) {
      isDragging.value = false
      dragCounter.value = 0
    }
  }

  async function handleDrop(event: DragEvent) {
    isDragging.value = false
    dragCounter.value = 0

    const files = event.dataTransfer?.files
    if (!files?.length) return

    const conversationId = await options.ensureConversation()
    if (!conversationId) return

    for (const file of Array.from(files)) {
      const ext = file.name.split('.').pop()?.toLowerCase() || ''
      if (!ALLOWED_EXTENSIONS.has(ext)) {
        options.onUnsupportedFile?.(file.name)
        continue
      }
      await options.uploadFile(file)
    }
  }

  async function handlePaste(event: ClipboardEvent) {
    const items = event.clipboardData?.items
    if (!items) return

    for (const item of Array.from(items)) {
      if (!item.type.startsWith('image/')) continue

      event.preventDefault()
      const blob = item.getAsFile()
      if (!blob) continue

      const now = new Date()
      const ts = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`
      const file = new File([blob], `clipboard_${ts}.png`, { type: 'image/png' })

      const conversationId = await options.ensureConversation()
      if (!conversationId) return

      await options.uploadFile(file)
      return
    }
  }

  return {
    isDragging,
    dragCounter,
    handleDragEnter,
    handleDragLeave,
    handleDrop,
    handlePaste,
  }
}
