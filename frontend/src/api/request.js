/**
 * axios 实例（预留：后端接口就绪后启用真实请求）
 * 当前 mock 阶段各 api 模块直接返回本地 mock 数据，不发起 http 请求
 */
import axios from 'axios'
import { getToken } from '../utils/auth'

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

// 响应拦截：解包统一响应结构 {code, message, data}
request.interceptors.response.use(
  (response) => {
    const res = response.data
    if (res && res.code === 0) {
      return res.data
    }
    const err = new Error(res && res.message ? res.message : '请求失败')
    err.code = res && res.code
    return Promise.reject(err)
  },
  (error) => {
    const err = new Error(error.response?.data?.message || error.message || '网络异常')
    err.code = error.response?.data?.code
    return Promise.reject(err)
  }
)

export default request
