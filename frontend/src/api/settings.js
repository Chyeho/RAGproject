/**
 * 系统设置接口层（对接后端真实接口）
 * 函数签名与返回结构与 mock 阶段保持一致，页面无需改动
 */
import request from './request'

/** 获取 RAG 参数配置 GET /api/settings/rag-config */
export async function getRagConfig() {
  return request.get('/settings/rag-config')
}

/** 保存 RAG 参数配置 PUT /api/settings/rag-config */
export async function saveRagConfig(payload) {
  return request.put('/settings/rag-config', payload)
}
