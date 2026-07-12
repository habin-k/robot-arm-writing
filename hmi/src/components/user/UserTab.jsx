import { useEffect, useState } from 'react'
import { getFonts, previewWriting, executeWriting, cancelWriting } from '../../api/writing'
import { useProgress } from '../../hooks/useProgress'
import { useRobotState } from '../../hooks/useRobotState'
import { usePersistentState } from '../../hooks/usePersistentState'
import PreviewCanvas from './PreviewCanvas'
import styles from './UserTab.module.css'

// 붓펜 색상 (task_manager PENS 와 id 일치). 빨강=두꺼운 붓, 보라·청록=얇은 붓.
const PENS = [
  { id: 'red',    label: '빨강', color: '#d64530' },
  { id: 'purple', label: '보라', color: '#7c3aed' },
  { id: 'cyan',   label: '청록', color: '#0891b2' },
]

export default function UserTab() {
  // 입력값은 sessionStorage 에 저장 → 다른 탭에 갔다 와도, 새로고침해도 유지된다.
  const [nickname, setNickname] = usePersistentState('write.nickname', '')
  const [text, setText] = usePersistentState('write.text', '')
  const [font, setFont] = usePersistentState('write.font', 'regular')
  const [size, setSize] = usePersistentState('write.size', 15)
  const [margin, setMargin] = usePersistentState('write.margin', 20)
  const [fillMode, setFillMode] = usePersistentState('write.fillMode', 'outline')
  const [pen, setPen] = usePersistentState('write.pen', 'red')
  const [waypoints, setWaypoints] = usePersistentState('write.waypoints', [])
  const [summary, setSummary] = usePersistentState('write.summary', null)
  const [fonts, setFonts] = useState([])
  const [loading, setLoading] = useState(false)
  const [previewKey, setPreviewKey] = useState(0)   // 미리보기 애니메이션 재생 트리거
  const { progress } = useProgress()
  const { robot, connected } = useRobotState()      // 종이 감지 상태(/ws/robot)

  useEffect(() => {
    getFonts().then(r => setFonts(r.data.fonts)).catch(() => {})
  }, [])

  // 미리보기 생성. silent=true → 조용히(에러 alert 없음) + 애니메이션 없이 정적 갱신.
  const runPreview = async (silent) => {
    if (!text.trim()) { setWaypoints([]); setSummary(null); return }
    if (!silent) setLoading(true)
    try {
      const r = await previewWriting({
        text, font_name: font, char_height_mm: size,
        margin_mm: margin, fill_mode: fillMode, skip_surface_detect: false
      })
      setWaypoints(r.data.waypoints)
      setSummary(r.data.summary)
      if (!silent) setPreviewKey(k => k + 1)   // 버튼 클릭 시에만 애니메이션 재생
    } catch (e) {
      if (!silent) alert('미리보기 실패: ' + (e.response?.data?.detail || e.message))
    } finally { if (!silent) setLoading(false) }
  }

  const handlePreview = () => runPreview(false)

  // 문구가 비면 캔버스를 비운다. (미리보기는 '미리보기' 버튼을 눌러야만 갱신됨)
  useEffect(() => {
    if (!text.trim()) { setWaypoints([]); setSummary(null) }
  }, [text])

  const handleExecute = async () => {
    if (!text.trim()) return
    if (!nickname.trim()) { alert('닉네임을 입력하세요. (이용 내역 구분에 사용됩니다)'); return }
    try {
      await executeWriting({
        text, font_name: font, char_height_mm: size,
        margin_mm: margin, fill_mode: fillMode, skip_surface_detect: false,
        nickname: nickname.trim(), pen
      })
    } catch (e) { alert('실행 실패: ' + (e.response?.data?.detail || e.message)) }
  }

  const handleCancel = async () => { try { await cancelWriting() } catch {} }

  const isWriting = progress.status === 'writing'

  return (
    <div className={styles.layout} style={{ flex: 1, minHeight: 0 }}>
      {/* 왼쪽: 설정 패널 */}
      <div className={styles.panel}>

        <div className={styles.card}>
          <div className={styles.field}>
            <label className={styles.label}>닉네임</label>
            <input className={styles.input} value={nickname}
              onChange={e => setNickname(e.target.value)}
              maxLength={20} />
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.field}>
            <label className={styles.label}>문구</label>
            <textarea className={styles.textarea} value={text}
              onChange={e => setText(e.target.value)}
              placeholder="쓸 문구를 입력하세요" rows={3} />
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.field}>
            <label className={styles.label}>폰트</label>
            <div className={styles.fontGrid}>
              {fonts.map(f => (
                <button key={f}
                  className={`${styles.fontBtn} ${font === f ? styles.fontBtnActive : ''}`}
                  onClick={() => setFont(f)}>{f}</button>
              ))}
            </div>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.field}>
            <label className={styles.label}>
              글씨 크기 <span className={styles.valueTag}>{size} mm</span>
            </label>
            <input type="range" min={5} max={50} value={size}
              onChange={e => setSize(Number(e.target.value))} className={styles.slider} />
            <div className={styles.sliderLabels}><span>5mm</span><span>50mm</span></div>
          </div>
          <div className={styles.field} style={{ marginTop: 14 }}>
            <label className={styles.label}>
              여백 <span className={styles.valueTag}>{margin} mm</span>
            </label>
            <input type="range" min={5} max={40} value={margin}
              onChange={e => setMargin(Number(e.target.value))} className={styles.slider} />
            <div className={styles.sliderLabels}><span>5mm</span><span>40mm</span></div>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.field}>
            <label className={styles.label}>쓰기 방식</label>
            <div className={styles.toggleGroup}>
              {['outline', 'hatch'].map(m => (
                <button key={m}
                  className={`${styles.toggleBtn} ${fillMode === m ? styles.toggleBtnActive : ''}`}
                  onClick={() => setFillMode(m)}>
                  {m === 'outline' ? '윤곽선' : '속 채우기'}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.field}>
            <label className={styles.label}>붓펜 색상</label>
            <div className={styles.toggleGroup}>
              {PENS.map(p => (
                <button key={p.id}
                  className={`${styles.toggleBtn} ${pen === p.id ? styles.toggleBtnActive : ''}`}
                  onClick={() => setPen(p.id)}>
                  <span style={{
                    display: 'inline-block', width: 10, height: 10, borderRadius: '50%',
                    background: p.color, marginRight: 6, verticalAlign: 'middle',
                  }} />
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className={styles.actions}>
          <button className={styles.btnPreview} onClick={handlePreview}
            disabled={loading || !text.trim()}>
            {loading ? '생성 중...' : '미리보기'}
          </button>
          {!isWriting
            ? <button className={styles.btnExecute} onClick={handleExecute} disabled={!text.trim() || !nickname.trim()}>▶ 시작</button>
            : <button className={styles.btnCancel} onClick={handleCancel}>■ 취소</button>
          }
        </div>
      </div>

      {/* 오른쪽: 종이 감지 + 캔버스 */}
      <div className={styles.canvasArea}>
        {/* 우측 상단: 종이 감지 */}
        <div className={styles.topInfo}>
          <div className={styles.infoCard}>
            <div className={styles.paperRow}>
              <span className={styles.paperLabel}>종이 감지</span>
              <span className={`${styles.paperBadge} ${
                !connected                    ? '' :
                robot.paper_present === true  ? styles.paperOk :
                robot.paper_present === false ? styles.paperNone : ''
              }`}>
                {!connected                     ? '연결 끊김'
                 : robot.paper_present === true  ? '종이 있음'
                 : robot.paper_present === false ? '종이 없음'
                 : '미확인'}
              </span>
            </div>
          </div>
        </div>

        <div className={styles.canvasBox}>
          <PreviewCanvas waypoints={waypoints} marginMm={margin} animateKey={previewKey}
            color={PENS.find(p => p.id === pen)?.color} />
        </div>
        {summary && (
          <div className={styles.summaryRow}>
            <span>웨이포인트 {summary.total_points}</span>
            <span>획 {summary.stroke_count}</span>
            <span>X {summary.x_range?.[0]?.toFixed(1)} ~ {summary.x_range?.[1]?.toFixed(1)} mm</span>
            <span>Y {summary.y_range?.[0]?.toFixed(1)} ~ {summary.y_range?.[1]?.toFixed(1)} mm</span>
          </div>
        )}
      </div>
    </div>
  )
}
