<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SkillManage from '@/views/admin/SkillManage.vue'
import SceneTagManage from '@/views/admin/SceneTagManage.vue'

type SkillTabKey = 'skills' | 'scene-tags'

const route = useRoute()
const router = useRouter()

const activeTab = computed<SkillTabKey>({
  get() {
    const tab = route.query.tab
    return tab === 'scene-tags' ? 'scene-tags' : 'skills'
  },
  set(value) {
    const query = { ...route.query }
    if (value === 'skills') {
      delete query.tab
    } else {
      query.tab = value
    }
    router.replace({ path: '/admin/skills', query })
  },
})
</script>

<template>
  <div class="skill-manage-tabs">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="Skill 管理" name="skills">
        <SkillManage />
      </el-tab-pane>
      <el-tab-pane label="场景标签" name="scene-tags">
        <SceneTagManage />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.skill-manage-tabs {
  width: 100%;
}
</style>
