<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  currentPage: number
  pageSize: number
  total: number
  pageSizes: number[]
  layout?: string
  hideWhenSinglePage?: boolean
}>(), {
  layout: 'total, sizes, prev, pager, next, jumper',
  hideWhenSinglePage: false,
})

const emit = defineEmits<{
  'update:currentPage': [value: number]
  'update:pageSize': [value: number]
  'current-change': [value: number]
  'size-change': [value: number]
}>()

const shouldShow = computed(() => !props.hideWhenSinglePage || props.total > props.pageSize)

function handleCurrentChange(value: number) {
  emit('update:currentPage', value)
  emit('current-change', value)
}

function handleSizeChange(value: number) {
  emit('update:pageSize', value)
  emit('size-change', value)
}
</script>

<template>
  <el-pagination
    v-if="shouldShow"
    :current-page="currentPage"
    :page-size="pageSize"
    :total="total"
    :page-sizes="pageSizes"
    background
    class="elegant-pagination"
    :layout="layout"
    @current-change="handleCurrentChange"
    @size-change="handleSizeChange"
  />
</template>
