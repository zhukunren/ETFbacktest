<template>
  <section class="results-panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Workbench</p>
        <h2>回测工作台</h2>
      </div>
      <div class="heading-actions">
        <el-button :icon="Download" @click="exportNetValueCsv">导出净值</el-button>
        <el-button :icon="Document" @click="exportJson">导出JSON</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="result-tabs">
      <el-tab-pane label="概览" name="overview">
        <div class="metrics-grid">
          <div
            v-for="metric in metrics"
            :key="metric.key"
            class="metric-card"
          >
            <span class="metric-label">{{ metric.label }}</span>
            <strong :class="metric.className">{{ metric.value }}</strong>
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

        <div class="result-section">
          <div class="section-title">
            <h3>净值曲线</h3>
            <el-tag effect="plain">{{ result.net_value_series.length }} 个交易日</el-tag>
          </div>
          <NetValueChart
            :net-value-series="result.net_value_series"
            :benchmark-series="result.benchmark_series"
            :benchmark-code="benchmarkCode"
          />
        </div>
      </el-tab-pane>

      <el-tab-pane label="资产曲线" name="assets" lazy>
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
      </el-tab-pane>

      <el-tab-pane label="调仓记录" name="records">
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
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Document, Download } from '@element-plus/icons-vue'
import AssetReturnChart from './AssetReturnChart.vue'
import NetValueChart from './NetValueChart.vue'
import { formatNumber, formatPercent } from '../utils/format'

const props = defineProps({
  result: {
    type: Object,
    required: true
  },
  benchmarkCode: {
    type: String,
    required: true
  }
})

const activeTab = ref('overview')
const selectedAssetCodes = ref([])

const metrics = computed(() => {
  const metricsValue = props.result.metrics || {}
  return [
    {
      key: 'total_return',
      label: '总收益率',
      value: formatPercent(metricsValue.total_return),
      className: Number(metricsValue.total_return) >= 0 ? 'positive' : 'negative'
    },
    {
      key: 'annual_return',
      label: '年化收益率',
      value: formatPercent(metricsValue.annual_return),
      className: Number(metricsValue.annual_return) >= 0 ? 'positive' : 'negative'
    },
    {
      key: 'max_drawdown',
      label: '最大回撤',
      value: formatPercent(metricsValue.max_drawdown),
      className: 'negative'
    },
    {
      key: 'volatility',
      label: '波动率',
      value: formatPercent(metricsValue.volatility),
      className: ''
    },
    {
      key: 'sharpe_ratio',
      label: '夏普比率',
      value: formatNumber(metricsValue.sharpe_ratio),
      className: ''
    },
    {
      key: 'final_value',
      label: '期末资产',
      value: formatNumber(metricsValue.final_value),
      className: ''
    }
  ]
})

const assetCodes = computed(() => Object.keys(props.result.asset_return_series || {}))
const visibleAssetCodes = computed(() => (
  selectedAssetCodes.value.length
    ? selectedAssetCodes.value
    : assetCodes.value.slice(0, 6)
))

watch(assetCodes, (codes) => {
  selectedAssetCodes.value = codes.slice(0, 6)
}, { immediate: true })

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
    ['date', 'strategy_net_value', `${props.benchmarkCode}_net_value`],
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
  gap: 16px;
  min-width: 0;
}

.panel-heading,
.heading-actions,
.section-title,
.section-actions {
  align-items: center;
  display: flex;
  gap: 12px;
}

.panel-heading,
.section-title {
  justify-content: space-between;
}

.heading-actions,
.section-actions {
  flex-wrap: wrap;
}

.eyebrow {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 4px;
  text-transform: uppercase;
}

h2,
h3 {
  color: var(--text);
  font-weight: 650;
  margin: 0;
}

h2 {
  font-size: 22px;
}

h3 {
  font-size: 15px;
}

.result-tabs {
  min-width: 0;
}

.metrics-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 16px;
}

.metric-card {
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: grid;
  gap: 8px;
  min-height: 88px;
  padding: 14px;
}

.metric-label {
  color: var(--muted);
  font-size: 13px;
}

.metric-card strong {
  color: var(--text);
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
  overflow-wrap: anywhere;
}

.metric-card strong.positive {
  color: var(--profit);
}

.metric-card strong.negative {
  color: var(--loss);
}

.warning-list {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
}

.result-section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}

.section-title {
  margin-bottom: 12px;
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

@media (max-width: 980px) {
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .panel-heading,
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
