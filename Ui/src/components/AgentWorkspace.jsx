/**
 * AgentWorkspace — WebSocket 기반 멀티에이전트 오케스트레이션 UI
 *
 * ✅ Point 2 (Observability):
 *   - WebSocket으로 백엔드 LangGraph 오케스트레이션과 직접 연결
 *   - 에이전트별 실시간 currentTask 툴팁
 *   - Pause / Resume / Kill 인라인 제어 버튼
 *   - 리뷰어 AI 결과 패널 (review_start → review_log → review_done)
 *
 * ✅ Point 3 (Non-LLM Hybrid):
 *   - 이미지 업로드 → /vision/analyze SSE → YOLO + LLM 파이프라인
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import styles from './AgentWorkspace.module.css'
import { wsClient } from '../utils/wsClient'

const BACKEND = 'http://localhost:8000'

// ── 에이전트 상태 카드 ─────────────────────────────────────

function AgentCard({ agent, onPause, onResume, onKill }) {
  const [hovered, setHovered] = useState(false)
  const isPaused    = agent.status === 'STOPPED'
  const isRunning   = agent.status === 'RUNNING'
  const isCompleted = agent.status === 'COMPLETED'

  return (
    <div
      className={`${styles.agentCard} ${isRunning ? styles.cardRunning : ''} ${isCompleted ? styles.cardDone : ''}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className={`${styles.aDot} ${isRunning ? styles.pulse : ''}`} style={{ background: agent.color }} />

      <div className={styles.aInfo}>
        <div className={styles.aName}>{agent.name}</div>
        <div className={styles.aAi} style={{ color: agent.color }}>{agent.provider?.toUpperCase() ?? 'AI'}</div>

        {/* 현재 작업 — Point 2 핵심 */}
        {agent.currentTask && (
          <div className={styles.currentTask} title={agent.currentTask}>
            ⚡ {agent.currentTask.length > 42 ? agent.currentTask.slice(0, 42) + '…' : agent.currentTask}
          </div>
        )}

        {/* 진행률 바 */}
        {isRunning && (
          <div className={styles.agentProgress}>
            <div className={styles.agentProgressFill} style={{ width: `${agent.progress ?? 0}%`, background: agent.color }} />
          </div>
        )}
      </div>

      {/* 제어 버튼 — Point 2 핵심 */}
      <div className={`${styles.controls} ${hovered || isPaused ? styles.controlsVisible : ''}`}>
        {isRunning  && <button className={`${styles.ctrlBtn} ${styles.pauseBtn}`}  onClick={() => onPause(agent.name)}  title="일시 정지">⏸</button>}
        {isPaused   && <button className={`${styles.ctrlBtn} ${styles.resumeBtn}`} onClick={() => onResume(agent.name)} title="재개">▶</button>}
        {!isCompleted && <button className={`${styles.ctrlBtn} ${styles.killBtn}`} onClick={() => onKill(agent.name)}   title="강제 종료">✕</button>}
        {isCompleted  && <span className={styles.aCheck} style={{ color: agent.color }}>✓</span>}
      </div>
    </div>
  )
}

// ── 리뷰 패널 — Point 2 핵심 ──────────────────────────────

function ReviewPanel({ review }) {
  if (!review.started) return (
    <div className={styles.reviewEmpty}>리뷰어가 활성화되지 않았거나 아직 결과가 없습니다.</div>
  )

  const verdictColor = review.verdict === 'PASS' ? '#4ade80' : review.verdict === 'FAIL' ? '#f87171' : '#a78bfa'

  return (
    <div className={styles.reviewPanel}>
      <div className={styles.reviewHeader}>
        <span className={styles.reviewIcon}>🔍</span>
        <span className={styles.reviewTitle}>리뷰어 AI 검토</span>
        {review.reviewer && <span className={styles.reviewerBadge}>{review.reviewer.toUpperCase()}</span>}
        {review.verdict && (
          <span className={styles.verdictBadge} style={{ background: verdictColor + '22', color: verdictColor, borderColor: verdictColor + '55' }}>
            {review.verdict}
          </span>
        )}
        {review.verdict === 'FAIL' && review.retry > 0 && (
          <span className={styles.retryBadge}>재시도 {review.retry}/{review.maxRetries}</span>
        )}
      </div>
      <div className={styles.reviewBody}>{review.text || <span className={styles.reviewWaiting}>리뷰 생성 중...</span>}</div>
    </div>
  )
}

// ── Vision 파이프라인 패널 — Point 3 핵심 ─────────────────

