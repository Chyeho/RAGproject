/**
 * 统计接口层（mock 阶段返回本地假数据，后端就绪后替换为 request 真实调用）
 */
import { delay } from '../utils/delay'
import * as statMock from '../mock/statistics'

/** 总览统计 GET /api/statistics/overview */
export async function getOverview() {
  await delay(300)
  return statMock.mockOverview()
}

/** 文件类型占比 GET /api/statistics/file-type-distribution */
export async function getFileTypeDistribution() {
  await delay(300)
  return statMock.mockFileTypeDistribution()
}

/** 近30天入库趋势 GET /api/statistics/daily-trend */
export async function getDailyTrend(days = 30) {
  await delay(300)
  return statMock.mockDailyTrend(days)
}

/** 向量化成功/失败占比 GET /api/statistics/vectorization-status */
export async function getVectorizationStatus() {
  await delay(300)
  return statMock.mockVectorizationStatus()
}
