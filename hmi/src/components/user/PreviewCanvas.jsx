import { useEffect, useRef } from 'react'

const PAPER_W = 295.57
const PAPER_H = 209.72

export default function PreviewCanvas({ waypoints }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const W = canvas.width
    const H = canvas.height
    const pad = 32

    ctx.clearRect(0, 0, W, H)

    // 종이 배경 (다크 테마에서 종이 색)
    ctx.fillStyle = '#1e1e1e'
    ctx.fillRect(pad, pad, W - pad * 2, H - pad * 2)
    ctx.strokeStyle = '#333'
    ctx.lineWidth = 1
    ctx.strokeRect(pad, pad, W - pad * 2, H - pad * 2)

    if (!waypoints || waypoints.length === 0) {
      ctx.fillStyle = '#444'
      ctx.font = '13px Inter, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('텍스트를 입력하면 미리보기가 표시됩니다', W / 2, H / 2)
      return
    }

    const scaleX = (W - pad * 2) / PAPER_W
    const scaleY = (H - pad * 2) / PAPER_H

    ctx.strokeStyle = '#e2e2e2'
    ctx.lineWidth = 1.2
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    let drawing = false
    ctx.beginPath()
    for (const [x, y, penDown] of waypoints) {
      const cx = pad + x * scaleX
      const cy = H - pad - y * scaleY
      if (penDown) {
        if (!drawing) { ctx.moveTo(cx, cy); drawing = true }
        else ctx.lineTo(cx, cy)
      } else {
        if (drawing) { ctx.stroke(); ctx.beginPath(); drawing = false }
        ctx.moveTo(cx, cy)
      }
    }
    if (drawing) ctx.stroke()
  }, [waypoints])

  return (
    <canvas
      ref={canvasRef}
      width={520}
      height={370}
      style={{ width: '100%', height: '100%', display: 'block' }}
    />
  )
}
