import apiClient from './client'

/**
 * 获取ETF列表
 */
export const getETFList = () => {
  return apiClient.get('/etf/list')
}

/**
 * 执行回测
 * @param {Object} params - 回测参数
 */
export const runBacktest = (params) => {
  return apiClient.post('/backtest/run', params)
}

/**
 * 健康检查
 */
export const healthCheck = () => {
  return apiClient.get('/health')
}
