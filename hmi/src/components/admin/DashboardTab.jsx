import { useEffect, useRef, useState } from 'react'
import { useProgress } from '../../hooks/useProgress'
import { useRobotState } from '../../hooks/useRobotState'
import styles from './DashboardTab.module.css'

// 시스템 상태(작업 상태 + 통신) → 표시 라벨/색/펄스. 기존 팔레트 토큰만 사용.
const STATE = {
  writing:         { label: '작업 중',       color: 'var(--ok)',        pulse: true  },
  done:            { label: '작업 완료',     color: 'var(--info)',      pulse: false },
  idle:            { label: '대기 중',       color: 'var(--ink-faint)', pulse: false },
  error:           { label: '오류 정지',     color: 'var(--danger)',    pulse: false },
  cancelled:       { label: '취소됨',        color: 'var(--ink-faint)', pulse: false },
  manual_required: { label: '수동 복구 필요', color: 'var(--danger)',    pulse: true  },
  offline:         { label: '통신 끊김',     color: 'var(--danger)',    pulse: true  },
  connecting:      { label: '연결 중…',      color: 'var(--ink-faint)', pulse: true  },
}

const STATUS_LABEL = {
  idle: '대기', writing: '쓰는 중', done: '완료',
  error: '오류', cancelled: '취소', manual_required: '수동 복구',
}

const now = () => new Date().toLocaleTimeString('ko-KR', { hour12: false })

