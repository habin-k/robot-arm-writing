import { api } from './client'

export const getFonts = () => api.get('/fonts')

export const previewWriting = (data) => api.post('/writing/preview', data)

export const executeWriting = (data) => api.post('/writing/execute', data)

export const cancelWriting = () => api.delete('/writing/cancel')

export const getWritingStatus = () => api.get('/writing/status')
