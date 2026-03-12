export interface ToolCallEvent {
  toolCallId: string
  toolName: string
  arguments?: string
}

export interface ToolCallResultEvent {
  toolCallId: string
  success: boolean
  resultPreview?: string
}

export interface ToolCallFilesEvent {
  toolCallId: string
  files: { file_id: number; filename: string; file_size: number }[]
}

export interface ToolCallErrorEvent {
  toolCallId: string
  errorMessage: string
}

export interface ToolCallProgressEvent {
  toolCallId: string
  toolName?: string
  progressTick: number
  elapsedMs: number
  elapsedSeconds: number
}

export interface SSECallbacks {
  onChunk: (content: string) => void
  onDone: (data: { message_id: number; token_usage?: any; tool_calls_count?: number }) => void
  onCancelled?: (data: { message?: string }) => void
  onTitleUpdated: (title: string) => void
  onContextWarning: (message: string) => void
  onError: (message: string) => void
  onToolCallStart?: (data: ToolCallEvent) => void
  onToolCallProgress?: (data: ToolCallProgressEvent) => void
  onToolCallResult?: (data: ToolCallResultEvent) => void
  onToolCallError?: (data: ToolCallErrorEvent) => void
  onToolCallFiles?: (data: ToolCallFilesEvent) => void
  onFallbackTriggered?: (data: { original_model: string; error_type: string; message: string }) => void
  onFallbackSwitched?: (data: { fallback_model: string; message: string }) => void
  onSkillMatched?: (data: { skill_id: number; skill_name: string; model_provider_id?: number; model_name?: string }) => void
  onSkillActivationRequest?: (data: { skill_id: number; skill_name: string; skill_description: string }) => void
  onRouteSelected?: (data: { provider_id: number; model_name: string; reason: string }) => void
  onThinkingDelta?: (content: string) => void
  onThinkingDone?: () => void
  onStreamDisconnected?: () => void
}

function buildHttpErrorMessage(response: Response, responseText?: string): string {
  const status = response.status
  const statusText = response.statusText || '请求失败'
  let backendMsg = ''

  if (responseText) {
    try {
      const parsed = JSON.parse(responseText)
      backendMsg = parsed?.message || parsed?.error || parsed?.data?.message || ''
    } catch {
      backendMsg = ''
    }
  }

  if (backendMsg) return backendMsg
  if (status >= 500) {
    return `服务异常（HTTP ${status}）。可能是模型连接超时，系统会自动重试/降级，请稍后再试。`
  }
  return `${statusText}（HTTP ${status}）`
}

export async function streamSSE(
  url: string,
  body: Record<string, unknown>,
  callbacks: SSECallbacks,
  abortSignal?: AbortSignal,
) {
  const token = localStorage.getItem('access_token')
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body: JSON.stringify(body),
    signal: abortSignal,
  })
  if (!response.ok || !response.body) {
    let responseText = ''
    try {
      responseText = await response.text()
    } catch {
      responseText = ''
    }
    callbacks.onError(buildHttpErrorMessage(response, responseText))
    return
  }
  await _readSSEStream(response, callbacks)
}

export async function editMessageSSE(
  conversationId: number,
  messageId: number,
  content: string,
  fileIds: number[],
  referencedMessageIds: number[],
  callbacks: SSECallbacks,
  abortSignal?: AbortSignal,
) {
  await streamSSE(
    `/api/conversations/${conversationId}/messages/${messageId}/edit`,
    { content, file_ids: fileIds, referenced_message_ids: referencedMessageIds },
    callbacks,
    abortSignal,
  )
}

export async function regenerateMessageSSE(
  conversationId: number,
  messageId: number,
  callbacks: SSECallbacks,
  abortSignal?: AbortSignal,
) {
  await streamSSE(
    `/api/conversations/${conversationId}/messages/${messageId}/regenerate`,
    {},
    callbacks,
    abortSignal,
  )
}

export async function continueFromMessageSSE(
  conversationId: number,
  messageId: number,
  callbacks: SSECallbacks,
  abortSignal?: AbortSignal,
) {
  await streamSSE(
    `/api/conversations/${conversationId}/messages/${messageId}/continue`,
    {},
    callbacks,
    abortSignal,
  )
}

export async function forkConversationSSE(
  conversationId: number,
  fromMessageId: number,
  content: string,
  fileIds: number[],
  callbacks: SSECallbacks,
  abortSignal?: AbortSignal,
) {
  await streamSSE(
    `/api/conversations/${conversationId}/fork`,
    { from_message_id: fromMessageId, content, file_ids: fileIds },
    callbacks,
    abortSignal,
  )
}

