/**
 * 认证接口层（对接后端真实接口）
 * 函数签名与返回结构与 mock 阶段保持一致，页面无需改动
 */
import request from './request'

/** 开发环境固定验证码（与后端一致） */
export const DEV_SMS_CODE = '123456'

/** 登录 POST /api/auth/login */
export async function login(payload) {
  return request.post('/auth/login', payload)
}

/** 注册 POST /api/auth/register */
export async function register(payload) {
  return request.post('/auth/register', payload)
}

/** 发送短信验证码 POST /api/auth/sms-code */
export async function sendSmsCode(payload) {
  return request.post('/auth/sms-code', payload)
}

/** 退出登录 POST /api/auth/logout */
export async function logout() {
  return request.post('/auth/logout')
}

/** 获取当前用户 GET /api/auth/me */
export async function getMe() {
  return request.get('/auth/me')
}

/** 修改个人信息 PUT /api/auth/profile */
export async function updateProfile(payload) {
  return request.put('/auth/profile', {
    nickname: payload.nickname,
    avatar: payload.avatar,
  })
}

/** 修改密码 PUT /api/auth/password */
export async function updatePassword(payload) {
  return request.put('/auth/password', {
    oldPassword: payload.oldPassword,
    newPassword: payload.newPassword,
    confirmPassword: payload.confirmPassword,
  })
}
