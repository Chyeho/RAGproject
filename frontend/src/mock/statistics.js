/**
 * mock 统计数据源（字段对齐接口JSON契约文档 第4章）
 * 统计口径直接基于 mock 文档列表推导，保证与知识库页数据一致
 */
import { mockDocuments } from './documents'

/** 总览统计 */
export function mockOverview() {
  return {
    totalDocuments: mockDocuments.length,
    totalSize: mockDocuments.reduce((sum, d) => sum + d.size, 0),
    vectorizeSuccess: mockDocuments.filter((d) => d.vectorizeStatus === 'success').length,
    vectorizeFailed: mockDocuments.filter((d) => d.vectorizeStatus === 'failed').length,
  }
}

/** 各类文件类型占比 */
export function mockFileTypeDistribution() {
  const countMap = {}
  mockDocuments.forEach((d) => {
    countMap[d.type] = (countMap[d.type] || 0) + 1
  })
  return {
    list: ['pdf', 'docx', 'txt', 'md', 'xlsx'].map((type) => ({
      type,
      count: countMap[type] || 0,
    })),
  }
}

/** 近 N 天每日入库趋势（按 mock 文档入库时间统计，未入库日期补 0） */
export function mockDailyTrend(days = 30) {
  const list = []
  const today = new Date()
  const countMap = {}
  mockDocuments.forEach((d) => {
    const date = d.uploadedAt.slice(0, 10)
    countMap[date] = (countMap[date] || 0) + 1
  })
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    const pad = (n) => String(n).padStart(2, '0')
    const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    list.push({ date, count: countMap[date] || 0 })
  }
  return { list }
}

/** 向量化成功与失败占比 */
export function mockVectorizationStatus() {
  return {
    success: mockDocuments.filter((d) => d.vectorizeStatus === 'success').length,
    failed: mockDocuments.filter((d) => d.vectorizeStatus === 'failed').length,
  }
}