export default function DashboardTab() {
  const { progress, connected: progConnected } = useProgress()
  const { robot, connected: robotConnected } = useRobotState()

  // ── 최초 연결 추적 ───────────────────────────────────────────
  // WebSocket 은 초기 상태가 '끊김'이라, 페이지 로드 직후 잠깐은 무조건 끊김으로 보인다.
  // '한 번이라도 붙은 적 있는지'를 기억해서, 최초 연결 전의 끊김은 '연결 중'으로 취급하고
  // 알람/이력에 남기지 않는다. 한 번 붙었다가 끊긴 경우만 진짜 '통신 끊김' 알람.
  const progEver  = useRef(false)
  const robotEver = useRef(false)
  if (progConnected)  progEver.current  = true
  if (robotConnected) robotEver.current = true
  const progDown  = progEver.current  && !progConnected
  const robotDown = robotEver.current && !robotConnected

  // ── 파생 상태 ────────────────────────────────────────────────
  const offline    = progDown
  const connecting = !progEver.current && !progConnected
  const stateKey = offline ? 'offline'
    : connecting ? 'connecting'
    : (STATE[progress.status] ? progress.status : 'idle')
  const st       = STATE[stateKey]

  const manual   = progress.status === 'manual_required'
  const mode     = manual ? 'MANUAL' : 'AUTO'
  const modeSub  = manual ? '수동 복구' : '자율 운전'

  const commOk   = progConnected && robotConnected
  const paper    = robot.paper_present   // true / false / null
  const isWriting = progress.status === 'writing'

  // ── 활성 알람/경고 (심각도 순) ───────────────────────────────
  const alarms = []
  if (progDown)  alarms.push({ key: 'ws-prog', level: 'crit', msg: '작업 서버 통신 끊김' })
  if (robotDown) alarms.push({ key: 'ws-robot', level: 'crit', msg: '로봇 상태 통신 끊김' })
  if (manual)  alarms.push({ key: 'manual', level: 'crit', msg: progress.error_msg || '수동 복구 모드 — 관리자 조치 필요' })
  if (progress.status === 'error') alarms.push({ key: 'err', level: 'warn', msg: progress.error_msg || '작업 오류로 중단됨' })
  if (paper === false) alarms.push({ key: 'paper', level: 'warn', msg: '종이 없음 — 용지를 확인하세요' })

  // ── 세션 알람 이력 (클라이언트 세션 동안 누적, 새로고침 시 초기화) ──
  const alarmSig = alarms.map(a => a.key).join('|')   // 알람 구성 시그니처
  const [history, setHistory] = useState([])
  const prevKeys = useRef(new Set())
  const alarmsRef = useRef(alarms)
  alarmsRef.current = alarms
  useEffect(() => {
    const fresh = alarmsRef.current.filter(a => !prevKeys.current.has(a.key))
    if (fresh.length) {
      setHistory(h => [
        ...fresh.map(a => ({ time: now(), level: a.level, msg: a.msg })),
        ...h,
      ].slice(0, 40))
    }
    prevKeys.current = new Set(alarmsRef.current.map(a => a.key))
  }, [alarmSig])   // 알람 구성이 바뀔 때만 실행

  // 합력 |F| = √(Fx²+Fy²+Fz²)
  const f = robot.tcp_force || [0, 0, 0]
  const fMag = Math.sqrt(f[0] ** 2 + f[1] ** 2 + f[2] ** 2)
  const pos = robot.tcp_position || [0, 0, 0]

  const dot = (color, pulse) => (
    <span className={styles.dot}
      style={{ background: color, animation: pulse ? 'pulse 1.2s infinite' : 'none' }} />
  )

  return (
    <div className={styles.layout}>
      {/* ── 시스템 상태 배너 (전체 너비) ── */}
      <div className={styles.hero}>
        <div className={styles.heroMain}>
          <div className={styles.heroState} style={{ color: st.color }}>
            {dot(st.color, st.pulse)}
            {st.label}
          </div>
          <div className={styles.heroSub}>
            {progress.job_id ? <>Job <span className={styles.mono}>#{progress.job_id}</span> · </> : null}
            {isWriting ? `"${progress.current_char || '—'}" 쓰는 중` : '실시간 모니터링'}
          </div>
        </div>

        {/* KPI 요약 */}
        <div className={styles.kpiRow}>
          <div className={styles.kpi}>
            <span className={styles.kpiLabel}>로봇 모드</span>
            <span className={styles.kpiValue}>
              <span className={`${styles.modeTag} ${manual ? styles.modeManual : styles.modeAuto}`}>{mode}</span>
            </span>
            <span className={styles.kpiSub}>{modeSub}</span>
          </div>
          <div className={styles.kpi}>
            <span className={styles.kpiLabel}>통신</span>
            <span className={styles.kpiValue}>
              {dot(commOk ? 'var(--ok)' : 'var(--danger)', commOk)}
              {commOk ? '정상' : '끊김'}
            </span>
            <span className={styles.kpiSub}>{commOk ? '서버·로봇 연결됨' : '연결 확인 필요'}</span>
          </div>
          <div className={styles.kpi}>
            <span className={styles.kpiLabel}>종이 감지</span>
            <span className={styles.kpiValue}>
              {dot(paper === true ? 'var(--ok)' : paper === false ? 'var(--danger)' : 'var(--ink-faint)', false)}
              {paper === true ? '있음' : paper === false ? '없음' : '미확인'}
            </span>
            <span className={styles.kpiSub}>용지 센서</span>
          </div>
          <div className={styles.kpi}>
            <span className={styles.kpiLabel}>작업 상태</span>
            <span className={styles.kpiValue}>{STATUS_LABEL[progress.status] || progress.status}</span>
            <span className={styles.kpiSub}>{isWriting ? `${progress.progress_pct}% 진행` : '현재 작업'}</span>
          </div>
        </div>
      </div>

      {/* ── 작업 진행률 ── */}
      <div className={styles.card}>
        <div className={styles.cardTitle}>작업 진행률</div>
        <div className={styles.pctRow}>
          <span className={styles.pctNum} style={{ color: st.color }}>{progress.progress_pct}</span>
          <span className={styles.pctUnit}>%</span>
        </div>
        <div className={styles.progressBar}>
          <div className={styles.progressFill}
            style={{ width: `${progress.progress_pct}%`, background: st.color }} />
        </div>
        <div className={styles.detailGrid}>
          <div className={styles.detailItem}>
            <span className={styles.detailLabel}>현재 글자</span>
            <span className={styles.detailValue}>{progress.current_char || '—'}</span>
          </div>
          <div className={styles.detailItem}>
            <span className={styles.detailLabel}>획 진행</span>
            <span className={styles.detailValue}>
              {progress.current_stroke} / {progress.total_strokes || '—'}
            </span>
          </div>
        </div>
      </div>

      {/* ── 로봇 상태 요약 ── */}
      <div className={styles.card}>
        <div className={styles.cardTitle}>
          로봇 상태 요약 (User 102)
          <span className={`${styles.wsDot} ${robotConnected ? styles.wsOn : ''}`} />
        </div>
        <div className={styles.coordGrid}>
          {['X', 'Y', 'Z'].map((ax, i) => (
            <div key={ax} className={styles.coordCell}>
              <span className={styles.coordAxis}>{ax}</span>
              <span className={styles.coordVal}>
                {robotConnected ? pos[i]?.toFixed(1) : '—'}
                <span className={styles.coordUnit}>mm</span>
              </span>
            </div>
          ))}
          <div className={styles.coordCell}>
            <span className={styles.coordAxis}>|F| 합력</span>
            <span className={styles.coordVal}>
              {robotConnected ? fMag.toFixed(1) : '—'}
              <span className={styles.coordUnit}>N</span>
            </span>
          </div>
          <div className={styles.coordCell}>
            <span className={styles.coordAxis}>Fz</span>
            <span className={styles.coordVal}>
              {robotConnected ? (f[2] ?? 0).toFixed(1) : '—'}
              <span className={styles.coordUnit}>N</span>
            </span>
          </div>
          <div className={styles.coordCell}>
            <span className={styles.coordAxis}>Rz</span>
            <span className={styles.coordVal}>
              {robotConnected ? (pos[5] ?? 0).toFixed(1) : '—'}
              <span className={styles.coordUnit}>°</span>
            </span>
          </div>
        </div>
      </div>

      {/* ── 알람 / 경고 요약 (전체 너비) ── */}
      <div className={styles.cardFull}>
        <div className={styles.cardTitle}>
          알람 · 경고
          {alarms.length > 0 && <span className={styles.alarmCount}>{alarms.length}</span>}
        </div>

        {alarms.length === 0 ? (
          <div className={styles.allClear}>
            {dot('var(--ok)', false)} 정상 — 활성 알람이 없습니다
          </div>
        ) : (
          <div className={styles.alarmList}>
            {alarms.map(a => (
              <div key={a.key} className={`${styles.alarmRow} ${a.level === 'crit' ? styles.crit : styles.warn}`}>
                <span className={styles.alarmBadge}>{a.level === 'crit' ? '심각' : '경고'}</span>
                <span className={styles.alarmMsg}>{a.msg}</span>
              </div>
            ))}
          </div>
        )}

        {/* 세션 알람 이력 */}
        <div className={styles.histTitle}>세션 알람 이력</div>
        {history.length === 0 ? (
          <div className={styles.histEmpty}>이번 접속 중 발생한 알람이 없습니다.</div>
        ) : (
          <div className={styles.histList}>
            {history.map((h, i) => (
              <div key={i} className={styles.histRow}>
                <span className={styles.histTime}>{h.time}</span>
                <span className={`${styles.histLevel} ${h.level === 'crit' ? styles.critText : styles.warnText}`}>
                  {h.level === 'crit' ? '심각' : '경고'}
                </span>
                <span className={styles.histMsg}>{h.msg}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
