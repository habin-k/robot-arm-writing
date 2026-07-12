import { useState, useRef, useCallback, useEffect } from 'react'
import UserTab from './components/user/UserTab'
import StatusTab from './components/user/StatusTab'
import HistoryTab from './components/user/HistoryTab'
import DashboardTab from './components/admin/DashboardTab'
import AdminTab from './components/admin/AdminTab'
import TuningTab from './components/admin/TuningTab'
import LoginModal from './components/admin/LoginModal'
import RecoveryModal from './components/admin/RecoveryModal'
import { useProgress } from './hooks/useProgress'
import { usePersistentState } from './hooks/usePersistentState'
import { setAuthToken, getStoredToken } from './api/client'
import './App.css'

const NAV = [
  { id: 'write',     label: '글씨 쓰기',  icon: '✏️',  admin: false },
  { id: 'dashboard', label: '대시보드',   icon: '🖥️',  admin: true  },
  { id: 'status',    label: '작업 상태',  icon: '📊',  admin: true  },
  { id: 'history',   label: '이용 내역',  icon: '🕘',  admin: true  },
  { id: 'robot',     label: '로봇 제어',  icon: '🤖',  admin: true  },
  { id: 'tuning',    label: '파라미터 설정', icon: '⚙️', admin: true  },
]

const PAGE_TITLE = {
  write:     '글씨 쓰기',
  dashboard: '대시보드',
  status:    '작업 상태',
  history:   '이용 내역',
  robot:     '로봇 제어',
  tuning:    '파라미터 설정',
}

const SIDEBAR_MIN = 160
const SIDEBAR_MAX = 460

export default function App() {
  // 현재 탭도 sessionStorage 에 보관 → 새로고침해도 보던 탭 유지 (창 닫으면 초기화)
  const [page, setPage] = usePersistentState('page', 'write')
  // 새로고침 시에도 로그인 유지 (토큰은 sessionStorage 에 보관, 창을 닫으면 사라짐)
  const [token, setToken] = useState(() => getStoredToken())

  // 복원된 탭이 관리자 전용인데 로그인이 안 돼 있으면 글씨쓰기로 폴백 (빈 화면 방지)
  useEffect(() => {
    const item = NAV.find(n => n.id === page)
    if (item?.admin && !token) setPage('write')
  }, [page, token, setPage])
  const [showLogin, setShowLogin] = useState(false)
  const [pendingPage, setPendingPage] = useState(null)

  // 로봇 수동 복구 팝업: 비상정지 등으로 MANUAL_REQUIRED 진입 시, 관리자에게만 표시.
  // (복구는 관리자 권한 작업이고 /robot/retry 도 관리자 전용이므로 로그인 상태에서만 띄운다.)
  const { progress } = useProgress()
  const [showRecovery, setShowRecovery] = useState(false)
  useEffect(() => {
    if (progress.status === 'manual_required') {
      if (token) setShowRecovery(true)
    } else {
      setShowRecovery(false)   // 재시도/리셋으로 복구되면 자동으로 닫힘
    }
  }, [progress.status, token])

  // 사이드바 너비 (드래그로 조절, localStorage에 저장)
  const [sidebarW, setSidebarW] = useState(() => {
    const v = Number(localStorage.getItem('sidebarW'))
    return v >= SIDEBAR_MIN && v <= SIDEBAR_MAX ? v : 220
  })
  const [dragging, setDragging] = useState(false)
  const dragRef = useRef(null)

  const startResize = useCallback((e) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startW: sidebarW }
    setDragging(true)
  }, [sidebarW])

  useEffect(() => {
    if (!dragging) return
    const onMove = (e) => {
      const { startX, startW } = dragRef.current
      const w = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, startW + (e.clientX - startX)))
      setSidebarW(w)
    }
    const onUp = () => setDragging(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [dragging])

  // 너비가 바뀔 때마다 저장 (드래그 종료 시점 포함)
  useEffect(() => { localStorage.setItem('sidebarW', String(sidebarW)) }, [sidebarW])

  const handleNav = (item) => {
    if (item.admin && !token) {
      setPendingPage(item.id)
      setShowLogin(true)
    } else {
      setPage(item.id)
    }
  }

  const handleLogin = (t) => {
    setAuthToken(t)
    setToken(t)
    setShowLogin(false)
    if (pendingPage) { setPage(pendingPage); setPendingPage(null) }
  }

  const handleLogout = () => {
    setAuthToken(null)
    setToken(null)
    setPage('write')
  }

  return (
    <div className={`app ${dragging ? 'appResizing' : ''}`}>
      {/* 사이드바 */}
      <aside className="sidebar" style={{ width: sidebarW }}>
        <div className="sidebarTop">
          <div className="sidebarLogo">Robot Writing</div>
        </div>

        <nav className="sidebarSection">
          <span className="sidebarLabel">사용자</span>
          {NAV.filter(n => !n.admin).map(item => (
            <button
              key={item.id}
              className={`navItem ${page === item.id ? 'navItemActive' : ''}`}
              onClick={() => handleNav(item)}
            >
              <span className="navIcon">{item.icon}</span>
              {item.label}
            </button>
          ))}

          <span className="sidebarLabel">관리자</span>
          {NAV.filter(n => n.admin).map(item => (
            <button
              key={item.id}
              className={`navItem ${page === item.id ? 'navItemActive' : ''}`}
              onClick={() => handleNav(item)}
            >
              <span className="navIcon">{item.icon}</span>
              {item.label}
              {!token && <span className="navLock">🔒</span>}
            </button>
          ))}
        </nav>

        <div className="sidebarBottom">
          {token ? (
            <>
              <div className="adminBadge">
                <span className="adminBadgeDot" />
                관리자
              </div>
              <button className="logoutBtn" onClick={handleLogout}>
                <span className="navIcon">↩</span>
                로그아웃
              </button>
            </>
          ) : (
            <button className="navItem" onClick={() => setShowLogin(true)}>
              <span className="navIcon">🔑</span>
              관리자 로그인
            </button>
          )}
        </div>
      </aside>

      {/* 사이드바 너비 조절 핸들 (드래그) */}
      <div
        className={`resizer ${dragging ? 'resizerActive' : ''}`}
        onMouseDown={startResize}
        role="separator"
        aria-orientation="vertical"
        title="드래그해서 너비 조절"
      />

      {/* 메인 */}
      <main className="main">
        <div className="pageHeader">
          <h1 className="pageTitle">{PAGE_TITLE[page]}</h1>
        </div>
        <div className="pageContent">
          {page === 'write'     && <UserTab />}
          {page === 'dashboard' && token && <DashboardTab />}
          {page === 'status'    && token && <StatusTab />}
          {page === 'history' && token && <HistoryTab />}
          {page === 'robot'   && token && <AdminTab />}
          {page === 'tuning'  && token && <TuningTab />}
        </div>
      </main>

      {showLogin && (
        <LoginModal
          onLogin={handleLogin}
          onClose={() => { setShowLogin(false); setPendingPage(null) }}
        />
      )}

      {showRecovery && token && (
        <RecoveryModal
          errorMsg={progress.error_msg}
          onClose={() => setShowRecovery(false)}
        />
      )}
    </div>
  )
}
