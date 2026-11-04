<template>
  <div class="page-container statistics-page">
    <!-- ================= 顶部：4 个统计数字卡片 ================= -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-value">{{ overview.totalDocuments }}</div>
        <div class="stat-label">文档总数量</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ formatFileSize(overview.totalSize) }}</div>
        <div class="stat-label">全部文档总占用大小</div>
      </div>
      <div class="stat-card">
        <div class="stat-value stat-success">{{ overview.vectorizeSuccess }}</div>
        <div class="stat-label">向量化成功文档数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value stat-failed">{{ overview.vectorizeFailed }}</div>
        <div class="stat-label">向量化失败文档数</div>
      </div>
    </div>

    <!-- ================= 图表区域 ================= -->
    <div v-if="overview.totalDocuments > 0" class="chart-area">
      <!-- 第一行：两个环形图并排，等高对称 -->
      <div class="chart-row chart-row-donut">
        <div class="chart-card">
          <div class="chart-head">
            <span class="chart-title">各类文件类型占比</span>
            <span class="chart-hint">共 {{ overview.totalDocuments }} 篇</span>
          </div>
          <div ref="pieRef" class="chart-box"></div>
        </div>
        <div class="chart-card">
          <div class="chart-head">
            <span class="chart-title">文档向量化成功与失败占比</span>
            <span class="chart-hint">
              成功 {{ overview.vectorizeSuccess }} · 失败 {{ overview.vectorizeFailed }}
            </span>
          </div>
          <div ref="ringRef" class="chart-box"></div>
        </div>
      </div>

      <!-- 第二行：趋势图独占整行，横向空间留给日期轴 -->
      <div class="chart-card">
        <div class="chart-head">
          <span class="chart-title">近 30 天每日入库文档数量趋势</span>
          <span class="chart-hint">单位：篇</span>
        </div>
        <div ref="barRef" class="chart-box chart-box-wide"></div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="chart-empty">
      <el-icon :size="44"><DataLine /></el-icon>
      <p>暂无文档统计数据，请前往知识库上传文档</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { DataLine } from '@element-plus/icons-vue'
import {
  getOverview,
  getFileTypeDistribution,
  getDailyTrend,
  getVectorizationStatus,
} from '../../api/statistics'
import { formatFileSize } from '../../utils/format'

// ---------------- 数据 ----------------
const overview = ref({
  totalDocuments: 0,
  totalSize: 0,
  vectorizeSuccess: 0,
  vectorizeFailed: 0,
})

// ---------------- 图表容器 ----------------
const pieRef = ref(null)
const barRef = ref(null)
const ringRef = ref(null)

let pieChart = null
let barChart = null
let ringChart = null

// 项目蓝紫渐变配色（蓝色为主、低饱和，统一不花哨）
const BLUE_PALETTE = ['#2B4FE0', '#4155DD', '#5A52D8', '#7450D2', '#8F64DE']
const SUCCESS_BLUE = '#4A52DF'
const FAILED_GRAY = '#E5E6EB'

onMounted(async () => {
  const [ov, fileDist, trend, vecStatus] = await Promise.all([
    getOverview(),
    getFileTypeDistribution(),
    getDailyTrend(30),
    getVectorizationStatus(),
  ])
  overview.value = ov

  if (ov.totalDocuments > 0) {
    await nextTick()
    initPie(fileDist.list)
    initBar(trend.list)
    initRing(vecStatus)
    window.addEventListener('resize', handleResize)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  pieChart?.dispose()
  barChart?.dispose()
  ringChart?.dispose()
})

function handleResize() {
  pieChart?.resize()
  barChart?.resize()
  ringChart?.resize()
}

// ---------------- 图表1：文件类型占比饼图 ----------------
function initPie(list) {
  pieChart = echarts.init(pieRef.value)
  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 篇 ({d}%)' },
    legend: {
      bottom: 0,
      icon: 'circle',
      textStyle: { color: '#86909C', fontSize: 12 },
    },
    color: BLUE_PALETTE,
    series: [
      {
        name: '文件类型占比',
        type: 'pie',
        radius: ['42%', '66%'],
        center: ['50%', '48%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#FFFFFF', borderWidth: 2 },
        label: { color: '#4E5969', fontSize: 12 },
        labelLine: { lineStyle: { color: '#C9CDD4' } },
        data: list.map((item) => ({
          name: item.type.toUpperCase(),
          value: item.count,
        })),
      },
    ],
  })
}

