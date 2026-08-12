/**
 * 系统设置接口层（mock 阶段返回本地假数据，后端就绪后替换为 request 真实调用）
 */
import { delay } from '../utils/delay'
import * as settingMock from '../mock/settings'

/** 获取 RAG 参数配置 GET /api/settings/rag-config */
export async function getRagConfig() {
  await delay(300)
  return settingMock.mockGetRagConfig()
}

/** 保存 RAG 参数配置 PUT /api/settings/rag-config */
export async function saveRagConfig(payload) {
  await delay(300)
  return settingMock.mockSaveRagConfig(payload)
}
