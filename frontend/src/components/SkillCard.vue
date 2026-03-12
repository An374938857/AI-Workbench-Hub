<script setup lang="ts">
defineProps<{
  skill: {
    id: number
    name: string
    icon_url: string | null
    icon_emoji: string | null
    brief_desc: string
    tags: { id: number; name: string }[]
    use_count: number
    creator_name: string | null
  }
}>()

defineEmits<{ click: [id: number] }>()
</script>

<template>
  <div class="skill-card" @click="$emit('click', skill.id)">
    <div class="card-icon">
      <img v-if="skill.icon_url" :src="skill.icon_url" :alt="`${skill.name} 图标`" />
      <span v-else-if="skill.icon_emoji" class="card-emoji">{{ skill.icon_emoji }}</span>
      <el-icon v-else :size="32" color="#409eff"><Promotion /></el-icon>
    </div>
    <div class="card-body">
      <h3 class="card-title">{{ skill.name }}</h3>
      <p class="card-desc">{{ skill.brief_desc }}</p>
      <div class="card-meta">
        <div class="card-tags">
          <el-tag v-for="t in skill.tags" :key="t.id" size="small" type="info">{{ t.name }}</el-tag>
        </div>
        <span class="card-usage">{{ skill.use_count }} 次使用</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skill-card {
  background: var(--bg-card, #fff);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 16px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.25s;
  display: flex;
  gap: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 2px 8px rgba(0, 0, 0, 0.02);
  margin-bottom: 2px; /* 预留 hover 空间 */
}

.skill-card:hover {
  border-color: #409eff;
  box-shadow: 0 4px 20px rgba(64, 158, 255, 0.14), 0 1px 3px rgba(0, 0, 0, 0.04);
  transform: translateY(-2px);
  margin-bottom: 0; /* 补偿 transform 偏移 */
}

.card-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: linear-gradient(135deg, #e0f2fe, #f0f4ff);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

html.dark .card-icon {
  background: linear-gradient(135deg, rgba(59,130,246,0.15), rgba(99,102,241,0.12));
}

.card-icon img {
  width: 32px;
  height: 32px;
  object-fit: contain;
}

.card-emoji {
  font-size: 28px;
  line-height: 1;
}

.card-body {
  flex: 1;
  min-width: 0;
}

.card-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}

.card-desc {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--text-muted, #909399);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.card-usage {
  font-size: 12px;
  color: #c0c4cc;
  white-space: nowrap;
}
</style>
