<template>
  <section class="results-panel">
    <div class="results-toolbar">
      <div class="tab-strip">
        <button
          v-for="tab in tabs"
          :key="tab.name"
          type="button"
          class="tab-button"
          :class="{ active: activeTab === tab.name }"
          @click="activeTab = tab.name"
        >
          {{ tab.label }}
        </button>
      </div>
      <div class="heading-actions">
        <el-button :icon="Download" @click="exportNetValueCsv">导出图表</el-button>
        <el-button :icon="Grid" @click="exportJson">导出数据</el-button>
      </div>
    </div>

    <template v-if="activeTab === 'overview'">
        <div class="metrics-grid">
          <div
            v-for="metric in metrics"
            :key="metric.key"
            class="metric-card"
            :class="`metric-${metric.tone}`"
          >
            <div class="metric-title">
              <span>{{ metric.label }}</span>
              <el-icon><InfoFilled /></el-icon>
            </div>
            <div class="metric-body">
              <span class="metric-icon">
                <el-icon><component :is="metric.icon" /></el-icon>
              </span>
              <strong :class="metric.className">{{ metric.value }}</strong>
            </div>
            <p>{{ metric.hint }}</p>
          </div>
        </div>

        <div v-if="result.warnings.length" class="warning-list">
          <el-alert
            v-for="warning in result.warnings"
            :key="warning"
            :title="warning"
            type="warning"
            :closable="false"
            show-icon
          />
        </div>

        <div class="result-section chart-section">
          <div class="section-title chart-title">
            <div>
              <h3>净值曲线</h3>
              <el-icon><InfoFilled /></el-icon>
            </div>
            <div class="chart-tools">
              <el-button
                v-for="range in chartRanges"
                :key="range.value"
                :type="activeChartRange === range.value ? 'primary' : ''"
                plain
                @click="activeChartRange = range.value"
              >
                {{ range.label }}
              </el-button>
              <el-button :icon="FullScreen" text aria-label="全屏" />
            </div>
          </div>
          <NetValueChart
            :net-value-series="filteredNetValueSeries"
            :benchmark-series="filteredBenchmarkSeries"
            :benchmark-label="benchmarkLabel"
          />
          <p class="chart-note">提示：图表显示复权净值，考虑了分红再投资。</p>
        </div>
    </template>

    <template v-else-if="activeTab === 'assets'">
        <div class="result-section">
          <div class="section-title">
            <h3>单资产净值</h3>
            <el-tag effect="plain">{{ assetCodes.length }} 只资产</el-tag>
          </div>

          <div class="asset-filter">
            <el-checkbox-group v-model="selectedAssetCodes">
              <el-checkbox-button
                v-for="code in assetCodes"
                :key="code"
                :label="code"
              >
                {{ code }}
              </el-checkbox-button>
            </el-checkbox-group>
          </div>

          <AssetReturnChart
            v-if="activeTab === 'assets'"
            :asset-return-series="result.asset_return_series"
            :selected-codes="visibleAssetCodes"
            :active="activeTab === 'assets'"
          />
        </div>
    </template>

    <template v-else>
        <div class="result-section">
          <div class="section-title">
            <h3>再均衡记录</h3>
            <div class="section-actions">
              <el-tag effect="plain">{{ result.rebalance_records.length }} 次调仓</el-tag>
              <el-button size="small" :icon="Download" @click="exportRecordsCsv">导出记录</el-button>
            </div>
          </div>
          <el-table
            :data="result.rebalance_records"
            max-height="520"
            size="small"
            class="rebalance-table"
          >
            <el-table-column prop="date" label="日期" width="118" fixed />
            <el-table-column label="调仓前" width="124" align="right">
              <template #default="scope">
                {{ formatNumber(scope.row.capital_before) }}
              </template>
            </el-table-column>
            <el-table-column label="调仓后" width="124" align="right">
              <template #default="scope">
                {{ formatNumber(scope.row.capital_after) }}
              </template>
            </el-table-column>
            <el-table-column label="现金" width="124" align="right">
              <template #default="scope">
                {{ formatNumber(scope.row.cash_after) }}
              </template>
            </el-table-column>
            <el-table-column label="费用" width="110" align="right">
              <template #default="scope">
                {{ formatNumber(scope.row.fee) }}
              </template>
            </el-table-column>
            <el-table-column label="持仓详情" min-width="360">
              <template #default="scope">
                <div class="holdings-list">
                  <div
                    v-for="(holding, code) in scope.row.holdings"
                    :key="code"
                    class="holding-line"
                  >
                    <span class="holding-code">{{ code }}</span>
                    <el-tag
                      v-if="holding.cash_substitute"
                      size="small"
                      type="warning"
                      effect="plain"
                    >
                      现金替代
                    </el-tag>
                    <template v-else>
                      <span>{{ formatNumber(holding.shares, 0) }}股</span>
                      <span>@ {{ formatNumber(holding.price) }}</span>
                      <span>{{ formatNumber(holding.value) }}</span>
                    </template>
                    <span class="target-weight">{{ (holding.target_weight * 100).toFixed(2) }}%</span>
                  </div>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
    </template>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import {
  Aim,
  BottomRight,
  DataLine,
  Download,
  FullScreen,
  Grid,
  Histogram,
  InfoFilled,
  Money,
  TrendCharts
} from '@element-plus/icons-vue'
import AssetReturnChart from './AssetReturnChart.vue'
import NetValueChart from './NetValueChart.vue'
import { formatNumber, formatPercent } from '../utils/format'

