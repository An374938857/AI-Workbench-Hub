import request from './request'
import type { AxiosResponse } from 'axios'

export interface RelatedSandboxFile {
  file_id: number
  original_name: string
  file_type: string
  file_size: number
  sandbox_path?: string
  created_at?: string
  preview_url: string
  download_url: string
}

export interface RelatedSandboxConversation {
  conversation_id: number
  conversation_title?: string
  binding_type: string
  scope_type?: 'PROJECT' | 'REQUIREMENT'
  scope_id?: number
  scope_title?: string
  sandbox_files: RelatedSandboxFile[]
}

export interface RelatedSandboxNode {
  instance_id: number
  node_id: number
  node_code: string
  node_name: string
  node_order: number
  status: string
  instance_scope_type?: 'PROJECT' | 'REQUIREMENT'
  instance_scope_id?: number
  instance_scope_title?: string
  conversations: RelatedSandboxConversation[]
}

export interface RelatedSandboxView {
  scope_type: 'PROJECT' | 'REQUIREMENT'
  scope_id: number
  scope_name?: string
  assets: Array<{
    id: number
    scope_type: 'PROJECT' | 'REQUIREMENT'
    scope_id: number
    scope_title?: string
    node_code?: string
    asset_type: string
    title?: string
    source_url?: string
    file_ref?: string
    file_type?: string
    file_size?: number
    refetch_status: string
    created_at?: string
  }>
  nodes: RelatedSandboxNode[]
  summary: {
    asset_count: number
    node_count: number
    conversation_count: number
    sandbox_file_count: number
    requirement_count?: number
  }
}

export function getProjectSandboxView(projectId: number) {
  return request.get(`/v1/sandbox-views/project/${projectId}`)
}

export function getRequirementSandboxView(requirementId: number) {
  return request.get(`/v1/sandbox-views/requirement/${requirementId}`)
}

export function downloadProjectSandboxArchive(projectId: number) {
  return request.get<never, AxiosResponse<Blob>>(
    `/v1/sandbox-views/project/${projectId}/archive/download`,
    {
      responseType: 'blob',
    },
  )
}

export function downloadRequirementSandboxArchive(requirementId: number) {
  return request.get<never, AxiosResponse<Blob>>(
    `/v1/sandbox-views/requirement/${requirementId}/archive/download`,
    {
      responseType: 'blob',
    },
  )
}
