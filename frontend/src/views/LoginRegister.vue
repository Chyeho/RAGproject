<template>
  <div class="login-page">
    <!-- 左侧：品牌展示区 -->
    <div class="login-left">
      <div class="brand-block">
        <img class="brand-logo" :src="horizontalLogo" alt="宸甄 PrivRAG" />
        <p class="brand-slogan">企业私有RAG知识库 · 文档本地安全可控</p>
      </div>
    </div>

    <!-- 右侧：登录/注册卡片区 -->
    <div class="login-right">
      <div class="login-card">
        <el-tabs v-model="activeTab" stretch>
          <!-- 登录 Tab -->
          <el-tab-pane label="登录" name="login">
            <el-form
              ref="loginFormRef"
              :model="loginForm"
              :rules="loginRules"
              size="large"
              @keyup.enter="handleLogin"
            >
              <el-form-item prop="phone">
                <el-input
                  v-model="loginForm.phone"
                  placeholder="请输入手机号"
                  clearable
                  maxlength="11"
                >
                  <template #prefix><el-icon><Iphone /></el-icon></template>
                </el-input>
              </el-form-item>

              <el-form-item prop="password">
                <el-input
                  v-model="loginForm.password"
                  type="password"
                  placeholder="请输入密码"
                  show-password
                >
                  <template #prefix><el-icon><Lock /></el-icon></template>
                </el-input>
              </el-form-item>

              <div class="login-options">
                <el-checkbox v-model="loginForm.remember">记住我</el-checkbox>
              </div>

              <el-button
                class="submit-btn"
                type="primary"
                size="large"
                :loading="loginLoading"
                @click="handleLogin"
              >
                登 录
              </el-button>
            </el-form>
          </el-tab-pane>

          <!-- 注册 Tab -->
          <el-tab-pane label="注册" name="register">
            <el-form
              ref="registerFormRef"
              :model="registerForm"
              :rules="registerRules"
              size="large"
              @keyup.enter="handleRegister"
            >
              <el-form-item prop="phone">
                <el-input
                  v-model="registerForm.phone"
                  placeholder="请输入手机号"
                  clearable
                  maxlength="11"
                >
                  <template #prefix><el-icon><Iphone /></el-icon></template>
                </el-input>
              </el-form-item>

              <el-form-item prop="smsCode">
                <div class="sms-row">
                  <el-input
                    v-model="registerForm.smsCode"
                    placeholder="请输入短信验证码"
                    maxlength="6"
                  >
                    <template #prefix><el-icon><Message /></el-icon></template>
                  </el-input>
                  <el-button
                    class="sms-btn"
                    :disabled="countdown > 0"
                    @click="handleGetCode"
                  >
                    {{ countdown > 0 ? `${countdown}s 后重发` : '获取验证码' }}
                  </el-button>
                </div>
              </el-form-item>

              <el-form-item prop="password">
                <el-input
                  v-model="registerForm.password"
                  type="password"
                  placeholder="请设置密码（6-20位）"
                  show-password
                >
                  <template #prefix><el-icon><Lock /></el-icon></template>
                </el-input>
              </el-form-item>

              <el-form-item prop="confirmPassword">
                <el-input
                  v-model="registerForm.confirmPassword"
                  type="password"
                  placeholder="请再次确认密码"
                  show-password
                >
                  <template #prefix><el-icon><Lock /></el-icon></template>
                </el-input>
              </el-form-item>

              <el-button
                class="submit-btn"
                type="primary"
                size="large"
                :loading="registerLoading"
                @click="handleRegister"
              >
                注 册
              </el-button>
            </el-form>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <!-- 底部版权 -->
    <footer class="login-footer">宸甄 PrivRAG ©2026 企业私有文档平台</footer>
  </div>
</template>

<script setup>
import { ref, reactive, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Iphone, Lock, Message } from '@element-plus/icons-vue'
import horizontalLogo from '../assets/images/宸甄 PrivRAG 企业私有知识库问答系统logo.png'
import { login, register, sendSmsCode } from '../api/auth'
import { setLoginState } from '../utils/auth'
import { MOCK_SMS_CODE } from '../mock/auth'

const router = useRouter()
const route = useRoute()

const activeTab = ref('login')

// ---------------- 登录 ----------------
const loginFormRef = ref(null)
const loginLoading = ref(false)
const loginForm = reactive({
  phone: '',
  password: '',
  remember: true,
})

const validatePhone = (rule, value, callback) => {
  if (!value) return callback(new Error('请输入手机号'))
  if (!/^1\d{10}$/.test(value)) return callback(new Error('请输入正确的11位手机号'))
  callback()
}

const loginRules = {
  phone: [{ required: true, validator: validatePhone, trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 20, message: '密码长度为6-20位', trigger: 'blur' },
  ],
}

