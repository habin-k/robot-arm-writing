import { useEffect, useRef, useState } from 'react'
import { useProgress } from '../../hooks/useProgress'
import styles from './StatusTab.module.css'

// 경과 시간(초) → "mm:ss" (1시간 넘으면 "h:mm:ss")
const fmtElapsed = (s) => {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const pad = (n) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(ss)}` : `${pad(m)}:${pad(ss)}`
}

// 서버가 준 elapsed_sec 를 기준으로, 진행 중이면 매초 로컬로 이어서 증가시킨다.
// (WebSocket 은 상태 변화 때만 push 되므로, 그 사이 초는 클라이언트가 채운다)
// 서버 base 가 갱신될 때마다 재동기화해서 시계 오차가 누적되지 않게 한다.
const useLiveElapsed = (progress) => {
  const base = progress.elapsed_sec || 0
  const running = !!progress.running
  const sync = useRef({ base: 0, at: Date.now() })
  const [, force] = useState(0)
  useEffect(() => {
    sync.current = { base, at: Date.now() }   // 서버 값 도착 시 기준 재동기화
    force((n) => n + 1)
  }, [base, running, progress.job_id])
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => force((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [running])
  const extra = running ? Math.floor((Date.now() - sync.current.at) / 1000) : 0
  return sync.current.base + extra
}

const STATUS_LABEL = {
  idle: '대기 중', writing: '쓰는 중', done: '완료',
  error: '오류', cancelled: '취소됨', manual_required: '수동 복구 필요',
}
// 토큰 팔레트와 일치 (--ink-faint / --ok / --info / --danger)
const STATUS_COLOR = {
  idle: '#9297a0', writing: '#1f9d57', done: '#2f6bd8',
  error: '#d64530', cancelled: '#9297a0', manual_required: '#d64530',
}

export default function StatusTab() {
  const { progress, connected } = useProgress()
  const color = STATUS_COLOR[progress.status] || '#9297a0'
  const isWriting = progress.status === 'writing'
  const elapsed = useLiveElapsed(progress)

  return (
    <div className={styles.layout}>
      {/* 현재 상태 — 전체 너비 */}
      <div className={styles.cardFull}>
        <div className={styles.cardTitle}>현재 상태</div>
        <div className={styles.statusBig} style={{ color }}>
          <span className={styles.statusDot} style={{
            background: color,
            animation: isWriting ? 'pulse 1.2s infinite' : 'none'
          }} />
          {STATUS_LABEL[progress.status] || progress.status}
        </div>
        {progress.job_id && (
          <div className={styles.jobId}>Job #{progress.job_id}</div>
        )}
        {(progress.running || elapsed > 0) && (
          <div style={{
            marginTop: 14, display: 'flex', alignItems: 'baseline', gap: 8,
          }}>
            <span style={{ fontSize: 13, color: 'var(--ink-faint)' }}>
              {progress.running ? '경과 시간' : '작업 소요 시간'}
            </span>
            <span style={{
              fontSize: 28, fontWeight: 600, fontVariantNumeric: 'tabular-nums',
              letterSpacing: 1, color,
            }}>
              {fmtElapsed(elapsed)}
            </span>
          </div>
        )}
      </div>

      {/* 진행률 */}
      <div className={styles.card}>
        <div className={styles.cardTitle}>진행률</div>
        <div className={styles.pctRow}>
          <span className={styles.pctNum}>{progress.progress_pct}</span>
          <span className={styles.pctUnit}>%</span>
        </div>
        <div className={styles.progressBar}>
          <div className={styles.progressFill}
            style={{ width: `${progress.progress_pct}%`, background: color }} />
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
        {progress.error_msg && (
          <div className={styles.errorMsg}>{progress.error_msg}</div>
        )}
      </div>

      {/* 연결 / 시스템 */}
      <div className={styles.card}>
        <div className={styles.cardTitle}>시스템</div>
        <div className={styles.connRow}>
          <span className={styles.connDot} style={{
            background: connected ? '#22c55e' : '#ef4444',
            animation: connected ? 'pulse 2.5s infinite' : 'none'
          }} />
          <span className={styles.connText}>
            {connected ? '서버 연결됨' : '서버 연결 끊김'}
          </span>
        </div>
        <div className={styles.connSub}>
          {connected ? 'WebSocket 실시간 수신 중' : '2초 후 재연결 시도 중...'}
        </div>

        <div style={{ marginTop: 20 }}>
          <div className={styles.lastJobGrid}>
            <div className={styles.lastJobItem}>
              <span className={styles.lastJobLabel}>Job ID</span>
              <span className={styles.lastJobValue}>{progress.job_id || '—'}</span>
            </div>
            <div className={styles.lastJobItem}>
              <span className={styles.lastJobLabel}>상태</span>
              <span className={styles.lastJobValue} style={{ color }}>
                {STATUS_LABEL[progress.status] || '—'}
              </span>
            </div>
            <div className={styles.lastJobItem}>
              <span className={styles.lastJobLabel}>완료 획</span>
              <span className={styles.lastJobValue}>{progress.current_stroke || 0}</span>
            </div>
            <div className={styles.lastJobItem}>
              <span className={styles.lastJobLabel}>전체 획</span>
              <span className={styles.lastJobValue}>{progress.total_strokes || 0}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
