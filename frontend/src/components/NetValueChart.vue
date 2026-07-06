<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, watch, ref } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  netValueSeries: {
    type: Array,
    required: true
  },
  benchmarkSeries: {
    type: Array,
    default: () => []
  },
  benchmarkCode: {
    type: String,
    required: true
  }
})

const chartRef = ref(null)
let chartInstance = null

const renderChart = async () => {
  await nextTick()
  if (!chartRef.value) return

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const strategySource = props.netValueSeries.map(item => [item.date, item.net_value])
  const benchmarkSource = props.benchmarkSeries.map(item => [item.date, item.net_value])

  chartInstance.setOption({
    color: ['#2563EB', '#16A34A'],
    tooltip: {
      trigger: 'axis',
      valueFormatter: value => Number(value).toFixed(4)
    },
    legend: {
      top: 0,
      right: 0,
      data: ['策略净值', props.benchmarkCode]
    },
    dataset: [
      { id: 'strategy', source: strategySource },
      { id: 'benchmark', source: benchmarkSource }
    ],
    grid: {
      left: 8,
      right: 18,
      bottom: 8,
      top: 42,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      axisLabel: {
        hideOverlap: true
      }
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: {
        lineStyle: {
          color: '#E5E7EB'
        }
      }
    },
    series: [
      {
        name: '策略净值',
        type: 'line',
        datasetId: 'strategy',
        encode: { x: 0, y: 1 },
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2.5 },
        areaStyle: { opacity: 0.08 }
      },
      {
        name: props.benchmarkCode,
        type: 'line',
        datasetId: 'benchmark',
        encode: { x: 0, y: 1 },
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2 }
      }
    ]
  }, true)
}

const resizeChart = () => {
  chartInstance?.resize()
}

watch(
  () => [props.netValueSeries, props.benchmarkSeries, props.benchmarkCode],
  renderChart,
  { deep: true }
)

onMounted(() => {
  renderChart()
  window.addEventListener('resize', resizeChart)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeChart)
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<style scoped>
.chart-surface {
  height: 420px;
  min-height: 320px;
  width: 100%;
}

@media (max-width: 720px) {
  .chart-surface {
    height: 340px;
  }
}
</style>
