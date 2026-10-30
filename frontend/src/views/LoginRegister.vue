<template>
  <div class="login-page">
    <!-- 左侧：品牌展示区 -->
    <div class="login-left">
      <div class="brand-block">
        <img class="brand-logo" :src="horizontalLogo" alt="宸甄 PrivRAG" />
        <p class="brand-slogan">企业私有RAG知识库 · 文档本地安全可控</p>
      </div>
    </div>

    <!-- 右侧：登录卡片区（账号由管理员创建，不提供自助注册） -->
    <div class="login-right">
      <div class="login-card">
        <div class="card-title">账号登录</div>

        <el-form
          ref="loginFormRef"
          :model="loginForm"
          :rules="loginRules"
          size="large"
          @keyup.enter="handleLogin"
        >
          <el-form-item prop="username">
            <el-input
              v-model="loginForm.username"
              placeholder="请输入账号"
              clearable
              maxlength="32"
            >
              <template #prefix><el-icon><User /></el-icon></template>
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

        <p class="login-tip">账号由系统管理员统一创建，如需开通请联系管理员</p>
      </div>
    </div>

    <!-- 底部版权 -->
    <footer class="login-footer">宸甄 PrivRAG ©2026 企业私有文档平台</footer>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import horizontalLogo from '../assets/images/宸甄 PrivRAG 企业私有知识库问答系统logo.png'
import { login } from '../api/auth'
import { setLoginState } from '../utils/auth'

const router = useRouter()
const route = useRoute()

const loginFormRef = ref(null)
const loginLoading = ref(false)
const loginForm = reactive({
  username: '',
  password: '',
  remember: true,
})

const loginRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  // 登录只校验非空：历史账号存在较短密码，强度校验仅在新增/修改密码时执行
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await loginFormRef.value.validate().catch(() => false)
  if (!valid) return
  loginLoading.value = true
  try {
    const { token, user } = await login({ ...loginForm })
    setLoginState(token, user, loginForm.remember)
    ElMessage.success('登录成功')
    if (user?.mustChangePassword) {
      ElMessage.warning('当前为初始密码，请先修改密码')
      router.push('/settings')
      return
    }
    const redirect = route.query.redirect || '/chat'
    router.push(redirect)
  } catch (e) {
    ElMessage.error(e.message || '登录失败')
  } finally {
    loginLoading.value = false
  }
}
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

/* 白色卡片框住登录主要区域 */
.login-card {
  width: 420px;
  background-color: #ffffff;
  border-radius: 12px;
  box-shadow: var(--shadow-dialog);
  padding: 32px 36px 26px;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-main);
  text-align: center;
  margin-bottom: 26px;
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

.login-tip {
  margin-top: 18px;
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
  line-height: 1.6;
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
