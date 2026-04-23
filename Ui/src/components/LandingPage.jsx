import { useRef } from 'react'
import styles from './LandingPage.module.css'

export default function LandingPage({ onStart, onInfo, onAdmin, theme = 'dark', onThemeToggle }) {
  const startBtnRef = useRef(null)

  const handleStart = () => {
    onStart(startBtnRef.current)
  }

  return (
    <div className={styles.landing}>
      <div className={styles.gridBg} />
      <div className={styles.glow} />

      <button className={styles.themeBtn} onClick={onThemeToggle} title={theme === 'dark' ? '라이트 모드' : '다크 모드'}>
        {theme === 'dark' ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="5"/>
            <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
            <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
        )}
      </button>

      <div className={styles.content}>
        <div className={styles.tag}>
          <span className={styles.tagDot} />
          AI Multi-Agent System
        </div>

        <h1 className={styles.title}>
          AI.<span className={styles.titleAccent}>Orc</span>
        </h1>

        <p className={styles.subtitle}>
          여러 AI 에이전트가 협력하여<br />
          복잡한 문제를 함께 해결합니다
        </p>

        <div className={styles.btnRow}>
          <button ref={startBtnRef} className={styles.btnStart} onClick={handleStart}>
            시작하기
          </button>
          <button className={styles.btnInfo} onClick={onInfo}>
            설명 보기
          </button>
          <button className={styles.btnInfo} onClick={onAdmin} style={{ marginLeft: 4 }}>
            관리자
          </button>
        </div>
      </div>
    </div>
  )
}
