/**
 * 完整路由配置 + 登录守卫
 */
import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn } from '../utils/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginRegister.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/',
    component: () => import('../layout/AppLayout.vue'),
    redirect: '/chat',
    children: [
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('../views/chat/ChatView.vue'),
        meta: { title: 'Bot问答' },
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('../views/knowledge/KnowledgeView.vue'),
        meta: { title: '知识库' },
      },
      {
        path: 'statistics',
        name: 'Statistics',
        component: () => import('../views/statistics/StatisticsView.vue'),
        meta: { title: '统计数据' },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('../views/settings/SettingsView.vue'),
        meta: { title: '系统设置' },
      },
    ],
  },
  // 未匹配路由统一回主框架
  { path: '/:pathMatch(.*)*', redirect: '/chat' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫：未登录访问主页路由 -> 重定向登录页；已登录访问登录页 -> 跳转主框架
router.beforeEach((to, from, next) => {
  const logged = isLoggedIn()
  if (to.path !== '/login' && !logged) {
    next({ path: '/login', query: { redirect: to.fullPath } })
  } else if (to.path === '/login' && logged) {
    next('/chat')
  } else {
    next()
  }
})

router.afterEach((to) => {
  const title = to.meta?.title
  document.title = title ? `${title} · 宸甄 PrivRAG` : '宸甄 PrivRAG'
})

export default router
