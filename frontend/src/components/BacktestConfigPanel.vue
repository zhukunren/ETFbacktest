<template>
  <section class="config-panel">
    <div class="section-block">
      <div class="section-title">
        <h3>ETF权重</h3>
      </div>

      <div class="quick-add">
        <div class="quick-add-field">
          <el-input
            v-model="quickAddText"
            placeholder="搜索并添加ETF（支持代码/名称）"
            :prefix-icon="Search"
            clearable
            @keyup.enter="submitQuickAdd"
          />
          <div v-if="showQuickAddResults" class="quick-add-results">
            <button
              v-for="etf in quickAddMatches"
              :key="etf.stock_code"
              type="button"
              class="quick-add-option"
              @mousedown.prevent="selectQuickAddOption(etf)"
            >
              <span class="option-code">{{ etf.stock_code }}</span>
              <span class="option-name">{{ etf.stock_name }}</span>
            </button>
            <div v-if="quickAddMoreCount > 0" class="quick-add-more">
              还有 {{ quickAddMoreCount }} 项匹配
            </div>
          </div>
          <div v-else-if="showQuickAddEmpty" class="quick-add-results empty">
            <span>未匹配到ETF</span>
          </div>
        </div>
        <el-button type="primary" :icon="Plus" @click="submitQuickAdd">添加</el-button>
      </div>

      <div v-if="selectedEtfs.length" class="etf-list">
        <div class="table-head etf-table-head">
          <span>代码</span>
          <span>名称</span>
          <span>权重</span>
        </div>
        <div
          v-for="(etf, index) in selectedEtfs"
          :key="etf.stock_code"
          class="etf-row"
        >
          <span class="etf-code">{{ etf.stock_code }}</span>
          <span class="etf-name">{{ etf.stock_name }}</span>
          <div class="etf-controls">
            <el-input-number
              :model-value="etf.weight"
              :min="0"
              :max="1"
              :step="0.01"
              :precision="4"
              :formatter="formatPercentInput"
              :parser="parsePercentInput"
              size="small"
              controls-position="right"
              @update:model-value="value => $emit('weight-change', index, Number(value || 0))"
            />
            <el-button
              type="danger"
              :icon="Delete"
              size="small"
              circle
              aria-label="删除ETF"
              @click="$emit('remove-etf', index)"
            />
          </div>
        </div>
      </div>

      <el-empty v-else description="请添加ETF" :image-size="72" />

      <div class="weight-footer">
        <span>合计权重</span>
        <strong :class="{ warn: !isWeightValid }">{{ formatPercentWeight(totalWeight) }}</strong>
        <div class="weight-actions">
          <el-button plain :icon="PieChart" @click="$emit('equal-weight')">等权</el-button>
          <el-button text :icon="RefreshRight" @click="$emit('normalize-weights')">
            归一化
          </el-button>
          <el-dropdown trigger="click">
            <el-button text>更多</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="$emit('reset-portfolio')">重置默认组合</el-dropdown-item>
                <el-dropdown-item @click="$emit('clear-portfolio')">清空组合</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>

    <div class="section-block">
      <div class="section-title">
        <h3>参数</h3>
      </div>

      <el-form label-position="left" label-width="86px" size="default" class="param-form">
        <el-form-item label="回测区间" class="full-field">
          <el-date-picker
            :model-value="dateRange"
            type="daterange"
            range-separator="~"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            @update:model-value="value => $emit('update:dateRange', value)"
          />
        </el-form-item>

        <el-form-item label="再均衡频率">
          <el-select
            :model-value="config.rebalance_freq"
            @update:model-value="value => updateConfig('rebalance_freq', value)"
          >
            <el-option label="不调仓" value="none" />
            <el-option label="月初调仓" value="month_start" />
            <el-option label="月末调仓" value="month_end" />
            <el-option label="周初调仓" value="week_start" />
            <el-option label="周末调仓" value="week_end" />
          </el-select>
        </el-form-item>

        <el-form-item label="买入手续费">
          <el-input-number
            :model-value="config.buy_fee_rate"
            :min="0"
            :max="0.1"
            :step="0.0001"
            :precision="4"
            controls-position="right"
            @update:model-value="value => updateConfig('buy_fee_rate', Number(value || 0))"
          />
        </el-form-item>

        <el-form-item label="卖出手续费">
          <el-input-number
            :model-value="config.sell_fee_rate"
            :min="0"
            :max="0.1"
            :step="0.0001"
            :precision="4"
            controls-position="right"
            @update:model-value="value => updateConfig('sell_fee_rate', Number(value || 0))"
          />
        </el-form-item>

      </el-form>
    </div>

    <div class="section-block">
      <div class="section-title">
        <h3>基准组合</h3>
        <el-button plain :icon="Plus" @click="addBenchmark">添加</el-button>
      </div>

      <div class="benchmark-list">
        <div class="table-head benchmark-table-head">
          <span>代码</span>
          <span>名称</span>
          <span>权重</span>
        </div>
        <div
          v-for="(benchmark, index) in benchmarkList"
          :key="`${benchmark.stock_code || 'benchmark'}-${index}`"
          class="benchmark-row"
        >
          <el-select
            :model-value="benchmark.stock_code"
            filterable
            allow-create
            default-first-option
            clearable
            placeholder="指数代码"
            @update:model-value="value => updateBenchmark(index, 'stock_code', value)"
          >
            <el-option
              v-for="option in benchmarkOptions"
              :key="option.stock_code"
              :label="`${option.name} ${option.stock_code}`"
              :value="option.stock_code"
            />
          </el-select>
          <span class="benchmark-name">{{ benchmark.name || '--' }}</span>
          <div class="benchmark-controls">
            <el-input-number
              :model-value="benchmark.weight"
              :min="0"
              :max="1"
              :step="0.01"
              :precision="4"
              size="small"
              controls-position="right"
              @update:model-value="value => updateBenchmark(index, 'weight', Number(value || 0))"
            />
            <el-button
              type="danger"
              :icon="Delete"
              size="small"
              circle
              aria-label="删除基准"
              :disabled="benchmarkList.length <= 1"
              @click="removeBenchmark(index)"
            />
          </div>
        </div>
      </div>

      <div class="weight-footer benchmark-footer">
        <span>合计权重</span>
        <strong :class="{ warn: !isBenchmarkWeightValid }">{{ benchmarkTotalWeight.toFixed(4) }}</strong>
        <div class="weight-actions">
          <el-button text @click="equalBenchmarkWeight">等权</el-button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Delete, PieChart, Plus, RefreshRight, Search } from '@element-plus/icons-vue'

