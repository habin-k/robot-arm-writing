import { useEffect, useRef, useState } from 'react'
import { WS_URL } from '../api/client'

// /ws/robot 구독: 로봇 실시간 상태(User_102 좌표·외력 + 종이 감지)
export const useRobotState = () => {
  const [robot, setRobot] = useState({
    tcp_position: [0, 0, 0, 0, 0, 0],
    tcp_force: [0, 0, 0, 0, 0, 0],
    paper_present: null,   // true=있음, false=없음, null=미확인
  })
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    let closed = false
    const connect = () => {
      const ws = new WebSocket(`${WS_URL}/ws/robot`)
      ws.onopen    = () => setConnected(true)
      ws.onmessage = (e) => {
        try { setRobot(JSON.parse(e.data)) } catch {}
      }
      ws.onclose   = () => {
        setConnected(false)
        if (!closed) setTimeout(connect, 2000)  // 2초 후 재연결
      }
      ws.onerror   = () => setConnected(false)
      wsRef.current = ws
    }
    connect()
    return () => { closed = true; wsRef.current?.close() }
  }, [])

  return { robot, connected }
}
