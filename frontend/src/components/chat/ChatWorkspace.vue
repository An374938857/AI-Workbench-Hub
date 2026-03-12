<script setup lang="ts">
defineProps<{
  loading: boolean
  showWorkspace: boolean
}>()
</script>

<template>
  <div class="chat-main" v-loading="loading">
    <template v-if="showWorkspace">
      <slot name="header" />
      <slot name="status" />
      <slot name="messages" />
      <slot name="composer" />
    </template>
    <template v-else>
      <slot name="empty" />
    </template>
  </div>
</template>

<style scoped>
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
}
</style>
