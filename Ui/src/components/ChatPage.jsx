import { useState, useRef, useEffect } from 'react'
import styles from './ChatPage.module.css'
import AgentWorkspace from './AgentWorkspace'
import { analyzeRequest } from '../utils/agentManager'

const delay = ms => new Promise(r => setTimeout(r, ms))

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

export default function ChatPage({ onBack }) {
  const [messages, setMessages] = useState([{
    id: 0, role: 'ai',
    text: '안녕하세요! 저는 AI.Orc의 관리자 AI입니다.\n요청을 입력하시면 필요한 에이전트를 구성하고 작업을 배분하겠습니다.',
  }])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [typing, setTyping] = useState(false)
  const [workspace, setWorkspace] = useState(null)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const msgIdRef = useRef(1)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typing])

  const addMsg = msg =>
    setMessages(prev => [...prev, { id: msgIdRef.current++, ...msg }])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || busy) return
    setBusy(true)
    setInput('')

    addMsg({ role: 'user', text })

    setTyping(true)
    const { intro, agents } = await analyzeRequest(text)
    setTyping(false)

    addMsg({ role: 'ai', text: intro })
    await delay(400)

    setWorkspace({ agents })
  }

  const handleWorkspaceDone = async (summary) => {
    setWorkspace(null)
    await delay(100)
    addMsg({ role: 'ai', text: summary })
    setBusy(false)
    inputRef.current?.focus()
  }

  return (
    <div className={styles.chatpage}>
      <div className={styles.topbar}>
        <button className={styles.backBtn} onClick={onBack}>← 돌아가기</button>
        <ManagerAvatar />
        <div className={styles.topbarInfo}>
          <div className={styles.topbarName}>관리자 AI</div>
          <div className={styles.topbarStatus}>온라인</div>
        </div>
      </div>

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

      <div className={styles.inputArea}>
        <textarea
          ref={inputRef}
          className={styles.input}
          placeholder="요청을 입력하세요..."
          rows={1}
          value={input}
          onChange={e => {
            setInput(e.target.value)
            e.target.style.height = 'auto'
            e.target.style.height = Math.min(e.target.scrollHeight, 100) + 'px'
          }}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
          }}
        />
        <button className={styles.sendBtn} onClick={handleSend} disabled={busy || !input.trim()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>

      {workspace && (
        <AgentWorkspace
          agents={workspace.agents}
          onDone={handleWorkspaceDone}
        />
      )}
    </div>
  )
}
