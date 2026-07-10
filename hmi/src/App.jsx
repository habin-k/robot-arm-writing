import { useState, useRef, useCallback, useEffect } from 'react'
import UserTab from './components/user/UserTab'
import StatusTab from './components/user/StatusTab'
import HistoryTab from './components/user/HistoryTab'
import AdminTab from './components/admin/AdminTab'
import LoginModal from './components/admin/LoginModal'
import { setAuthToken, getStoredToken } from './api/client'
import './App.css'

const NAV = [
  { id: 'write',   label: '글씨 쓰기',  icon: '✏️',  admin: false },
  { id: 'status',  label: '작업 상태',  icon: '📊',  admin: false },
  { id: 'history', label: '이용 내역',  icon: '🕘',  admin: false },
  { id: 'robot',   label: '로봇 제어',  icon: '🤖',  admin: true  },
]

const PAGE_TITLE = {
  write:   '글씨 쓰기',
  status:  '작업 상태',
  history: '이용 내역',
  robot:   '로봇 제어',
}

const SIDEBAR_MIN = 160
const SIDEBAR_MAX = 460

export default function App() {
  const [page, setPage] = useState('write')
  // 새로고침 시에도 로그인 유지 (토큰은 sessionStorage 에 보관, 창을 닫으면 사라짐)
  const [token, setToken] = useState(() => getStoredToken())
  const [showLogin, setShowLogin] = useState(false)
  const [pendingPage, setPendingPage] = useState(null)

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
          {page === 'write'   && <UserTab />}
          {page === 'status'  && <StatusTab />}
          {page === 'history' && <HistoryTab />}
          {page === 'robot'   && token && <AdminTab />}
        </div>
      </main>

      {showLogin && (
        <LoginModal
          onLogin={handleLogin}
          onClose={() => { setShowLogin(false); setPendingPage(null) }}
        />
      )}
    </div>
  )
}
