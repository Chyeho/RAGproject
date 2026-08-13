/**
 * axios 实例：对接后端真实接口
 * 统一处理：请求注入登录令牌、响应解包 {code, message, data}、401 登录失效跳转
 */
import axios from 'axios'
import { getToken, clearLoginState } from '../utils/auth'

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截：注入登录令牌
request.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：解包统一响应结构 {code, message, data}；文件流（blob）直接透传
request.interceptors.response.use(
  (response) => {
    // 文件下载：透传 blob，并解析 Content-Disposition 中的原始文件名挂到 blob.name（供 a.download 使用）
    if (response.config.responseType === 'blob') {
      const blob = response.data
      const cd = response.headers['content-disposition'] || ''
      // 优先 filename*=utf-8''xxx，回退 filename="xxx"
      const m = cd.match(/filename\*=utf-8''([^;]+)/i) || cd.match(/filename="?([^";]+)"?/i)
      if (m && m[1]) {
        try {
          blob.name = decodeURIComponent(m[1])
        } catch (e) {
          blob.name = m[1]
        }
      }
      return blob
    }
    const res = response.data
    if (res && res.code === 0) {
      return res.data
    }
    const err = new Error(res && res.message ? res.message : '请求失败')
    err.code = res && res.code
    return Promise.reject(err)
  },
  (error) => {
    const resData = error.response?.data
    const err = new Error(resData?.message || error.message || '网络异常')
    err.code = resData?.code ?? error.response?.status
    // 登录失效（契约 code=3001）：清除本地登录态并跳转登录页
    if (err.code === 3001) {
      clearLoginState()
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

export default request
