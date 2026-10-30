/**
 * 认证接口层（对接后端真实接口）
 */
import request from './request'

/** 登录 POST /api/auth/login */
export async function login(payload) {
  return request.post('/auth/login', payload)
}

/** 退出登录 POST /api/auth/logout */
export async function logout() {
  return request.post('/auth/logout')
}

/** 获取当前用户 GET /api/auth/me */
export async function getMe() {
  return request.get('/auth/me')
}

/** 修改密码 POST /api/auth/change-password */
export async function changePassword(payload) {
  return request.post('/auth/change-password', {
    oldPassword: payload.oldPassword,
    newPassword: payload.newPassword,
    confirmPassword: payload.confirmPassword,
  })
}
