/**
 * 沙箱文件管理 API
 * 对话沙箱文件操作
 */
import type { AxiosResponse } from "axios";
import request from "./request";

interface ApiResult<T> {
  code: number;
  message: string;
  data: T;
}

export interface SandboxFile {
  file_id: number;
  original_name: string;
  file_type: string;
  file_size: number;
  sandbox_path?: string | null;
  source: string;
  created_at: string;
}

export interface SandboxFileListResponse {
  files: SandboxFile[];
  total: number;
  sandbox_size_mb: number;
  sandbox_size_limit_mb: number;
}

export interface SandboxCleanupResponse {
  success: boolean;
  message: string;
  freed_size: number;
}

export interface SandboxDeleteDirectoryResponse {
  message: string;
  deleted_count: number;
  path: string;
}

export interface SandboxMarkReadResponse {
  conversation_id: number;
  unread_before: number;
  unread_after: number;
}

export interface SandboxSheetPreview {
  name: string;
  columns: string[];
  rows: Record<string, unknown>[];
  total_rows: number;
  total_columns: number;
  truncated_rows: boolean;
  truncated_columns: boolean;
}

export interface SandboxFilePreviewResponse {
  file_id: number;
  filename: string;
  file_type: string;
  file_size: number;
  preview_type: "image" | "pdf" | "html" | "markdown" | "text" | "xlsx_table" | "download_only";
  can_edit?: boolean;
  content?: string;
  truncated?: boolean;
  preview_notice?: string;
  preview_url?: string;
  download_url?: string;
  sheets?: SandboxSheetPreview[];
  sheet_count?: number;
}

/**
 * 获取沙箱文件列表
 */
export function getSandboxFiles(conversationId: number) {
  return request.get<never, ApiResult<SandboxFileListResponse>>(
    `/conversations/${conversationId}/sandbox/files`,
  );
}

/**
 * 获取沙箱文件详情
 */
export function getSandboxFile(conversationId: number, fileId: number) {
  return request.get<never, ApiResult<SandboxFilePreviewResponse>>(
    `/conversations/${conversationId}/sandbox/files/${fileId}`,
  );
}

/**
 * 删除沙箱文件
 */
export function deleteSandboxFile(conversationId: number, fileId: number) {
  return request.delete<never, ApiResult<{ message: string }>>(
    `/conversations/${conversationId}/sandbox/files/${fileId}`,
  );
}

export function renameSandboxFile(conversationId: number, fileId: number, newName: string) {
  return request.put<never, ApiResult<{ file_id: number; original_name: string; sandbox_path?: string | null }>>(
    `/conversations/${conversationId}/sandbox/files/${fileId}/rename`,
    { new_name: newName },
  );
}

export function updateSandboxFileContent(conversationId: number, fileId: number, content: string) {
  return request.put<
    never,
    ApiResult<{ file_id: number; file_size: number; file_type: string; content: string }>
  >(`/conversations/${conversationId}/sandbox/files/${fileId}/content`, { content });
}

/**
 * 删除沙箱目录
 */
export function deleteSandboxDirectory(conversationId: number, path: string) {
  return request.delete<never, ApiResult<SandboxDeleteDirectoryResponse>>(
    `/conversations/${conversationId}/sandbox/directories`,
    { params: { path } },
  );
}

/**
 * 清理沙箱
 */
export function cleanupSandbox(conversationId: number) {
  return request.post<never, ApiResult<SandboxCleanupResponse>>(
    `/conversations/${conversationId}/sandbox/cleanup`,
  );
}

/**
 * 清空沙箱文件变更未读计数
 */
export function markSandboxChangesRead(conversationId: number) {
  return request.post<never, ApiResult<SandboxMarkReadResponse>>(
    `/conversations/${conversationId}/sandbox/changes/read`,
  );
}

/**
 * 下载沙箱文件
 */
export function downloadSandboxFile(conversationId: number, fileId: number) {
  return request.get<never, AxiosResponse<Blob>>(
    `/conversations/${conversationId}/sandbox/files/${fileId}/download`,
    {
      responseType: "blob",
    },
  );
}

/**
 * 下载对话沙箱压缩包
 */
export function downloadSandboxArchive(conversationId: number) {
  return request.get<never, AxiosResponse<Blob>>(
    `/conversations/${conversationId}/sandbox/archive/download`,
    {
      responseType: "blob",
    },
  );
}
