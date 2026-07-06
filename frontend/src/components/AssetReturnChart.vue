<template>
  <div ref="chartRef" class="chart-surface"></div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  assetReturnSeries: {
    type: Object,
    default: () => ({})
  },
  selectedCodes: {
    type: Array,
    default: () => []
  },
  active: {
    type: Boolean,
    default: true
  }
})

const chartRef = ref(null)
let chartInstance = null
let resizeObserver = null
let resizeTimer = null

const scheduleResize = () => {
  if (!props.active) return
  window.clearTimeout(resizeTimer)
  resizeTimer = window.setTimeout(() => {
    if (chartInstance) {
      chartInstance.resize()
    } else if (chartRef.value?.clientWidth > 0) {
      renderChart()
    }
  }, 80)
}

const renderChart = async () => {
  await nextTick()
  if (!chartRef.value || !props.active) return

  if (chartRef.value.clientWidth === 0) {
    scheduleResize()
    return
  }

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const codes = props.selectedCodes.length
    ? props.selectedCodes
    : Object.keys(props.assetReturnSeries).slice(0, 6)

  chartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      valueFormatter: value => Number(value).toFixed(4)
    },
    legend: {
      top: 0,
      type: 'scroll',
      data: codes
    },
    grid: {
      left: 8,
      right: 18,
      bottom: 46,
      top: 42,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      axisLabel: { hideOverlap: true }
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: {
        lineStyle: { color: '#E5E7EB' }
      }
    },
    dataZoom: [
      {
        type: 'inside',
        throttle: 50
      },
      {
        type: 'slider',
        height: 18,
        bottom: 8
      }
    ],
    series: codes.map(code => ({
      name: code,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2 },
      data: (props.assetReturnSeries[code] || []).map(item => [item.date, item.net_value])
    }))
  }, true)

  scheduleResize()
}

const resizeChart = () => {
  scheduleResize()
}

watch(
  () => [props.assetReturnSeries, props.selectedCodes, props.active],
  renderChart,
  { deep: true }
)

onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    scheduleResize()
  })
  if (chartRef.value) {
    resizeObserver.observe(chartRef.value)
  }

  renderChart()
  window.addEventListener('resize', resizeChart)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeChart)
  window.clearTimeout(resizeTimer)
  resizeObserver?.disconnect()
  resizeObserver = null
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<style scoped>
.chart-surface {
  display: block;
  height: 380px;
  min-height: 300px;
  min-width: 0;
  width: 100%;
}
</style>
