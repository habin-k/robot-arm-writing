import axios from 'axios'

// HMI에 접속한 host를 그대로 따라감 (localhost로 열면 localhost, 172.23.x로 열면 172.23.x).
// WiFi가 바뀌어 IP가 달라져도 자동으로 맞춰지므로 하드코딩 불필요.
// 서버(uvicorn)와 HMI(vite)가 같은 노트북에서 뜬다는 전제. 다른 PC면 아래 상수로 교체.
const SERVER_PORT = 8000
const BASE_URL = `${window.location.protocol}//${window.location.hostname}:${SERVER_PORT}`
// 고정 서버로 강제하려면 위 줄 대신: const BASE_URL = 'http://172.23.0.201:8000'

export const api = axios.create({ baseURL: BASE_URL })

export const setAuthToken = (token) => {
  if (token) api.defaults.headers.common['Authorization'] = `Bearer ${token}`
  else delete api.defaults.headers.common['Authorization']
}

export const WS_URL = BASE_URL.replace('http', 'ws')
