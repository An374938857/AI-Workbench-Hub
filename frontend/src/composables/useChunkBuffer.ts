/**
 * SSE chunk 缓冲器 — 将高频 chunk 合并为低频批量更新，减少 Vue 响应式触发频率。
 */
export class ChunkBuffer {
  private buffer = ''
  private timer: ReturnType<typeof setTimeout> | null = null
  private onFlush: (content: string) => void
  private flushInterval: number

  constructor(onFlush: (content: string) => void, flushInterval = 50) {
    this.onFlush = onFlush
    this.flushInterval = flushInterval
  }

  append(chunk: string) {
    this.buffer += chunk
    if (!this.timer) {
      this.timer = setTimeout(() => this.flush(), this.flushInterval)
    }
  }

  flush() {
    if (this.buffer) {
      this.onFlush(this.buffer)
      this.buffer = ''
    }
    if (this.timer) {
      clearTimeout(this.timer)
      this.timer = null
    }
  }

  destroy() {
    this.flush()
  }
}