export async function sendMessageSSE(
  conversationId: number,
  content: string,
  fileIds: number[],
  callbacks: SSECallbacks,
  abortSignal?: AbortSignal,
  referencedMessageIds?: number[],
  providerId?: number | null,
  modelName?: string | null,
  referenceMode?: string | null,
) {
  const token = localStorage.getItem('access_token')

  const body: any = { content, file_ids: fileIds }
  if (referencedMessageIds && referencedMessageIds.length > 0) {
    body.referenced_message_ids = referencedMessageIds
  } else {
    body.referenced_message_ids = []
  }
  if (providerId) body.provider_id = providerId
  if (modelName) body.model_name = modelName
  if (referenceMode) body.reference_mode = referenceMode

  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal: abortSignal,
  })

  if (!response.ok || !response.body) {
    let responseText = ''
    try {
      responseText = await response.text()
    } catch {
      responseText = ''
    }
    callbacks.onError(buildHttpErrorMessage(response, responseText))
    return
  }

  await _readSSEStream(response, callbacks)
}

async function _readSSEStream(response: Response, callbacks: SSECallbacks) {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let hasTerminalEvent = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let eventType = ''
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        const dataStr = line.slice(6)
        let data
        let parseError = false
        try {
          data = JSON.parse(dataStr)
        } catch {
          parseError = true
        }
        if (parseError) continue

        if (eventType === 'message' || eventType === '') {
          switch (data.type) {
            case 'chunk':
              callbacks.onChunk(data.content)
              break
            case 'done':
              hasTerminalEvent = true
              callbacks.onDone(data)
              break
            case 'cancelled':
              hasTerminalEvent = true
              callbacks.onCancelled?.(data)
              break
            case 'title_updated':
              callbacks.onTitleUpdated(data.title)
              break
            case 'tool_call_start':
              callbacks.onToolCallStart?.({
                toolCallId: data.tool_call_id,
                toolName: data.tool_name,
                arguments: data.arguments,
              })
              break
            case 'tool_call_progress':
              callbacks.onToolCallProgress?.({
                toolCallId: data.tool_call_id,
                toolName: data.tool_name,
                progressTick: Number(data.progress_tick || 0),
                elapsedMs: Number(data.elapsed_ms || 0),
                elapsedSeconds: Number(data.elapsed_seconds || 0),
              })
              break
            case 'tool_call_result':
              callbacks.onToolCallResult?.({
                toolCallId: data.tool_call_id,
                success: data.success,
                resultPreview: data.result_preview,
              })
              break
            case 'tool_call_error':
              callbacks.onToolCallError?.({
                toolCallId: data.tool_call_id,
                errorMessage: data.error_message,
              })
              break
            case 'tool_call_files':
              callbacks.onToolCallFiles?.({
                toolCallId: data.tool_call_id,
                files: data.files,
              })
              break
            case 'skill_matched':
              callbacks.onSkillMatched?.(data)
              break
            case 'skill_activation_request':
              // 等待技能确认属于可预期暂停态，不应在流结束时误判为断流异常。
              hasTerminalEvent = true
              console.log('[SSE] Received skill_activation_request event:', data)
              callbacks.onSkillActivationRequest?.(data)
              break
            case 'skill_activation_pending':
              // 部分路径仅返回 pending 提示，不发 request 事件；同样视为等待确认态。
              hasTerminalEvent = true
              break
            case 'route_selected':
              callbacks.onRouteSelected?.(data)
              break
            case 'thinking_delta':
              callbacks.onThinkingDelta?.(data.content)
              break
            case 'thinking_done':
              callbacks.onThinkingDone?.()
              break
          }
        } else if (eventType === 'context_warning') {
          callbacks.onContextWarning(data.message)
        } else if (eventType === 'fallback_triggered') {
          callbacks.onFallbackTriggered?.(data)
        } else if (eventType === 'fallback_switched') {
          callbacks.onFallbackSwitched?.(data)
        } else if (eventType === 'error') {
          hasTerminalEvent = true
          callbacks.onError(data.message)
        }
      }
    }
  }

  // 连接异常断开时，后端可能没有机会发出 done/error 事件。
  // 显式触发错误回调，避免前端一直卡在“生成中”状态。
  if (!hasTerminalEvent) {
    callbacks.onStreamDisconnected?.()
    callbacks.onError('连接已中断，请重试')
  }
}

export async function streamEventSource(
  url: string,
  callbacks: {
    onEvent: (eventType: string, data: any) => void
    onError: (message: string) => void
  },
  abortSignal?: AbortSignal,
) {
  const token = localStorage.getItem('access_token')
  const response = await fetch(url, {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
    signal: abortSignal,
  })

  if (!response.ok || !response.body) {
    callbacks.onError('请求失败，请重试')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let eventType = ''
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        try {
          callbacks.onEvent(eventType || 'message', JSON.parse(line.slice(6)))
        } catch {
          callbacks.onError('SSE 数据解析失败')
        }
      }
    }
  }
}
