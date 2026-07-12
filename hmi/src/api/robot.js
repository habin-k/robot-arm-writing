import { api } from './client'

export const login = (data) => api.post('/auth/login', data)

export const goHome = () => api.post('/robot/home')

export const emergencyStop = () => api.post('/robot/emergency-stop')

export const errorReset = () => api.post('/robot/error-reset')

// 수동 복구(MANUAL_REQUIRED) 후 작업 재시도. 성공 시 자율모드 복귀 + run_once 재실행.
export const retryTask = () => api.post('/robot/retry')

export const jog = (data) => api.post('/robot/jog', data)

export const grip = () => api.post('/robot/grip')

export const ungrip = () => api.post('/robot/ungrip')
