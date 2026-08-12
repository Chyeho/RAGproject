/**
 * mock 认证数据源（字段对齐接口JSON契约文档 第1章）
 */

// 开发环境固定验证码
export const MOCK_SMS_CODE = '123456'

// mock 用户库（内存态）
const users = [
  {
    id: 1,
    phone: '13800138000',
    password: '123456',
    nickname: '宸甄管理员',
    avatar: '',
    createdAt: '2026-06-01 10:00:00',
  },
]

/** 去掉敏感字段（password）后返回用户公开信息 */
function toPublicUser(user) {
  return {
    id: user.id,
    phone: user.phone,
    nickname: user.nickname,
    avatar: user.avatar,
    createdAt: user.createdAt,
  }
}

/** mock 登录：校验手机号+密码 */
export function mockLogin({ phone, password }) {
  const user = users.find((u) => u.phone === phone)
  if (!user || user.password !== password) {
    throw new Error('2001|手机号或密码错误')
  }
  return {
    token: `mock-token-${Date.now()}`,
    user: toPublicUser(user),
  }
}

/** mock 注册：手机号未注册即可成功（验证码由前端校验固定 123456） */
export function mockRegister({ phone, nickname = '新用户' }) {
  if (users.some((u) => u.phone === phone)) {
    throw new Error('2003|该手机号已注册')
  }
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  users.push({
    id: Date.now(),
    phone,
    password: '123456',
    nickname,
    avatar: '',
    createdAt: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`,
  })
}

/** mock 获取当前用户（以手机号定位，默认返回管理员） */
export function mockMe(phone) {
  const user = users.find((u) => u.phone === phone) || users[0]
  return toPublicUser(user)
}

/** mock 修改个人信息 */
export function mockUpdateProfile(phone, payload) {
  const user = users.find((u) => u.phone === phone) || users[0]
  if (payload.nickname != null) user.nickname = payload.nickname
  if (payload.avatar != null) user.avatar = payload.avatar
  return toPublicUser(user)
}

/** mock 修改密码 */
export function mockUpdatePassword(phone, { oldPassword, newPassword }) {
  const user = users.find((u) => u.phone === phone) || users[0]
  if (user.password !== oldPassword) {
    throw new Error('2001|旧密码错误')
  }
  user.password = newPassword
}
