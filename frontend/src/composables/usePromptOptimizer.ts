import { nextTick, type Ref } from 'vue'
import { ElMessage } from 'element-plus'

interface UsePromptOptimizerOptions {
  inputText: Ref<string>
  optimizing: Ref<boolean>
  showOptimizedDialog: Ref<boolean>
  optimizedPrompt: Ref<string>
  optimizeAbortController: Ref<AbortController | null>
  optimizedPromptContainerRef: Ref<HTMLElement | null>
  shouldAutoScrollOptimizedPrompt: Ref<boolean>
}

export function usePromptOptimizer(options: UsePromptOptimizerOptions) {
  const {
    inputText,
    optimizing,
    showOptimizedDialog,
    optimizedPrompt,
    optimizeAbortController,
    optimizedPromptContainerRef,
    shouldAutoScrollOptimizedPrompt,
  } = options

  function setOptimizedPromptContainerRef(el: HTMLElement | null) {
    optimizedPromptContainerRef.value = el
  }

  function updateOptimizedPromptAutoScroll() {
    const el = optimizedPromptContainerRef.value
    if (!el) return
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    shouldAutoScrollOptimizedPrompt.value = distanceToBottom <= 24
  }

  function scrollOptimizedPromptToBottom() {
    const el = optimizedPromptContainerRef.value
    if (!el) return
    el.scrollTop = el.scrollHeight
    shouldAutoScrollOptimizedPrompt.value = true
  }

  async function handleOptimizePrompt() {
    const text = inputText.value.trim()
    if (!text) return

    optimizedPrompt.value = ''
    shouldAutoScrollOptimizedPrompt.value = true
    showOptimizedDialog.value = true
    optimizing.value = true
    optimizeAbortController.value = new AbortController()

    try {
      const response = await fetch('/api/prompt/optimize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({ prompt: text }),
        signal: optimizeAbortController.value.signal,
      })

      if (!response.ok) {
        const error = await response.json()
        ElMessage.error(error.detail || '优化失败')
        showOptimizedDialog.value = false
        return
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) return

      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue

          const data = line.slice(6).trim()
          if (data === '[DONE]') continue

          try {
            const json = JSON.parse(data)
            if (json.content) {
              optimizedPrompt.value += json.content
              await nextTick()
              const markdownContainer = optimizedPromptContainerRef.value
              if (markdownContainer && shouldAutoScrollOptimizedPrompt.value) {
                markdownContainer.scrollTop = markdownContainer.scrollHeight
              }
            } else if (json.error) {
              ElMessage.error(json.error)
              showOptimizedDialog.value = false
              return
            }
          } catch {
            // ignore invalid stream line
          }
        }
      }
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        ElMessage.error(error.message || '优化失败')
      }
      showOptimizedDialog.value = false
    } finally {
      optimizing.value = false
      optimizeAbortController.value = null
    }
  }

  function stopOptimizing() {
    optimizeAbortController.value?.abort()
  }

  function applyOptimizedPrompt() {
    inputText.value = optimizedPrompt.value
    showOptimizedDialog.value = false
    ElMessage.success('已应用优化后的提示词')
  }

  return {
    setOptimizedPromptContainerRef,
    updateOptimizedPromptAutoScroll,
    scrollOptimizedPromptToBottom,
    handleOptimizePrompt,
    stopOptimizing,
    applyOptimizedPrompt,
  }
}
