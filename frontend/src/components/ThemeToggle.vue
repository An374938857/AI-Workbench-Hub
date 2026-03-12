<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from '@/composables/useTheme'

const { theme, setTheme } = useTheme()

const isDark = computed({
  get: () => {
    if (theme.value === 'system') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches
    }
    return theme.value === 'dark'
  },
  set: (val: boolean) => {
    setTheme(val ? 'dark' : 'light')
  },
})
</script>

<template>
  <label class="theme-toggle" :title="isDark ? '切换到亮色模式' : '切换到深色模式'">
    <input type="checkbox" v-model="isDark" aria-label="切换主题" />
    <span class="toggle-track">
      <span class="toggle-thumb" />
    </span>
  </label>
</template>

<style scoped>
.theme-toggle {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  flex-shrink: 0;
}

.theme-toggle input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
  pointer-events: none;
}

.toggle-track {
  position: relative;
  width: 44px;
  height: 24px;
  border-radius: 12px;
  background: #dcdfe6;
  transition: background 0.3s;
}

.theme-toggle input:checked + .toggle-track {
  background: #409eff;
}

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  justify-content: center;
}

.toggle-thumb::after {
  content: '☀️';
  font-size: 12px;
  line-height: 1;
}

.theme-toggle input:checked + .toggle-track .toggle-thumb {
  transform: translateX(20px);
}

.theme-toggle input:checked + .toggle-track .toggle-thumb::after {
  content: '🌙';
}
</style>
