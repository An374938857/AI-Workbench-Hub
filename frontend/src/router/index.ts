import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    children: [
      {
        path: '',
        name: 'Home',
        component: () => import('@/views/Home.vue'),
      },
      {
        path: 'prompt-templates',
        name: 'PromptTemplates',
        component: () => import('@/views/PromptTemplates.vue'),
        meta: { scrollableMain: true },
      },
      {
        path: 'prompt-templates/new',
        name: 'PromptTemplateNew',
        component: () => import('@/views/PromptTemplateDetail.vue'),
      },
      {
        path: 'prompt-templates/:id',
        name: 'PromptTemplateDetail',
        component: () => import('@/views/PromptTemplateDetail.vue'),
      },
      {
        path: 'sandbox-files/:conversationId',
        name: 'SandboxFiles',
        redirect: to => ({
          name: 'Chat',
          params: { id: to.params.conversationId },
          query: {
            ...to.query,
            panel: 'sandbox',
          },
        }),
      },
      {
        path: 'skills',
        name: 'SkillSquare',
        component: () => import('@/views/SkillSquare.vue'),
        meta: { scrollableMain: true },
      },
      {
        path: 'skills/:id',
        name: 'SkillDetail',
        component: () => import('@/views/SkillDetail.vue'),
      },
      {
        path: 'mcps',
        name: 'McpSquare',
        component: () => import('@/views/McpSquare.vue'),
        meta: { scrollableMain: true },
      },
      {
        path: 'mcps/:id',
        name: 'McpDetail',
        component: () => import('@/views/McpDetail.vue'),
      },
      {
        path: 'chat/:id?',
        name: 'Chat',
        component: () => import('@/views/Chat.vue'),
      },
      {
        path: 'projects',
        name: 'ProjectList',
        component: () => import('@/views/project/ProjectList.vue'),
        meta: { scrollableMain: true },
      },
      {
        path: 'requirements',
        name: 'RequirementPool',
        component: () => import('@/views/requirement/RequirementPool.vue'),
        meta: { scrollableMain: true },
      },
      {
        path: 'admin/dashboard',
        name: 'AdminDashboard',
        component: () => import('@/views/admin/DashboardTest.vue'),
        meta: { roles: ['admin'], scrollableMain: true, fullBleedMain: true },
      },
    ],
  },
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { roles: ['provider', 'admin'] },
    children: [
      {
        path: 'skills',
        name: 'AdminSkillManage',
        component: () => import('@/views/admin/SkillManageTabs.vue'),
      },
      {
        path: 'skills/new',
        name: 'AdminSkillNew',
        component: () => import('@/views/admin/SkillEditor.vue'),
      },
      {
        path: 'skills/:id/edit',
        name: 'AdminSkillEdit',
        component: () => import('@/views/admin/SkillEditor.vue'),
      },
      {
        path: 'users',
        name: 'AdminUserManage',
        component: () => import('@/views/admin/UserManage.vue'),
        meta: { roles: ['admin'] },
      },
      {
        path: 'model-providers',
        name: 'AdminModelProvider',
        component: () => import('@/views/admin/ModelManageTabs.vue'),
        meta: { roles: ['admin'] },
      },
      {
        path: 'mcps',
        name: 'AdminMcpManage',
        component: () => import('@/views/admin/McpManage.vue'),
        meta: { roles: ['admin'] },
      },
      {
        path: 'embedding',
        name: 'AdminEmbeddingManage',
        component: () => import('@/views/admin/EmbeddingManage.vue'),
        meta: { roles: ['admin'] },
      },
      {
        path: 'scene-tags',
        name: 'AdminSceneTag',
        redirect: {
          path: '/admin/skills',
          query: { tab: 'scene-tags' },
        },
        meta: { roles: ['admin'] },
      },
      {
        path: 'routing-rules',
        name: 'AdminRoutingRules',
        redirect: {
          path: '/admin/model-providers',
          query: { tab: 'routing-rules' },
        },
        meta: { roles: ['admin'] },
      },
      {
        path: 'workflows',
        name: 'AdminWorkflowDefinitions',
        component: () => import('@/views/workflow/WorkflowDefinitionList.vue'),
      },
      {
        path: 'workflows/:definitionId',
        name: 'AdminWorkflowDefinitionEditor',
        component: () => import('@/views/workflow/WorkflowDefinitionEditor.vue'),
      },
      {
        path: 'audit/dashboard',
        name: 'AdminAuditDashboard',
        redirect: {
          path: '/admin/audit/conversations',
          query: { tab: 'monitor' },
        },
        meta: { roles: ['admin'] },
      },
      {
        path: 'audit/conversations',
        name: 'AdminAuditConversations',
        component: () => import('@/views/admin/AuditManageTabs.vue'),
        meta: { roles: ['admin'] },
      },
      {
        path: 'audit/conversations/:id',
        name: 'AdminAuditConversationDetail',
        component: () => import('@/views/admin/AuditConversationDetail.vue'),
        meta: { roles: ['admin'] },
      },
      {
        path: 'audit/conversations/:id/round/:roundNo',
        name: 'AdminAuditRoundDetail',
        component: () => import('@/views/admin/AuditRoundJsonDetail.vue'),
        meta: { roles: ['admin'] },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  if (to.meta.public) {
    next()
    return
  }

  if (!authStore.isLoggedIn) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }

  if (!authStore.user) {
    await authStore.fetchUser()
  }

  const requiredRoles = to.matched
    .map((record) => record.meta.roles as string[] | undefined)
    .filter(Boolean)
    .pop()

  if (requiredRoles && authStore.user && !requiredRoles.includes(authStore.user.role)) {
    next({ name: 'SkillSquare' })
    return
  }

  next()
})

export default router
