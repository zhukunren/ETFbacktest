<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <el-button class="nav-icon" :icon="Menu" text aria-label="菜单" />
        <span class="brand-mark">
          <el-icon><DataAnalysis /></el-icon>
        </span>
        <h1>ETF再均衡回测系统</h1>
      </div>
      <div class="topbar-stats">
        <div class="stat-pill">
          <span>ETF数量</span>
          <strong>{{ selectedETFs.length }}</strong>
        </div>
        <div class="stat-pill stat-pill-success">
          <span>总ETF权重</span>
          <strong :class="{ warn: !isWeightValid }">{{ formatPercentWeight(totalWeight) }}</strong>
        </div>
        <div class="stat-pill stat-pill-info">
          <span>基准权重</span>
          <strong :class="{ warn: !isBenchmarkWeightValid }">{{ formatPercentWeight(totalBenchmarkWeight) }}</strong>
        </div>
        <div class="stat-pill stat-pill-range wide">
          <span>回测区间</span>
          <el-icon><Calendar /></el-icon>
          <strong>{{ dateRange[0] || '--' }} ~ {{ dateRange[1] || '--' }}</strong>
        </div>
      </div>
      <div class="topbar-actions">
        <el-button
          type="primary"
          :icon="VideoPlay"
          :loading="loading"
          :disabled="!canSubmitBacktest"
          @click="runBacktest"
        >
          运行回测
        </el-button>
      </div>
    </header>

    <main class="workspace">
      <aside class="config-frame">
        <BacktestConfigPanel
          :selected-etfs="selectedETFs"
          :date-range="dateRange"
          :config="backtestConfig"
          :total-weight="totalWeight"
          :can-run-backtest="canSubmitBacktest"
          :is-weight-valid="isWeightValid"
          :loading="loading"
          :etf-list="etfList"
          :etf-loading="etfLoading"
          :etf-count="etfList.length"
          :etf-source-label="etfSourceLabel"
          :benchmark-total-weight="totalBenchmarkWeight"
          :is-benchmark-weight-valid="isBenchmarkWeightValid"
          @add-etf="openETFDialog()"
          @quick-add="quickAddETF"
          @select-etf="selectETF"
          @remove-etf="removeETF"
          @normalize-weights="normalizeWeights"
          @equal-weight="equalWeight"
          @reset-portfolio="resetPortfolio"
          @clear-portfolio="clearPortfolio"
          @refresh-etfs="refreshETFList"
          @weight-change="updateETFWeight"
          @update:date-range="updateDateRange"
          @update:config="updateConfig"
          @run="runBacktest"
        />
      </aside>

      <section class="results-frame">
        <BacktestResults
          v-if="backtestResult"
          :result="backtestResult"
          :benchmark-label="benchmarkLabel"
        />
        <div v-else class="empty-results">
          <el-empty description="运行回测后查看结果" :image-size="170" />
        </div>
      </section>
    </main>

    <EtfPickerDialog
      v-model="showETFDialog"
      :etf-list="etfList"
      :initial-search-text="etfDialogSearchText"
      @select="selectETF"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Calendar, DataAnalysis, Menu, VideoPlay } from '@element-plus/icons-vue'
import BacktestConfigPanel from './components/BacktestConfigPanel.vue'
import BacktestResults from './components/BacktestResults.vue'
import EtfPickerDialog from './components/EtfPickerDialog.vue'
import { getETFList, runBacktest as runBacktestApi } from './api/backtest'
import { defaultETFPortfolio } from './constants/portfolio'
import { normalizeCode } from './utils/securities'

const today = new Date().toISOString().slice(0, 10)

const loading = ref(false)
const etfLoading = ref(false)
const showETFDialog = ref(false)
const etfDialogSearchText = ref('')
const etfList = ref([])
const etfLoadError = ref('')
const selectedETFs = ref(defaultETFPortfolio.map(item => ({ ...item })))
const dateRange = ref(['2015-01-01', today])
const backtestConfig = ref({
  rebalance_freq: 'month_start',
  buy_fee_rate: 0.0003,
  sell_fee_rate: 0.0003,
  benchmark_list: [
    { stock_code: '000001.SH', name: '上证指数', weight: 0.5 },
    { stock_code: '000300.SH', name: '沪深300', weight: 0.5 }
  ]
})
const backtestResult = ref(null)

const totalWeight = computed(() => (
  selectedETFs.value.reduce((sum, etf) => sum + Number(etf.weight || 0), 0)
))

const isWeightValid = computed(() => Math.abs(totalWeight.value - 1) <= 0.0001)

const totalBenchmarkWeight = computed(() => (
  (backtestConfig.value.benchmark_list || []).reduce((sum, item) => sum + Number(item.weight || 0), 0)
))

const isBenchmarkWeightValid = computed(() => Math.abs(totalBenchmarkWeight.value - 1) <= 0.0001)

