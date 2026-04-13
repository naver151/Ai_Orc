import { useState, useRef } from 'react'
import './styles/globals.css'
import LandingPage from './components/LandingPage'
import ChatPage from './components/ChatPage'
import InfoModal from './components/InfoModal'

export default function App() {
  const [page, setPage] = useState('landing')
  const [modalOpen, setModalOpen] = useState(false)
  const [expanding, setExpanding] = useState(false)
  const [expandStyle, setExpandStyle] = useState({})
  const appRef = useRef(null)

  const handleStart = (btnEl) => {
    if (!btnEl) return
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
          setPage('chat')
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

  return (
    <div ref={appRef} style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden', background: 'var(--bg)' }}>

      {page === 'landing' && (
        <LandingPage
          onStart={handleStart}
          onInfo={() => setModalOpen(true)}
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

      {page === 'chat' && (
        <ChatPage onBack={() => setPage('landing')} />
      )}

      <InfoModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  )
}
