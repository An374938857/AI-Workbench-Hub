<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { DEFAULTS, renderMermaidSVG, THEMES } from 'beautiful-mermaid'
import mermaid from 'mermaid'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import sql from 'highlight.js/lib/languages/sql'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import java from 'highlight.js/lib/languages/java'
import go from 'highlight.js/lib/languages/go'
import markdown from 'highlight.js/lib/languages/markdown'
import yaml from 'highlight.js/lib/languages/yaml'
import 'highlight.js/styles/github.css'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('json', json)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('vue', xml)
hljs.registerLanguage('css', css)
hljs.registerLanguage('java', java)
hljs.registerLanguage('go', go)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)

const props = defineProps<{ content: string }>()
const containerRef = ref<HTMLElement>()

const md = new MarkdownIt({ html: true, linkify: true, breaks: true })

function highlightCode(code: string, lang: string): string {
  if (lang && hljs.getLanguage(lang)) {
    try {
      return hljs.highlight(code, { language: lang }).value
    } catch { /* fallback */ }
  }
  try {
    return hljs.highlightAuto(code).value
  } catch {
    return md.utils.escapeHtml(code)
  }
}

const defaultFence = md.renderer.rules.fence!.bind(md.renderer.rules)
md.renderer.rules.fence = (tokens: any[], idx: number, options: any, env: any, self: any) => {
  const token = tokens[idx]
  const lang = token.info.trim()
  if (lang === 'mermaid') {
    return defaultFence(tokens, idx, options, env, self)
  }
  const rawCode = token.content
  const highlighted = highlightCode(rawCode, lang)
  const langLabel = lang || 'code'
  
  const isHTML = lang === 'html' || lang === 'xml'
  const htmlActions = isHTML 
    ? `<button class="code-preview-btn" data-code-index="${idx}">预览</button>
       <button class="code-open-btn" data-code-index="${idx}">在浏览器中打开</button>`
    : ''
  
  // 保存原始代码到全局数组
  if (isHTML) {
    htmlCodeBlocks[idx] = rawCode
  }
  
  return (
    `<div class="code-block-wrapper" data-lang="${md.utils.escapeHtml(lang)}" data-code-idx="${idx}">` +
      `<div class="code-block-header">` +
        `<span class="code-lang">${md.utils.escapeHtml(langLabel)}</span>` +
        `<div class="code-actions">` +
          htmlActions +
          `<button class="code-copy-btn">复制</button>` +
        `</div>` +
      `</div>` +
      `<pre><code class="hljs language-${md.utils.escapeHtml(lang)}">${highlighted}</code></pre>` +
    `</div>`
  )
}

const MERMAID_PLACEHOLDER = '___MERMAID_BLOCK___'
let mermaidBlocks: string[] = []
let htmlCodeBlocks: Record<number, string> = {}

const rendered = computed(() => {
  mermaidBlocks = []
  htmlCodeBlocks = {}
  const raw = props.content || ''
  const result = raw.replace(/```mermaid\s*\n([\s\S]*?)```/g, (_match, code) => {
    const index = mermaidBlocks.length
    mermaidBlocks.push(code.trim())
    return `${MERMAID_PLACEHOLDER}${index}`
  })
  
  let html = md.render(result)
  mermaidBlocks.forEach((code, i) => {
    const placeholder = `${MERMAID_PLACEHOLDER}${i}`
    const safeCode = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    html = html.replace(
      placeholder,
      `<div class="mermaid-wrapper" data-mermaid-index="${i}">` +
        `<div class="mermaid-toolbar">` +
          `<button class="mermaid-toggle-btn active" data-mode="diagram" data-index="${i}">图表</button>` +
          `<button class="mermaid-toggle-btn" data-mode="source" data-index="${i}">源码</button>` +
        `</div>` +
        `<div class="mermaid-diagram" data-diagram-index="${i}"><div class="mermaid">${code}</div></div>` +
        `<div class="mermaid-source" data-source-index="${i}" style="display:none">` +
          `<div class="source-header"><button class="source-copy-btn" data-copy-index="${i}">复制</button></div>` +
          `<pre><code>${safeCode}</code></pre>` +
        `</div>` +
      `</div>`,
    )
  })
  return html
})

// 记录已渲染的 mermaid 块内容，避免重复渲染
const renderedMermaidHashes = new Map<string, string>() // index -> content
let mermaidTimer: ReturnType<typeof setTimeout> | null = null