// ---------------- 图表2：近30天入库趋势柱状图 ----------------
// 接口只返回「有入库记录的日期」，这里补零成完整 30 天，
// 否则柱子会被均匀摊在整条轴上，看不出时间间隔
function buildDailySeries(list, days = 30) {
  const countMap = new Map(list.map((item) => [item.date, item.count]))
  const today = new Date()
  const series = []
  for (let i = days - 1; i >= 0; i -= 1) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i)
    const key =
      `${d.getFullYear()}-` +
      `${String(d.getMonth() + 1).padStart(2, '0')}-` +
      `${String(d.getDate()).padStart(2, '0')}`
    series.push({ date: key, count: countMap.get(key) || 0 })
  }
  return series
}

function initBar(list) {
  const series = buildDailySeries(list)
  barChart = echarts.init(barRef.value)
  barChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 48, right: 24, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: series.map((item) => item.date.slice(5)), // MM-DD
      axisLine: { lineStyle: { color: '#E5E6EB' } },
      axisTick: { show: false },
      // 30 个日期按每 5 天显示一个，避免标签挤在一起
      axisLabel: { color: '#86909C', fontSize: 11, margin: 10, interval: 4 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#86909C', fontSize: 11 },
      splitLine: { lineStyle: { color: '#F2F3F5' } },
    },
    series: [
      {
        name: '入库文档数',
        type: 'bar',
        barMaxWidth: 20,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#6249D4' },
            { offset: 1, color: '#2B4FE0' },
          ]),
          borderRadius: [3, 3, 0, 0],
        },
        data: series.map((item) => item.count),
      },
    ],
  })
}

// ---------------- 图表3：向量化占比环形图 ----------------
function initRing({ success, failed }) {
  ringChart = echarts.init(ringRef.value)
  ringChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 篇 ({d}%)' },
    legend: {
      bottom: 0,
      icon: 'circle',
      textStyle: { color: '#86909C', fontSize: 12 },
    },
    color: [SUCCESS_BLUE, FAILED_GRAY],
    series: [
      {
        name: '向量化占比',
        type: 'pie',
        radius: ['48%', '68%'],
        center: ['50%', '48%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#FFFFFF', borderWidth: 2 },
        label: { color: '#4E5969', fontSize: 12 },
        labelLine: { lineStyle: { color: '#C9CDD4' } },
        data: [
          { name: '向量化成功', value: success },
          { name: '向量化失败', value: failed },
        ],
      },
    ],
  })
}
</script>

<style scoped>
/* 内边距由 .page-container 统一提供，这里不再重复声明，避免左右留白翻倍 */
.statistics-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ------- 统计卡片 ------- */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  min-height: 104px;
  padding: 20px 24px;
  background-color: var(--bg-card);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
  transition: box-shadow 0.2s ease;
}

.stat-card:hover {
  box-shadow: var(--shadow-hover);
}

.stat-value {
  font-size: 30px;
  font-weight: 700;
  color: var(--text-main);
  line-height: 1.1;
  letter-spacing: 0.5px;
  font-variant-numeric: tabular-nums;
}

.stat-success {
  color: var(--brand-color);
}

.stat-failed {
  color: var(--danger);
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
}

/* ------- 图表区域 ------- */
.chart-area {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chart-row {
  display: grid;
  gap: 16px;
}

/* 两个环形图等高并排 */
.chart-row-donut {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.chart-card {
  display: flex;
  flex-direction: column;
  padding: 18px 20px 12px;
  background-color: var(--bg-card);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
}

/* 卡片头：标题左、统计口径右 */
.chart-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.chart-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-main);
}

.chart-hint {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.chart-box {
  height: 300px;
}

.chart-box-wide {
  height: 280px;
}

/* ------- 空状态 ------- */
.chart-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 320px;
  background-color: var(--bg-card);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
  color: var(--text-secondary);
  gap: 12px;
  font-size: 14px;
}

/* ------- 窄屏自适应 ------- */
@media (max-width: 1280px) {
  .stat-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chart-row-donut {
    grid-template-columns: 1fr;
  }
}
</style>