const props = defineProps({
  result: {
    type: Object,
    required: true
  },
  benchmarkLabel: {
    type: String,
    required: true
  }
})

const activeTab = ref('overview')
const activeChartRange = ref('all')
const selectedAssetCodes = ref([])
const tabs = [
  { name: 'overview', label: '概览' },
  { name: 'assets', label: '资产曲线' },
  { name: 'records', label: '调仓记录' }
]
const chartRanges = [
  { label: '近1年', value: '1y', years: 1 },
  { label: '近3年', value: '3y', years: 3 },
  { label: '近5年', value: '5y', years: 5 },
  { label: '全部', value: 'all', years: null }
]

const metrics = computed(() => {
  const metricsValue = props.result.metrics || {}
  return [
    {
      key: 'total_return',
      label: '总收益率',
      value: formatPercent(metricsValue.total_return),
      className: Number(metricsValue.total_return) >= 0 ? 'positive' : 'negative',
      hint: `年化收益 ${formatPercent(metricsValue.annual_return)}`,
      icon: TrendCharts,
      tone: 'blue'
    },
    {
      key: 'annual_return',
      label: '年化收益率',
      value: formatPercent(metricsValue.annual_return),
      className: Number(metricsValue.annual_return) >= 0 ? 'positive' : 'negative',
      hint: '日均收益 --',
      icon: Histogram,
      tone: 'green'
    },
    {
      key: 'max_drawdown',
      label: '最大回撤',
      value: formatPercent(metricsValue.max_drawdown),
      className: 'negative',
      hint: '回撤开始 --',
      icon: BottomRight,
      tone: 'red'
    },
    {
      key: 'volatility',
      label: '波动率',
      value: formatPercent(metricsValue.volatility),
      className: '',
      hint: '年化波动率',
      icon: DataLine,
      tone: 'purple'
    },
    {
      key: 'sharpe_ratio',
      label: '夏普比率',
      value: formatNumber(metricsValue.sharpe_ratio),
      className: '',
      hint: '无风险利率 2.50%',
      icon: Aim,
      tone: 'teal'
    },
    {
      key: 'final_net_value',
      label: '期末净值',
      value: formatNumber(metricsValue.final_net_value, 4),
      className: 'primary',
      hint: '初始净值 1.0000',
      icon: Money,
      tone: 'blue'
    }
  ]
})

