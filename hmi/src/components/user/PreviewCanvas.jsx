import { useEffect, useRef } from 'react'

const PAPER_W = 295.57
const PAPER_H = 209.72

// 종이·먹 팔레트 (App.css 토큰과 일치)
const C_PAPER  = '#fdfcf9'
const C_LINE   = '#e7e5df'
const C_GUIDE  = '#e2ddd0'
const C_INK    = '#17191c'
const C_EMPTY  = '#b0b4bb'

export default function PreviewCanvas({ waypoints, marginMm = 20, animateKey = 0, color = C_INK }) {
  const canvasRef = useRef(null)
  const lastKeyRef = useRef(animateKey)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const W = canvas.width
    const H = canvas.height

    // 종이(A4)를 캔버스 안에 '정확한 A4 비율'로 레터박스 배치한다.
    // 캔버스 픽셀 비율과 무관하게 흰 종이 영역이 항상 PAPER_W:PAPER_H(=A4) 비율이 되도록,
    // 가용 영역에 비율을 유지한 채 최대 크기로 맞추고 가운데 정렬한다.
    const inset = 14
    const availW = W - inset * 2
    const availH = H - inset * 2
    const ratio = PAPER_W / PAPER_H
    let pw, ph
    if (availW / availH > ratio) { ph = availH; pw = ph * ratio }
    else                         { pw = availW; ph = pw / ratio }
    const ox = (W - pw) / 2          // 종이 좌측
    const oy = (H - ph) / 2          // 종이 상단
    const scaleX = pw / PAPER_W
    const scaleY = ph / PAPER_H

    const toX = (x) => ox + x * scaleX
    const toY = (y) => oy + ph - y * scaleY   // y=0 은 종이 하단

    // 배경(종이) + 테두리 + 실제 여백 가이드
    const drawPaper = () => {
      ctx.clearRect(0, 0, W, H)
      ctx.fillStyle = C_PAPER
      ctx.fillRect(ox, oy, pw, ph)
      ctx.strokeStyle = C_LINE
      ctx.lineWidth = 1
      ctx.strokeRect(ox, oy, pw, ph)

      // 여백 상자 (mm → 캔버스). 슬라이더를 움직이면 실시간으로 반영됨.
      const m = Math.max(0, Math.min(marginMm, PAPER_W / 2 - 1))
      const mx = m * scaleX
      const my = m * scaleY
      ctx.save()
      ctx.strokeStyle = C_GUIDE
      ctx.setLineDash([4, 4])
      ctx.strokeRect(ox + mx, oy + my, pw - mx * 2, ph - my * 2)
      ctx.restore()
    }

    // 웨이포인트 앞에서부터 count개까지 획을 그림
    const drawInk = (count) => {
      ctx.strokeStyle = color   // 선택한 붓펜 색 (윤곽선·속채우기 모두 이 색으로)
      ctx.lineWidth = 1.4
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      let drawing = false
      ctx.beginPath()
      const n = Math.min(count, waypoints.length)
      for (let i = 0; i < n; i++) {
        const [x, y, penDown] = waypoints[i]
        const cx = toX(x)
        const cy = toY(y)
        if (penDown) {
          if (!drawing) { ctx.moveTo(cx, cy); drawing = true }
          else ctx.lineTo(cx, cy)
        } else {
          if (drawing) { ctx.stroke(); ctx.beginPath(); drawing = false }
          ctx.moveTo(cx, cy)
        }
      }
      if (drawing) ctx.stroke()
    }

    const render = (count) => { drawPaper(); drawInk(count) }

    // 빈 상태
    if (!waypoints || waypoints.length === 0) {
      drawPaper()
      ctx.fillStyle = C_EMPTY
      ctx.font = '13px Inter, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('텍스트를 입력하면 미리보기가 표시됩니다', W / 2, H / 2)
      lastKeyRef.current = animateKey
      return
    }

    const total = waypoints.length
    const isNewPreview = animateKey !== lastKeyRef.current
    lastKeyRef.current = animateKey

    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    // 새 미리보기일 때만 애니메이션. (여백 슬라이더 조정 등은 즉시 전체 렌더)
    if (!isNewPreview || reduce) {
      render(total)
      return
    }

    // 실시간으로 붓이 써지는 듯한 재생
    let raf
    const duration = Math.min(6000, Math.max(1400, total * 3.5))  // ms
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      // ease-out 으로 처음 빠르게, 끝에서 부드럽게
      const eased = 1 - Math.pow(1 - t, 2)
      render(Math.floor(eased * total))
      if (t < 1) raf = requestAnimationFrame(tick)
      else render(total)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [waypoints, animateKey, marginMm, color])

  return (
    <canvas
      ref={canvasRef}
      width={600}
      height={426}
      style={{ width: '100%', height: '100%', display: 'block' }}
    />
  )
}
