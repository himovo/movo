import axios, { type AxiosInstance, type CreateAxiosDefaults } from 'axios'


export function createApiClient(config: CreateAxiosDefaults = {}): AxiosInstance {
  const client = axios.create(config)
  client.interceptors.request.use((request) => {
    const token = typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : ''
    if (token && !request.headers.Authorization) {
      request.headers.Authorization = `Bearer ${token}`
    }
    return request
  })
  return client
}
