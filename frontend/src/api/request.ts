import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, InternalAxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

export interface RequestOptions extends AxiosRequestConfig {
  _silent?: boolean
}

type InternalRequestOptions = InternalAxiosRequestConfig & {
  _silent?: boolean
}

const request: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

request.interceptors.request.use(
  (config: InternalRequestOptions) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

request.interceptors.response.use(
  (response: AxiosResponse) => {
    if (response.config.responseType === 'blob') {
      return response
    }
    const { data } = response
    // 如果有 code 字段，检查是否为 0
    if (data.code !== undefined && data.code !== 0) {
      if (!(response.config as RequestOptions)._silent) {
        ElMessage.error(data.message || '请求失败')
      }
      return Promise.reject(new Error(data.message))
    }
    return data
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
      return Promise.reject(error)
    }
    // 如果请求标记了 _silent，不弹错误提示
    if (error.config?._silent) {
      return Promise.reject(error)
    }
    const msg = error.response?.data?.detail || error.response?.data?.message || error.message || '网络错误'
    ElMessage.error(msg)
    return Promise.reject(error)
  },
)

export default request
