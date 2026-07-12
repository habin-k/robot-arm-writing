import { useState } from 'react'
import { retryTask, errorReset } from '../../api/robot'
import styles from './RecoveryModal.module.css'

// 비상정지 등으로 작업이 중단돼 로봇이 '수동 복구 모드(MANUAL_REQUIRED)'로 진입했을 때
// 뜨는 팝업. 관리자만 볼 수 있으며(App.jsx 에서 로그인 상태일 때만 렌더), 여기서 바로
// 작업을 재시도하거나 에러를 리셋할 수 있다.
export default function RecoveryModal({ errorMsg, onClose }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState('')

  const run = async (fn, okMsg) => {
    setBusy(true)
    setResult('')
    try {
      const res = await fn()
      setResult(res?.data?.message || okMsg)
      // 재시도 성공(자율모드 복귀) 시 잠시 후 팝업 닫기
      setTimeout(onClose, 1200)
    } catch (e) {
      setResult('오류: ' + (e.response?.data?.detail || e.message))
      setBusy(false)
    }
  }

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <div className={styles.iconRow}>
          <span className={styles.icon}>⚠️</span>
          <h2 className={styles.title}>작업이 중단되었습니다</h2>
        </div>
        <p className={styles.desc}>
          비상정지 또는 오류로 로봇이 <b>수동 복구 모드</b>로 전환되었습니다.
          {errorMsg && <><br /><span className={styles.reason}>{errorMsg}</span></>}
        </p>
        <p className={styles.hint}>
          로봇 주변 안전을 확인한 뒤, 같은 작업을 이어서 재시도하거나 에러를 리셋하세요.
        </p>

        {result && <div className={styles.result}>{result}</div>}

        <div className={styles.actions}>
          <button className={styles.btnSecondary} onClick={() => run(errorReset, '에러 리셋 명령 전송')}
            disabled={busy}>
            ↺ 에러 리셋
          </button>
          <button className={styles.btnPrimary} onClick={() => run(retryTask, '작업 재시도 요청 전송')}
            disabled={busy}>
            ▶ 작업 재시도
          </button>
        </div>

        <button className={styles.dismiss} onClick={onClose} disabled={busy}>나중에</button>
      </div>
    </div>
  )
}
