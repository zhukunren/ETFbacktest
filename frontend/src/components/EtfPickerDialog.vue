<template>
  <el-dialog
    :model-value="modelValue"
    title="选择ETF"
    width="min(720px, 92vw)"
    class="etf-picker-dialog"
    @update:model-value="value => $emit('update:modelValue', value)"
    @closed="searchText = ''"
  >
    <div class="picker-toolbar">
      <el-input
        v-model="searchText"
        placeholder="搜索ETF代码或名称"
        :prefix-icon="Search"
        clearable
      />
      <span class="result-count">{{ filteredETFList.length }} 项</span>
    </div>

    <el-table
      :data="filteredETFList"
      max-height="420"
      row-key="stock_code"
      class="picker-table"
      @row-click="row => $emit('select', row)"
    >
      <el-table-column prop="stock_code" label="代码" width="130" />
      <el-table-column prop="stock_name" label="名称" min-width="180" />
      <el-table-column prop="index_name" label="跟踪指数" min-width="160" show-overflow-tooltip />
      <el-table-column label="来源" width="96">
        <template #default="scope">
          <el-tag size="small" effect="plain">{{ sourceLabel(scope.row.source) }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    required: true
  },
  etfList: {
    type: Array,
    required: true
  }
})

defineEmits(['update:modelValue', 'select'])

const searchText = ref('')

const filteredETFList = computed(() => {
  const keyword = normalizeSearchText(searchText.value)
  if (!keyword) return props.etfList
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

const normalizeSearchText = (value) => (
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
)

const sourceLabel = (source) => {
  if (source === 'tushare') return 'Tushare'
  if (source === 'excel') return 'Excel'
  return '本地'
}
</script>

<style scoped>
.picker-toolbar {
  align-items: center;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1fr) auto;
  margin-bottom: 14px;
}

.result-count {
  color: var(--muted);
  font-size: 13px;
  white-space: nowrap;
}

.picker-table {
  cursor: pointer;
}

@media (max-width: 640px) {
  .picker-toolbar {
    grid-template-columns: 1fr;
  }
}
</style>