const assetCodes = computed(() => Object.keys(props.result.asset_return_series || {}))
const visibleAssetCodes = computed(() => (
  selectedAssetCodes.value.length
    ? selectedAssetCodes.value
    : assetCodes.value.slice(0, 6)
))

const filteredNetValueSeries = computed(() => (
  filterSeriesByRange(props.result.net_value_series || [], activeChartRange.value)
))

const filteredBenchmarkSeries = computed(() => (
  filterSeriesByRange(props.result.benchmark_series || [], activeChartRange.value)
))

watch(assetCodes, (codes) => {
  selectedAssetCodes.value = codes.slice(0, 6)
}, { immediate: true })

watch(
  () => props.result,
  () => {
    activeChartRange.value = 'all'
  }
)

const filterSeriesByRange = (series, rangeValue) => {
  const range = chartRanges.find(item => item.value === rangeValue)
  if (!range?.years || !series.length) return series

  const lastDate = latestSeriesDate([
    props.result.net_value_series || [],
    props.result.benchmark_series || []
  ])
  if (!lastDate) return series

  const cutoff = new Date(lastDate.getTime())
  cutoff.setFullYear(cutoff.getFullYear() - range.years)
  const cutoffText = formatDateKey(cutoff)
  return series.filter(item => String(item.date || '') >= cutoffText)
}

const latestSeriesDate = (seriesList) => {
  const dates = seriesList
    .flatMap(series => series.map(item => parseDateKey(item.date)).filter(Boolean))
  if (!dates.length) return null
  return new Date(Math.max(...dates.map(date => date.getTime())))
}

const parseDateKey = (value) => {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return null
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
}

