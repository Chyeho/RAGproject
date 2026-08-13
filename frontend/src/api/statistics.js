/**
 * 统计接口层（对接后端真实接口）
 * 函数签名与返回结构与 mock 阶段保持一致，页面无需改动
 */
import request from './request'

/** 总览统计 GET /api/statistics/overview */
export async function getOverview() {
  return request.get('/statistics/overview')
}

/** 文件类型占比 GET /api/statistics/file-type-distribution */
export async function getFileTypeDistribution() {
  return request.get('/statistics/file-type-distribution')
}

/** 近 N 天入库趋势 GET /api/statistics/daily-trend */
export async function getDailyTrend(days = 30) {
  return request.get('/statistics/daily-trend', { params: { days } })
}

/** 向量化成功/失败占比 GET /api/statistics/vectorization-status */
export async function getVectorizationStatus() {
  return request.get('/statistics/vectorization-status')
}
