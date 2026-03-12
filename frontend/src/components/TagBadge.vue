<script setup lang="ts">
defineProps<{
  name: string
  color: string
  closable?: boolean
}>()

const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <span class="tag-badge" :style="{ '--tag-color': color }">
    <span class="tag-dot" />
    <span class="tag-name">{{ name }}</span>
    <button v-if="closable" class="tag-close" @click.stop="emit('close')">×</button>
  </span>
</template>

<style scoped>
.tag-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 8px;
  height: 20px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--tag-color) 58%, #94a3b8 42%);
  font-size: 11px;
  font-weight: 500;
  background: transparent;
  color: color-mix(in srgb, var(--tag-color) 68%, #334155 32%);
  line-height: 20px;
  white-space: nowrap;
  max-width: 100%;
}

.tag-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--tag-color);
  flex-shrink: 0;
}

.tag-name {
  max-width: 78px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag-close {
  border: none;
  background: none;
  color: var(--tag-color);
  cursor: pointer;
  font-size: 13px;
  padding: 0;
  line-height: 1;
  opacity: 0.6;
}

.tag-close:hover {
  opacity: 1;
}
</style>
