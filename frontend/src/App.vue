<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <p class="eyebrow">ETF Rebalance</p>
        <h1>ETF再均衡回测系统</h1>
      </div>
      <div class="topbar-stats">
        <div class="stat-pill">
          <span>ETF</span>
          <strong>{{ selectedETFs.length }}</strong>
        </div>
        <div class="stat-pill">
          <span>列表</span>
          <strong>{{ etfList.length }}</strong>
        </div>
        <div class="stat-pill">
          <span>权重</span>
          <strong :class="{ warn: !canRunBacktest }">{{ totalWeight.toFixed(4) }}</strong>
        </div>
        <div class="stat-pill wide">
          <span>区间</span>
          <strong>{{ dateRange[0] }} - {{ dateRange[1] }}</strong>
        </div>
      </div>
      <div class="topbar-actions">
        <el-button :icon="Refresh" :loading="etfLoading" @click="refreshETFList">刷新ETF</el-button>
        <el-button
          type="primary"
          :icon="Promotion"
          :loading="loading"
          :disabled="!canRunBacktest"
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
          :can-run-backtest="canRunBacktest"
          :loading="loading"
          :etf-loading="etfLoading"
          :etf-count="etfList.length"
          :etf-source-label="etfSourceLabel"
          @add-etf="showETFDialog = true"
          @quick-add="quickAddETF"
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
          :benchmark-code="normalizeCode(backtestConfig.benchmark_code)"
        />
        <div v-else class="empty-results">
          <el-empty description="运行回测后查看结果" :image-size="170" />
        </div>
      </section>
    </main>

    <EtfPickerDialog
      v-model="showETFDialog"
      :etf-list="etfList"
      @select="selectETF"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Promotion, Refresh } from '@element-plus/icons-vue'
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
const etfList = ref([])
const etfLoadError = ref('')
const selectedETFs = ref(defaultETFPortfolio.map(item => ({ ...item })))
const dateRange = ref(['2015-01-01', today])
const backtestConfig = ref({
  rebalance_freq: 'month_start',
  initial_capital: 100000,
  buy_fee_rate: 0.0003,
  sell_fee_rate: 0.0003,
  benchmark_code: '000001.SH'
})
const backtestResult = ref(null)

const totalWeight = computed(() => (
  selectedETFs.value.reduce((sum, etf) => sum + Number(etf.weight || 0), 0)
))

const canRunBacktest = computed(() => (
  selectedETFs.value.length > 0 &&
  dateRange.value &&
  dateRange.value.length === 2 &&
  Math.abs(totalWeight.value - 1) <= 0.0001
))

const etfSourceLabel = computed(() => {
  if (etfLoading.value) return '正在加载ETF列表'
  if (etfLoadError.value) return 'ETF列表加载失败'
  if (!etfList.value.length) return 'ETF列表未加载'
  const sources = new Set(etfList.value.map(item => item.source || 'local'))
  if (sources.has('tushare')) return '来源: Tushare'
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

  normalizeWeights()
  showETFDialog.value = false
}

const quickAddETF = (keyword) => {
  const normalizedKeyword = normalizeSearchText(keyword)
  const found = etfList.value.find(item => {
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

  if (!found) {
    ElMessage.warning('未匹配到ETF，请打开选择列表搜索')
    return
  }
  selectETF(found)
}

const removeETF = (index) => {
  selectedETFs.value.splice(index, 1)
  normalizeWeights()
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
  if (!canRunBacktest.value) return

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
      initial_capital: backtestConfig.value.initial_capital,
      buy_fee_rate: backtestConfig.value.buy_fee_rate,
      sell_fee_rate: backtestConfig.value.sell_fee_rate,
      benchmark_code: normalizeCode(backtestConfig.value.benchmark_code)
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
  background: var(--page-bg);
  min-height: 100vh;
}

.topbar {
  align-items: center;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 24px;
  justify-content: space-between;
  min-height: 84px;
  padding: 18px 28px;
}

.brand {
  min-width: 0;
}

.eyebrow {
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  margin-bottom: 4px;
  text-transform: uppercase;
}

h1 {
  color: var(--text);
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0;
}

.topbar-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
}

.topbar-actions {
  align-items: center;
  display: flex;
  gap: 10px;
}

.stat-pill {
  align-items: center;
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  gap: 10px;
  min-height: 38px;
  padding: 8px 12px;
}

.stat-pill span {
  color: var(--muted);
  font-size: 12px;
}

.stat-pill strong {
  color: var(--text);
  font-size: 14px;
  font-weight: 750;
  white-space: nowrap;
}

.stat-pill strong.warn {
  color: var(--warning);
}

.workspace {
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(360px, 430px) minmax(0, 1fr);
  margin: 0 auto;
  max-width: 1680px;
  padding: 22px;
}

.config-frame,
.results-frame,
.empty-results {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow);
  min-width: 0;
}

.config-frame {
  align-self: start;
  padding: 18px;
  position: sticky;
  top: 16px;
}

.results-frame {
  padding: 18px;
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

  .workspace {
    gap: 14px;
    padding: 14px;
  }

  .config-frame,
  .results-frame {
    padding: 14px;
  }

  .stat-pill.wide {
    width: 100%;
  }

  .topbar-actions {
    align-items: stretch;
    width: 100%;
  }

  h1 {
    font-size: 21px;
  }
}
</style>
