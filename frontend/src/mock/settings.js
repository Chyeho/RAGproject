/**
 * mock RAG 参数配置数据源（字段对齐接口JSON契约文档 第5章）
 */
let ragConfig = {
  chunkSize: 200,
  topK: 3,
  chunkOverlap: 20,
  separators: ['\n\n', '\n', '.', '!', '?', '。', '！', '？', ' ', ''],
}

/** 获取 RAG 参数配置 */
export function mockGetRagConfig() {
  return { ...ragConfig }
}

/** 保存 RAG 参数配置 */
export function mockSaveRagConfig(payload) {
  if (payload.chunkSize != null) ragConfig.chunkSize = payload.chunkSize
  if (payload.topK != null) ragConfig.topK = payload.topK
  return { ...ragConfig }
}
