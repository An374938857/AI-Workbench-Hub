import request from './request'
import type { AxiosResponse } from 'axios'

interface ApiResult<T> {
  code: number
  message: string
  data: T
}

export interface AssetFilePreviewSheet {
  name: string
  columns: string[]
  rows: Record<string, unknown>[]
  total_rows: number
  total_columns: number
  truncated_rows: boolean
  truncated_columns: boolean
}

export interface AssetFilePreviewResponse {
  asset_id: number
  filename: string
  file_type: string
  file_size: number
  preview_type: 'image' | 'pdf' | 'html' | 'markdown' | 'text' | 'xlsx_table' | 'download_only'
  content?: string
  truncated?: boolean
  preview_notice?: string
  preview_url?: string
  download_url?: string
  sheets?: AssetFilePreviewSheet[]
  sheet_count?: number
}

interface ResolveUrlTitleResponse {
  title: string
  description: string
  source_url: string
  icon_url: string
  image_url?: string | null
}

export function listAssets(params?: { scope_type?: 'PROJECT' | 'REQUIREMENT'; scope_id?: number; node_code?: string }) {
  return request.get('/v1/assets', { params })
}

export function createAsset(data: {
  scope_type: 'PROJECT' | 'REQUIREMENT'
  scope_id: number
  node_code?: string
  asset_type: 'FILE' | 'MARKDOWN' | 'URL' | 'YUQUE_URL'
  title?: string
  content?: string
  source_url?: string
  file_ref?: string
}) {
  const isUrlLike = data.asset_type === 'URL' || data.asset_type === 'YUQUE_URL'
  return request.post('/v1/assets', data, isUrlLike ? { timeout: 180000 } : undefined)
}

export function refetchAsset(assetId: number) {
  return request.post<never, ApiResult<any>>(`/v1/assets/${assetId}/refetch`)
}

export function getAssetPreview(assetId: number) {
  return request.get<never, ApiResult<AssetFilePreviewResponse>>(`/v1/assets/${assetId}/preview`)
}

export function downloadAssetFile(assetId: number) {
  return request.get<never, AxiosResponse<Blob>>(`/v1/assets/${assetId}/download`, {
    responseType: 'blob',
  })
}

export function deleteAsset(assetId: number) {
  return request.delete<never, ApiResult<{ id: number }>>(`/v1/assets/${assetId}`)
}

export function renameAsset(assetId: number, title: string) {
  return request.put<never, ApiResult<{ id: number; title: string }>>(`/v1/assets/${assetId}/rename`, { title })
}

export function resolveUrlTitle(sourceUrl: string) {
  return request.post<never, ApiResult<ResolveUrlTitleResponse>>('/v1/assets/resolve-url-title', {
    source_url: sourceUrl,
  })
}

export function uploadProjectAssetFile(file: File, projectId: number, nodeCode?: string, title?: string) {
  return uploadAssetFile(file, 'PROJECT', projectId, nodeCode, title)
}

export function uploadAssetFile(
  file: File,
  scopeType: 'PROJECT' | 'REQUIREMENT',
  scopeId: number,
  nodeCode?: string,
  title?: string,
) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('scope_type', scopeType)
  formData.append('scope_id', String(scopeId))
  if (nodeCode) formData.append('node_code', nodeCode)
  if (title) formData.append('title', title)
  return request.post('/v1/assets/upload-file', formData)
}
