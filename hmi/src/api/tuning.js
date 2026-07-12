import { api } from './client'

// 관리자 파라미터 설정 (JWT 필요)
// 로봇 모션: 저장 즉시 /robot/tuning 발행 → task_manager 실시간 반영
export const getMotionParams = () => api.get('/tuning/motion')
export const setMotionParams = (data) => api.post('/tuning/motion', data)

// 경로 생성: 저장 후 다음 미리보기/실행부터 반영
export const getPathParams = () => api.get('/tuning/path')
export const setPathParams = (data) => api.post('/tuning/path', data)
