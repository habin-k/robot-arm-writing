import { useEffect, useState } from 'react'
import { getFonts, previewWriting, executeWriting, cancelWriting } from '../../api/writing'
import { useProgress } from '../../hooks/useProgress'
import { useRobotState } from '../../hooks/useRobotState'
import { usePersistentState } from '../../hooks/usePersistentState'
import PreviewCanvas from './PreviewCanvas'
import styles from './UserTab.module.css'

const STATUS_LABEL = {
  idle: '대기 중', writing: '쓰는 중', done: '완료', error: '오류', cancelled: '취소됨',
}

export default function UserTab() {
  // 입력값은 sessionStorage 에 저장 → 다른 탭에 갔다 와도, 새로고침해도 유지된다.
  const [nickname, setNickname] = usePersistentState('write.nickname', '')
  const [text, setText] = usePersistentState('write.text', '')
  const [font, setFont] = usePersistentState('write.font', 'regular')
  const [size, setSize] = usePersistentState('write.size', 15)
  const [margin, setMargin] = usePersistentState('write.margin', 20)
  const [fillMode, setFillMode] = usePersistentState('write.fillMode', 'outline')
  const [skipDetect, setSkipDetect] = usePersistentState('write.skipDetect', false)
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
        margin_mm: margin, fill_mode: fillMode, skip_surface_detect: skipDetect
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
        margin_mm: margin, fill_mode: fillMode, skip_surface_detect: skipDetect,
        nickname: nickname.trim()
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
          <div className={styles.switchRow} style={{ marginTop: 12 }}>
            <label className={styles.switchLabel}>표면 자동 감지</label>
            <button
              className={`${styles.switch} ${!skipDetect ? styles.switchOn : ''}`}
              onClick={() => setSkipDetect(v => !v)}>
              <span className={styles.switchKnob} />
            </button>
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

      {/* 오른쪽: 상태 + 캔버스 */}
      <div className={styles.canvasArea}>
        {/* 우측 상단: 종이 감지 · 작업 상태 */}
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

          <div className={styles.infoCard}>
            <div className={styles.progressHeader}>
              <span className={`${styles.statusDot} ${styles['dot_' + progress.status]}`} />
              <span className={styles.statusText}>{STATUS_LABEL[progress.status] || progress.status}</span>
              {isWriting && <span className={styles.progressPct}>{progress.progress_pct}%</span>}
            </div>
            {isWriting && (
              <>
                <div className={styles.progressBar}>
                  <div className={styles.progressFill} style={{ width: `${progress.progress_pct}%` }} />
                </div>
                <div className={styles.progressDetail}>
                  획 {progress.current_stroke} / {progress.total_strokes}
                  {progress.current_char && ` · "${progress.current_char}" 쓰는 중`}
                </div>
              </>
            )}
            {progress.error_msg && <div className={styles.errorMsg}>{progress.error_msg}</div>}
          </div>
        </div>

        <div className={styles.canvasBox}>
          <PreviewCanvas waypoints={waypoints} marginMm={margin} animateKey={previewKey} />
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
