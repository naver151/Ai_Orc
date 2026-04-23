import { useState, useRef, useEffect } from 'react'
import styles from './ChatPage.module.css'
import AgentWorkspace from './AgentWorkspace'
import { sendChatMessage, generateChatResponse, analyzeRequest, detectProjectIntent, pollCeleryResults } from '../utils/agentManager'


const BACKEND = 'http://localhost:8000'

async function saveOrchLog({ request, agents, workerResults, synthesisResult }) {
  try {
    await fetch(`${BACKEND}/orchestration-logs/ui`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request, agents, worker_results: workerResults, synthesis_result: synthesisResult }),
    })
  } catch {}
}

// ── 채팅 저장소 헬퍼 ─────────────────────────────────────────
function loadChatList(uid) {
  try { return JSON.parse(localStorage.getItem(`aiorc_chats_${uid}`)) ?? [] } catch { return [] }
}
function saveChatList(uid, list) {
  try { localStorage.setItem(`aiorc_chats_${uid}`, JSON.stringify(list)) } catch {}
}
function loadChatMsgs(uid, id) {
  try { return JSON.parse(localStorage.getItem(`aiorc_msgs_${uid}_${id}`)) ?? [] } catch { return [] }
}
function saveChatMsgs(uid, id, msgs) {
  try { localStorage.setItem(`aiorc_msgs_${uid}_${id}`, JSON.stringify(msgs)) } catch {}
}
function genChatId() {
  return `c${Date.now()}${Math.random().toString(36).slice(2, 5)}`
}
function fmtDate(ts) {
  const d = new Date(ts)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })
}
function makeGreetingText(user) {
  const hi = user?.name ? `안녕하세요, ${user.name}님!` : '안녕하세요!'
  return `${hi} 저는 AI.Orc의 관리자 AI입니다.\n무엇이든 편하게 말씀해 주세요. 복잡한 작업이 생기면 에이전트들을 배치해 드릴게요.`
}

// ── 아바타 ────────────────────────────────────────────────────
function ManagerAvatar() {
  return (
    <div className={styles.managerAvatar}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a897ff" strokeWidth="2">
        <circle cx="12" cy="8" r="4" />
        <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
      </svg>
    </div>
  )
}

function UserAvatar() {
  return (
    <div className={styles.userAvatar}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8888a0" strokeWidth="2">
        <circle cx="12" cy="8" r="4" />
        <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
      </svg>
    </div>
  )
}