function getMermaidFallbackConfig(isDark: boolean) {
  if (isDark) {
    return {
      startOnLoad: false,
      securityLevel: 'loose' as const,
      theme: 'base' as const,
      themeVariables: {
        darkMode: true,
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif',
        background: '#282a36',
        primaryColor: '#44475a',
        primaryTextColor: '#f8f8f2',
        primaryBorderColor: '#6272a4',
        secondaryColor: '#343746',
        tertiaryColor: '#2f3240',
        lineColor: '#bd93f9',
        textColor: '#f8f8f2',
        mainBkg: '#44475a',
        secondBkg: '#343746',
        tertiaryBkg: '#2f3240',
        clusterBkg: '#343746',
        clusterBorder: '#6272a4',
        edgeLabelBackground: 'transparent',
        actorBkg: '#44475a',
        actorBorder: '#6272a4',
        actorTextColor: '#f8f8f2',
        actorLineColor: '#bd93f9',
        signalColor: '#f8f8f2',
        signalTextColor: '#f8f8f2',
        labelBoxBkgColor: '#343746',
        labelBoxBorderColor: '#6272a4',
        labelTextColor: '#f8f8f2',
        noteBkgColor: '#343746',
        noteBorderColor: '#6272a4',
        noteTextColor: '#f8f8f2',
        taskBkgColor: '#44475a',
        taskBorderColor: '#6272a4',
        taskTextColor: '#f8f8f2',
        taskTextDarkColor: '#f8f8f2',
        taskTextOutsideColor: '#e2e2dc',
        sectionBkgColor: '#343746',
        sectionBkgColor2: '#2f3240',
        sectionTextColor: '#f8f8f2',
        sectionTextColor2: '#f8f8f2',
        pie1: '#bd93f9',
        pie2: '#8be9fd',
        pie3: '#50fa7b',
        pie4: '#ffb86c',
        pie5: '#ff79c6',
        pie6: '#f1fa8c',
        pie7: '#6272a4',
      },
      themeCSS: `
        .edgeLabel, .edgeLabel .label, .edgeLabel foreignObject div { background: transparent !important; }
        .edgeLabel rect { fill: transparent !important; stroke: none !important; }
      `,
    }
  }

  return {
    startOnLoad: false,
    securityLevel: 'loose' as const,
    theme: 'base' as const,
    themeVariables: {
      darkMode: false,
      fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif',
      background: '#ffffff',
      primaryColor: '#f5f7fa',
      primaryTextColor: '#303133',
      primaryBorderColor: '#dcdfe6',
      secondaryColor: '#f8f9fb',
      tertiaryColor: '#f0f2f5',
      lineColor: '#409eff',
      textColor: '#303133',
      mainBkg: '#f5f7fa',
      secondBkg: '#f8f9fb',
      tertiaryBkg: '#f0f2f5',
      clusterBkg: '#f8f9fb',
      clusterBorder: '#dcdfe6',
      edgeLabelBackground: 'transparent',
      actorBkg: '#f5f7fa',
      actorBorder: '#dcdfe6',
      actorTextColor: '#303133',
      actorLineColor: '#409eff',
      signalColor: '#303133',
      signalTextColor: '#303133',
      labelBoxBkgColor: '#f8f9fb',
      labelBoxBorderColor: '#dcdfe6',
      labelTextColor: '#303133',
      noteBkgColor: '#f8f9fb',
      noteBorderColor: '#dcdfe6',
      noteTextColor: '#303133',
      taskBkgColor: '#f5f7fa',
      taskBorderColor: '#dcdfe6',
      taskTextColor: '#303133',
      taskTextDarkColor: '#303133',
      taskTextOutsideColor: '#606266',
      sectionBkgColor: '#f8f9fb',
      sectionBkgColor2: '#f0f2f5',
      sectionTextColor: '#303133',
      sectionTextColor2: '#303133',
      pie1: '#409eff',
      pie2: '#67c23a',
      pie3: '#e6a23c',
      pie4: '#f56c6c',
      pie5: '#909399',
      pie6: '#9a60b4',
      pie7: '#73c0de',
    },
    themeCSS: `
      .edgeLabel, .edgeLabel .label, .edgeLabel foreignObject div { background: transparent !important; }
      .edgeLabel rect { fill: transparent !important; stroke: none !important; }
    `,
  }
}

