<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { changePasswordOnLogin, register } from '@/api/auth'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const form = ref({ username: '', password: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  await formRef.value?.validate()
  loading.value = true
  try {
    await authStore.login(form.value.username, form.value.password)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } finally {
    loading.value = false
  }
}

const pwdDialogVisible = ref(false)
const pwdFormRef = ref<FormInstance>()
const pwdLoading = ref(false)
const pwdForm = reactive({
  username: '',
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const pwdRules: FormRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  oldPassword: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string, callback: any) => {
        if (value !== pwdForm.newPassword) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

function openPwdDialog() {
  pwdForm.username = form.value.username
  pwdForm.oldPassword = ''
  pwdForm.newPassword = ''
  pwdForm.confirmPassword = ''
  pwdDialogVisible.value = true
}

async function handleChangePassword() {
  await pwdFormRef.value?.validate()
  pwdLoading.value = true
  try {
    await changePasswordOnLogin(pwdForm.username, pwdForm.oldPassword, pwdForm.newPassword)
    ElMessage.success('密码修改成功，请使用新密码登录')
    pwdDialogVisible.value = false
  } finally {
    pwdLoading.value = false
  }
}

const regDialogVisible = ref(false)
const regFormRef = ref<FormInstance>()
const regLoading = ref(false)
const regForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  display_name: '',
  role: 'user',
})

const regRules: FormRules = {
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    { min: 2, max: 50, message: '长度 2-50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 50, message: '长度 6-50 个字符', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string, callback: any) => {
        if (value !== regForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
  display_name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

function openRegDialog() {
  regForm.username = ''
  regForm.password = ''
  regForm.confirmPassword = ''
  regForm.display_name = ''
  regForm.role = 'user'
  regDialogVisible.value = true
}

async function handleRegister() {
  await regFormRef.value?.validate()
  regLoading.value = true
  try {
    const res: any = await register({
      username: regForm.username,
      password: regForm.password,
      display_name: regForm.display_name,
      role: regForm.role,
    })
    ElMessage.success(res.message || '注册成功')
    regDialogVisible.value = false
  } finally {
    regLoading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <!-- 背景波浪装饰 -->
    <svg class="bg-waves" viewBox="0 0 1440 900" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M0 300 Q360 150 720 350 T1440 250 V900 H0Z" fill="rgba(255,255,255,0.045)"/>
      <path d="M0 450 Q300 300 700 500 T1440 380 V900 H0Z" fill="rgba(255,255,255,0.035)"/>
      <path d="M0 600 Q400 480 800 620 T1440 520 V900 H0Z" fill="rgba(255,255,255,0.025)"/>
      <circle cx="1250" cy="150" r="200" fill="rgba(255,255,255,0.04)"/>
      <circle cx="150" cy="750" r="160" fill="rgba(255,255,255,0.03)"/>
    </svg>
    <div class="login-container">
      <!-- 左侧品牌区 -->
      <div class="login-brand">
        <div class="brand-content">
          <div class="brand-icon">
            <svg viewBox="0 0 48 48" fill="none" width="52" height="52">
              <rect width="48" height="48" rx="12" fill="#4a7dff"/>
              <path d="M14 34V14l20 10-20 10z" fill="#fff"/>
              <circle cx="34" cy="14" r="4" fill="rgba(255,255,255,0.6)"/>
            </svg>
          </div>
          <h1>Welcome</h1>
          <p class="brand-name">AI 能力共享平台</p>
          <div class="brand-features">
            <div class="feature-item">
              <span class="feature-icon">🤖</span>
              <span>AI 技能共享，全员一键使用</span>
            </div>
            <div class="feature-item">
              <span class="feature-icon">💬</span>
              <span>自然语言对话完成专业工作</span>
            </div>
            <div class="feature-item">
              <span class="feature-icon">📄</span>
              <span>PRD、会议纪要、周报一键生成</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧登录区 -->
      <div class="login-panel">
        <div class="login-header">
          <h2>登录</h2>
          <p>登录你的账号以继续</p>
        </div>
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-width="0"
          size="large"
          @keyup.enter="handleLogin"
        >
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="请输入账号" :prefix-icon="User" />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="请输入密码" :prefix-icon="Lock" show-password />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" class="login-btn" @click="handleLogin">登 录</el-button>
          </el-form-item>
        </el-form>
        <div class="login-footer">
          <el-button type="primary" link @click="openRegDialog">注册账号</el-button>
          <span class="footer-divider">|</span>
          <el-button type="primary" link @click="openPwdDialog">修改密码</el-button>
        </div>
      </div>
    </div>

    <!-- 修改密码对话框 -->
    <el-dialog
      v-model="pwdDialogVisible"
      width="460px"
      :close-on-click-modal="false"
      :show-close="true"
      destroy-on-close
      align-center
      class="auth-dialog"
    >
      <template #header>
        <div class="dialog-header">
          <h3 class="dialog-title">修改密码</h3>
          <p class="dialog-desc">通过原密码验证身份后设置新密码</p>
        </div>
      </template>
      <el-form
        ref="pwdFormRef"
        :model="pwdForm"
        :rules="pwdRules"
        label-position="top"
        class="auth-form"
        @keyup.enter="handleChangePassword"
      >
        <el-form-item label="账号" prop="username">
          <el-input v-model="pwdForm.username" placeholder="请输入账号" :prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item label="原密码" prop="oldPassword">
          <el-input v-model="pwdForm.oldPassword" type="password" placeholder="请输入原密码" :prefix-icon="Lock" size="large" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="pwdForm.newPassword" type="password" placeholder="请输入新密码（至少6位）" :prefix-icon="Lock" size="large" show-password />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input v-model="pwdForm.confirmPassword" type="password" placeholder="请再次输入新密码" :prefix-icon="Lock" size="large" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button size="large" @click="pwdDialogVisible = false">取 消</el-button>
          <el-button type="primary" size="large" :loading="pwdLoading" @click="handleChangePassword">确认修改</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 注册对话框 -->
    <el-dialog
      v-model="regDialogVisible"
      width="460px"
      :close-on-click-modal="false"
      :show-close="true"
      destroy-on-close
      align-center
      class="auth-dialog"
    >
      <template #header>
        <div class="dialog-header">
          <h3 class="dialog-title">注册新账号</h3>
          <p class="dialog-desc">填写以下信息创建你的账号</p>
        </div>
      </template>
      <el-form
        ref="regFormRef"
        :model="regForm"
        :rules="regRules"
        label-position="top"
        class="auth-form"
        @keyup.enter="handleRegister"
      >
        <el-form-item label="账号" prop="username">
          <el-input v-model="regForm.username" placeholder="请输入账号（2-50个字符）" :prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item label="显示名称" prop="display_name">
          <el-input v-model="regForm.display_name" placeholder="请输入显示名称（其他用户可见）" size="large" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="regForm.password" type="password" placeholder="请输入密码（至少6位）" :prefix-icon="Lock" size="large" show-password />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input v-model="regForm.confirmPassword" type="password" placeholder="请再次输入密码" :prefix-icon="Lock" size="large" show-password />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-radio-group v-model="regForm.role" class="role-radio-group">
            <el-radio-button value="user">
              <span class="role-option-label">普通用户</span>
              <span class="role-option-desc">使用平台 AI 技能</span>
            </el-radio-button>
            <el-radio-button value="provider">
              <span class="role-option-label">技能管理员</span>
              <span class="role-option-desc">创建和管理 AI 技能</span>
            </el-radio-button>
            <el-radio-button value="admin">
              <span class="role-option-label">超级管理员</span>
              <span class="role-option-desc">管理平台所有功能</span>
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-alert
          v-if="regForm.role !== 'user'"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: -8px"
        >
          <template #title>
            选择非「普通用户」角色需要管理员审核通过后才能登录使用
          </template>
        </el-alert>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button size="large" @click="regDialogVisible = false">取 消</el-button>
          <el-button type="primary" size="large" :loading="regLoading" @click="handleRegister">注 册</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #4a7dff 0%, #5b8def 40%, #6e9fff 100%);
  padding: 24px;
  position: relative;
  overflow: hidden;
}

.login-page::before,
.login-page::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
}

.login-page::before {
  width: 800px;
  height: 800px;
  top: -300px;
  right: -200px;
  background: rgba(255,255,255,0.07);
}

.login-page::after {
  width: 600px;
  height: 600px;
  bottom: -250px;
  left: -150px;
  background: rgba(255,255,255,0.05);
}

.bg-waves {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.login-container {
  position: relative;
  z-index: 1;
  display: flex;
  width: 900px;
  max-width: 100%;
  min-height: 520px;
  background: #fff;
  border-radius: 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

/* ── 左侧品牌区 ── */
.login-brand {
  width: 380px;
  flex-shrink: 0;
  background: #eef2fb;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 40px;
}

.brand-content { text-align: center; }
.brand-icon { margin-bottom: 20px; }

.login-brand h1 {
  margin: 0 0 6px;
  font-size: 36px;
  font-weight: 800;
  color: #1e293b;
}

.brand-name {
  margin: 0 0 36px;
  font-size: 15px;
  color: #64748b;
}

.brand-features {
  display: flex;
  flex-direction: column;
  gap: 14px;
  text-align: left;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: #475569;
}

.feature-icon {
  font-size: 18px;
  flex-shrink: 0;
}

/* ── 右侧登录区 ── */
.login-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 48px 56px;
}

.login-header { margin-bottom: 32px; }

.login-header h2 {
  margin: 0 0 6px;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
}

.login-header p {
  margin: 0;
  font-size: 14px;
  color: #94a3b8;
}

.login-panel :deep(.el-input__wrapper) {
  padding: 8px 14px;
  border-radius: 8px;
  box-shadow: 0 0 0 1px #e2e8f0;
  transition: box-shadow 0.2s;
}

.login-panel :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #cbd5e1;
}

.login-panel :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px #4a7dff;
}

.login-btn {
  width: 100%;
  height: 46px;
  font-size: 15px;
  font-weight: 600;
  border-radius: 8px;
  background: #4a7dff;
  border-color: #4a7dff;
  letter-spacing: 2px;
}

.login-btn:hover {
  background: #3b6ef0;
  border-color: #3b6ef0;
}

.login-footer {
  text-align: center;
  margin-top: -8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.footer-divider { color: #dcdfe6; font-size: 12px; }

/* ── 对话框 ── */
.dialog-header { display: flex; flex-direction: column; gap: 4px; }
.dialog-title { margin: 0; font-size: 20px; font-weight: 700; color: #0f172a; }
.dialog-desc { margin: 0; font-size: 14px; color: #94a3b8; }
.auth-form { margin-top: 8px; }
.auth-form :deep(.el-form-item__label) { font-weight: 500; color: #334155; padding-bottom: 6px; }
.auth-form :deep(.el-input__wrapper) { border-radius: 8px; box-shadow: 0 0 0 1px #e2e8f0; transition: box-shadow 0.2s; }
.auth-form :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #cbd5e1; }
.auth-form :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 2px #4a7dff; }
.dialog-footer { display: flex; gap: 12px; justify-content: flex-end; }
.dialog-footer .el-button { min-width: 100px; border-radius: 8px; font-weight: 600; }
.dialog-footer .el-button--primary { background: #4a7dff; border-color: #4a7dff; }
.dialog-footer .el-button--primary:hover { background: #3b6ef0; border-color: #3b6ef0; }

/* ── 角色选择 ── */
.role-radio-group { width: 100%; display: flex; gap: 10px; }
.role-radio-group :deep(.el-radio-button) { flex: 1; }
.role-radio-group :deep(.el-radio-button__inner) {
  width: 100%; height: auto; padding: 12px 8px; border-radius: 10px !important;
  border: 1.5px solid #e2e8f0 !important; box-shadow: none !important;
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  transition: all 0.2s; white-space: nowrap; line-height: 1.4; background: #fff; color: #334155;
}
.role-radio-group :deep(.el-radio-button__inner:hover) { border-color: #93c5fd !important; background: #eff6ff; }
.role-radio-group :deep(.el-radio-button.is-active .el-radio-button__inner) { border-color: #4a7dff !important; background: #eff6ff; color: #2563eb; }
.role-option-label { font-size: 13px; font-weight: 600; }
.role-option-desc { font-size: 11px; color: #94a3b8; font-weight: 400; }
.role-radio-group :deep(.el-radio-button.is-active) .role-option-desc { color: #93c5fd; }

@media (max-width: 768px) {
  .login-container { flex-direction: column; width: 100%; }
  .login-brand { width: 100%; padding: 32px 24px; }
  .login-panel { padding: 32px 24px; }
}
</style>

<!-- 对话框全局样式（非 scoped） -->
<style>
.auth-dialog .el-overlay {
  background: rgba(74, 125, 255, 0.18);
  backdrop-filter: blur(4px);
}

.auth-dialog .el-dialog {
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.12);
}

.auth-dialog .el-dialog__header {
  padding: 28px 32px 16px;
  margin-right: 0;
}

.auth-dialog .el-dialog__body {
  padding: 8px 32px 16px;
}

.auth-dialog .el-dialog__footer {
  padding: 12px 32px 28px;
}

.auth-dialog .el-dialog__headerbtn {
  top: 20px;
  right: 20px;
  width: 36px;
  height: 36px;
  font-size: 18px;
}
</style>
