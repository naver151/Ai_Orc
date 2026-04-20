import { useState, useRef, useEffect } from 'react'
import './styles/globals.css'
import LandingPage from './components/LandingPage'
import UserFormPage from './components/UserFormPage'
import ChatPage from './components/ChatPage'
import InfoModal from './components/InfoModal'

function loadSession() {
  try {
    const saved = localStorage.getItem('aiorc_session')
    if (saved) return JSON.parse(saved)
  } catch {}
  return null
}

function saveSession(page, user) {
  try {
    localStorage.setItem('aiorc_session', JSON.stringify({ page, user }))
  } catch {}
}

export default function App() {
  const session = loadSession()
  const [page, setPage] = useState(session?.page ?? 'landing')
  const [modalOpen, setModalOpen] = useState(false)
  const [expanding, setExpanding] = useState(false)
  const [expandStyle, setExpandStyle] = useState({})
  const [user, setUser] = useState(session?.user ?? null)
  const [theme, setTheme] = useState(() => localStorage.getItem('aiorc_theme') ?? 'dark')
  const [fontSize, setFontSize] = useState(() => localStorage.getItem('aiorc_font_size') ?? 'medium')
  const appRef = useRef(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('aiorc_theme', theme)
  }, [theme])

  useEffect(() => {
    if (fontSize === 'medium') {
      document.documentElement.removeAttribute('data-font-size')
    } else {
      document.documentElement.setAttribute('data-font-size', fontSize)
    }
    localStorage.setItem('aiorc_font_size', fontSize)
  }, [fontSize])

  const FONT_SIZES = ['small', 'medium', 'large', 'xl']
  const FONT_LABELS = { small: 'S', medium: 'M', large: 'L', xl: 'XL' }
  const cycleFontSize = () =>
    setFontSize(cur => FONT_SIZES[(FONT_SIZES.indexOf(cur) + 1) % FONT_SIZES.length])

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  const runExpandAnim = (btnEl, onDone) => {
    if (!btnEl) { onDone(); return }
    const btnRect = btnEl.getBoundingClientRect()
    const appRect = appRef.current.getBoundingClientRect()

    const x = btnRect.left - appRect.left
    const y = btnRect.top - appRect.top
    const w = btnRect.width
    const h = btnRect.height
    const scale = Math.max(appRect.width, appRect.height) * 2.5 / Math.min(w, h)

    setExpandStyle({
      left: x + 'px',
      top: y + 'px',
      width: w + 'px',
      height: h + 'px',
      borderRadius: '14px',
      opacity: 1,
      transform: 'scale(1)',
      transition: 'none',
    })
    setExpanding(true)

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setExpandStyle(prev => ({
          ...prev,
          transform: `scale(${scale})`,
          borderRadius: '0px',
          transition: 'transform 0.65s cubic-bezier(0.76,0,0.24,1), border-radius 0.5s ease',
        }))

        setTimeout(() => {
          onDone()
          setExpandStyle(prev => ({
            ...prev,
            opacity: 0,
            transition: 'opacity 0.3s ease',
          }))
          setTimeout(() => {
            setExpanding(false)
            setExpandStyle({})
          }, 320)
        }, 500)
      })
    })
  }

  // 랜딩 → 정보 입력 폼 (저장된 프로필 있으면 바로 채팅)
  const handleStart = (btnEl) => {
    const savedUser = (() => {
      try { return JSON.parse(localStorage.getItem('aiorc_user')) } catch { return null }
    })()
    runExpandAnim(btnEl, () => {
      if (savedUser) {
        setUser(savedUser)
        setPage('chat')
        saveSession('chat', savedUser)
      } else {
        setPage('userform')
        saveSession('userform', user)
      }
    })
  }

  // 정보 입력 완료 → 채팅
  const handleUserFormSubmit = (userData) => {
    // 사용자별 고유 ID 생성 (최초 1회)
    const uid = `u${Date.now()}${Math.random().toString(36).slice(2, 6)}`
    const userWithId = { ...userData, uid }
    localStorage.setItem('aiorc_user', JSON.stringify(userWithId))
    setUser(userWithId)
    setPage('chat')
    saveSession('chat', userWithId)
  }

  // 채팅 → 랜딩으로 돌아갈 때 세션만 초기화 (프로필은 유지)
  const handleBack = () => {
    setPage('landing')
    setUser(null)
    saveSession('landing', null)
  }

  return (
    <div ref={appRef} style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden', background: 'var(--bg)' }}>

      {page === 'landing' && (
        <LandingPage
          onStart={handleStart}
          onInfo={() => setModalOpen(true)}
          theme={theme}
          onThemeToggle={toggleTheme}
        />
      )}

      {expanding && (
        <div style={{
          position: 'absolute',
          background: 'var(--accent)',
          pointerEvents: 'none',
          zIndex: 90,
          ...expandStyle,
        }} />
      )}

      {page === 'userform' && (
        <UserFormPage onSubmit={handleUserFormSubmit} theme={theme} onThemeToggle={toggleTheme} />
      )}

      {page === 'chat' && (
        <ChatPage
          user={user}
          onBack={handleBack}
          theme={theme}
          onThemeToggle={toggleTheme}
          fontSize={fontSize}
          fontLabel={FONT_LABELS[fontSize]}
          onFontSizeCycle={cycleFontSize}
        />
      )}

      <InfoModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  )
}
