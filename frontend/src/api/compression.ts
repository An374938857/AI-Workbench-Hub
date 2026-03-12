import request from './request'
import type { RequestOptions } from './request'

export interface CompressionResult {
  saved_tokens: number
  summary: string
  original_token_count: number
  compressed_token_count: number
}

export interface CompressionSummary {
  summary: string
  original_token_count: number
  compressed_token_count: number
  saved_tokens: number
  split_message_id: number | null
  created_at: string
}

export function compressConversation(conversationId: number) {
  return request.post<CompressionResult>(`/conversations/${conversationId}/compress`) as unknown as Promise<CompressionResult>
}

export function getCompressionSummary(conversationId: number) {
  const options: RequestOptions = {
    _silent: true,
  }
  return request.get<CompressionSummary>(`/conversations/${conversationId}/compression-summary`, options) as unknown as Promise<CompressionSummary>
}
