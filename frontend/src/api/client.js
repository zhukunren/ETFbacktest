import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  config => {
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    const message = error.response?.data?.detail ||
      (error.request ? '无法连接后端服务，请确认后端已启动，且前端 API 代理配置正确' : error.message) ||
      '请求失败'
    return Promise.reject(new Error(message))
  }
)

export default apiClient
