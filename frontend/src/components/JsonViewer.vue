<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import hljs from 'highlight.js/lib/core'
import json from 'highlight.js/lib/languages/json'
import 'highlight.js/styles/github.css'

hljs.registerLanguage('json', json)

interface Props {
  title?: string
  raw: string
  filename?: string
}

const props = defineProps<Props>()

const prettyJson = computed(() => {
  try {
    return JSON.stringify(JSON.parse(props.raw), null, 2)
  } catch {
    return props.raw
  }
})

const highlightedJson = computed(() => {
  try {
    return hljs.highlight(prettyJson.value, { language: 'json' }).value
  } catch {
    return prettyJson.value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  }
})

async function copyJson() {
  await navigator.clipboard.writeText(prettyJson.value)
  ElMessage.success('已复制')
}

function downloadJson() {
  const blob = new Blob([prettyJson.value], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = props.filename || 'audit.json'
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <el-card class="json-viewer" shadow="never">
    <template #header>
      <div class="header-row">
        <div class="title">{{ title || 'JSON' }}</div>
        <div class="actions">
          <el-button size="small" @click="copyJson">复制</el-button>
          <el-button size="small" type="primary" plain @click="downloadJson">下载</el-button>
        </div>
      </div>
    </template>

    <pre class="json-pre"><code class="hljs language-json" v-html="highlightedJson" /></pre>
  </el-card>
</template>

<style scoped>
.json-viewer {
  border: 1px solid var(--border-primary, #e5e7eb);
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.title {
  font-weight: 600;
  color: var(--text-primary, #1f2937);
}

.actions {
  display: flex;
  gap: 8px;
}

.json-pre {
  margin: 0;
  max-height: 460px;
  overflow: auto;
  background: #f8fafc;
  color: #0f172a;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  font-size: 12px;
  line-height: 1.55;
}

:global(html.dark) .json-pre {
  background: #0f172a;
  color: #dbeafe;
  border-color: #334155;
}
</style>
