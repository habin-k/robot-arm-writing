import { useState } from 'react'
import { login } from '../../api/robot'
import { setAuthToken } from '../../api/client'
import styles from './LoginModal.module.css'

export default function LoginModal({ onLogin, onClose }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const r = await login({ username, password })
      setAuthToken(r.data.access_token)
      onLogin(r.data.access_token)
    } catch {
      setError('아이디 또는 비밀번호가 올바르지 않습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <form className={styles.modal} onSubmit={handleSubmit}>
        <div className={styles.header}>
          <h2 className={styles.title}>관리자 로그인</h2>
          <button type="button" className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>
        <div className={styles.field}>
          <label className={styles.label}>아이디</label>
          <input className={styles.input} value={username}
            onChange={e => setUsername(e.target.value)} autoFocus />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>비밀번호</label>
          <input className={styles.input} type="password" value={password}
            onChange={e => setPassword(e.target.value)} />
        </div>
        {error && <p className={styles.error}>{error}</p>}
        <button className={styles.btn} disabled={loading}>
          {loading ? '로그인 중...' : '로그인'}
        </button>
      </form>
    </div>
  )
}
