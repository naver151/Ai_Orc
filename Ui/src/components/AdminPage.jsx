import { useState, useEffect, useCallback } from 'react'
import styles from './AdminPage.module.css'

const BACKEND = 'http://localhost:8000'

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('ko-KR', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

export default function AdminPage({ onBack }) {
  const [logs, setLogs]           = useState([])
  const [loading, setLoading]     = useState(true)
  const [selected, setSelected]   = useState(null)   // 선택된 로그 상세
  const [ratingDone, setRatingDone] = useState(false)

  const fetchLogs = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${BACKEND}/orchestration-logs?limit=50`)
      if (res.ok) setLogs(await res.json())
    } catch {}
    setLoading(false)
  }, [])

  const fetchDetail = useCallback(async (id) => {
    try {
      const res = await fetch(`${BACKEND}/orchestration-logs/${id}`)
      if (res.ok) {
        setSelected(await res.json())
        setRatingDone(false)
      }
    } catch {}
  }, [])

  const submitRating = useCallback(async (logId, rating) => {
    try {
      const res = await fetch(`${BACKEND}/orchestration-logs/${logId}/rating`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating }),
      })
      if (res.ok) {
        const updated = await res.json()
        setSelected(updated)
        setLogs(prev => prev.map(l => l.id === logId ? { ...l, rating } : l))
        setRatingDone(true)
      }
    } catch {}
  }, [])

  const exportJSONL = useCallback(() => {
    window.open(`${BACKEND}/orchestration-logs/export?min_rating=4`, '_blank')
  }, [])

  useEffect(() => { fetchLogs() }, [fetchLogs])

  return (
    <div className={styles.page}>

      {/* 헤더 */}
      <div className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>← 뒤로</button>
        <span className={styles.title}>오케스트레이션 로그</span>
        <span className={styles.subtitle}>총 {logs.length}건</span>
        <button className={styles.exportBtn} onClick={exportJSONL}>
          ↓ JSONL 내보내기 (평점 4+)
        </button>
      </div>

      <div className={styles.body}>

        {/* 목록 */}
        <div className={styles.listPanel}>
          <div className={styles.listHeader}>실행 기록</div>

          {loading && <div className={styles.loading}>불러오는 중...</div>}

          {!loading && logs.length === 0 && (
            <div className={styles.empty}>아직 기록이 없습니다.</div>
          )}

          {logs.map(log => (
            <div
              key={log.id}
              className={`${styles.logItem} ${selected?.id === log.id ? styles.logItemActive : ''}`}
              onClick={() => fetchDetail(log.id)}
            >
              <div className={styles.logPrompt}>{log.user_prompt}</div>
              <div className={styles.logMeta}>
                <span>{formatDate(log.created_at)}</span>
                {log.rating && (
                  <span className={styles.ratingBadge}>★ {log.rating}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* 상세 */}
        <div className={styles.detailPanel}>
          {!selected ? (
            <div className={styles.noSelect}>로그를 선택하면 상세 내용이 표시됩니다.</div>
          ) : (
            <>
              <div className={styles.detailPrompt}>{selected.user_prompt}</div>

              {selected.plan_summary && (
                <div className={styles.detailPlan}>계획: {selected.plan_summary}</div>
              )}

              {/* 에이전트별 작업 */}
              {selected.subtasks?.length > 0 && (
                <div>
                  <div className={styles.sectionTitle}>에이전트 작업</div>
                  <div className={styles.agentList}>
                    {selected.subtasks.map((task, i) => (
                      <div key={i} className={styles.agentRow}>
                        <div className={styles.agentRowName}>
                          {selected.worker_names?.[i] ?? `에이전트 ${i + 1}`}
                        </div>
                        <div>{task}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 에이전트 결과 */}
              {selected.worker_results?.length > 0 && (
                <div>
                  <div className={styles.sectionTitle}>에이전트 결과</div>
                  <div className={styles.agentList}>
                    {selected.worker_results.map((result, i) => (
                      <div key={i} className={styles.agentRow}>
                        <div className={styles.agentRowName}>
                          {selected.worker_names?.[i] ?? `에이전트 ${i + 1}`}
                        </div>
                        <div style={{ whiteSpace: 'pre-wrap', marginTop: 6, fontSize: 12 }}>
                          {result?.length > 500 ? result.slice(0, 500) + '...' : result}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 최종 결과 */}
              {selected.synthesis_result && (
                <div>
                  <div className={styles.sectionTitle}>최종 결과</div>
                  <div className={styles.resultBox}>{selected.synthesis_result}</div>
                </div>
              )}

              {/* 평점 */}
              <div className={styles.ratingRow}>
                <span className={styles.ratingLabel}>평점:</span>
                <div className={styles.stars}>
                  {[1, 2, 3, 4, 5].map(n => (
                    <button
                      key={n}
                      className={`${styles.star} ${(selected.rating ?? 0) >= n ? styles.starActive : ''}`}
                      onClick={() => submitRating(selected.id, n)}
                    >
                      ★
                    </button>
                  ))}
                </div>
                {ratingDone && <span className={styles.ratingDone}>저장됨</span>}
              </div>
            </>
          )}
        </div>

      </div>
    </div>
  )
}