const formatPercentWeight = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`

const canSubmitBacktest = computed(() => (
  selectedETFs.value.length > 0 &&
  dateRange.value &&
  dateRange.value.length === 2
))

const benchmarkLabel = computed(() => {
  const benchmarkList = backtestConfig.value.benchmark_list || []
  if (benchmarkList.length === 1) {
    const item = benchmarkList[0]
    return item.name || normalizeCode(item.stock_code)
  }
  return '基准组合'
})

const etfSourceLabel = computed(() => {
  if (etfLoading.value) return '正在加载ETF列表'
  if (etfLoadError.value) return 'ETF列表加载失败'
  if (!etfList.value.length) return 'ETF列表未加载'
  const sources = new Set(etfList.value.map(item => item.source || 'local'))
  if (sources.has('akshare')) return '来源: AkShare'
  if (sources.has('excel')) return '来源: 本地Excel'
  return `来源: ${Array.from(sources).join(', ')}`
})

const loadETFList = async () => {
  etfLoading.value = true
  etfLoadError.value = ''
  try {
    etfList.value = await getETFList()
    hydrateSelectedETFNames()
  } catch (error) {
    etfLoadError.value = error.message
    ElMessage.error('加载ETF列表失败: ' + error.message)
  } finally {
    etfLoading.value = false
  }
}

const refreshETFList = () => {
  loadETFList()
}

const hydrateSelectedETFNames = () => {
  const byCode = new Map(etfList.value.map(item => [normalizeCode(item.stock_code), item]))
  selectedETFs.value.forEach(item => {
    const found = byCode.get(normalizeCode(item.stock_code))
    if (found?.stock_name) {
      item.stock_name = found.stock_name
    }
  })
}

const openETFDialog = (searchText = '') => {
  etfDialogSearchText.value = searchText
  showETFDialog.value = true
}

const selectETF = (row) => {
  const code = normalizeCode(row.stock_code)
  if (selectedETFs.value.find(e => normalizeCode(e.stock_code) === code)) {
    ElMessage.warning('该ETF已添加')
    return
  }

  selectedETFs.value.push({
    stock_code: code,
    stock_name: row.stock_name,
    source: row.source,
    weight: 0
  })

  showETFDialog.value = false
}

const quickAddETF = (keyword) => {
  const normalizedKeyword = normalizeSearchText(keyword)
  const matches = etfList.value.filter(item => {
    const fields = [
      item.stock_code,
      String(item.stock_code || '').replace('.', ''),
      item.stock_name,
      item.index_name,
      item.mgr_name,
      item.exchange
    ]
    return fields.some(field => normalizeSearchText(field).includes(normalizedKeyword))
  })

  if (!matches.length) {
    ElMessage.warning('未匹配到ETF，请打开选择列表搜索')
    return
  }

  const normalizedCode = normalizeCode(keyword)
  const exactCodeMatch = matches.find(item => (
    normalizeCode(item.stock_code) === normalizedCode ||
    normalizeSearchText(String(item.stock_code || '').replace('.', '')) === normalizedKeyword
  ))
  if (exactCodeMatch) {
    selectETF(exactCodeMatch)
    return
  }

  const exactNameMatches = matches.filter(item => (
    normalizeSearchText(item.stock_name) === normalizedKeyword
  ))
  if (exactNameMatches.length === 1) {
    selectETF(exactNameMatches[0])
    return
  }

  if (matches.length > 1) {
    ElMessage.warning(`匹配到 ${matches.length} 只ETF，请在列表中选择`)
    openETFDialog(keyword)
    return
  }

  const found = matches[0]
  selectETF(found)
}

const removeETF = (index) => {
  selectedETFs.value.splice(index, 1)
}

const updateETFWeight = (index, weight) => {
  if (!selectedETFs.value[index]) return
  selectedETFs.value[index].weight = weight
}

const updateDateRange = (value) => {
  dateRange.value = value || []
}

const updateConfig = (value) => {
  backtestConfig.value = value
}

const equalWeight = () => {
  if (!selectedETFs.value.length) return
  const weight = 1 / selectedETFs.value.length
  selectedETFs.value = selectedETFs.value.map(etf => ({
    ...etf,
    weight
  }))
}

const resetPortfolio = () => {
  selectedETFs.value = defaultETFPortfolio.map(item => ({ ...item }))
  hydrateSelectedETFNames()
}

const clearPortfolio = () => {
  selectedETFs.value = []
}

const normalizeWeights = () => {
  const total = totalWeight.value
  if (total <= 0 || selectedETFs.value.length === 0) return

  selectedETFs.value = selectedETFs.value.map(etf => ({
    ...etf,
    weight: etf.weight / total
  }))
}

const normalizeSearchText = (value) => (
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
)

const runBacktest = async () => {
  if (!canSubmitBacktest.value) return
  if (!isWeightValid.value) {
    ElMessage.warning(`权重总和必须为1，当前为 ${totalWeight.value.toFixed(4)}`)
    return
  }

  const benchmarkList = (backtestConfig.value.benchmark_list || [])
    .map(item => ({
      stock_code: normalizeCode(item.stock_code),
      weight: Number(item.weight || 0)
    }))
    .filter(item => item.stock_code)

  if (!benchmarkList.length) {
    ElMessage.warning('请至少选择一个基准指数')
    return
  }

  if (!isBenchmarkWeightValid.value) {
    ElMessage.warning(`基准权重总和必须为1，当前为 ${totalBenchmarkWeight.value.toFixed(4)}`)
    return
  }

  loading.value = true
  try {
    const params = {
      etf_list: selectedETFs.value.map(e => ({
        stock_code: normalizeCode(e.stock_code),
        weight: e.weight
      })),
      start_date: dateRange.value[0],
      end_date: dateRange.value[1],
      rebalance_freq: backtestConfig.value.rebalance_freq,
      buy_fee_rate: backtestConfig.value.buy_fee_rate,
      sell_fee_rate: backtestConfig.value.sell_fee_rate,
      benchmark_list: benchmarkList
    }

    backtestResult.value = await runBacktestApi(params)
    ElMessage.success('回测完成')
  } catch (error) {
    ElMessage.error('回测失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

loadETFList()
</script>

<style scoped>
.app-shell {
  background: #F5F7FA;
  min-height: 100vh;
}

.topbar {
  align-items: center;
  background: var(--surface);
  border-bottom: 1px solid #E5E7EB;
  display: flex;
  gap: 20px;
  justify-content: space-between;
  min-height: 64px;
  padding: 12px 20px;
}

.brand {
  align-items: center;
  display: flex;
  gap: 14px;
  min-width: 0;
}

.nav-icon {
  color: #111827;
  font-size: 20px;
  height: 34px;
  width: 34px;
}

.brand-mark {
  align-items: center;
  background: linear-gradient(135deg, #2563EB, #1D4ED8);
  border-radius: 8px;
  color: #FFFFFF;
  display: inline-flex;
  flex: 0 0 auto;
  font-size: 20px;
  height: 36px;
  justify-content: center;
  width: 36px;
}

h1 {
  color: var(--text);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.25;
  margin: 0;
  white-space: nowrap;
}

.topbar-stats {
  display: flex;
  flex: 1;
  flex-wrap: nowrap;
  gap: 12px;
  justify-content: flex-end;
  min-width: 0;
}

.topbar-actions {
  align-items: center;
  display: flex;
  flex: 0 0 auto;
  gap: 10px;
}

.topbar-actions :deep(.el-button) {
  font-size: 14px;
  height: 38px;
  min-width: 90px;
}

.stat-pill {
  align-items: center;
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  display: flex;
  gap: 6px;
  min-height: 38px;
  padding: 8px 12px;
  white-space: nowrap;
}

.stat-pill-success {
  background: #F0FDF4;
  border-color: #D1FAE5;
}

.stat-pill-info {
  background: #EFF6FF;
  border-color: #DBEAFE;
}

.stat-pill-range {
  background: #FFFFFF;
  max-width: 330px;
  overflow: hidden;
}

.stat-pill span {
  color: #6B7280;
  font-size: 13px;
  font-weight: 600;
}

.stat-pill strong {
  color: var(--text);
  font-size: 14px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stat-pill-success strong {
  color: #15803D;
}

.stat-pill-info strong {
  color: #2563EB;
}

.stat-pill strong.warn {
  color: var(--warning);
}

.workspace {
  display: grid;
  gap: 12px;
  grid-template-columns: 400px minmax(0, 1fr);
  margin: 0 auto;
  max-width: 1920px;
  padding: 16px;
}

.config-frame,
.results-frame,
.empty-results {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  min-width: 0;
  overflow: hidden;
}

.config-frame {
  align-self: start;
  padding: 0;
  position: sticky;
  top: 10px;
}

.results-frame {
  padding: 0;
}

.empty-results {
  align-items: center;
  display: flex;
  min-height: 540px;
  justify-content: center;
}

@media (max-width: 1180px) {
  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .topbar-stats,
  .topbar-actions {
    justify-content: flex-start;
  }

  .topbar-stats {
    flex-wrap: wrap;
  }

  .workspace {
    grid-template-columns: 1fr;
  }

  .config-frame {
    position: static;
  }
}

@media (max-width: 640px) {
  .topbar {
    padding: 16px;
  }

  .brand {
    gap: 10px;
  }

  .workspace {
    gap: 14px;
    padding: 14px;
  }

  .config-frame,
  .results-frame {
    padding: 0;
  }

  .stat-pill.wide {
    width: 100%;
  }

  .topbar-actions {
    align-items: stretch;
    width: 100%;
  }

  h1 {
    font-size: 20px;
  }
}
</style>
