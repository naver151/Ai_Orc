import { useRef } from 'react'
import styles from './LandingPage.module.css'

export default function LandingPage({ onStart, onInfo }) {
  const startBtnRef = useRef(null)

  const handleStart = () => {
    onStart(startBtnRef.current)
  }

  return (
    <div className={styles.landing}>
      <div className={styles.gridBg} />
      <div className={styles.glow} />

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
        </div>
      </div>
    </div>
  )
}
