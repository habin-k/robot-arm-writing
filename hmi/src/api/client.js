import axios from 'axios'

// HMI에 접속한 host를 그대로 따라감 (localhost로 열면 localhost, 172.23.x로 열면 172.23.x).
// WiFi가 바뀌어 IP가 달라져도 자동으로 맞춰지므로 하드코딩 불필요.
// 서버(uvicorn)와 HMI(vite)가 같은 노트북에서 뜬다는 전제. 다른 PC면 아래 상수로 교체.
const SERVER_PORT = 8000
const BASE_URL = `${window.location.protocol}//${window.location.hostname}:${SERVER_PORT}`
// 고정 서버로 강제하려면 위 줄 대신: const BASE_URL = 'http://172.23.0.201:8000'

export const api = axios.create({ baseURL: BASE_URL })

// 로그인 토큰은 sessionStorage 에 보관한다.
// → 새로고침해도 유지되고, 창(탭)을 완전히 닫으면 사라진다 (브라우저 세션과 동일한 동작).
const TOKEN_KEY = 'authToken'

export const getStoredToken = () => sessionStorage.getItem(TOKEN_KEY)

export const setAuthToken = (token) => {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`
    sessionStorage.setItem(TOKEN_KEY, token)
  } else {
    delete api.defaults.headers.common['Authorization']
    sessionStorage.removeItem(TOKEN_KEY)
  }
}

// 새로고침 직후 App 이 마운트되기 전에도 요청에 토큰이 실리도록, 모듈 로드 시 복원한다.
{
  const stored = getStoredToken()
  if (stored) api.defaults.headers.common['Authorization'] = `Bearer ${stored}`
}

export const WS_URL = BASE_URL.replace('http', 'ws')
