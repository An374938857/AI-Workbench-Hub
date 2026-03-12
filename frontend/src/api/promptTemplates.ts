/**
 * Prompt 模板 API
 * 提示词模板 CRUD、收藏、设置默认
 */
import request from "./request";

export interface PromptTemplate {
  id: number;
  name: string;
  category: string;
  content: string;
  is_default: boolean;
  priority: number;
  is_builtin: boolean;
  visibility: string;
  is_global_default: boolean;
  created_by: number | null;
  created_at: string;
  updated_at: string;
  is_favorited: boolean;
}

export interface PromptTemplateStats {
  conversation_count: number;
  favorite_count: number;
  last_used_at: string | null;
  version_count: number;
}

export interface PromptTemplateVersion {
  id: number;
  template_id: number;
  version_no: number;
  name: string;
  category: string;
  content: string;
  priority: number;
  visibility: string;
  note: string | null;
  created_by: number | null;
  created_at: string;
}

export interface TemplateListResponse {
  templates: PromptTemplate[];
  total: number;
  page: number;
  page_size: number;
}

/**
 * 获取模板列表
 */
export function getTemplates(params?: {
  page?: number;
  page_size?: number;
  category?: string;
  search?: string;
}) {
  return request.get<any, any>("/prompt-templates", { params });
}

/**
 * 获取模板详情
 */
export function getTemplate(id: number) {
  return request.get<any, any>(`/prompt-templates/${id}`);
}

/**
 * 创建模板
 */
export function createTemplate(data: {
  name: string;
  category: string;
  content: string;
  priority?: number;
  visibility?: string;
}) {
  return request.post<any, any>("/prompt-templates", data);
}

/**
 * 更新模板
 */
export function updateTemplate(id: number, data: {
  name?: string;
  category?: string;
  content?: string;
  priority?: number;
  visibility?: string;
  is_default?: boolean;
}) {
  return request.put<any, any>(`/prompt-templates/${id}`, data);
}

/**
 * 删除模板
 */
export function deleteTemplate(id: number) {
  return request.delete<any, any>(`/prompt-templates/${id}`);
}

/**
 * 设置全局默认
 */
export function setGlobalDefault(id: number) {
  return request.post<any, any>(`/prompt-templates/${id}/set-default`);
}

/**
 * 收藏/取消收藏
 */
export function toggleFavorite(id: number) {
  return request.post<any, any>(`/prompt-templates/${id}/favorite`);
}

/**
 * 复制模板
 */
export function duplicateTemplate(id: number, name?: string) {
  return request.post<any, any>(`/prompt-templates/${id}/duplicate`, { name });
}

/**
 * 获取模板统计信息
 */
export function getTemplateStats(id: number) {
  return request.get<any, any>(`/prompt-templates/${id}/stats`);
}

/**
 * 获取模板版本列表
 */
export function getTemplateVersions(id: number) {
  return request.get<any, any>(`/prompt-templates/${id}/versions`);
}

/**
 * 保存模板版本
 */
export function createTemplateVersion(id: number, note?: string) {
  return request.post<any, any>(`/prompt-templates/${id}/versions`, { note });
}

/**
 * 恢复模板到指定版本
 */
export function restoreTemplateVersion(id: number, versionId: number) {
  return request.post<any, any>(`/prompt-templates/${id}/restore/${versionId}`);
}
