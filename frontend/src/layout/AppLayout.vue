<template>
  <div class="app-layout">
    <!-- ================= 顶部导航栏 ================= -->
    <header class="layout-header">
      <div class="header-left">
        <img class="header-logo" :src="horizontalLogo" alt="宸甄 PrivRAG" />
      </div>

      <div class="header-right">
        <el-dropdown trigger="click" @command="handleCommand">
          <div class="user-trigger">
            <div class="user-avatar">
              <el-icon :size="18"><UserFilled /></el-icon>
            </div>
            <span class="user-name">{{ userInfo?.nickname || '用户' }}</span>
            <el-icon class="user-caret" :size="12"><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">
                <el-icon><User /></el-icon>个人信息
              </el-dropdown-item>
              <el-dropdown-item command="password">
                <el-icon><Key /></el-icon>修改密码
              </el-dropdown-item>
              <el-dropdown-item command="logout" divided>
                <el-icon><SwitchButton /></el-icon>退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <div class="layout-body">
      <!-- ================= 左侧侧边菜单栏 ================= -->
      <aside class="layout-sidebar">
        <el-menu
          :default-active="activeMenu"
          router
          background-color="transparent"
          text-color="#FFFFFF"
          active-text-color="#FFFFFF"
          class="sidebar-menu"
        >
          <el-menu-item index="/chat">
            <el-icon><ChatDotRound /></el-icon>
            <span>Bot问答</span>
          </el-menu-item>
          <el-menu-item index="/knowledge">
            <el-icon><FolderOpened /></el-icon>
            <span>知识库</span>
          </el-menu-item>
          <el-menu-item index="/statistics">
            <el-icon><DataAnalysis /></el-icon>
            <span>统计数据</span>
          </el-menu-item>
          <el-menu-item index="/settings">
            <el-icon><Setting /></el-icon>
            <span>系统设置</span>
          </el-menu-item>
        </el-menu>
      </aside>

      <!-- ================= 右侧主内容容器 ================= -->
      <main class="layout-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  UserFilled,
  ArrowDown,
  User,
  Key,
  SwitchButton,
} from '@element-plus/icons-vue'
import horizontalLogo from '../assets/images/宸甄 PrivRAG 企业私有知识库问答系统logo.png'
import { getUser, clearLoginState } from '../utils/auth'
import { logout } from '../api/auth'

const route = useRoute()
const router = useRouter()

// 当前用户（mock 登录态）
const userInfo = ref(getUser())

// 侧边菜单当前激活项（跟随路由）
const activeMenu = computed(() => route.path)

// 顶栏用户下拉
async function handleCommand(command) {
  if (command === 'profile') {
    router.push('/settings')
  } else if (command === 'password') {
    router.push('/settings')
  } else if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定要退出登录吗？', '退出登录', {
        confirmButtonText: '退出',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch (e) {
      return
    }
    logout().catch(() => {})
    clearLoginState()
    ElMessage.success('已退出登录')
    router.push('/login')
  }
}
</script>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background-color: #ffffff;
}

/* ------- 顶部导航栏 ------- */
.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--header-height);
  padding: 0 20px;
  background: var(--brand-gradient);
  flex-shrink: 0;
  box-shadow: 0 2px 10px rgba(30, 55, 160, 0.22);
}

.header-left {
  display: flex;
  align-items: center;
}

.header-logo {
  height: 44px;
  width: auto;
  object-fit: contain;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background-color 0.2s;
}

.user-trigger:hover {
  background-color: rgba(255, 255, 255, 0.12);
}

.user-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.25);
  color: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.4);
}

.user-name {
  color: #ffffff;
  font-size: 14px;
}

.user-caret {
  color: rgba(255, 255, 255, 0.75);
}

/* ------- 主体区域 ------- */
.layout-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* 左侧侧边菜单栏 */
.layout-sidebar {
  width: var(--sidebar-width);
  background: var(--brand-gradient);
  flex-shrink: 0;
  overflow-y: auto;
}

.sidebar-menu {
  border-right: none;
  padding-top: 8px;
}

.sidebar-menu :deep(.el-menu-item) {
  height: 48px;
  line-height: 48px;
  margin: 4px 10px;
  border-radius: 6px;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  background-color: rgba(255, 255, 255, 0.12);
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.26), rgba(255, 255, 255, 0.12));
  font-weight: 600;
}

.sidebar-menu :deep(.el-menu-item .el-icon) {
  font-size: 17px;
}

/* 右侧主内容容器 */
.layout-content {
  flex: 1;
  min-width: 0;
  background-color: #ffffff;
  overflow: hidden;
}
</style>
