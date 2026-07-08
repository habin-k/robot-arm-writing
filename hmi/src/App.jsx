import { useState } from 'react'
import UserTab from './components/user/UserTab'
import StatusTab from './components/user/StatusTab'
import AdminTab from './components/admin/AdminTab'
import LoginModal from './components/admin/LoginModal'
import { setAuthToken } from './api/client'
import './App.css'

const NAV = [
  { id: 'write',  label: '글씨 쓰기',  icon: '✏️',  admin: false },
  { id: 'status', label: '작업 상태',  icon: '📊',  admin: false },
  { id: 'robot',  label: '로봇 제어',  icon: '🤖',  admin: true  },
  { id: 'estop',  label: '비상정지',   icon: '🔴',  admin: true  },
]

const PAGE_TITLE = {
  write:  '글씨 쓰기',
  status: '작업 상태',
  robot:  '로봇 제어',
  estop:  '비상정지',
}

export default function App() {
  const [page, setPage] = useState('write')
  const [token, setToken] = useState(null)
  const [showLogin, setShowLogin] = useState(false)
  const [pendingPage, setPendingPage] = useState(null)

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
    <div className="app">
      {/* 사이드바 */}
      <aside className="sidebar">
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

      {/* 메인 */}
      <main className="main">
        <div className="pageHeader">
          <h1 className="pageTitle">{PAGE_TITLE[page]}</h1>
        </div>
        <div className="pageContent">
          {page === 'write'  && <UserTab />}
          {page === 'status' && <StatusTab />}
          {page === 'robot'  && token && <AdminTab />}
          {page === 'estop'  && token && <AdminTab estopOnly />}
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
