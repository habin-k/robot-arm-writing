import { api } from './client'

export const login = (data) => api.post('/auth/login', data)

export const goHome = () => api.post('/robot/home')

export const emergencyStop = () => api.post('/robot/emergency-stop')

export const errorReset = () => api.post('/robot/error-reset')

export const jog = (data) => api.post('/robot/jog', data)
