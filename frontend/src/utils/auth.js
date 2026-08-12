/**
 * mock 登录态管理（localStorage）
 * 后端就绪后：token 与 user 改为真实接口返回，读取逻辑保持一致
 */
const TOKEN_KEY = 'privrag_token'
const USER_KEY = 'privrag_user'
const REMEMBER_KEY = 'privrag_remember'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch (e) {
    return null
  }
}

export function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function isLoggedIn() {
  return !!getToken()
}

export function getRemember() {
  return localStorage.getItem(REMEMBER_KEY) === '1'
}

/**
 * 登录成功后写入登录态
 * @param {string} token mock token
 * @param {object} user 用户对象（契约 user 结构）
 * @param {boolean} remember 记住我
 */
export function setLoginState(token, user, remember) {
  setToken(token)
  setUser(user)
  if (remember) {
    localStorage.setItem(REMEMBER_KEY, '1')
  } else {
    localStorage.removeItem(REMEMBER_KEY)
  }
}

/** 退出登录：清除全部 mock 登录状态 */
export function clearLoginState() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(REMEMBER_KEY)
}
