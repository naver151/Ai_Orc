import { useState, useEffect, useCallback } from 'react'
import styles from './AdminPage.module.css'

const BACKEND = 'http://localhost:8000'

// ── 날짜 포맷 ────────────────────────────────────────────────
function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('ko-KR', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

// ── 점수 → 색상 ──────────────────────────────────────────────
function scoreColor(score) {
  if (score == null) return '#555'
  if (score >= 8)   return 'var(--teal)'
  if (score >= 6)   return '#f5a623'
  return '#ff5555'
}

// ── KPI 카드 ─────────────────────────────────────────────────
function KpiCard({ icon, label, value, sub, color }) {
  return (
    <div className={styles.kpiCard}>
      <div className={styles.kpiIcon} style={{ color }}>{icon}</div>
      <div className={styles.kpiValue} style={{ color }}>{value ?? '—'}</div>
      <div className={styles.kpiLabel}>{label}</div>
      {sub && <div className={styles.kpiSub}>{sub}</div>}
    </div>
  )
}

// ── 수평 바 차트 ─────────────────────────────────────────────
function BarChart({ items }) {
  if (!items?.length) return <div className={styles.noData}>데이터 없음</div>
  const max = Math.max(...items.map(x => x.value), 1)
  return (
    <div className={styles.barChart}>
      {items.map((item, i) => (
        <div key={i} className={styles.barRow}>
          <div className={styles.barLabel}>{item.label}</div>
          <div className={styles.barTrack}>
            <div
              className={styles.barFill}
              style={{
                width: `${(item.value / max) * 100}%`,
                background: item.color ?? 'var(--accent)',
              }}
            />
            <span className={styles.barValue} style={{ color: item.color ?? 'var(--accent)' }}>
              {typeof item.value === 'number' ? item.value.toFixed(1) : item.value}
            </span>
          </div>
          {item.sub && <div className={styles.barSub}>{item.sub}</div>}
        </div>
      ))}
    </div>
  )
}

// ── SVG 선 그래프 ─────────────────────────────────────────────
function LineChart({ data }) {
  if (!data?.length) return <div className={styles.noData}>데이터 없음</div>
  const W = 600, H = 180, PAD = { t: 16, r: 20, b: 32, l: 32 }
  const iW = W - PAD.l - PAD.r
  const iH = H - PAD.t - PAD.b
  const n  = data.length

  const xOf = i  => PAD.l + (n > 1 ? (i / (n - 1)) * iW : iW / 2)
  const yOf = sc => PAD.t + iH - ((sc - 1) / 9) * iH   // score 1~10

  // provider별 포인트 그룹 (선 색상용)
  const byProvider = {}
  data.forEach((d, i) => {
    if (!byProvider[d.provider]) byProvider[d.provider] = { color: d.color, pts: [] }
    byProvider[d.provider].pts.push({ i, score: d.score })
  })

  // 전체 평균선
  const avg = data.reduce((s, d) => s + d.score, 0) / n
  const avgY = yOf(avg)

  // y축 눈금 (2, 4, 6, 8, 10)
  const yTicks = [2, 4, 6, 8, 10]

  return (
    <div className={styles.lineChartWrap}>
      <svg viewBox={`0 0 ${W} ${H}`} className={styles.lineSvg} preserveAspectRatio="xMidYMid meet">
        {/* 배경 눈금 */}
        {yTicks.map(t => (
          <g key={t}>
            <line
              x1={PAD.l} y1={yOf(t)} x2={W - PAD.r} y2={yOf(t)}
              stroke="var(--border)" strokeWidth="1" strokeDasharray="4 4"
            />
            <text x={PAD.l - 6} y={yOf(t) + 4} fontSize="10" fill="var(--text3)" textAnchor="end">{t}</text>
          </g>
        ))}

        {/* 평균선 */}
        <line
          x1={PAD.l} y1={avgY} x2={W - PAD.r} y2={avgY}
          stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" strokeDasharray="6 3"
        />
        <text x={W - PAD.r + 4} y={avgY + 4} fontSize="9" fill="rgba(255,255,255,0.4)">avg</text>

        {/* provider별 선 */}
        {Object.entries(byProvider).map(([prov, { color, pts }]) => {
          if (pts.length < 2) return null
          const d = pts.map((p, j) => `${j === 0 ? 'M' : 'L'}${xOf(p.i)},${yOf(p.score)}`).join(' ')
          return (
            <path key={prov} d={d} fill="none"
              stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              opacity="0.8"
            />
          )
        })}

        {/* 포인트 */}
        {data.map((d, i) => (
          <circle
            key={i}
            cx={xOf(i)} cy={yOf(d.score)} r="4"
            fill={d.color} stroke="var(--bg)" strokeWidth="1.5"
          >
            <title>{d.label} — {d.task_label} — {d.score}/10\n{formatDate(d.created_at)}</title>
          </circle>
        ))}

        {/* x축 라벨 (처음·끝·중간) */}
        {[0, Math.floor((n - 1) / 2), n - 1].filter((v, i, a) => a.indexOf(v) === i && v < n).map(i => (
          <text key={i} x={xOf(i)} y={H - 6} fontSize="9" fill="var(--text3)" textAnchor="middle">
            {data[i] ? formatDate(data[i].created_at).slice(0, 8) : ''}
          </text>
        ))}
      </svg>

      {/* 범례 */}
      <div className={styles.lineLegend}>
        {Object.entries(byProvider).map(([prov, { color, pts }]) => (
          <div key={prov} className={styles.legendItem}>
            <div className={styles.legendDot} style={{ background: color }} />
            <span style={{ color }}>{prov}</span>
            <span className={styles.legendCount}>({pts.length}건)</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── task_type × provider 히트맵 ──────────────────────────────
function HeatmapGrid({ matrix, leaderboard }) {
  if (!matrix || !Object.keys(matrix).length) return <div className={styles.noData}>데이터 없음</div>
  const providers = leaderboard.map(l => l.provider)
  const taskTypes = Object.keys(matrix)

  const cellColor = (score) => {
    if (score == null) return 'transparent'
    const t = (score - 4) / 6   // 4→0, 10→1
    const r = Math.round(255 * (1 - t))
    const g = Math.round(200 * t)
    return `rgba(${r},${g},80,0.25)`
  }

  return (
    <div className={styles.heatmap}>
      <table className={styles.heatmapTable}>
        <thead>
          <tr>
            <th className={styles.heatmapTh}>태스크 유형</th>
            {providers.map(p => {
              const info = leaderboard.find(l => l.provider === p)
              return (
                <th key={p} className={styles.heatmapTh}>
                  <span style={{ color: info?.color }}>{info?.label ?? p}</span>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {taskTypes.map(tt => {
            const row = matrix[tt]
            return (
              <tr key={tt}>
                <td className={styles.heatmapRowLabel}>{row.label}</td>
                {providers.map(p => {
                  const cell = row.providers?.[p]
                  const score = cell?.avg ?? null
                  return (
                    <td
                      key={p}
                      className={styles.heatmapCell}
                      style={{ background: cellColor(score) }}
                      title={score != null ? `${score}/10 (${cell.count}건)` : '데이터 없음'}
                    >
                      {score != null ? (
                        <span style={{ color: scoreColor(score), fontWeight: 700 }}>
                          {score.toFixed(1)}
                        </span>
                      ) : (
                        <span className={styles.heatmapNull}>—</span>
                      )}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── 도넛 차트 (CSS) ───────────────────────────────────────────
function DonutChart({ items }) {
  if (!items?.length) return <div className={styles.noData}>데이터 없음</div>
  const total = items.reduce((s, x) => s + x.count, 0) || 1
  let offset = 0

  return (
    <div className={styles.donutWrap}>
      <svg viewBox="0 0 120 120" className={styles.donutSvg}>
        {items.map((item, i) => {
          const pct   = item.count / total
          const dash  = pct * 314.16
          const gap   = 314.16 - dash
          const rot   = offset * 360
          offset += pct
          return (
            <circle
              key={i}
              cx="60" cy="60" r="50"
              fill="none"
              stroke={item.color ?? '#888'}
              strokeWidth="18"
              strokeDasharray={`${dash} ${gap}`}
              strokeLinecap="butt"
              transform={`rotate(${rot - 90} 60 60)`}
              opacity="0.85"
            >
              <title>{item.label}: {item.count}건 ({(pct * 100).toFixed(1)}%)</title>
            </circle>
          )
        })}
        <text x="60" y="56" fontSize="14" fontWeight="700" fill="var(--text)" textAnchor="middle">{total}</text>
        <text x="60" y="70" fontSize="9"  fill="var(--text3)" textAnchor="middle">총 실행</text>
      </svg>
      <div className={styles.donutLegend}>
        {items.map((item, i) => (
          <div key={i} className={styles.donutItem}>
            <div className={styles.donutDot} style={{ background: item.color }} />
            <span className={styles.donutLabel}>{item.label}</span>
            <span className={styles.donutCount}>{item.count}건</span>
            <span className={styles.donutPct}>{((item.count / total) * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// 탭 1: 실행 로그
// ═══════════════════════════════════════════════════════════════
function LogsTab() {
  const [logs, setLogs]           = useState([])
  const [loading, setLoading]     = useState(true)
  const [selected, setSelected]   = useState(null)
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
      if (res.ok) { setSelected(await res.json()); setRatingDone(false) }
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

  useEffect(() => { fetchLogs() }, [fetchLogs])

  return (
    <div className={styles.tabBody}>
      {/* 목록 */}
      <div className={styles.listPanel}>
        <div className={styles.listHeader}>
          실행 기록
          <span className={styles.listCount}>{logs.length}건</span>
        </div>

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
              <div className={styles.detailPlan}>📋 계획: {selected.plan_summary}</div>
            )}

            {selected.subtasks?.length > 0 && (
              <div>
                <div className={styles.sectionTitle}>에이전트 작업</div>
                <div className={styles.agentList}>
                  {selected.subtasks.map((task, i) => {
                    const name = task?.worker_name ?? selected.worker_names?.[i] ?? `에이전트 ${i + 1}`
                    const desc = task?.task ?? (typeof task === 'string' ? task : JSON.stringify(task))
                    return (
                      <div key={i} className={styles.agentRow}>
                        <div className={styles.agentRowName}>{name}</div>
                        <div>{desc}</div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {selected.worker_results?.length > 0 && (
              <div>
                <div className={styles.sectionTitle}>에이전트 결과</div>
                <div className={styles.agentList}>
                  {selected.worker_results.map((item, i) => {
                    const name = item?.worker ?? selected.worker_names?.[i] ?? `에이전트 ${i + 1}`
                    const text = item?.result ?? (typeof item === 'string' ? item : '')
                    return (
                      <div key={i} className={styles.agentRow}>
                        <div className={styles.agentRowName}>{name}</div>
                        <div style={{ whiteSpace: 'pre-wrap', marginTop: 6, fontSize: 12 }}>
                          {text.length > 500 ? text.slice(0, 500) + '…' : text}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {selected.synthesis_result && (
              <div>
                <div className={styles.sectionTitle}>최종 결과</div>
                <div className={styles.resultBox}>{selected.synthesis_result}</div>
              </div>
            )}

            <div className={styles.ratingRow}>
              <span className={styles.ratingLabel}>평점:</span>
              <div className={styles.stars}>
                {[1, 2, 3, 4, 5].map(n => (
                  <button
                    key={n}
                    className={`${styles.star} ${(selected.rating ?? 0) >= n ? styles.starActive : ''}`}
                    onClick={() => submitRating(selected.id, n)}
                  >★</button>
                ))}
              </div>
              {ratingDone && <span className={styles.ratingDone}>저장됨 ✓</span>}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// 탭 2: AI 성능 통계
// ═══════════════════════════════════════════════════════════════
function StatsTab() {
  const [stats,  setStats]  = useState(null)
  const [trend,  setTrend]  = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [sRes, tRes] = await Promise.all([
          fetch(`${BACKEND}/performance/stats`),
          fetch(`${BACKEND}/performance/trend?limit=60`),
        ])
        if (sRes.ok) setStats(await sRes.json())
        if (tRes.ok) setTrend(await tRes.json())
      } catch {}
      setLoading(false)
    }
    load()
  }, [])

  if (loading) return <div className={styles.tabLoading}>통계 불러오는 중...</div>

  if (!stats || !stats.leaderboard.length) {
    return (
      <div className={styles.tabEmpty}>
        <div className={styles.tabEmptyIcon}>📊</div>
        <div className={styles.tabEmptyTitle}>아직 성능 데이터가 없습니다</div>
        <div className={styles.tabEmptyDesc}>
          에이전트 오케스트레이션을 실행하면 AI 리뷰 점수가 자동으로 누적됩니다.<br />
          최소 5건 이상 쌓이면 적응형 분배가 활성화됩니다.
        </div>
      </div>
    )
  }

  return (
    <div className={styles.statsBody}>

      {/* KPI 카드 */}
      <div className={styles.kpiRow}>
        <KpiCard
          icon="📈" label="총 평가 횟수"
          value={stats.total_evaluations + '건'}
          color="var(--accent)"
        />
        <KpiCard
          icon="⭐" label="전체 평균 점수"
          value={stats.overall_avg_score + '/10'}
          sub="AI 교차 리뷰 기준"
          color={scoreColor(stats.overall_avg_score)}
        />
        <KpiCard
          icon="🥇" label="최고 성능 AI"
          value={stats.leaderboard[0]?.label ?? '—'}
          sub={`평균 ${stats.leaderboard[0]?.avg_score ?? '—'}/10`}
          color={stats.leaderboard[0]?.color ?? '#888'}
        />
        <KpiCard
          icon="🔢" label="평가된 유형 수"
          value={Object.keys(stats.task_matrix).length + '종'}
          color="var(--teal)"
        />
      </div>

      <div className={styles.statsGrid}>

        {/* 리더보드 */}
        <div className={styles.statsCard}>
          <div className={styles.statsCardTitle}>🏆 Provider 리더보드</div>
          <BarChart
            items={stats.leaderboard.map(l => ({
              label: l.label,
              value: l.avg_score,
              color: l.color,
              sub:   `${l.count}건 평가`,
            }))}
          />
        </div>

        {/* 태스크 유형 히트맵 */}
        <div className={styles.statsCard}>
          <div className={styles.statsCardTitle}>🗂️ 태스크 유형별 성능 비교</div>
          <HeatmapGrid matrix={stats.task_matrix} leaderboard={stats.leaderboard} />
        </div>

      </div>

      {/* 점수 추이 */}
      <div className={styles.statsCard} style={{ marginTop: 16 }}>
        <div className={styles.statsCardTitle}>📉 점수 추이 (최근 60건)</div>
        <LineChart data={trend} />
      </div>

    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// 탭 3: 시스템 현황
// ═══════════════════════════════════════════════════════════════
function SystemTab() {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const res = await fetch(`${BACKEND}/performance/summary`)
        if (res.ok) setSummary(await res.json())
      } catch {}
      setLoading(false)
    }
    load()
  }, [])

  if (loading) return <div className={styles.tabLoading}>불러오는 중...</div>
  if (!summary)  return <div className={styles.tabLoading}>데이터를 가져올 수 없습니다.</div>

  return (
    <div className={styles.statsBody}>

      {/* KPI 카드 */}
      <div className={styles.kpiRow}>
        <KpiCard
          icon="🚀" label="총 오케스트레이션"
          value={summary.total_orchestrations + '회'}
          sub={`오늘 ${summary.today_orchestrations}회`}
          color="var(--accent)"
        />
        <KpiCard
          icon="⭐" label="평균 사용자 평점"
          value={summary.avg_rating ? summary.avg_rating + '/5' : '미평가'}
          color="#f5a623"
        />
        <KpiCard
          icon="🧪" label="총 AI 리뷰"
          value={summary.total_evaluations + '건'}
          sub={`오늘 ${summary.today_evaluations}건`}
          color="var(--teal)"
        />
        <KpiCard
          icon="📊" label="전체 평균 점수"
          value={summary.avg_score ? summary.avg_score + '/10' : '—'}
          color={scoreColor(summary.avg_score)}
        />
      </div>

      <div className={styles.statsGrid}>

        {/* Provider 분포 도넛 */}
        <div className={styles.statsCard}>
          <div className={styles.statsCardTitle}>🤖 Provider 실행 분포</div>
          {summary.provider_distribution?.length > 0 ? (
            <DonutChart items={summary.provider_distribution} />
          ) : (
            <div className={styles.noData}>데이터 없음</div>
          )}
        </div>

        {/* 태스크 유형 분포 */}
        <div className={styles.statsCard}>
          <div className={styles.statsCardTitle}>📂 태스크 유형 분포</div>
          {summary.task_distribution?.length > 0 ? (
            <BarChart
              items={summary.task_distribution.map(t => ({
                label: t.label,
                value: t.count,
                color: 'var(--accent)',
              }))}
            />
          ) : (
            <div className={styles.noData}>데이터 없음</div>
          )}
        </div>

      </div>

      {/* 일별 실행 현황 */}
      {summary.daily_counts?.length > 0 && (
        <div className={styles.statsCard} style={{ marginTop: 16 }}>
          <div className={styles.statsCardTitle}>📅 일별 평가 현황 (최근 7일)</div>
          <BarChart
            items={summary.daily_counts.map(d => ({
              label: d.day?.slice(5) ?? '',   // MM-DD
              value: d.count,
              color: 'var(--teal)',
            }))}
          />
        </div>
      )}

    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// 메인 컴포넌트
// ═══════════════════════════════════════════════════════════════
const TABS = [
  { key: 'logs',   label: '📋 실행 로그' },
  { key: 'stats',  label: '📊 AI 성능'   },
  { key: 'system', label: '🖥️ 시스템'    },
]

export default function AdminPage({ onBack }) {
  const [tab, setTab] = useState('logs')

  const exportJSONL = () => {
    window.open(`${BACKEND}/orchestration-logs/export?min_rating=4`, '_blank')
  }

  return (
    <div className={styles.page}>

      {/* 헤더 */}
      <div className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>← 뒤로</button>
        <span className={styles.title}>관리자 대시보드</span>

        {/* 탭 */}
        <div className={styles.tabs}>
          {TABS.map(t => (
            <button
              key={t.key}
              className={`${styles.tabBtn} ${tab === t.key ? styles.tabBtnActive : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div style={{ marginLeft: 'auto' }}>
          {tab === 'logs' && (
            <button className={styles.exportBtn} onClick={exportJSONL}>
              ↓ JSONL 내보내기
            </button>
          )}
        </div>
      </div>

      {/* 탭 콘텐츠 */}
      {tab === 'logs'   && <LogsTab />}
      {tab === 'stats'  && <StatsTab />}
      {tab === 'system' && <SystemTab />}

    </div>
  )
}
