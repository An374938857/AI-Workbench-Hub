import { computed, type Ref } from 'vue'
import { getTemplates } from '@/api/promptTemplates'

function flattenModels(response: any): any[] {
  const allModels: any[] = []
  const providers = response?.providers || response?.data?.providers || []
  providers.forEach((provider: any) => {
    provider?.models?.forEach((model: any) => {
      allModels.push({
        provider_id: provider.provider_id,
        provider_name: provider.provider_name,
        model_name: model.model_name,
        display_name: model.display_name || model.model_name,
        ...model,
      })
    })
  })
  return allModels
}

function sortTemplates(templates: any[]) {
  return [...templates].sort((a: any, b: any) => {
    if (a.is_favorited && !b.is_favorited) return -1
    if (!a.is_favorited && b.is_favorited) return 1
    const aDefault = a.is_global_default || a.is_default
    const bDefault = b.is_global_default || b.is_default
    if (aDefault && !bDefault) return -1
    if (!aDefault && bDefault) return 1
    return (b.priority || 0) - (a.priority || 0)
  })
}

interface UseComposerCatalogsOptions {
  modelList: Ref<any[]>
  skillList: Ref<any[]>
  mcpList: Ref<any[]>
  templateList: Ref<any[]>
  currentTemplateId: Ref<number | null>
  loadingTemplate: Ref<boolean>
  shouldApplyTemplateDefault: () => boolean
}

export function useComposerCatalogs(options: UseComposerCatalogsOptions) {
  const {
    modelList,
    skillList,
    mcpList,
    templateList,
    currentTemplateId,
    loadingTemplate,
    shouldApplyTemplateDefault,
  } = options

  async function loadModelList() {
    const { getAvailableModels } = await import('@/api/models')
    const response: any = await getAvailableModels()
    modelList.value = flattenModels(response)
  }

  async function loadSkillList() {
    const { getSkillList } = await import('@/api/skills')
    const response: any = await getSkillList()
    skillList.value = response?.data?.items || response?.items || []
  }

  async function loadMcpList() {
    const { getMcpPublicList } = await import('@/api/mcps')
    const response: any = await getMcpPublicList()
    mcpList.value = Array.isArray(response?.data) ? response.data : (response?.data?.items || response?.items || [])
  }

  async function loadTemplateList() {
    if (templateList.value.length > 0) return
    loadingTemplate.value = true
    try {
      const response: any = await getTemplates({ page: 1, page_size: 100 })
      const templates = response?.templates || response?.data?.templates || []
      templateList.value = sortTemplates(templates)

      if (currentTemplateId.value == null && shouldApplyTemplateDefault()) {
        const globalDefault = templateList.value.find((template: any) => template.is_global_default || template.is_default)
        if (globalDefault) {
          currentTemplateId.value = globalDefault.id
        }
      }
    } finally {
      loadingTemplate.value = false
    }
  }

  const visibleTemplateList = computed(() => templateList.value.filter((template: any) => template.name !== '自由对话'))

  return {
    loadModelList,
    loadSkillList,
    loadMcpList,
    loadTemplateList,
    visibleTemplateList,
  }
}