function renderMermaid() {
  // debounce: 流式输出时避免高频触发
  if (mermaidTimer) clearTimeout(mermaidTimer)
  mermaidTimer = setTimeout(() => {
    void doRenderMermaid()
  }, 300)
}

function handleThemeMermaidRerender() {
  renderedMermaidHashes.clear()
  renderMermaid()
}

async function doRenderMermaid() {
  await nextTick()
  if (!containerRef.value) return
  const isDark = document.documentElement.classList.contains('dark')
  const theme = isDark ? THEMES['dracula'] : DEFAULTS

  const nodes = containerRef.value.querySelectorAll('.mermaid') as NodeListOf<HTMLElement>
  const fallbackNodes: HTMLElement[] = []
  const prepareFallbackNode = (node: HTMLElement, code: string) => {
    // Mermaid official renderer may skip nodes marked as already processed.
    node.removeAttribute('data-processed')
    node.textContent = code
    fallbackNodes.push(node)
  }
  nodes.forEach((node) => {
    const idx = node.closest('.mermaid-wrapper')?.getAttribute('data-mermaid-index') || ''
    const code = mermaidBlocks[Number(idx)] || ''
    if (!code) return
    // 内容没变则跳过
    const key = `${idx}:${isDark}`
    if (node.querySelector('svg') && renderedMermaidHashes.get(idx) === key) return
    renderedMermaidHashes.set(idx, key)
    try {
      node.innerHTML = renderMermaidSVG(code, { ...theme, transparent: true })
    } catch {
      // Fall back to official mermaid for unsupported diagram types (e.g. gantt/pie).
      prepareFallbackNode(node, code)
    }
  })

  if (!fallbackNodes.length) return
  mermaid.initialize(getMermaidFallbackConfig(isDark))
  try {
    await mermaid.run({ nodes: fallbackNodes })
  } catch {
    /* ignore parse errors */
  }
}

function handleClick(e: MouseEvent) {
  console.log('Click event:', e.target)
  
  const codeCopyBtn = (e.target as HTMLElement).closest('.code-copy-btn') as HTMLElement | null
  if (codeCopyBtn) {
    const wrapper = codeCopyBtn.closest('.code-block-wrapper')
    const codeEl = wrapper?.querySelector('pre code')
    const code = codeEl?.textContent || ''
    navigator.clipboard.writeText(code).then(() => {
      codeCopyBtn.textContent = '已复制 ✓'
      setTimeout(() => { codeCopyBtn.textContent = '复制' }, 1500)
    })
    return
  }

  const previewBtn = (e.target as HTMLElement).closest('.code-preview-btn') as HTMLElement | null
  console.log('previewBtn:', previewBtn, 'dataset:', previewBtn?.dataset)
  if (previewBtn) {
    const idx = Number(previewBtn.dataset.codeIndex)
    const wrapper = previewBtn.closest('.code-block-wrapper')
    const htmlCode = htmlCodeBlocks[idx] || ''
    
    console.log('Preview clicked, idx:', idx, 'htmlCode length:', htmlCode.length, 'all blocks:', htmlCodeBlocks)
    
    if (!htmlCode) {
      console.error('No HTML code found for index:', idx)
      return
    }
    
    let previewEl = wrapper?.querySelector('.html-preview') as HTMLElement
    const codeEl = wrapper?.querySelector('pre') as HTMLElement
    
    if (previewEl) {
      previewEl.remove()
      if (codeEl) codeEl.style.display = ''
      previewBtn.textContent = '预览'
    } else {
      if (codeEl) codeEl.style.display = 'none'
      
      previewEl = document.createElement('div')
      previewEl.className = 'html-preview'
      previewEl.innerHTML = `
        <div class="preview-header">
          <span>预览</span>
          <button class="preview-close-btn">×</button>
        </div>
        <iframe class="preview-iframe" sandbox="allow-scripts allow-same-origin"></iframe>
      `
      wrapper?.appendChild(previewEl)
      
      const iframe = previewEl.querySelector('iframe') as HTMLIFrameElement
      iframe.srcdoc = htmlCode
      
      const closeBtn = previewEl.querySelector('.preview-close-btn')
      closeBtn?.addEventListener('click', () => {
        previewEl?.remove()
        if (codeEl) codeEl.style.display = ''
        previewBtn.textContent = '预览'
      })
      
      previewBtn.textContent = '关闭预览'
    }
    return
  }

  const openBtn = (e.target as HTMLElement).closest('.code-open-btn') as HTMLElement | null
  if (openBtn) {
    const idx = Number(openBtn.dataset.codeIndex)
    const htmlCode = htmlCodeBlocks[idx] || ''
    
    if (!htmlCode) return
    
    const blob = new Blob([htmlCode], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 100)
    return
  }

  const copyBtn = (e.target as HTMLElement).closest('.source-copy-btn') as HTMLElement | null
  if (copyBtn) {
    const index = Number(copyBtn.dataset.copyIndex)
    const code = mermaidBlocks[index]
    if (code) {
      navigator.clipboard.writeText(code).then(() => {
        copyBtn.textContent = '已复制'
        setTimeout(() => { copyBtn.textContent = '复制' }, 1500)
      })
    }
    return
  }

  const btn = (e.target as HTMLElement).closest('.mermaid-toggle-btn') as HTMLElement | null
  if (!btn) return

  const mode = btn.dataset.mode
  const index = btn.dataset.index
  if (!mode || !index) return

  const wrapper = containerRef.value?.querySelector(`.mermaid-wrapper[data-mermaid-index="${index}"]`)
  if (!wrapper) return

  const diagramEl = wrapper.querySelector(`.mermaid-diagram[data-diagram-index="${index}"]`) as HTMLElement
  const sourceEl = wrapper.querySelector(`.mermaid-source[data-source-index="${index}"]`) as HTMLElement
  const buttons = wrapper.querySelectorAll('.mermaid-toggle-btn')

  buttons.forEach((b) => b.classList.remove('active'))
  btn.classList.add('active')

  if (mode === 'diagram') {
    diagramEl.style.display = ''
    sourceEl.style.display = 'none'
  } else {
    diagramEl.style.display = 'none'
    sourceEl.style.display = ''
  }
}

