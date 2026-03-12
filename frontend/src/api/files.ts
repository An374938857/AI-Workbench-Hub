import request from './request'

export function uploadFile(file: File, conversationId: number) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('conversation_id', String(conversationId))
  return request.post('/files/upload', formData)
}

export function getImageUrl(fileId: number): string {
  return `/api/files/image/${fileId}`
}
