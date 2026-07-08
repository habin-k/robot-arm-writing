import { useState, useRef, useEffect } from 'react'
import { goHome, emergencyStop, errorReset, jog } from '../../api/robot'
import styles from './AdminTab.module.css'

const SPEEDS = [
  { label: '저속', value: 10 },
  { label: '중속', value: 30 },
  { label: '고속', value: 60 },
]

export default function AdminTab({ estopOnly }) {
  const [speed, setSpeed] = useState(30)
  const [feedback, setFeedback] = useState('')
  const activeAxis = useRef(null)

  const send = async (fn, msg) => {
    try {
      await fn()
      setFeedback(msg)
      setTimeout(() => setFeedback(''), 2500)
    } catch (e) {
      setFeedback('오류: ' + (e.response?.data?.detail || e.message))
    }
  }

  // 누르는 순간: 해당 축으로 연속 이동 시작
  const startJog = (axis, dir) => {
    activeAxis.current = axis
    jog({ axis, direction: dir, moving: true, speed }).catch(() => {})
    setFeedback(`${axis.toUpperCase()} ${dir > 0 ? '+' : '−'} 이동 중`)
  }

  // 떼는 순간: 정지
  const stopJog = () => {
    const axis = activeAxis.current
    if (!axis) return
    activeAxis.current = null
    jog({ axis, direction: 1, moving: false, speed }).catch(() => {})
    setFeedback('')
  }

  // 언마운트 시 정지 보장
  useEffect(() => () => stopJog(), [])

  const JogBtn = ({ axis, dir, label }) => (
    <button
      className={styles.dpadBtn}
      onMouseDown={() => startJog(axis, dir)}
      onMouseUp={stopJog}
      onMouseLeave={stopJog}
      onTouchStart={(e) => { e.preventDefault(); startJog(axis, dir) }}
      onTouchEnd={stopJog}
    >{label}</button>
  )

  return (
    <div className={styles.layout}>
      <button className={styles.estop} onClick={() => send(emergencyStop, '비상정지 실행됨')}>
        ⬛ 비상정지
      </button>

      {!estopOnly && (
        <div className={styles.grid}>
          {/* 로봇 제어 */}
          <div className={styles.card}>
            <div className={styles.cardTitle}>로봇 제어</div>
            <button className={styles.actionBtn} onClick={() => send(goHome, '원점 복귀 명령 전송')}>
              ⌂ 원점 복귀
            </button>
            <button className={styles.actionBtn} onClick={() => send(errorReset, '에러 리셋 명령 전송')}>
              ↺ 에러 리셋
            </button>
            {feedback && <div className={styles.feedback}>{feedback}</div>}
          </div>

          {/* 조그 */}
          <div className={styles.card}>
            <div className={styles.cardTitle}>수동 조그 <span className={styles.jogHint}>(누르고 있으면 계속 이동)</span></div>
            <div className={styles.stepRow}>
              {SPEEDS.map(s => (
                <button key={s.value}
                  className={`${styles.stepBtn} ${speed === s.value ? styles.stepBtnActive : ''}`}
                  onClick={() => setSpeed(s.value)}
                >{s.label}</button>
              ))}
            </div>

            <span className={styles.jogLabel}>X / Y</span>
            <div className={styles.dpad}>
              <div /><JogBtn axis="y" dir={1} label="Y+" /><div />
              <JogBtn axis="x" dir={-1} label="X−" />
              <div className={styles.dpadCenter} />
              <JogBtn axis="x" dir={1} label="X+" />
              <div /><JogBtn axis="y" dir={-1} label="Y−" /><div />
            </div>

            <span className={styles.jogLabel}>Z</span>
            <div className={styles.zRow}>
              <JogBtn axis="z" dir={1} label="Z+" />
              <JogBtn axis="z" dir={-1} label="Z−" />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