async function handleLogin() {
  const valid = await loginFormRef.value.validate().catch(() => false)
  if (!valid) return
  loginLoading.value = true
  try {
    const { token, user } = await login({ ...loginForm })
    setLoginState(token, user, loginForm.remember)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect || '/chat'
    router.push(redirect)
  } catch (e) {
    ElMessage.error(e.message || '登录失败')
  } finally {
    loginLoading.value = false
  }
}

// ---------------- 注册 ----------------
const registerFormRef = ref(null)
const registerLoading = ref(false)
const countdown = ref(0)
let countdownTimer = null

const registerForm = reactive({
  phone: '',
  smsCode: '',
  password: '',
  confirmPassword: '',
})

const validateConfirm = (rule, value, callback) => {
  if (!value) return callback(new Error('请再次确认密码'))
  if (value !== registerForm.password) return callback(new Error('两次输入的密码不一致'))
  callback()
}

const registerRules = {
  phone: [{ required: true, validator: validatePhone, trigger: 'blur' }],
  smsCode: [
    { required: true, message: '请输入短信验证码', trigger: 'blur' },
    { len: 6, message: '验证码为6位数字', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请设置密码', trigger: 'blur' },
    { min: 6, max: 20, message: '密码长度为6-20位', trigger: 'blur' },
  ],
  confirmPassword: [{ required: true, validator: validateConfirm, trigger: 'blur' }],
}

function handleGetCode() {
  if (!registerForm.phone) {
    ElMessage.warning('请先输入手机号')
    return
  }
  if (!/^1\d{10}$/.test(registerForm.phone)) {
    ElMessage.warning('请输入正确的11位手机号')
    return
  }
  sendSmsCode({ phone: registerForm.phone, scene: 'register' })
  ElMessage.success(`验证码已发送（开发环境固定为 ${MOCK_SMS_CODE}）`)
  countdown.value = 60
  countdownTimer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) clearInterval(countdownTimer)
  }, 1000)
}

async function handleRegister() {
  const valid = await registerFormRef.value.validate().catch(() => false)
  if (!valid) return
  registerLoading.value = true
  try {
    await register({ ...registerForm })
    ElMessage.success('注册成功，请登录')
    activeTab.value = 'login'
    loginForm.phone = registerForm.phone
    registerFormRef.value.resetFields()
  } catch (e) {
    ElMessage.error(e.message || '注册失败')
  } finally {
    registerLoading.value = false
  }
}

onBeforeUnmount(() => {
  if (countdownTimer) clearInterval(countdownTimer)
})
</script>

<style scoped>
.login-page {
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  background: var(--brand-gradient-soft);
}

/* ------- 左侧品牌区（占比大） ------- */
.login-left {
  position: relative;
  flex: 1.4;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--brand-gradient-soft-deep);
  overflow: hidden;
}

/* 低调的科技感光晕装饰（低饱和蓝紫，不抢眼） */
.login-left::before,
.login-left::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  opacity: 0.5;
  pointer-events: none;
}

.login-left::before {
  width: 420px;
  height: 420px;
  top: -120px;
  left: -100px;
  background: radial-gradient(circle, rgba(90, 108, 224, 0.28), transparent 70%);
}

.login-left::after {
  width: 480px;
  height: 480px;
  bottom: -160px;
  right: -120px;
  background: radial-gradient(circle, rgba(124, 96, 220, 0.26), transparent 70%);
}

.brand-block {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 40px;
}

.brand-logo {
  height: 104px;
  width: auto;
  object-fit: contain;
}

.brand-slogan {
  margin-top: 28px;
  font-size: 15px;
  color: #86909c;
  letter-spacing: 1px;
}

/* ------- 右侧登录卡片区（背景保持蓝紫渐变不变） ------- */
.login-right {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

/* 白色卡片框住登录注册主要区域 */
.login-card {
  width: 420px;
  background-color: #ffffff;
  border-radius: 12px;
  box-shadow: var(--shadow-dialog);
  padding: 28px 36px 24px;
}

.login-card :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.login-card :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background-color: #e5e6eb;
}

.login-card :deep(.el-tabs__item) {
  font-size: 16px;
  color: #86909c;
}

.login-card :deep(.el-tabs__item.is-active) {
  color: var(--brand-color);
  font-weight: 600;
}

.login-card :deep(.el-tabs__active-bar) {
  background: var(--brand-gradient);
}

.login-card :deep(.el-tabs__content) {
  padding-top: 28px;
}

.login-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: -4px 0 20px;
}

.login-options :deep(.el-checkbox__label) {
  color: #86909c;
}

.submit-btn {
  width: 100%;
  height: 44px;
  font-size: 16px;
  letter-spacing: 4px;
}

.sms-row {
  display: flex;
  width: 100%;
  gap: 12px;
}

.sms-btn {
  flex-shrink: 0;
}

/* ------- 底部版权 ------- */
.login-footer {
  position: absolute;
  bottom: 16px;
  left: 0;
  right: 0;
  text-align: center;
  font-size: 12px;
  color: #a6acbe;
}
</style>