const props = defineProps({
  selectedEtfs: {
    type: Array,
    required: true
  },
  dateRange: {
    type: Array,
    required: true
  },
  config: {
    type: Object,
    required: true
  },
  totalWeight: {
    type: Number,
    required: true
  },
  canRunBacktest: {
    type: Boolean,
    required: true
  },
  isWeightValid: {
    type: Boolean,
    default: true
  },
  loading: {
    type: Boolean,
    required: true
  },
  etfList: {
    type: Array,
    default: () => []
  },
  etfLoading: {
    type: Boolean,
    default: false
  },
  etfCount: {
    type: Number,
    default: 0
  },
  etfSourceLabel: {
    type: String,
    default: 'ETF列表未加载'
  },
  benchmarkTotalWeight: {
    type: Number,
    default: 0
  },
  isBenchmarkWeightValid: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits([
  'add-etf',
  'quick-add',
  'select-etf',
  'remove-etf',
  'normalize-weights',
  'equal-weight',
  'reset-portfolio',
  'clear-portfolio',
  'refresh-etfs',
  'weight-change',
  'update:dateRange',
  'update:config',
  'run'
])

const quickAddText = ref('')
const quickAddLimit = 12
const benchmarkOptions = [
  { stock_code: '000001.SH', name: '上证指数' },
  { stock_code: '000016.SH', name: '上证50' },
  { stock_code: '000300.SH', name: '沪深300' },
  { stock_code: '000905.SH', name: '中证500' },
  { stock_code: '000852.SH', name: '中证1000' },
  { stock_code: '399006.SZ', name: '创业板指' }
]

const benchmarkList = computed(() => (
  props.config.benchmark_list?.length
    ? props.config.benchmark_list
    : [{ stock_code: '000001.SH', name: '上证指数', weight: 1 }]
))

const normalizedQuickAddText = computed(() => normalizeSearchText(quickAddText.value))

const allQuickAddMatches = computed(() => {
  const keyword = normalizedQuickAddText.value
  if (!keyword) return []

  return props.etfList.filter(etf => {
    const fields = [
      etf.stock_code,
      String(etf.stock_code || '').replace('.', ''),
      etf.stock_name,
      etf.index_name,
      etf.mgr_name,
      etf.exchange
    ]
    return fields.some(field => normalizeSearchText(field).includes(keyword))
  })
})

const quickAddMatches = computed(() => allQuickAddMatches.value.slice(0, quickAddLimit))
const quickAddMoreCount = computed(() => Math.max(0, allQuickAddMatches.value.length - quickAddLimit))
const showQuickAddResults = computed(() => normalizedQuickAddText.value && quickAddMatches.value.length > 0)
const showQuickAddEmpty = computed(() => normalizedQuickAddText.value && !allQuickAddMatches.value.length)
const formatPercentWeight = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`
const formatPercentInput = (value) => {
  if (value === '' || value === null || value === undefined) return ''
  return `${(Number(value || 0) * 100).toFixed(2)}%`
}
const parsePercentInput = (value) => {
  const normalized = String(value || '').replace('%', '').trim()
  if (!normalized) return ''
  return String(Number(normalized) / 100)
}

const updateConfig = (key, value) => {
  emit('update:config', {
    ...props.config,
    [key]: value
  })
}

const updateBenchmarkList = (list) => {
  updateConfig('benchmark_list', list)
}

const updateBenchmark = (index, key, value) => {
  const next = benchmarkList.value.map(item => ({ ...item }))
  if (!next[index]) return

  next[index][key] = value
  if (key === 'stock_code') {
    const matched = benchmarkOptions.find(option => option.stock_code === value)
    next[index].name = matched?.name || value
  }
  updateBenchmarkList(next)
}

const addBenchmark = () => {
  updateBenchmarkList([
    ...benchmarkList.value.map(item => ({ ...item })),
    { stock_code: '', name: '', weight: 0 }
  ])
}

const removeBenchmark = (index) => {
  if (benchmarkList.value.length <= 1) return
  updateBenchmarkList(benchmarkList.value.filter((_, itemIndex) => itemIndex !== index))
}

const equalBenchmarkWeight = () => {
  if (!benchmarkList.value.length) return
  const weight = 1 / benchmarkList.value.length
  updateBenchmarkList(benchmarkList.value.map(item => ({
    ...item,
    weight
  })))
}

const submitQuickAdd = () => {
  const value = quickAddText.value.trim()
  if (!value) return
  emit('quick-add', value)
  if (allQuickAddMatches.value.length <= 1) quickAddText.value = ''
}

const selectQuickAddOption = (etf) => {
  emit('select-etf', etf)
  quickAddText.value = ''
}

const normalizeSearchText = (value) => (
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
)
</script>

<style scoped>
.config-panel {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
}

.section-title,
.weight-footer,
.weight-actions {
  display: flex;
  align-items: center;
}

.weight-actions {
  gap: 6px;
}

h3 {
  color: #111827;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
  margin: 0;
}

.section-block {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 20px 18px;
}

.section-block:last-child {
  border-bottom: 0;
}

.section-title {
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.quick-add {
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 1fr) auto;
  margin-bottom: 10px;
  position: relative;
}

.quick-add-field {
  min-width: 0;
  position: relative;
}

.quick-add-results {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.14);
  display: grid;
  left: 0;
  max-height: 316px;
  overflow: auto;
  padding: 6px;
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  z-index: 30;
}

.quick-add-results.empty {
  color: var(--muted);
  font-size: 13px;
  padding: 10px 12px;
}

.quick-add-option {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 6px;
  color: var(--text);
  cursor: pointer;
  display: grid;
  gap: 8px;
  grid-template-columns: 92px minmax(0, 1fr);
  min-height: 34px;
  padding: 7px 8px;
  text-align: left;
}

.quick-add-option:hover {
  background: var(--surface-soft);
}

.option-code {
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
}

.option-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-add-more {
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 12px;
  margin-top: 4px;
  padding: 8px;
}

.etf-list,
.benchmark-list {
  border: 1px solid var(--border);
  border-radius: 6px;
  display: grid;
  overflow: hidden;
}

.table-head,
.etf-row,
.benchmark-row {
  align-items: center;
  display: grid;
  gap: 8px;
}

.table-head {
  background: #F8FAFC;
  border-bottom: 1px solid var(--border);
  color: #374151;
  font-size: 13px;
  font-weight: 700;
  min-height: 32px;
  padding: 0 10px;
}

.etf-table-head,
.etf-row {
  grid-template-columns: 100px minmax(0, 1fr) 174px;
}

.benchmark-table-head,
.benchmark-row {
  grid-template-columns: 118px minmax(0, 1fr) 174px;
}

.etf-row,
.benchmark-row {
  background: #FFFFFF;
  border-bottom: 1px solid #EEF2F7;
  min-height: 38px;
  padding: 4px 10px;
}

.etf-row:last-child,
.benchmark-row:last-child {
  border-bottom: 0;
}

.etf-code {
  color: var(--accent);
  font-size: 14px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.etf-name,
.benchmark-name {
  color: #1F2937;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.etf-controls {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.benchmark-controls {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.weight-footer {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  color: #374151;
  font-size: 14px;
  justify-content: space-between;
  margin-top: 10px;
  min-height: 36px;
  padding: 7px 10px;
}

.weight-footer strong {
  color: #15803D;
  font-weight: 800;
  margin-right: auto;
  padding-left: 10px;
}

.weight-footer strong.warn {
  color: var(--warning);
}

.param-form {
  display: grid;
  gap: 10px;
  grid-template-columns: 1fr;
}

.full-field {
  grid-column: 1 / -1;
}

:deep(.el-date-editor),
:deep(.el-select),
:deep(.el-input-number),
:deep(.el-input) {
  width: 100%;
}

:deep(.el-form-item) {
  align-items: center;
  margin-bottom: 0;
}

:deep(.el-form-item__label) {
  color: #374151;
  font-weight: 650;
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper) {
  min-height: 31px;
}

:deep(.el-input-number.is-controls-right .el-input__wrapper) {
  padding-left: 8px;
  padding-right: 32px;
}

:deep(.el-input-number--small) {
  width: 126px;
}

:deep(.el-button.is-circle) {
  height: 28px;
  width: 28px;
}

@media (max-width: 720px) {
  .section-title {
    align-items: stretch;
    flex-direction: column;
  }

  .etf-table-head,
  .etf-row,
  .benchmark-table-head,
  .benchmark-row {
    grid-template-columns: 1fr;
  }

  .table-head {
    display: none;
  }

  .etf-controls,
  .benchmark-controls {
    justify-content: space-between;
  }

  .param-form {
    grid-template-columns: 1fr;
  }

  .quick-add {
    grid-template-columns: 1fr;
  }
}
</style>