onMounted(() => {
  renderMermaid()
  window.addEventListener('chat:rerender-mermaid', handleThemeMermaidRerender)
})
onUnmounted(() => {
  window.removeEventListener('chat:rerender-mermaid', handleThemeMermaidRerender)
})
watch(() => props.content, renderMermaid)
</script>

<template>
  <div ref="containerRef" class="md-body" v-html="rendered" @click="handleClick" />
</template>

<style scoped>
.md-body { font-size: 14px; line-height: 1.75; color: var(--text-primary, #303133); word-break: break-word }
.md-body :deep(h1) { font-size: 22px; margin: 20px 0 10px; padding-bottom: 8px; border-bottom: 1px solid var(--border-primary, #ebeef5); color: var(--text-primary) }
.md-body :deep(h2) { font-size: 18px; margin: 18px 0 8px; color: var(--text-primary) }
.md-body :deep(h3) { font-size: 16px; margin: 14px 0 6px; color: var(--text-primary) }
.md-body :deep(h4) { font-size: 15px; margin: 12px 0 4px; color: var(--text-primary) }
.md-body :deep(p) { margin: 8px 0 }
.md-body :deep(ul), .md-body :deep(ol) { padding-left: 24px; margin: 8px 0 }
.md-body :deep(li) { margin: 4px 0 }
.md-body :deep(blockquote) { border-left: 4px solid var(--border-primary, #dcdfe6); padding: 8px 16px; margin: 12px 0; color: var(--text-secondary, #606266); background: var(--bg-code, #f5f7fa) }
.md-body :deep(code) { background: var(--bg-code, #f0f2f5); padding: 2px 6px; border-radius: 3px; font-size: 13px; font-family: 'Menlo', 'Monaco', monospace; color: var(--text-primary) }
.md-body :deep(pre) { background: var(--bg-code, #f5f7fa); padding: 14px; border-radius: 6px; overflow-x: auto; margin: 0 }
.md-body :deep(pre code) { background: none; padding: 0; font-size: 13px; line-height: 1.6; color: var(--text-primary) }

/* Mermaid edge labels - remove background */
.md-body :deep(.edgeLabel) { background: none !important; }
.md-body :deep(.edgeLabel .label) { background: none !important; }
.md-body :deep(.edgeLabel foreignObject div) { background: none !important; }
.md-body :deep([class*="edgeLabel"] rect),
.md-body :deep(.edgeLabel rect),
.md-body :deep(g.edgeLabel rect) { fill: none !important; stroke: none !important; }

.md-body :deep(.code-block-wrapper) {
  margin: 12px 0;
  border: 1px solid var(--border-primary, #ebeef5);
  border-radius: 8px;
  overflow: hidden;
}

.md-body :deep(.code-block-wrapper pre) {
  margin: 0;
  border-radius: 0;
  border: none;
}

.md-body :deep(.code-block-header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  background: var(--bg-code, #f5f7fa);
  border-bottom: 1px solid var(--border-primary, #ebeef5);
}

.md-body :deep(.code-actions) {
  display: flex;
  gap: 6px;
}

.md-body :deep(.code-lang) {
  font-size: 11px;
  color: var(--text-muted, #909399);
  font-family: 'Menlo', 'Monaco', monospace;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.md-body :deep(.code-copy-btn),
.md-body :deep(.code-preview-btn),
.md-body :deep(.code-open-btn) {
  padding: 2px 10px;
  font-size: 12px;
  border: 1px solid var(--border-primary, #dcdfe6);
  border-radius: 4px;
  background: var(--bg-card, #fff);
  color: var(--text-secondary, #606266);
  cursor: pointer;
  transition: all 0.2s;
}

.md-body :deep(.code-copy-btn:hover),
.md-body :deep(.code-preview-btn:hover),
.md-body :deep(.code-open-btn:hover) {
  color: #409eff;
  border-color: #409eff;
}

.md-body :deep(.html-preview) {
  border-top: 1px solid var(--border-primary, #ebeef5);
  background: var(--bg-card, #fff);
}

.md-body :deep(.preview-header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: var(--bg-code, #f5f7fa);
  border-bottom: 1px solid var(--border-primary, #ebeef5);
  font-size: 12px;
  color: var(--text-muted, #909399);
}

.md-body :deep(.preview-close-btn) {
  border: none;
  background: none;
  font-size: 20px;
  color: var(--text-muted, #909399);
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.md-body :deep(.preview-close-btn:hover) {
  background: var(--border-primary, #ebeef5);
  color: var(--text-primary, #303133);
}

.md-body :deep(.preview-iframe) {
  width: 100%;
  height: 600px;
  border: none;
  display: block;
  background: white;
}
.md-body :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0 }
.md-body :deep(th), .md-body :deep(td) { border: 1px solid var(--border-primary, #dcdfe6); padding: 8px 12px; text-align: left; color: var(--text-primary) }
.md-body :deep(th) { background: var(--bg-code, #f5f7fa); font-weight: 600 }
.md-body :deep(a) { color: #409eff; text-decoration: none }
.md-body :deep(a:hover) { text-decoration: underline }
.md-body :deep(img) { max-width: 100% }
.md-body :deep(hr) { border: none; border-top: 1px solid var(--border-primary, #ebeef5); margin: 16px 0 }
.md-body :deep(strong) { color: var(--text-primary) }

.md-body :deep(.mermaid-wrapper) {
  margin: 12px 0;
  border: 1px solid var(--border-primary, #ebeef5);
  border-radius: 8px;
  overflow: hidden;
}

.md-body :deep(.mermaid-toolbar) {
  display: flex;
  gap: 0;
  background: var(--bg-code, #f5f7fa);
  border-bottom: 1px solid var(--border-primary, #ebeef5);
  padding: 0 4px;
}

.md-body :deep(.mermaid-toggle-btn) {
  padding: 6px 14px;
  font-size: 12px;
  border: none;
  background: transparent;
  color: var(--text-muted, #909399);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.md-body :deep(.mermaid-toggle-btn:hover) {
  color: #409eff;
}

.md-body :deep(.mermaid-toggle-btn.active) {
  color: #409eff;
  border-bottom-color: #409eff;
}

.md-body :deep(.mermaid-diagram) {
  padding: 16px;
  text-align: center;
  overflow-x: auto;
}

.md-body :deep(.mermaid-source) {
  margin: 0;
}

.md-body :deep(.mermaid-source pre) {
  margin: 0;
  border-radius: 0;
}

.md-body :deep(.source-header) {
  display: flex;
  justify-content: flex-end;
  padding: 4px 8px;
  background: var(--bg-code, #f5f7fa);
}

.md-body :deep(.source-copy-btn) {
  padding: 2px 10px;
  font-size: 12px;
  border: 1px solid var(--border-primary, #dcdfe6);
  border-radius: 4px;
  background: var(--bg-card, #fff);
  color: var(--text-secondary, #606266);
  cursor: pointer;
  transition: all 0.2s;
}

.md-body :deep(.source-copy-btn:hover) {
  color: #409eff;
  border-color: #409eff;
}
</style>
