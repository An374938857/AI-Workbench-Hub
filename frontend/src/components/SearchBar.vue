<template>
  <div class="search-bar">
    <!-- 搜索触发按钮 -->
    <button class="search-trigger" @click="openDialog" title="搜索对话 (⌘F)">
      <el-icon :size="16"><Search /></el-icon>
    </button>

    <!-- 搜索弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :show-close="true"
      width="800px"
      class="search-dialog"
      append-to-body
      align-center
      :destroy-on-close="false"
      @close="handleClose"
      @opened="searchInputRef?.focus()"
    >
      <!-- 搜索输入框 -->
      <div class="search-header">
        <div class="search-title">搜索对话</div>
        <div class="search-input-wrapper">
          <el-input
            ref="searchInputRef"
            v-model="searchQuery"
            placeholder="输入关键词搜索对话（可选）"
            :prefix-icon="Search"
            clearable
            size="large"
            @keyup.enter="handleSearch"
          >
            <template #append>
              <el-button :icon="Search" :loading="loading" @click="handleSearch">
                搜索
              </el-button>
            </template>
          </el-input>
        </div>
      </div>

      <!-- 筛选器 - 始终显示 -->
      <div class="filters">
        <el-select
          v-model="filters.skill_id"
          placeholder="选择技能"
          clearable
          style="width: 180px"
        >
          <el-option
            v-for="skill in skillList"
            :key="skill.id"
            :label="skill.name"
            :value="skill.id"
          />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          style="width: 280px"
          @change="handleDateChange"
        />
      </div>

      <!-- 搜索结果列表 -->
      <div v-loading="loading" class="results-list">
        <div v-if="!hasSearched" class="empty">
          <el-empty description="输入关键词开始搜索" />
        </div>
        <div v-else-if="searchResults.length === 0" class="empty">
          <el-empty description="未找到相关对话" />
        </div>
        <div
          v-for="result in searchResults"
          :key="result.conversation_id"
          class="result-item"
          @click="goToConversation(result.conversation_id)"
        >
          <div class="result-title">
            <span class="result-title-text" v-html="getDisplayTitle(result)"></span>
            <span class="result-time">{{ formatTime(result.updated_at || '') }}</span>
          </div>
          <div class="result-meta">
            <div
              v-if="result.active_skills && result.active_skills.length > 0"
              class="result-skill-tags"
            >
              <span
                v-for="skill in result.active_skills"
                :key="`${result.conversation_id}-${skill.id}`"
                class="result-skill-tag"
              >
                {{ skill.name }}
              </span>
            </div>
            <span v-else class="result-free-tag">自由对话</span>
          </div>
          <div
            v-if="result.highlights['messages.content']"
            class="result-content"
            v-html="getHighlight(result, 'messages.content')"
          ></div>
          <div v-if="result.tags && result.tags.length > 0" class="result-tags">
            <TagBadge
              v-for="tag in result.tags"
              :key="tag.id"
              :name="tag.name"
              :color="tag.color"
            />
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        style="margin-top: 16px; justify-content: center"
        @current-change="handlePageChange"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import { searchConversations, getSearchHistory, saveSearchHistory, type SearchResult } from '@/api/search'
import { getSkillList } from '@/api/skills'
import { ElMessage } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import TagBadge from './TagBadge.vue'

const router = useRouter()
const chatStore = useChatStore()

