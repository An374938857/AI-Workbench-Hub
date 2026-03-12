export type FilePreviewType =
  | 'image'
  | 'pdf'
  | 'xlsx_table'
  | 'html'
  | 'markdown'
  | 'text'
  | 'download_only'

export type FilePreviewSource = 'asset' | 'sandbox'

export interface FilePreviewSheet {
  name: string
  columns: string[]
  rows: Record<string, unknown>[]
  total_rows: number
  total_columns: number
  truncated_rows: boolean
  truncated_columns: boolean
}

export interface FilePreviewPayload {
  preview_type: FilePreviewType
  can_edit?: boolean
  file_type?: string
  file_size?: number
  filename?: string
  content?: string
  preview_notice?: string
  preview_url?: string
  download_url?: string
  truncated?: boolean
  sheets?: FilePreviewSheet[]
  sheet_count?: number
}

export interface FilePreviewTarget {
  label: string
  fileType?: string
  fileSize?: number
  source: FilePreviewSource
  assetId?: number
  conversationId?: number
  fileId?: number
  assetType?: string
}
