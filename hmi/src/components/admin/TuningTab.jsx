import { useEffect, useState } from 'react'
import {
  getMotionParams, setMotionParams, getPathParams, setPathParams,
} from '../../api/tuning'
import styles from './TuningTab.module.css'

// [키, 라벨, 단위] — 속도/가속은 [일반, 회전] 2개 값
const MOTION_PAIRS = [
  ['write_vel',  '글씨 속도',  'mm/s'],
  ['write_acc',  '글씨 가속',  'mm/s²'],
  ['travel_vel', '공이동 속도', 'mm/s'],
  ['travel_acc', '공이동 가속', 'mm/s²'],
]
const PEN_LABELS = { red: '빨강', purple: '보라', cyan: '청록' }
const PATH_FIELDS = [
  ['line_spacing_factor', '줄 간격 계수', '×'],
  ['char_spacing_mm',     '글자 간격',   'mm'],
  ['paper_width_mm',      '도화지 가로', 'mm'],
  ['paper_height_mm',     '도화지 세로', 'mm'],
  ['hatch_spacing_mm',    '해칭 간격',   'mm'],
  ['curve_steps',         '곡선 세밀도', 'step'],
]

// 숫자 입력 한 칸
function NumInput({ value, onChange, step = 'any' }) {
  return (
    <input
      className={styles.num}
      type="number"
      step={step}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

export default function TuningTab() {
  const [motion, setMotion] = useState(null)
  const [path, setPath] = useState(null)
  const [busy, setBusy] = useState('')      // 'motion' | 'path' | ''
  const [msg, setMsg] = useState('')

  useEffect(() => {
    getMotionParams().then(r => setMotion(r.data)).catch(() => setMsg('모션 파라미터 로드 실패'))
    getPathParams().then(r => setPath(r.data)).catch(() => setMsg('경로 파라미터 로드 실패'))
  }, [])

  const flash = (t) => { setMsg(t); setTimeout(() => setMsg(''), 3000) }
  const errText = (e) => {
    const d = e.response?.data?.detail
    if (Array.isArray(d)) return d[0]?.msg || '입력값 오류'
    return d || e.message
  }

  const setPair = (key, idx, val) =>
    setMotion(m => ({ ...m, [key]: m[key].map((v, i) => (i === idx ? val : v)) }))
  const setCF = (pen, val) =>
    setMotion(m => ({ ...m, contact_force: { ...m.contact_force, [pen]: val } }))
  const setPathVal = (key, val) => setPath(p => ({ ...p, [key]: val }))

  const saveMotion = async () => {
    setBusy('motion')
    try {
      const payload = {
        write_vel:  motion.write_vel.map(Number),
        write_acc:  motion.write_acc.map(Number),
        travel_vel: motion.travel_vel.map(Number),
        travel_acc: motion.travel_acc.map(Number),
        write_force_z: Number(motion.write_force_z),
        force_on_z: Number(motion.force_on_z),
        contact_force: Object.fromEntries(
          Object.entries(motion.contact_force).map(([k, v]) => [k, Number(v)])),
      }
      const r = await setMotionParams(payload)
      setMotion(r.data.motion)
      flash('로봇 모션 파라미터 적용됨 (실시간 반영)')
    } catch (e) { flash('오류: ' + errText(e)) }
    finally { setBusy('') }
  }

  const savePath = async () => {
    setBusy('path')
    try {
      const payload = Object.fromEntries(
        PATH_FIELDS.map(([k]) => [k, k === 'curve_steps' ? parseInt(path[k], 10) : Number(path[k])]))
      const r = await setPathParams(payload)
      setPath(r.data.path)
      flash('경로 생성 파라미터 저장됨 (다음 미리보기부터 반영)')
    } catch (e) { flash('오류: ' + errText(e)) }
    finally { setBusy('') }
  }

  return (
    <div className={styles.wrap}>
      {msg && <div className={styles.toast}>{msg}</div>}

      {/* 로봇 모션 파라미터 */}
      <div className={styles.card}>
        <div className={styles.cardTitle}>
          로봇 모션 파라미터
          <span className={styles.cardHint}>저장 즉시 로봇에 실시간 반영</span>
        </div>

        {!motion ? <div className={styles.loading}>불러오는 중…</div> : (
          <>
            {MOTION_PAIRS.map(([key, label, unit]) => (
              <div key={key} className={styles.row}>
                <span className={styles.label}>{label}</span>
                <div className={styles.inputs}>
                  <NumInput value={motion[key][0]} onChange={(v) => setPair(key, 0, v)} />
                  <NumInput value={motion[key][1]} onChange={(v) => setPair(key, 1, v)} />
                  <span className={styles.unit}>{unit}</span>
                </div>
                <span className={styles.sub}>일반 · 회전</span>
              </div>
            ))}

            <div className={styles.row}>
              <span className={styles.label}>붓 누르는 힘</span>
              <div className={styles.inputs}>
                <NumInput value={motion.write_force_z} onChange={(v) => setMotion(m => ({ ...m, write_force_z: v }))} />
                <span className={styles.unit}>N</span>
              </div>
              <span className={styles.sub}>음수 = 아래로 누름</span>
            </div>

            <div className={styles.row}>
              <span className={styles.label}>힘제어 높이</span>
              <div className={styles.inputs}>
                <NumInput value={motion.force_on_z} onChange={(v) => setMotion(m => ({ ...m, force_on_z: v }))} />
                <span className={styles.unit}>mm</span>
              </div>
              <span className={styles.sub}>하강해 힘제어 켜는 z</span>
            </div>

            <div className={styles.row}>
              <span className={styles.label}>접촉 판단 힘</span>
              <div className={styles.inputs}>
                {['red', 'purple', 'cyan'].map(pen => (
                  <label key={pen} className={styles.penField}>
                    <span className={styles.penLabel}>{PEN_LABELS[pen]}</span>
                    <NumInput value={motion.contact_force[pen]} onChange={(v) => setCF(pen, v)} />
                  </label>
                ))}
                <span className={styles.unit}>N</span>
              </div>
              <span className={styles.sub}>펜별 바닥 접촉 판정</span>
            </div>

            <button className={styles.saveBtn} onClick={saveMotion} disabled={busy === 'motion'}>
              {busy === 'motion' ? '적용 중…' : '모션 파라미터 저장'}
            </button>
          </>
        )}
      </div>

      {/* 경로 생성 파라미터 */}
      <div className={styles.card}>
        <div className={styles.cardTitle}>
          경로 생성 파라미터
          <span className={styles.cardHint}>다음 미리보기/실행부터 반영</span>
        </div>

        {!path ? <div className={styles.loading}>불러오는 중…</div> : (
          <>
            {PATH_FIELDS.map(([key, label, unit]) => (
              <div key={key} className={styles.row}>
                <span className={styles.label}>{label}</span>
                <div className={styles.inputs}>
                  <NumInput
                    value={path[key]}
                    step={key === 'curve_steps' ? '1' : 'any'}
                    onChange={(v) => setPathVal(key, v)}
                  />
                  <span className={styles.unit}>{unit}</span>
                </div>
              </div>
            ))}

            <button className={styles.saveBtn} onClick={savePath} disabled={busy === 'path'}>
              {busy === 'path' ? '저장 중…' : '경로 파라미터 저장'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
