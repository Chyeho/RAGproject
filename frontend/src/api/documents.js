/**
 * 文档接口层（对接后端真实接口）
 * 函数签名与返回结构与 mock 阶段保持一致，页面无需改动
 */
import request from './request'

/** 上传文档 POST /api/documents/upload（multipart，字段名 files） */
export async function uploadDocuments(files) {
  const formData = new FormData()
  files.forEach((f) => formData.append('files', f))
  return request.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 获取文档列表 GET /api/documents */
export async function queryDocuments(params) {
  return request.get('/documents', { params })
}

/** 文档预览 GET /api/documents/{id}/preview */
export async function previewDocument(id) {
  return request.get(`/documents/${id}/preview`)
}

/** 文档下载 GET /api/documents/{id}/download（文件流，触发浏览器下载，保留原始文件名） */
export async function downloadDocument(id) {
  const blob = await request.get(`/documents/${id}/download`, { responseType: 'blob' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = blob.name || ''
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  return null
}

/** 删除文档 DELETE /api/documents/{id} */
export async function deleteDocument(id) {
  return request.delete(`/documents/${id}`)
}
