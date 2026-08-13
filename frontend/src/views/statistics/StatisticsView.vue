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
      <!-- 第一行：左右两图 -->
      <div class="chart-row">
        <div class="chart-card">
          <div class="chart-title">各类文件类型占比</div>
          <div ref="pieRef" class="chart-box"></div>
        </div>
        <div class="chart-card">
          <div class="chart-title">近30天每日入库文档数量趋势</div>
          <div ref="barRef" class="chart-box"></div>
        </div>
      </div>

      <!-- 第二行：居中环形图 -->
      <div class="chart-row chart-row-center">
        <div class="chart-card chart-card-center">
          <div class="chart-title">文档向量化成功与失败占比</div>
          <div ref="ringRef" class="chart-box"></div>
        </div>
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
        radius: ['40%', '68%'],
        center: ['50%', '45%'],
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
function initBar(list) {
  barChart = echarts.init(barRef.value)
  barChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 40, right: 20, top: 30, bottom: 24 },
    xAxis: {
      type: 'category',
      data: list.map((item) => item.date.slice(5)), // MM-DD
      axisLine: { lineStyle: { color: '#E5E6EB' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909C', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      name: '数量',
      nameTextStyle: { color: '#86909C' },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#86909C', fontSize: 11 },
      splitLine: { lineStyle: { color: '#F2F3F5' } },
    },
    series: [
      {
        name: '入库文档数',
        type: 'bar',
        barMaxWidth: 14,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#6249D4' },
            { offset: 1, color: '#2B4FE0' },
          ]),
          borderRadius: [3, 3, 0, 0],
        },
        data: list.map((item) => item.count),
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
        radius: ['48%', '70%'],
        center: ['50%', '45%'],
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
.statistics-page {
  padding: 20px;
}

/* ------- 统计卡片 ------- */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.stat-card {
  background-color: var(--bg-card);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
  padding: 22px 24px;
}

.stat-value {
  font-size: 30px;
  font-weight: 700;
  color: var(--text-main);
  line-height: 1.2;
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
  margin-top: 10px;
  font-size: 13px;
  color: var(--text-secondary);
}

/* ------- 图表区域 ------- */
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.chart-row-center {
  grid-template-columns: 1fr;
}

.chart-card {
  background-color: var(--bg-card);
  border-radius: 8px;
  box-shadow: var(--shadow-card);
  padding: 18px 20px;
}

.chart-card-center {
  width: 100%;
  max-width: 560px;
  margin: 0 auto;
}

.chart-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 12px;
}

.chart-box {
  height: 300px;
}

/* ------- 空状态 ------- */
.chart-empty {
  display: flex;
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
</style>
