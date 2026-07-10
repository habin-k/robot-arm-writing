import { api } from './client'

export const getFonts = () => api.get('/fonts')

export const previewWriting = (data) => api.post('/writing/preview', data)

export const executeWriting = (data) => api.post('/writing/execute', data)

export const cancelWriting = () => api.delete('/writing/cancel')

export const getWritingStatus = () => api.get('/writing/status')

export const getWritingHistory = (limit = 100) => api.get('/writing/history', { params: { limit } })

// ids 로 선택 삭제, all=true 로 전체 삭제
export const deleteWritingHistory = ({ ids = [], all = false } = {}) =>
  api.delete('/writing/history', { data: { ids, all } })
