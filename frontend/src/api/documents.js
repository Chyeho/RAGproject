/**
 * 文档接口层（mock 阶段返回本地假数据，后端就绪后替换为 request 真实调用）
 */
import { delay } from '../utils/delay'
import * as docMock from '../mock/documents'

/** 上传文档 POST /api/documents/upload */
export async function uploadDocuments(files) {
  await delay(600)
  const added = docMock.mockUpload(files)
  return { list: added }
}

/** 获取文档列表 GET /api/documents */
export async function queryDocuments(params) {
  await delay(300)
  return docMock.mockQueryDocuments(params)
}

/** 文档预览 GET /api/documents/{id}/preview */
export async function previewDocument(id) {
  await delay(300)
  const doc = docMock.mockGetDocument(id)
  return {
    ...doc,
    content: docMock.mockPreviewContent(doc),
  }
}

/** 文档下载 GET /api/documents/{id}/download（mock 无真实下载） */
export async function downloadDocument(id) {
  await delay(200)
  return null
}

/** 删除文档 DELETE /api/documents/{id} */
export async function deleteDocument(id) {
  await delay(300)
  docMock.mockRemoveDocument(id)
  return null
}
