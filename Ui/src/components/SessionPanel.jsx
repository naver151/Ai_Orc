/**
 * SessionPanel
 *
 * 프로젝트 세션 이력 패널.
 * 워크스페이스 우측에 붙는 슬라이드 패널.
 * 마지막 세션 요약과 변경된 파일 목록을 표시.
 *
 * Props:
 *   projectId   프로젝트 ID (null이면 렌더 안 함)
 *   visible     표시 여부
 *   onClose     () => void
 */

import { useState, useEffect, useCallback } from 'react'
import styles from './SessionPanel.module.css'

const BACKEND = 'http://localhost:8000'

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now - d
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1)  return '방금 전'
  if (diffMin < 60) return `${diffMin}분 전`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24)   return `${diffH}시간 전`
  return d.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function fmtDuration(startIso, endIso) {
  if (!startIso || !endIso) return null
  const diffMs = new Date(endIso) - new Date(startIso)
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '1분 미만'
  if (diffMin < 60) return `${diffMin}분`
  return `${Math.floor(diffMin / 60)}시간 ${diffMin % 60}분`
}

// ── 세션 카드 ──────────────────────────────────────────────────────────────
function SessionCard({ session, index }) {
  const [open, setOpen] = useState(index === 0)  // 첫 번째만 기본 열림

  const duration  = fmtDuration(session.started_at, session.ended_at)
  const isRunning = !session.ended_at

  return (
    <div className={`${styles.card} ${isRunning ? styles.cardRunning : ''}`}>
      {/* 카드 헤더 */}
      <button className={styles.cardHeader} onClick={() => setOpen(o => !o)}>
        <div className={styles.cardLeft}>
          {isRunning
            ? <span className={styles.runningDot} title="진행 중" />
            : <span className={styles.doneIcon}>✓</span>
          }
          <div className={styles.cardMeta}>
            <span className={styles.cardDate}>{fmtDate(session.started_at)}</span>
            {duration && <span className={styles.cardDuration}>{duration}</span>}
          </div>
        </div>
        <div className={styles.cardRight}>
          {session.files_changed?.length > 0 && (
            <span className={styles.filesBadge}>📄 {session.files_changed.length}</span>
          )}
          <span className={styles.toggle}>{open ? '▾' : '▸'}</span>
        </div>
      </button>

      {/* 카드 바디 */}
      {open && (
        <div className={styles.cardBody}>
          {/* 요약 */}
          {session.summary ? (
            <div className={styles.summary}>{session.summary}</div>
          ) : (
            <div className={styles.noSummary}>
              {isRunning ? '진행 중...' : '요약 없음'}
            </div>
          )}

          {/* 변경된 파일 */}
          {session.files_changed?.length > 0 && (
            <div className={styles.filesSection}>
              <div className={styles.filesSectionTitle}>변경된 파일</div>
              <div className={styles.filesList}>
                {session.files_changed.map((f, i) => (
                  <div key={i} className={styles.fileItem}>
                    <span className={styles.fileIcon}>📄</span>
                    <span className={styles.filePath}>{f}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────
export default function SessionPanel({ projectId, visible, onClose }) {
  const [sessions, setSessions] = useState([])
  const [loading,  setLoading]  = useState(false)

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const res = await fetch(`${BACKEND}/projects/${projectId}/sessions`)
      if (res.ok) setSessions(await res.json())
    } catch { /* 무시 */ }
    finally { setLoading(false) }
  }, [projectId])

  useEffect(() => {
    if (visible && projectId) load()
  }, [visible, projectId, load])

  // 패널이 열려 있는 동안 30초마다 자동 갱신 (진행 중인 세션 반영)
  useEffect(() => {
    if (!visible || !projectId) return
    const timer = setInterval(load, 30000)
    return () => clearInterval(timer)
  }, [visible, projectId, load])

  if (!visible) return null

  return (
    <div className={styles.panel}>
      {/* 헤더 */}
      <div className={styles.header}>
        <span className={styles.headerIcon}>📅</span>
        <span className={styles.headerTitle}>세션 이력</span>
        {loading && <span className={styles.spinner}>↻</span>}
        <button className={styles.refreshBtn} onClick={load} title="새로고침">⟳</button>
        <button className={styles.closeBtn} onClick={onClose} title="닫기">✕</button>
      </div>

      {/* 세션 목록 */}
      <div className={styles.list}>
        {!loading && sessions.length === 0 && (
          <div className={styles.empty}>
            아직 세션이 없습니다<br />
            <span className={styles.emptyHint}>작업을 시작하면 자동으로 기록됩니다</span>
          </div>
        )}
        {sessions.map((s, i) => (
          <SessionCard key={s.id} session={s} index={i} />
        ))}
      </div>
    </div>
  )
}