const formatDateKey = (date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const exportJson = () => {
  downloadText(
    `backtest-result-${timestamp()}.json`,
    JSON.stringify(props.result, null, 2),
    'application/json;charset=utf-8'
  )
}

const exportNetValueCsv = () => {
  const benchmarkByDate = new Map(
    (props.result.benchmark_series || []).map(item => [item.date, item.net_value])
  )
  const rows = [
    ['date', 'strategy_net_value', 'benchmark_net_value'],
    ...(props.result.net_value_series || []).map(item => [
      item.date,
      item.net_value,
      benchmarkByDate.get(item.date) ?? ''
    ])
  ]
  downloadCsv(`net-value-${timestamp()}.csv`, rows)
}

const exportRecordsCsv = () => {
  const rows = [
    ['date', 'capital_before', 'capital_after', 'cash_after', 'turnover', 'fee'],
    ...(props.result.rebalance_records || []).map(record => [
      record.date,
      record.capital_before,
      record.capital_after,
      record.cash_after,
      record.turnover,
      record.fee
    ])
  ]
  downloadCsv(`rebalance-records-${timestamp()}.csv`, rows)
}

const downloadCsv = (filename, rows) => {
  const csv = rows.map(row => row.map(escapeCsvCell).join(',')).join('\n')
  downloadText(filename, `\uFEFF${csv}`, 'text/csv;charset=utf-8')
}

const escapeCsvCell = (value) => {
  const text = String(value ?? '')
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

const downloadText = (filename, content, type) => {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

const timestamp = () => new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
</script>

<style scoped>
.results-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
  padding: 20px;
}

.heading-actions,
.section-title,
.section-actions,
.results-toolbar,
.tab-strip {
  align-items: center;
  display: flex;
}

.results-toolbar,
.section-title {
  justify-content: space-between;
}

.heading-actions,
.section-actions {
  gap: 10px;
  flex-wrap: wrap;
}

h3 {
  color: var(--text);
  font-size: 17px;
  font-weight: 700;
  margin: 0;
}

.results-toolbar {
  border-bottom: 1px solid #E5E7EB;
  min-height: 50px;
  padding: 0 0 12px;
}

.tab-strip {
  gap: 30px;
}

.tab-button {
  background: transparent;
  border: 0;
  color: #6B7280;
  cursor: pointer;
  font-size: 15px;
  font-weight: 600;
  line-height: 42px;
  padding: 0;
  position: relative;
  transition: color 0.2s;
}

.tab-button:hover {
  color: #111827;
}

.tab-button.active {
  color: #2563EB;
  font-weight: 700;
}

.tab-button.active::after {
  background: #2563EB;
  border-radius: 2px;
  bottom: -13px;
  content: "";
  height: 2px;
  left: 0;
  position: absolute;
  right: 0;
}

.metrics-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.metric-card {
  background: #FFFFFF;
  border: 1px solid var(--border);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 130px;
  padding: 20px;
}

.metric-title,
.metric-body {
  align-items: center;
  display: flex;
}

.metric-title {
  color: #6B7280;
  font-size: 14px;
  font-weight: 600;
  gap: 6px;
  justify-content: space-between;
}

.metric-title .el-icon {
  color: #9CA3AF;
  font-size: 16px;
}

.metric-body {
  gap: 12px;
  flex: 1;
  align-items: flex-end;
}

.metric-icon {
  align-items: center;
  border-radius: 10px;
  display: inline-flex;
  flex: 0 0 auto;
  font-size: 22px;
  height: 40px;
  justify-content: center;
  width: 40px;
}

.metric-card strong {
  color: var(--text);
  font-size: 32px;
  font-weight: 700;
  line-height: 1;
  overflow-wrap: anywhere;
}

.metric-card p {
  color: #9CA3AF;
  font-size: 13px;
  margin: 0;
  margin-top: auto;
}

.metric-card strong.positive {
  color: #15803D;
}

.metric-card strong.negative {
  color: #DC2626;
}

.metric-card strong.primary {
  color: #2563EB;
}

.metric-blue .metric-icon {
  background: #DBEAFE;
  color: #2563EB;
}

.metric-green .metric-icon {
  background: #DCFCE7;
  color: #16A34A;
}

.metric-red .metric-icon {
  background: #FEE2E2;
  color: #DC2626;
}

.metric-purple .metric-icon {
  background: #EDE9FE;
  color: #7C3AED;
}

.metric-teal .metric-icon {
  background: #CCFBF1;
  color: #0F766E;
}

.warning-list {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
}

.result-section {
  background: transparent;
  border: 0;
  border-radius: 0;
  padding: 0;
}

.section-title {
  margin-bottom: 16px;
}

.chart-section {
  min-height: 500px;
}

.chart-title > div:first-child {
  align-items: center;
  display: flex;
  gap: 8px;
}

.chart-title .el-icon {
  color: #6B7280;
}

.chart-tools {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chart-tools :deep(.el-button) {
  min-width: 70px;
}

.chart-tools :deep(.el-button.is-text) {
  min-width: 34px;
}

.chart-note {
  color: #9CA3AF;
  font-size: 13px;
  margin: 6px 0 0;
}

.asset-filter {
  margin-bottom: 12px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.rebalance-table {
  width: 100%;
}

.holdings-list {
  display: grid;
  gap: 6px;
}

.holding-line {
  align-items: center;
  color: var(--muted);
  display: flex;
  flex-wrap: wrap;
  font-size: 12px;
  gap: 8px;
  line-height: 1.5;
}

.holding-code {
  color: var(--text);
  font-weight: 700;
}

.target-weight {
  color: var(--accent);
  font-weight: 700;
}

@media (max-width: 1500px) {
  .metrics-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .results-toolbar {
    align-items: stretch;
    flex-direction: column;
    gap: 8px;
  }
}

@media (max-width: 640px) {
  .section-title {
    align-items: flex-start;
    flex-direction: column;
  }

  .metrics-grid {
    grid-template-columns: 1fr;
  }

  .metric-card strong {
    font-size: 21px;
  }
}
</style>