const dialogVisible = ref(false)
const searchQuery = ref('')
const loading = ref(false)
const hasSearched = ref(false)
const searchHistory = ref<string[]>([])
const searchResults = ref<SearchResult[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const skillList = ref<Array<{ id: number; name: string }>>([])

const filters = ref({
  skill_id: null as number | null,
  date_start: '',
  date_end: ''
})

const dateRange = ref<[string, string] | null>(null)

const searchInputRef = ref()

const openDialog = async () => {
  dialogVisible.value = true
  hasSearched.value = false
  searchResults.value = []
  total.value = 0
  
  // 加载技能列表
  if (skillList.value.length === 0) {
    try {
      const res: any = await getSkillList({ page: 1, page_size: 100 })
      skillList.value = res.data.items.map((s: any) => ({ id: s.id, name: s.name }))
    } catch (error) {
      console.error('加载技能列表失败:', error)
    }
  }
}

const handleClose = () => {
  searchQuery.value = ''
  searchResults.value = []
  hasSearched.value = false
  currentPage.value = 1
  filters.value = {
    skill_id: null,
    date_start: '',
    date_end: ''
  }
  dateRange.value = null
}

const handleSearch = async () => {
  // 至少需要关键词或筛选条件之一
  if (!searchQuery.value.trim() && !filters.value.skill_id && !filters.value.date_start) {
    ElMessage.warning('请输入关键词或选择筛选条件')
    return
  }

  loading.value = true
  hasSearched.value = true

  try {
    const params: any = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    
    // 关键词可选
    if (searchQuery.value.trim()) {
      params.q = searchQuery.value
    }
    
    // 添加筛选条件
    if (filters.value.skill_id) {
      params.skill_id = filters.value.skill_id
    }
    if (filters.value.date_start) {
      params.date_start = filters.value.date_start
    }
    if (filters.value.date_end) {
      params.date_end = filters.value.date_end
    }

    const response = await searchConversations(params)
    searchResults.value = response.data.results
    total.value = response.data.total
    
    if (searchQuery.value.trim()) {
      saveSearchHistory(searchQuery.value)
      searchHistory.value = getSearchHistory()
    }
  } catch (error: any) {
    console.error('搜索失败:', error)
    ElMessage.error(error.response?.data?.message || '搜索失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

const selectHistory = (query: string) => {
  searchQuery.value = query
  handleSearch()
}

const handleDateChange = (value: [string, string] | null) => {
  if (value) {
    filters.value.date_start = value[0]
    filters.value.date_end = value[1]
  } else {
    filters.value.date_start = ''
    filters.value.date_end = ''
  }
  if (hasSearched.value) {
    handleSearch()
  }
}

const handlePageChange = () => {
  handleSearch()
}

const getHighlight = (result: SearchResult, field: string) => {
  if (field === 'title') {
    return result.highlights.title?.[0] || result.title
  } else if (field === 'messages.content') {
    return result.highlights['messages.content']?.join(' ... ') || ''
  }
  return ''
}

const getDisplayTitle = (result: SearchResult) => {
  const title = (getHighlight(result, 'title') || '').trim()
  return title || '无标题'
}

const goToConversation = async (conversationId: number) => {
  dialogVisible.value = false
  chatStore.triggerHighlight(conversationId)
  await router.push(`/chat/${conversationId}`)
}

const formatTime = (dateStr: string) => {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 7) return `${days}天前`
  if (days < 30) return `${Math.floor(days / 7)}周前`
  if (days < 365) return `${Math.floor(days / 30)}个月前`
  return date.toLocaleDateString()
}

onMounted(() => {
  searchHistory.value = getSearchHistory()
})

// 暴露方法供父组件调用
defineExpose({
  open: openDialog
})
</script>

<style>
.search-dialog.el-dialog {
  border-radius: 24px !important;
  overflow: hidden;
}

.search-dialog .el-dialog__header {
  padding: 0;
  margin: 0;
  height: 0;
  border: none;
}

.search-dialog .el-dialog__headerbtn {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 32px;
  height: 32px;
  z-index: 10;
}

.search-dialog .el-dialog__headerbtn .el-dialog__close {
  color: var(--text-muted, #94a3b8);
  transition: color 0.2s;
  font-size: 16px;
}

.search-dialog .el-dialog__headerbtn:hover .el-dialog__close {
  color: var(--text-primary, #0f172a);
}

.search-dialog .el-dialog__body {
  padding: 24px !important;
  background: var(--bg-primary, #ffffff);
}

html.dark .search-dialog .el-dialog__body {
  background: var(--bg-primary, #1a1a1a);
}
</style>

<style scoped>
.search-bar {
  display: inline-block;
}

.search-trigger {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  color: var(--text-secondary, #64748b);
}

.search-trigger:hover {
  background: rgba(0, 0, 0, 0.04);
  border-color: rgba(0, 0, 0, 0.12);
  color: var(--text-primary, #0f172a);
  transform: translateY(-1px);
}

.search-trigger:active {
  transform: translateY(0);
}

html.dark .search-trigger {
  border-color: rgba(255, 255, 255, 0.08);
  color: var(--text-secondary, #94a3b8);
}

html.dark .search-trigger:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
  color: var(--text-primary, #f1f5f9);
}

.search-header {
  margin-bottom: 20px;
}

.search-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #0f172a);
  margin-bottom: 16px;
}

.search-input-wrapper {
  margin-bottom: 0;
}

:deep(.search-input-wrapper .el-input__wrapper) {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.06);
  transition: all 0.2s;
}

:deep(.search-input-wrapper .el-input__wrapper:hover) {
  border-color: rgba(59, 130, 246, 0.3);
}

:deep(.search-input-wrapper .el-input__wrapper.is-focus) {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

html.dark :deep(.search-input-wrapper .el-input__wrapper) {
  border-color: rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.search-history {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

.history-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.history-tag {
  margin-right: 8px;
  margin-bottom: 8px;
  cursor: pointer;
}

.history-tag:hover {
  opacity: 0.8;
}

.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.results-list {
  min-height: 300px;
  max-height: 500px;
  overflow-y: auto;
  padding: 4px;
}

.empty {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}

.result-item {
  padding: 16px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  background: var(--bg-card, #ffffff);
}

html.dark .result-item {
  background: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.08);
}

.result-item:hover {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(59, 130, 246, 0.04) 100%);
  border-color: rgba(59, 130, 246, 0.3);
  transform: translateX(2px);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.08);
}

.result-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.result-title-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #0f172a);
  margin-right: 10px;
}

.result-meta {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  min-height: 18px;
}

.result-skill-tags {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  overflow-x: auto;
  scrollbar-width: none;
}

.result-skill-tags::-webkit-scrollbar {
  display: none;
}

.result-time {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
}

.result-skill-tag {
  display: inline-flex;
  align-items: center;
  padding: 0 6px;
  height: 18px;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 500;
  color: #8b7bc6;
  background: rgba(139, 123, 198, 0.1);
  white-space: nowrap;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-free-tag {
  display: inline-flex;
  align-items: center;
  padding: 0 6px;
  height: 18px;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 500;
  color: #6ba3d6;
  background: rgba(107, 163, 214, 0.1);
  white-space: nowrap;
}

.result-content {
  color: var(--text-secondary, #64748b);
  font-size: 14px;
  line-height: 1.6;
  margin-bottom: 8px;
}

.result-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.result-content :deep(em) {
  background: rgba(245, 158, 11, 0.18);
  color: #b45309;
  font-style: normal;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.result-title :deep(em) {
  background: rgba(245, 158, 11, 0.18);
  color: #b45309;
  font-style: normal;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}
</style>