function VisionPanel() {
  const [imagePath, setImagePath]   = useState('')
  const [question, setQuestion]     = useState('')
  const [uploading, setUploading]   = useState(false)
  const [analyzing, setAnalyzing]   = useState(false)
  const [yoloResult, setYoloResult] = useState(null)
  const [llmResult, setLlmResult]   = useState('')
  const [previewUrl, setPreviewUrl] = useState(null)
  const fileRef = useRef(null)

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setPreviewUrl(URL.createObjectURL(file))
    setUploading(true); setYoloResult(null); setLlmResult('')
    const form = new FormData()
    form.append('file', file)
    try {
      const res  = await fetch(`${BACKEND}/upload`, { method: 'POST', body: form })
      const data = await res.json()
      setImagePath(data.path)
    } catch (err) { console.error('업로드 실패:', err) }
    finally { setUploading(false) }
  }

  const handleAnalyze = async () => {
    if (!imagePath) return
    setAnalyzing(true); setYoloResult(null); setLlmResult('')
    const res = await fetch(`${BACKEND}/vision/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_path: imagePath, question: question || undefined, provider: 'github' }),
    })
    const reader = res.body.getReader(); const decoder = new TextDecoder(); let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))
          if (data.stage === 'yolo') setYoloResult(data.result)
          if (data.stage === 'llm')  setLlmResult(prev => prev + data.chunk)
          if (data.stage === 'done') setAnalyzing(false)
        } catch {}
      }
    }
    setAnalyzing(false)
  }

  return (
    <div className={styles.visionPanel}>
      <div className={styles.visionHeader}>
        <span>👁 Vision 분석</span>
        <span className={styles.visionBadge}>YOLO + LLM</span>
      </div>

      <div className={styles.uploadZone} onClick={() => fileRef.current?.click()}>
        {previewUrl
          ? <img src={previewUrl} alt="preview" className={styles.uploadPreview} />
          : <div className={styles.uploadPlaceholder}>
              <span className={styles.uploadIcon}>📁</span>
              <span>이미지를 클릭하여 업로드</span>
              <span className={styles.uploadHint}>JPG, PNG, WebP 지원</span>
            </div>
        }
        {uploading && <div className={styles.uploadLoading}>업로드 중...</div>}
      </div>
      <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleFileChange} />

      <input className={styles.visionInput} type="text" placeholder="분석 질문 (선택): 예) 위험 요소가 있나요?" value={question} onChange={e => setQuestion(e.target.value)} />

      <button className={styles.visionBtn} onClick={handleAnalyze} disabled={!imagePath || analyzing}>
        {analyzing ? '분석 중...' : '🔍 YOLO + LLM 분석 시작'}
      </button>

      {yoloResult && (
        <div className={styles.yoloResult}>
          <div className={styles.yoloTitle}>YOLO 탐지 결과 — 총 <strong>{yoloResult.total}</strong>개</div>
          {(yoloResult.summary ?? []).map((s, i) => <div key={i} className={styles.yoloItem}>• {s}</div>)}
        </div>
      )}

      {llmResult && (
        <div className={styles.llmResult}>
          <div className={styles.llmTitle}>LLM 해석</div>
          <div className={styles.llmText}>{llmResult}</div>
        </div>
      )}
    </div>
  )
}

// ── 메인 컴포넌트 ──────────────────────────────────────────

export default function AgentWorkspace({ agents, request, onDone, reviewerProvider = '' }) {
  const [agentStates, setAgentStates] = useState(() =>
    Object.fromEntries(agents.map(a => [a.name, {
      name: a.name, color: a.color,
      provider: a.provider ?? a.aiType ?? 'github',
      status: 'READY', progress: 0, currentTask: '', log: [],
    }]))
  )
  const [streamLog, setStreamLog] = useState([])
  const [review, setReview]       = useState({ started: false, text: '', verdict: null, retry: 0, maxRetries: 2, reviewer: '' })
  const [completed, setCompleted] = useState(false)
  const [tab, setTab]             = useState('stream')
  const streamEndRef = useRef(null)
  const startedRef   = useRef(false)

  const updateAgent = useCallback((name, patch) => {
    setAgentStates(prev => prev[name] ? { ...prev, [name]: { ...prev[name], ...patch } } : prev)
  }, [])

  const appendLog = useCallback((name, message, color) => {
    setStreamLog(prev => [...prev, { name, message, color, ts: Date.now() }])
  }, [])

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    wsClient.connect()
    if (reviewerProvider) wsClient.setReviewer(reviewerProvider)

    const agentColorMap = Object.fromEntries(agents.map(a => [a.name, a.color]))

    const unsubs = [
      wsClient.on('status',       ({ aiName, status })  => updateAgent(aiName, { status })),
      wsClient.on('progress',     ({ aiName, percent }) => updateAgent(aiName, { progress: percent })),
      wsClient.on('current_task', ({ aiName, task })    => updateAgent(aiName, { currentTask: task })),
      wsClient.on('log', ({ aiName, message }) => {
        appendLog(aiName, message, agentColorMap[aiName] ?? '#a897ff')
      }),
      wsClient.on('orchestration_start',     ({ aiName }) => updateAgent(aiName, { status: 'RUNNING', currentTask: '작업 분배 중...' })),
      wsClient.on('orchestration_synthesis', ({ aiName }) => updateAgent(aiName, { currentTask: '결과 종합 중...' })),
      wsClient.on('orchestration_done',      ({ aiName }) => {
        updateAgent(aiName, { status: 'COMPLETED', currentTask: '', progress: 100 })
        setCompleted(true); onDone?.()
      }),
      wsClient.on('review_start', ({ reviewer }) => {
        setReview(r => ({ ...r, started: true, reviewer, text: '' }))
        setTab('review')
      }),
      wsClient.on('review_log',  ({ message }) => setReview(r => ({ ...r, text: r.text + message }))),
      wsClient.on('review_done', ({ verdict, retry, maxRetries }) => {
        setReview(r => ({ ...r, verdict, retry: retry ?? 0, maxRetries: maxRetries ?? 2 }))
        if (verdict === 'PASS' || (retry ?? 0) >= (maxRetries ?? 2)) { setCompleted(true); onDone?.() }
      }),
    ]

    const managerName = agents[0]?.name
    agents.forEach(a => wsClient.spawn(a.name, a.provider ?? a.aiType ?? 'github'))
    setTimeout(() => { if (managerName) wsClient.prompt(managerName, request) }, 400)

    return () => { unsubs.forEach(u => u?.()) }
  }, [])

  useEffect(() => { streamEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [streamLog])

  const handlePause  = (name) => { wsClient.pause(name);  updateAgent(name, { status: 'STOPPED' }) }
  const handleResume = (name) => { wsClient.resume(name); updateAgent(name, { status: 'RUNNING' }) }
  const handleKill   = (name) => { wsClient.kill(name);   updateAgent(name, { status: 'STOPPED', currentTask: '' }) }

  const agentList = Object.values(agentStates)
  const hasReview = review.started

  return (
    <div className={styles.workspace}>

      {/* 왼쪽: 에이전트 패널 */}
      <div className={styles.agentPanel}>
        <div className={styles.panelTitle}>
          에이전트
          <span className={styles.liveTag}><span className={styles.liveDot} />LIVE</span>
        </div>

        {agentList.map(agent => (
          <AgentCard key={agent.name} agent={agent} onPause={handlePause} onResume={handleResume} onKill={handleKill} />
        ))}

        {!completed && (
          <button className={styles.killAllBtn} onClick={() => agentList.forEach(a => handleKill(a.name))}>
            ⏹ 전체 중단
          </button>
        )}
        {completed && <div className={styles.completedBadge}>✓ 작업 완료</div>}
      </div>

      {/* 오른쪽: 탭 영역 */}
      <div className={styles.contentArea}>
        <div className={styles.tabBar}>
          <button className={`${styles.tab} ${tab === 'stream' ? styles.tabActive : ''}`} onClick={() => setTab('stream')}>협업 스트림</button>
          <button className={`${styles.tab} ${tab === 'review' ? styles.tabActive : ''} ${hasReview ? styles.tabHighlight : ''}`} onClick={() => setTab('review')}>
            🔍 리뷰 {hasReview && review.verdict && (
              <span style={{ color: review.verdict === 'PASS' ? '#4ade80' : '#f87171', marginLeft: 4 }}>{review.verdict}</span>
            )}
          </button>
          <button className={`${styles.tab} ${tab === 'vision' ? styles.tabActive : ''}`} onClick={() => setTab('vision')}>👁 Vision</button>
        </div>

        <div className={styles.tabContent}>
          {tab === 'stream' && (
            <div className={styles.streamLog}>
              {streamLog.length === 0 && <div className={styles.streamEmpty}>에이전트 작업을 기다리는 중...</div>}
              {streamLog.map((e, i) => <span key={i} style={{ color: e.color }}>{e.message}</span>)}
              <div ref={streamEndRef} />
            </div>
          )}
          {tab === 'review' && <ReviewPanel review={review} />}
          {tab === 'vision' && <VisionPanel />}
        </div>
      </div>
    </div>
  )
}
