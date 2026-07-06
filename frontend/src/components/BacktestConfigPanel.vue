<template>
  <section class="config-panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Portfolio</p>
        <h2>回测配置</h2>
      </div>
      <div class="heading-actions">
        <el-button :icon="Refresh" :loading="etfLoading" @click="$emit('refresh-etfs')">
          刷新
        </el-button>
        <el-button type="primary" :icon="Plus" @click="$emit('add-etf')">
          添加ETF
        </el-button>
      </div>
    </div>

    <div class="source-strip">
      <span>{{ etfCount }} 只可选ETF</span>
      <span>{{ etfSourceLabel }}</span>
    </div>

    <div class="section-block">
      <div class="section-title">
        <h3>ETF权重</h3>
        <el-tag :type="weightTagType" effect="plain">
          {{ totalWeight.toFixed(4) }}
        </el-tag>
      </div>

      <div class="quick-add">
        <el-input
          v-model="quickAddText"
          placeholder="输入代码或名称快速添加"
          :prefix-icon="Search"
          clearable
          @keyup.enter="submitQuickAdd"
        />
        <el-button :icon="Plus" @click="submitQuickAdd">添加</el-button>
      </div>

      <div v-if="selectedEtfs.length" class="etf-list">
        <div
          v-for="(etf, index) in selectedEtfs"
          :key="etf.stock_code"
          class="etf-row"
        >
          <div class="etf-meta">
            <span class="etf-code">{{ etf.stock_code }}</span>
            <span class="etf-name">{{ etf.stock_name }}</span>
          </div>
          <div class="etf-controls">
            <el-input-number
              :model-value="etf.weight"
              :min="0"
              :max="1"
              :step="0.01"
              :precision="4"
              size="small"
              controls-position="right"
              @update:model-value="value => $emit('weight-change', index, Number(value || 0))"
              @change="$emit('normalize-weights')"
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
        <span>{{ selectedEtfs.length }} 只ETF</span>
        <div class="weight-actions">
          <el-button text @click="$emit('equal-weight')">等权</el-button>
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

      <el-form label-position="top" size="default" class="param-form">
        <el-form-item label="回测周期" class="full-field">
          <el-date-picker
            :model-value="dateRange"
            type="daterange"
            range-separator="至"
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
            <el-option label="不再平衡" value="none" />
            <el-option label="月初" value="month_start" />
            <el-option label="月末" value="month_end" />
            <el-option label="周初" value="week_start" />
            <el-option label="周末" value="week_end" />
          </el-select>
        </el-form-item>

        <el-form-item label="初始资金">
          <el-input-number
            :model-value="config.initial_capital"
            :min="1000"
            :step="10000"
            controls-position="right"
            @update:model-value="value => updateConfig('initial_capital', Number(value || 0))"
          />
        </el-form-item>

        <el-form-item label="买入费率">
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

        <el-form-item label="卖出费率">
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

        <el-form-item label="基准代码" class="full-field">
          <el-input
            :model-value="config.benchmark_code"
            @update:model-value="value => updateConfig('benchmark_code', value)"
          />
        </el-form-item>
      </el-form>
    </div>

    <div class="run-footer">
      <div class="run-meta">
        <span>{{ dateRange?.[0] || '--' }}</span>
        <span>至</span>
        <span>{{ dateRange?.[1] || '--' }}</span>
      </div>
      <el-button
        type="primary"
        size="large"
        :icon="Promotion"
        :loading="loading"
        :disabled="!canRunBacktest"
        @click="$emit('run')"
      >
        运行回测
      </el-button>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Delete, Plus, Promotion, Refresh, RefreshRight, Search } from '@element-plus/icons-vue'

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
  loading: {
    type: Boolean,
    required: true
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
  }
})

const emit = defineEmits([
  'add-etf',
  'quick-add',
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

const weightTagType = computed(() => (
  Math.abs(props.totalWeight - 1) <= 0.0001 ? 'success' : 'warning'
))

const updateConfig = (key, value) => {
  emit('update:config', {
    ...props.config,
    [key]: value
  })
}

const submitQuickAdd = () => {
  const value = quickAddText.value.trim()
  if (!value) return
  emit('quick-add', value)
  quickAddText.value = ''
}
</script>

<style scoped>
.config-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.panel-heading,
.heading-actions,
.section-title,
.weight-footer,
.weight-actions,
.run-footer,
.run-meta {
  display: flex;
  align-items: center;
}

.panel-heading {
  justify-content: space-between;
  gap: 16px;
}

.heading-actions,
.weight-actions {
  gap: 8px;
}

.source-strip {
  align-items: center;
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--muted);
  display: flex;
  font-size: 13px;
  gap: 10px;
  justify-content: space-between;
  padding: 10px 12px;
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

.section-block {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}

.section-title {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.etf-list {
  display: grid;
  gap: 10px;
}

.quick-add {
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 1fr) auto;
  margin-bottom: 12px;
}

.etf-row {
  align-items: center;
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1fr) auto;
  min-height: 58px;
  padding: 10px 12px;
}

.etf-meta {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.etf-code {
  color: var(--accent);
  font-weight: 700;
}

.etf-name {
  color: var(--muted);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.etf-controls {
  align-items: center;
  display: flex;
  gap: 8px;
}

.weight-footer {
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 13px;
  justify-content: space-between;
  margin-top: 14px;
  padding-top: 10px;
}

.param-form {
  display: grid;
  gap: 0 14px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.full-field {
  grid-column: 1 / -1;
}

.run-footer {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  justify-content: space-between;
  padding: 14px 16px;
}

.run-meta {
  color: var(--muted);
  font-size: 13px;
  gap: 6px;
  min-width: 0;
}

:deep(.el-date-editor),
:deep(.el-select),
:deep(.el-input-number),
:deep(.el-input) {
  width: 100%;
}

@media (max-width: 720px) {
  .panel-heading,
  .heading-actions,
  .run-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .etf-row {
    grid-template-columns: 1fr;
  }

  .etf-controls {
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
