import { useEffect, useRef, useState } from 'react'
import { WS_URL } from '../api/client'

export const useProgress = () => {
  const [progress, setProgress] = useState({
    status: 'idle',
    progress_pct: 0,
    current_stroke: 0,
    total_strokes: 0,
    current_char: '',
    error_msg: '',
    job_id: null,
  })
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(`${WS_URL}/ws/progress`)
      ws.onopen    = () => setConnected(true)
      ws.onmessage = (e) => setProgress(JSON.parse(e.data))
      ws.onclose   = () => {
        setConnected(false)
        setTimeout(connect, 2000)  // 2초 후 재연결 시도
      }
      ws.onerror   = () => setConnected(false)
      wsRef.current = ws
    }
    connect()
    return () => wsRef.current?.close()
  }, [])

  return { progress, connected }
}
