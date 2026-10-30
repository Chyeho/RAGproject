/**
 * 登录态管理（localStorage）
 * 后端返回的 user 对象包含 role / level / permissions，前端据此渲染菜单与按钮
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

/**
 * 权限判断（后端 permissions 布尔字典）
 * 权限键：chat / statistics / knowledgeRead / knowledgeWrite / ragConfig / accountManage
 */
export function hasPermission(permission) {
  const user = getUser()
  return !!user?.permissions?.[permission]
}

export function getRemember() {
  return localStorage.getItem(REMEMBER_KEY) === '1'
}

/**
 * 登录成功后写入登录态
 * @param {string} token JWT
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

/** 退出登录：清除全部登录状态（含聊天输入草稿，避免同浏览器下一账号看到上一账号内容） */
export function clearLoginState() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(REMEMBER_KEY)
  sessionStorage.removeItem('privrag_chat_draft')
}
