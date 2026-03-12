import request from './request'
import type { RequestOptions } from './request'

export function createConversation(skillId?: number | null, isTest = false) {
  return request.post('/conversations', { skill_id: skillId || null, is_test: isTest })
}

export function getConversationList(
  params?: { page?: number; page_size?: number; tag_id?: number },
  options?: RequestOptions,
) {
  return request.get('/conversations', { ...options, params })
}

export function getConversationDetail(
  id: number,
  params?: { admin_view?: boolean },
  options?: RequestOptions,
) {
  return request.get(`/conversations/${id}`, { ...options, params })
}

export function getConversationLiveState(
  id: number,
  params?: { admin_view?: boolean },
  options?: RequestOptions,
) {
  return request.get(`/conversations/${id}/live-state`, { ...options, params })
}

export function markConversationSidebarSignalRead(id: number) {
  return request.post(`/conversations/${id}/sidebar-signal/read`)
}

export function deleteConversation(id: number) {
  return request.delete(`/conversations/${id}`)
}

export function cancelConversationGeneration(id: number) {
  return request.post(`/conversations/${id}/cancel`)
}

export interface ConversationCancelMeta {
  reason?: string
  source?: string
}

export function cancelConversationGenerationWithMeta(id: number, meta?: ConversationCancelMeta) {
  return request.post(`/conversations/${id}/cancel`, meta ?? {})
}

export function updateConversationTitle(id: number, title: string) {
  return request.patch(`/conversations/${id}/title`, { title })
}

export function regenerateConversationTitle(id: number) {
  return request.post(`/conversations/${id}/regenerate-title`)
}

export function exportConversation(id: number, format: 'md' | 'docx', scope: 'last' | 'all') {
  return request.post(`/conversations/${id}/export`, { format, scope }, { responseType: 'blob' })
}

export function submitFeedback(id: number, rating: number, comment?: string) {
  return request.post(`/conversations/${id}/feedback`, { rating, comment })
}

export function getFeedback(id: number) {
  return request.get(`/conversations/${id}/feedback`)
}

// 分支管理
export function getMessageBranches(convId: number, msgId: number) {
  return request.get(`/conversations/${convId}/messages/${msgId}/branches`)
}

export function switchBranch(convId: number, messageId: number, branchIndex: number, parentId?: number) {
  return request.post(`/conversations/${convId}/switch-branch`, {
    message_id: messageId,
    branch_index: branchIndex,
    parent_id: parentId,
  })
}

// 批量操作
export function batchDeleteConversations(ids: number[]) {
  const chunkSize = 100
  if (ids.length <= chunkSize) {
    return request.post('/conversations/batch-delete', { ids })
  }
  return (async () => {
    let deletedCount = 0
    for (let i = 0; i < ids.length; i += chunkSize) {
      const chunk = ids.slice(i, i + chunkSize)
      const res: any = await request.post('/conversations/batch-delete', { ids: chunk })
      deletedCount += Number(res?.data?.deleted_count || 0)
    }
    return {
      code: 0,
      message: 'ok',
      data: {
        deleted_count: deletedCount,
      },
    }
  })()
}

export function batchExportConversations(ids: number[], format: 'md' | 'docx') {
  return request.post('/conversations/batch-export', { ids, format }, { responseType: 'blob' })
}

export function batchTagConversations(ids: number[], tagId: number) {
  const chunkSize = 100
  if (ids.length <= chunkSize) {
    return request.post('/conversations/batch-tag', { ids, tag_id: tagId })
  }
  return (async () => {
    for (let i = 0; i < ids.length; i += chunkSize) {
      const chunk = ids.slice(i, i + chunkSize)
      await request.post('/conversations/batch-tag', { ids: chunk, tag_id: tagId })
    }
    return {
      code: 0,
      message: 'ok',
      data: {},
    }
  })()
}

// 对话标签关联
export function addConversationTag(convId: number, tagId: number) {
  return request.post(`/conversations/${convId}/tags`, { tag_id: tagId })
}

export function removeConversationTag(convId: number, tagId: number) {
  return request.delete(`/conversations/${convId}/tags/${tagId}`)
}

export function switchConversationModel(convId: number, providerId: number, modelName: string) {
  return request.post(`/conversations/${convId}/switch-model`, {
    provider_id: providerId,
    model_name: modelName,
  })
}

export function activateConversationSkill(conversationId: number, skillId: number) {
  return request.post(`/conversations/${conversationId}/skills`, null, {
    params: {
      skill_id: skillId,
    },
  })
}

export function compareModels(
  convId: number,
  content: string,
  modelAProviderId: number,
  modelAName: string,
  modelBProviderId: number,
  modelBName: string
) {
  return request.post(`/conversations/${convId}/messages/compare`, {
    content,
    model_a_provider_id: modelAProviderId,
    model_a_name: modelAName,
    model_b_provider_id: modelBProviderId,
    model_b_name: modelBName,
  })
}

export function chooseComparisonWinner(convId: number, comparisonId: number, winner: 'a' | 'b') {
  return request.post(`/conversations/${convId}/compare/${comparisonId}/choose?winner=${winner}`)
}

// Prompt 模板管理
export function switchPromptTemplate(conversationId: number, templateId: number) {
  return request.post(`/conversations/${conversationId}/prompt-template`, { template_id: templateId })
}

export function getPromptTemplate(conversationId: number) {
  return request.get(`/conversations/${conversationId}/prompt-template`)
}
