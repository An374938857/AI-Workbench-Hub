<template>
  <el-dropdown-menu>
    <el-dropdown-item v-if="canPreview" command="preview">
      <el-icon><View /></el-icon>
      <span>预览</span>
    </el-dropdown-item>
    <el-dropdown-item v-if="canDownload" command="download">
      <el-icon><Download /></el-icon>
      <span>下载</span>
    </el-dropdown-item>
    <el-dropdown-item v-if="canRename" command="rename">
      <el-icon><Edit /></el-icon>
      <span>重命名</span>
    </el-dropdown-item>
    <el-dropdown-item v-if="canEdit" command="edit">
      <el-icon><Edit /></el-icon>
      <span>编辑</span>
    </el-dropdown-item>
    <el-dropdown-item v-if="canRefetch" command="refetch">
      <el-icon><RefreshRight /></el-icon>
      <span>重抓</span>
    </el-dropdown-item>
    <el-dropdown-item v-if="canDelete" command="delete" class="danger-item">
      <el-icon><Delete /></el-icon>
      <span>{{ deleteLabel }}</span>
    </el-dropdown-item>
  </el-dropdown-menu>
</template>

<script setup lang="ts">
import { Delete, Download, Edit, RefreshRight, View } from '@element-plus/icons-vue'

withDefaults(
  defineProps<{
    canPreview?: boolean
    canDownload?: boolean
    canRename?: boolean
    canEdit?: boolean
    canRefetch?: boolean
    canDelete?: boolean
    deleteLabel?: string
  }>(),
  {
    canPreview: false,
    canDownload: false,
    canRename: false,
    canEdit: false,
    canRefetch: false,
    canDelete: false,
    deleteLabel: '删除',
  },
)
</script>
