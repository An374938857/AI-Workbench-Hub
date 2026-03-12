import { ElMessage } from 'element-plus'

function parseFilenameFromDisposition(disposition: string, format: 'md' | 'docx'): string {
  const defaultName = `export.${format}`
  if (!disposition) return defaultName

  let filename = ''
  const filenameStarMatch = disposition.match(/filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i)
  if (filenameStarMatch?.[1]) {
    const raw = filenameStarMatch[1].trim().replace(/^"(.*)"$/, '$1')
    try {
      filename = decodeURIComponent(raw)
    } catch {
      filename = raw
    }
  }

  if (!filename) {
    const filenameMatch = disposition.match(/filename\s*=\s*([^;]+)/i)
    if (filenameMatch?.[1]) {
      filename = filenameMatch[1].trim().replace(/^"(.*)"$/, '$1')
    }
  }

  if (!filename) return defaultName
  if (!filename.toLowerCase().endsWith(`.${format}`)) {
    return `${filename}.${format}`
  }
  return filename
}

export async function exportConversation(
  conversationId: number,
  format: 'md' | 'docx',
  scope: 'last' | 'all' | 'message',
  messageId?: number,
) {
  const token = localStorage.getItem('access_token')

  const body: Record<string, unknown> = { format, scope }
  if (messageId) body.message_id = messageId

  const resp = await fetch(`/api/conversations/${conversationId}/export`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  })

  if (!resp.ok) {
    const contentType = resp.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      const data = await resp.json()
      ElMessage.error(data.message || '导出失败')
    } else {
      ElMessage.error('导出失败')
    }
    return
  }

  const disposition = resp.headers.get('content-disposition') || ''
  const filename = parseFilenameFromDisposition(disposition, format)

  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)

  ElMessage.success('导出成功')
}
