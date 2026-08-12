/**
 * 认证接口层
 * mock 阶段：直接返回本地假数据；后端就绪后替换为 request 真实调用，函数签名与返回结构保持不变
 */
import { delay } from '../utils/delay'
import * as authMock from '../mock/auth'

/** 抛错工具：契约错误码统一为 错误码|消息 格式 */
function parseError(err) {
  const msg = err && err.message ? err.message : '操作失败'
  const idx = msg.indexOf('|')
  if (idx !== -1) {
    const e = new Error(msg.slice(idx + 1))
    e.code = Number(msg.slice(0, idx))
    return e
  }
  return err
}

/** 登录 POST /api/auth/login */
export async function login(payload) {
  await delay(400)
  try {
    return authMock.mockLogin(payload)
  } catch (err) {
    throw parseError(err)
  }
}

/** 注册 POST /api/auth/register */
export async function register(payload) {
  await delay(400)
  try {
    authMock.mockRegister(payload)
    return null
  } catch (err) {
    throw parseError(err)
  }
}

/** 发送短信验证码 POST /api/auth/sms-code */
export async function sendSmsCode(payload) {
  await delay(300)
  return null
}

/** 退出登录 POST /api/auth/logout */
export async function logout() {
  await delay(200)
  return null
}

/** 获取当前用户 GET /api/auth/me */
export async function getMe(phone) {
  await delay(200)
  return authMock.mockMe(phone)
}

/** 修改个人信息 PUT /api/auth/profile */
export async function updateProfile(payload) {
  await delay(300)
  return authMock.mockUpdateProfile(payload.phone, payload)
}

/** 修改密码 PUT /api/auth/password */
export async function updatePassword(payload) {
  await delay(300)
  try {
    authMock.mockUpdatePassword(payload.phone, payload)
    return null
  } catch (err) {
    throw parseError(err)
  }
}