function TypingBubble() {
  return (
    <div className={`${styles.msg} ${styles.ai}`}>
      <ManagerAvatar />
      <div className={styles.bubble}>
        <div className={styles.typingDots}>
          <span className={styles.dot} />
          <span className={styles.dot} />
          <span className={styles.dot} />
        </div>
      </div>
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────
// ── 테마 토글 아이콘 ──────────────────────────────────────────
function ThemeToggleBtn({ theme, onToggle, className }) {
  return (
    <button className={className} onClick={onToggle} title={theme === 'dark' ? '라이트 모드' : '다크 모드'}>
      {theme === 'dark' ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="5"/>
          <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
          <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
      )}
    </button>
  )
}

export default function ChatPage({ user, onBack, theme = 'dark', onThemeToggle, fontLabel = 'M', onFontSizeCycle }) {
  // ── refs ──────────────────────────────────────────────────
  const chatIdRef       = useRef(null)
  const msgIdRef        = useRef(1)
  const isFirstRender   = useRef(true)   // 첫 렌더 자동저장 방지
  const suppressNextSave = useRef(false) // switchToChat 로드 시 방지
  const inputRef        = useRef(null)
  const messagesEndRef  = useRef(null)
  const chatBtnRef      = useRef(null)
  const dragStateRef    = useRef({ dragging: false })
  const celeryStopRef   = useRef(null)   // Celery 폴링 정리 함수

  const uid = user?.uid ?? 'guest'

  // ── 채팅 목록 ─────────────────────────────────────────────
  const [chatList, setChatList] = useState(() => loadChatList(uid))

  // ── 현재 채팅 ID + 메시지 초기화 ─────────────────────────
  const [currentChatId, setCurrentChatId] = useState(() => {
    const list = loadChatList(uid)
    if (list.length > 0) {
      const msgs = loadChatMsgs(uid, list[0].id)
      if (msgs.length > 0) {
        chatIdRef.current = list[0].id
        msgIdRef.current = Math.max(...msgs.map(m => m.id ?? 0), 0) + 1
        return list[0].id
      }
    }
    return null
  })

  const [messages, setMessages] = useState(() => {
    if (chatIdRef.current) {
      const msgs = loadChatMsgs(uid, chatIdRef.current)
      if (msgs.length > 0) return msgs
    }
    return [{ id: 0, role: 'ai', text: makeGreetingText(user) }]
  })

  // ── UI 상태 ───────────────────────────────────────────────
  const [input, setInput]             = useState('')
  const [modalInput, setModalInput]   = useState('')
  const [mode, setMode]               = useState('chat')
  const [pendingRequest, setPending]  = useState('')
  const [typing, setTyping]           = useState(false)
  const [workspace, setWorkspace]     = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [chatModalOpen, setChatModalOpen] = useState(false)

  const busy = false

  // ── 스크롤 ───────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typing])

  // ── 자동 저장 ─────────────────────────────────────────────
  // 규칙:
  //  - 첫 렌더 / switchToChat 로드 시에는 저장 건너뜀
  //  - chatIdRef가 없으면 (앱 최초 실행 상태) 첫 유저 메시지에서 채팅 생성
  //  - chatIdRef가 있으면 메시지 저장 + 사이드바 메타 업데이트
  useEffect(() => {
    if (isFirstRender.current)   { isFirstRender.current = false; return }
    if (suppressNextSave.current) { suppressNextSave.current = false; return }

    const firstUser = messages.find(m => m.role === 'user')

    // 앱 최초 실행: chatId 없이 첫 메시지를 보낸 경우
    if (!chatIdRef.current) {
      if (!firstUser) return
      const id = genChatId()
      chatIdRef.current = id
      setCurrentChatId(id)
      const entry = { id, title: firstUser.text.slice(0, 36), updatedAt: Date.now() }
      setChatList(prev => { const next = [entry, ...prev]; saveChatList(uid, next); return next })
      saveChatMsgs(uid, id, messages)
      return
    }

    // 일반 저장
    const id = chatIdRef.current
    saveChatMsgs(uid, id, messages)

    if (!firstUser) return  // 인사말만 있는 상태는 메타 업데이트 불필요

    setChatList(prev => {
      const idx = prev.findIndex(c => c.id === id)
      if (idx === -1) return prev
      const copy = [...prev]
      const cur = copy[idx]
      copy[idx] = {
        ...cur,
        // 제목이 '새 채팅'이면 첫 유저 메시지로 교체
        title: cur.title === '새 채팅' ? firstUser.text.slice(0, 36) : cur.title,
        updatedAt: Date.now(),
      }
      copy.sort((a, b) => b.updatedAt - a.updatedAt)
      saveChatList(uid, copy)
      return copy
    })
  }, [messages])

  // ── 메시지 추가 ──────────────────────────────────────────
  const addMsg = msg =>
    setMessages(prev => [...prev, { id: msgIdRef.current++, ...msg }])

  // ── 새 채팅 (사이드바에 즉시 등록) ───────────────────────
  const startNewChat = () => {
    const id = genChatId()
    const greeting = { id: 0, role: 'ai', text: makeGreetingText(user) }
    const entry = { id, title: '새 채팅', updatedAt: Date.now() }

    chatIdRef.current = id
    setCurrentChatId(id)
    msgIdRef.current = 1

    setChatList(prev => { const next = [entry, ...prev]; saveChatList(uid, next); return next })
    saveChatMsgs(uid, id, [greeting])

    setMessages([greeting])
    setMode('chat')
    setWorkspace(null)
    setPending('')
    setInput('')
    setSidebarOpen(false)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  // ── 채팅 전환 ─────────────────────────────────────────────
  const switchToChat = (chatId) => {
    if (chatId === chatIdRef.current) { setSidebarOpen(false); return }
    const msgs = loadChatMsgs(uid, chatId)
    if (!msgs.length) return

    suppressNextSave.current = true
    chatIdRef.current = chatId
    setCurrentChatId(chatId)
    msgIdRef.current = Math.max(...msgs.map(m => m.id ?? 0), 0) + 1
    setMessages(msgs)
    setMode('chat')
    setWorkspace(null)
    setPending('')
    setInput('')
    setSidebarOpen(false)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  // ── 채팅 삭제 ─────────────────────────────────────────────
  const deleteChat = (e, chatId) => {
    e.stopPropagation()
    localStorage.removeItem(`aiorc_msgs_${uid}_${chatId}`)
    setChatList(prev => { const next = prev.filter(c => c.id !== chatId); saveChatList(uid, next); return next })
    if (chatIdRef.current === chatId) startNewChat()
  }

  // ── 메시지 전송 ───────────────────────────────────────────
  const handleSend = async () => {
    const text = input.trim()
    if (!text || busy) return

    setInput('')
    addMsg({ role: 'user', text })

    // ── 프로젝트 요청: AI 호출 없이 바로 분배 모드 ───────
    // 관리자 AI가 채팅에서 결과물을 출력하는 것을 원천 차단
    if (detectProjectIntent(text)) {
      addMsg({ role: 'ai', text: '에이전트에게 업무를 분배하겠습니다.' })
      setPending(text)
      setMode('confirming')
      return
    }

    // ── 일반 대화만 AI 호출 ───────────────────────────────
    const historySnapshot = [...messages]
    setTyping(true)
    const aiId = msgIdRef.current++

    try {
      setTyping(false)
      setMessages(prev => [...prev, { id: aiId, role: 'ai', text: '' }])

      await sendChatMessage(text, historySnapshot, (chunk) => {
        setMessages(prev =>
          prev.map(m => m.id === aiId ? { ...m, text: m.text + chunk } : m)
        )
      })
    } catch (err) {
      setTyping(false)
      const errMsg = err?.message ?? ''
      let reply
      if (errMsg.includes('키가 없')) {
        reply = '⚠️ AI API 키가 설정되지 않았습니다.\n\n백엔드 .env 파일에 아래 중 하나를 입력해주세요:\n• GITHUB_TOKEN (무료)\n• ANTHROPIC_API_KEY\n• OPENAI_API_KEY'
      } else if (errMsg.includes('fetch') || errMsg.includes('Failed') || errMsg.includes('NetworkError') || errMsg.includes('ECONNREFUSED')) {
        reply = '⚠️ 백엔드 서버에 연결할 수 없습니다.\nVSCode에서 F5를 눌러 서버를 먼저 실행해주세요.'
      } else {
        reply = generateChatResponse(text)
      }
      setMessages(prev => {
        if (prev.some(m => m.id === aiId)) {
          return prev.map(m => m.id === aiId ? { ...m, text: reply } : m)
        }
        return [...prev, { id: aiId, role: 'ai', text: reply }]
      })
    }
  }

  // ── 모달에서 명령 전송 ────────────────────────────────────
  const handleModalSend = async () => {
    const text = modalInput.trim()
    if (!text || busy) return

    setModalInput('')
    addMsg({ role: 'user', text })

    if (detectProjectIntent(text)) {
      addMsg({ role: 'ai', text: '에이전트에게 업무를 분배하겠습니다.' })
      setPending(text)
      setMode('confirming')
      return
    }

    const historySnapshot = [...messages]
    setTyping(true)
    const aiId = msgIdRef.current++

    try {
      setTyping(false)
      setMessages(prev => [...prev, { id: aiId, role: 'ai', text: '' }])
      await sendChatMessage(text, historySnapshot, (chunk) => {
        setMessages(prev =>
          prev.map(m => m.id === aiId ? { ...m, text: m.text + chunk } : m)
        )
      })
    } catch (err) {
      setTyping(false)
      const errMsg = err?.message ?? ''
      let reply
      if (errMsg.includes('키가 없')) {
        reply = '⚠️ AI API 키가 설정되지 않았습니다.'
      } else if (errMsg.includes('fetch') || errMsg.includes('Failed') || errMsg.includes('ECONNREFUSED')) {
        reply = '⚠️ 백엔드 서버에 연결할 수 없습니다.'
      } else {
        reply = generateChatResponse(text)
      }
      setMessages(prev => {
        if (prev.some(m => m.id === aiId)) {
          return prev.map(m => m.id === aiId ? { ...m, text: reply } : m)
        }
        return [...prev, { id: aiId, role: 'ai', text: reply }]
      })
    }
  }

  // ── 프로젝트 확인 ─────────────────────────────────────────
  const handleConfirm = async () => {
    const req = pendingRequest
    setMode('working')
    setPending('')
    const { agents, projectId, celeryWarning } = await analyzeRequest(req)
    setWorkspace({ id: Date.now(), agents, request: req, instant: workspace !== null })
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)

    if (celeryWarning) {
      addMsg({ role: 'ai', text: '⚠️ 백그라운드 큐(Redis/Celery)에 연결할 수 없어 DB 이력은 저장되지 않습니다. 에이전트 실시간 협업은 정상 동작합니다.' })
    }

    // Celery 결과 폴링 시작 (project_id 있을 때만)
    if (projectId) {
      celeryStopRef.current?.()   // 이전 폴링이 남아 있으면 정리
      celeryStopRef.current = pollCeleryResults(projectId, {
        onAllDone: () => {
          addMsg({ role: 'ai', text: '백그라운드 처리가 완료되어 DB에 저장됐습니다.' })
          celeryStopRef.current = null
        },
        onError: (_name, err) => {
          console.warn('[Celery 폴링 오류]', err)
        },
      })
    }
  }

  // ── 프로젝트 취소 ─────────────────────────────────────────
  const handleCancel = () => {
    setMode('chat')
    setPending('')
    addMsg({ role: 'ai', text: '알겠습니다! 다른 작업이 생기면 언제든지 말씀해 주세요.' })
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  // ── 워크스페이스 닫기 (채팅으로 복귀) ────────────────────
  const handleCloseWorkspace = () => {
    celeryStopRef.current?.()   // Celery 폴링 정리
    celeryStopRef.current = null
    setWorkspace(null)
    setMode('chat')
    setChatModalOpen(false)
    addMsg({ role: 'ai', text: '작업이 완료되었습니다. 추가로 도움이 필요하시면 말씀해 주세요.' })
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      inputRef.current?.focus()
    }, 50)
  }

  // ── 플로팅 버튼 드래그 ────────────────────────────────────
  const startDrag = (clientX, clientY) => {
    const btn = chatBtnRef.current
    if (!btn) return
    const parent = btn.offsetParent
    const pRect  = parent.getBoundingClientRect()
    const bRect  = btn.getBoundingClientRect()

    // right/bottom → left/top 으로 전환 (드래그 중 계산 단순화)
    btn.style.right  = 'auto'
    btn.style.bottom = 'auto'
    btn.style.left   = (bRect.left - pRect.left) + 'px'
    btn.style.top    = (bRect.top  - pRect.top)  + 'px'

    const ds = dragStateRef.current
    ds.dragging = true
    ds.moved    = false
    ds.startX   = clientX
    ds.startY   = clientY
    ds.startL   = parseFloat(btn.style.left)
    ds.startT   = parseFloat(btn.style.top)

    const onMove = (cx, cy) => {
      const dx = cx - ds.startX
      const dy = cy - ds.startY
      if (!ds.moved && Math.abs(dx) < 4 && Math.abs(dy) < 4) return
      ds.moved = true
      btn.style.cursor = 'grabbing'
      const btnW = btn.offsetWidth
      const btnH = btn.offsetHeight
      const maxL = pRect.width  - btnW
      const maxT = pRect.height - btnH
      btn.style.left = Math.max(0, Math.min(ds.startL + dx, maxL)) + 'px'
      btn.style.top  = Math.max(0, Math.min(ds.startT + dy, maxT)) + 'px'
    }

    const onEnd = () => {
      ds.dragging = false
      btn.style.cursor = ''
      cleanup()
      if (!ds.moved) setChatModalOpen(o => !o)
    }

    const onMouseMove = e => onMove(e.clientX, e.clientY)
    const onMouseUp   = () => onEnd()
    const onTouchMove = e => { e.preventDefault(); onMove(e.touches[0].clientX, e.touches[0].clientY) }
    const onTouchEnd  = () => onEnd()

    const cleanup = () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup',   onMouseUp)
      document.removeEventListener('touchmove', onTouchMove)
      document.removeEventListener('touchend',  onTouchEnd)
    }
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup',   onMouseUp)
    document.addEventListener('touchmove', onTouchMove, { passive: false })
    document.addEventListener('touchend',  onTouchEnd)
  }

  const handleBtnMouseDown = e => { e.preventDefault(); startDrag(e.clientX, e.clientY) }
  const handleBtnTouchStart = e => startDrag(e.touches[0].clientX, e.touches[0].clientY)

  // 유저 메시지가 없을 때 = 입력창 중앙 배치
  const isCentered = !messages.some(m => m.role === 'user') && mode === 'chat'

  // 입력창 (중앙/하단 모두 동일 마크업, 모달용 placeholder 별도)
  const renderInputBar = (isModal = false) => (
    <div className={isCentered ? styles.centerInputArea : styles.inputArea}>
      <textarea
        ref={isModal ? null : inputRef}
        className={styles.input}
        placeholder={isModal ? '관리자에게 명령하기...' : '무엇이든 말씀해 보세요...'}
        rows={1}
        value={isModal ? modalInput : input}
        disabled={busy}
        onChange={e => {
          if (isModal) {
            setModalInput(e.target.value)
          } else {
            setInput(e.target.value)
          }
          e.target.style.height = 'auto'
          e.target.style.height = Math.min(e.target.scrollHeight, 100) + 'px'
        }}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            isModal ? handleModalSend() : handleSend()
          }
        }}
      />
      <button
        className={styles.sendBtn}
        onClick={isModal ? handleModalSend : handleSend}
        disabled={busy || !(isModal ? modalInput : input).trim()}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5">
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    </div>
  )

  return (
    <div className={styles.chatpage}>

      {/* ── 사이드바 백드롭 (일반 챗 모드만) ── */}
      {!workspace && sidebarOpen && (
        <div className={styles.sidebarBackdrop} onClick={() => setSidebarOpen(false)} />
      )}

      {/* ── 사이드바 (일반 챗 모드만) ── */}
      {!workspace && (
        <div className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarVisible : ''}`}>
          <div className={styles.sidebarHeader}>
            <span className={styles.sidebarTitle}>채팅 기록</span>
            <button className={styles.newChatBtn} onClick={startNewChat}>+ 새 채팅</button>
          </div>
          <div className={styles.sidebarList}>
            {chatList.length === 0 && (
              <div className={styles.sidebarEmpty}>저장된 채팅이 없습니다</div>
            )}
            {chatList.map(chat => (
              <div
                key={chat.id}
                className={`${styles.sidebarItem} ${currentChatId === chat.id ? styles.sidebarItemActive : ''}`}
                onClick={() => switchToChat(chat.id)}
              >
                <div className={styles.sidebarItemTitle}>{chat.title}</div>
                <div className={styles.sidebarItemDate}>{fmtDate(chat.updatedAt)}</div>
                <button
                  className={styles.sidebarItemDel}
                  onClick={(e) => deleteChat(e, chat.id)}
                  title="삭제"
                >×</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 메인 영역 ── */}
      <div className={styles.main}>

        {workspace ? (
          /* ════════════════════════════════════════════
             워크스페이스 전체화면 모드
             ════════════════════════════════════════════ */
          <>
            {/* 워크스페이스 전체화면 */}
            <div className={styles.workspaceFull}>
              <div className={styles.wsFullHeader}>
                <div className={styles.wsFullHeaderLeft}>
                  <div className={styles.wsFullDot} />
                  <span className={styles.wsFullTitle}>AI 에이전트 협업</span>
                </div>
                <div className={styles.wsFullHeaderRight}>
                  <button className={styles.fontSizeBtn} onClick={onFontSizeCycle} title="글씨 크기">
                    {fontLabel}
                  </button>
                  <ThemeToggleBtn theme={theme} onToggle={onThemeToggle} className={styles.themeToggleBtn} />
                  <button className={styles.wsCloseBtn} onClick={handleCloseWorkspace}>
                    ← 채팅으로 돌아가기
                  </button>
                </div>
              </div>
              <div className={styles.wsFullBody}>
                <AgentWorkspace
                  key={workspace.id}
                  agents={workspace.agents}
                  request={workspace.request}
                  instant={workspace.instant ?? false}
                  onDone={({ request, agents, workerResults, synthesisResult }) =>
                    saveOrchLog({ request, agents, workerResults, synthesisResult })
                  }
                />
              </div>
            </div>

            {/* 플로팅 챗 버튼 */}
            <button
              ref={chatBtnRef}
              className={`${styles.chatBubbleBtn} ${chatModalOpen ? styles.chatBubbleBtnActive : ''}`}
              onMouseDown={handleBtnMouseDown}
              onTouchStart={handleBtnTouchStart}
              title="관리자 AI 채팅"
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="8" r="4" />
                <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
              </svg>
              <div className={styles.chatBubblePulse} />
            </button>

            {/* 챗 모달 */}
            {chatModalOpen && (
              <div className={styles.chatModal}>
                <div className={styles.chatModalHeader}>
                  <ManagerAvatar />
                  <span className={styles.chatModalTitle}>관리자 AI</span>
                  <button className={styles.chatModalClose} onClick={() => setChatModalOpen(false)}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>

                <div className={styles.chatModalMsgs}>
                  {messages.map(msg => (
                    <div key={msg.id} className={`${styles.msg} ${styles[msg.role]}`}>
                      {msg.role === 'ai' ? <ManagerAvatar /> : <UserAvatar />}
                      <div className={styles.bubble}>
                        {msg.text.split('\n').map((line, i, arr) => (
                          <span key={i}>{line}{i < arr.length - 1 && <br />}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                  {typing && <TypingBubble />}
                  <div ref={messagesEndRef} />
                </div>

                {/* 확인 버튼 (모달 내) */}
                {mode === 'confirming' && (
                  <div className={styles.confirmBar}>
                    <span className={styles.confirmLabel}>에이전트를 배치할까요?</span>
                    <div className={styles.confirmBtns}>
                      <button className={styles.btnConfirm} onClick={handleConfirm}>
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                        네, 시작할게요
                      </button>
                      <button className={styles.btnCancel} onClick={handleCancel}>아니요</button>
                    </div>
                  </div>
                )}

                {renderInputBar(true)}
              </div>
            )}
          </>
        ) : (
          /* ════════════════════════════════════════════
             일반 챗 모드
             ════════════════════════════════════════════ */
          <>
            {/* 상단 바 */}
            <div className={styles.topbar}>
              <button className={styles.hamburgerBtn} onClick={() => setSidebarOpen(o => !o)} aria-label="채팅 기록">
                <span /><span /><span />
              </button>
              <button className={styles.backBtn} onClick={onBack}>← 돌아가기</button>
              <ManagerAvatar />
              <div className={styles.topbarInfo}>
                <div className={styles.topbarName}>관리자 AI</div>
                <div className={styles.topbarStatus}>온라인</div>
              </div>
              {user?.name && (
                <div className={styles.userBadge}>{user.name}</div>
              )}
              <button className={styles.fontSizeBtn} onClick={onFontSizeCycle} title="글씨 크기">
                {fontLabel}
              </button>
              <ThemeToggleBtn theme={theme} onToggle={onThemeToggle} className={styles.themeToggleBtn} />
            </div>

            {/* 중앙 입력 모드 (첫 메시지 전) */}
            {isCentered ? (
              <div className={styles.centerLayout}>
                <div className={styles.centerContent}>
                  <div className={styles.centerAvatarWrap}>
                    <ManagerAvatar />
                  </div>
                  <div className={styles.centerTitle}>관리자 AI</div>
                  <div className={styles.centerSub}>
                    {user?.name
                      ? `${user.name}님, 무엇이든 도와드릴게요.`
                      : '무엇이든 편하게 말씀해 주세요.'}
                  </div>
                  {renderInputBar()}
                </div>
              </div>
            ) : (
              <>
                {/* 메시지 목록 */}
                <div className={styles.messages}>
                  {messages.map(msg => (
                    <div key={msg.id} className={`${styles.msg} ${styles[msg.role]}`}>
                      {msg.role === 'ai' ? <ManagerAvatar /> : <UserAvatar />}
                      <div className={styles.bubble}>
                        {msg.text.split('\n').map((line, i, arr) => (
                          <span key={i}>{line}{i < arr.length - 1 && <br />}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                  {typing && <TypingBubble />}
                  <div ref={messagesEndRef} />
                </div>

                {/* 확인 버튼 바 */}
                {mode === 'confirming' && (
                  <div className={styles.confirmBar}>
                    <span className={styles.confirmLabel}>에이전트를 배치할까요?</span>
                    <div className={styles.confirmBtns}>
                      <button className={styles.btnConfirm} onClick={handleConfirm}>
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                        네, 시작할게요
                      </button>
                      <button className={styles.btnCancel} onClick={handleCancel}>아니요</button>
                    </div>
                  </div>
                )}

                {renderInputBar()}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
