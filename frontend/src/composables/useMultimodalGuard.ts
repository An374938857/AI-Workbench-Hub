import type { Ref } from 'vue'

interface MultimodalGuardContext {
  hasImages: boolean
  autoRouteEnabled: boolean
  providerId: number | null
  modelName: string | null
  modelList: Ref<any[]>
  loadModelList: () => Promise<void>
  showWarning: (message: string) => void
  showConfirm: (payload: {
    title: string
    subject: string
    detail: string
    confirmText: string
    confirmType: 'primary' | 'danger'
  }) => Promise<unknown>
  onUnsupportedConfirmed: () => void
}

export function useMultimodalGuard() {
  async function ensureMultimodalSupport(context: MultimodalGuardContext): Promise<boolean> {
    const {
      hasImages,
      autoRouteEnabled,
      providerId,
      modelName,
      modelList,
      loadModelList,
      showWarning,
      showConfirm,
      onUnsupportedConfirmed,
    } = context

    if (!hasImages) return true

    if (autoRouteEnabled) {
      showWarning('包含图片的对话不支持使用智能路由，请手动选择模型')
      return false
    }

    if (!providerId || !modelName) {
      return true
    }

    if (modelList.value.length === 0) {
      await loadModelList()
    }

    const currentModelInfo = modelList.value.find((model: any) => (
      model.provider_id === providerId && model.model_name === modelName
    ))
    const tags: string[] = currentModelInfo?.capability_tags || []

    if (tags.includes('multimodal')) {
      return true
    }

    await showConfirm({
      title: '模型能力提示',
      subject: currentModelInfo?.display_name || modelName,
      detail: '该模型不支持多模态，图片将被忽略，仅处理文本内容。建议切换到支持多模态的模型。',
      confirmText: '继续发送（忽略图片）',
      confirmType: 'primary',
    })

    onUnsupportedConfirmed()
    return true
  }

  return {
    ensureMultimodalSupport,
  }
}
