/**
 * AgentConfigPanel
 *
 * 에이전트 구성 설정 모달.
 * 워크스페이스 시작 전에 에이전트 목록을 편집할 수 있다.
 *
 * Props:
 *   open       boolean — 모달 표시 여부
 *   onClose    () => void
 *   onConfirm  (agents: Agent[]) => void  — 확인 시 에이전트 목록 반환
 *   initial    Agent[]  — 초기 에이전트 목록
 */

import { useState, useEffect } from 'react'
import styles from './AgentConfigPanel.module.css'

const PROVIDERS = [
  { key: 'github', label: 'GitHub (GPT-4.1)',   color: '#4caf82' },
  { key: 'claude', label: 'Claude Sonnet',       color: '#e98a4c' },
  { key: 'gemini', label: 'Google Gemini',       color: '#4285f4' },
  { key: 'gpt',    label: 'OpenAI GPT-4o',       color: '#10a37f' },
]

const ROLES = [
  { key: 'analyst',  label: '분석가',   emoji: '🔍' },
  { key: 'executor', label: '개발자',   emoji: '💻' },
  { key: 'writer',   label: '작성자',   emoji: '✍️' },
  { key: 'reviewer', label: '검토자',   emoji: '🔎' },
  { key: 'designer', label: '디자이너', emoji: '🎨' },
  { key: 'custom',   label: '커스텀',   emoji: '⚙️' },
]

const AGENT_COLORS = ['#7c6dfa', '#4caf82', '#f5a623', '#e98a4c', '#4285f4', '#e14d6e', '#10a37f', '#888']

let _idCounter = 1
function newId() { return `ag_${Date.now()}_${_idCounter++}` }

function makeAgent(isManager = false, index = 0) {
  return {
    _id:      newId(),
    name:     isManager ? '관리자 AI' : `작업자 AI ${String.fromCharCode(64 + index)}`,
    roleKey:  isManager ? 'analyst' : 'executor',
    aiType:   'github',
    provider: 'github',
    color:    AGENT_COLORS[index % AGENT_COLORS.length],
    isManager,
    task:     isManager ? '명령을 기다리는 중...' : '',
    handoffMsg: null,
  }
}

// ── 에이전트 행 ───────────────────────────────────────────────
function AgentRow({ agent, index, isOnly, onUpdate, onDelete }) {
  const role = ROLES.find(r => r.key === agent.roleKey) ?? ROLES[0]

  return (
    <div className={`${styles.agentRow} ${agent.isManager ? styles.managerRow : ''}`}>
      {/* 색상 도트 */}
      <div className={styles.colorDot} style={{ background: agent.color }} />

      {/* 이름 입력 */}
      <input
        className={styles.nameInput}
        value={agent.name}
        onChange={e => onUpdate({ name: e.target.value })}
        placeholder="에이전트 이름"
        maxLength={24}
      />

      {/* 역할 선택 */}
      <select
        className={styles.select}
        value={agent.roleKey}
        onChange={e => onUpdate({ roleKey: e.target.value })}
      >
        {ROLES.map(r => (
          <option key={r.key} value={r.key}>{r.emoji} {r.label}</option>
        ))}
      </select>

      {/* 모델/공급자 선택 */}
      <select
        className={styles.select}
        value={agent.aiType}
        onChange={e => onUpdate({ aiType: e.target.value, provider: e.target.value })}
      >
        {PROVIDERS.map(p => (
          <option key={p.key} value={p.key}>{p.label}</option>
        ))}
      </select>

      {/* 색상 선택 */}
      <div className={styles.colorPicker}>
        {AGENT_COLORS.map(c => (
          <button
            key={c}
            className={`${styles.colorSwatch} ${agent.color === c ? styles.colorSwatchActive : ''}`}
            style={{ background: c }}
            onClick={() => onUpdate({ color: c })}
            title={c}
          />
        ))}
      </div>

      {/* 관리자 뱃지 / 삭제 */}
      {agent.isManager ? (
        <span className={styles.managerBadge}>관리자</span>
      ) : (
        <button
          className={styles.deleteRow}
          onClick={onDelete}
          disabled={isOnly}
          title="제거"
        >×</button>
      )}
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────
export default function AgentConfigPanel({ open, onClose, onConfirm, initial }) {
  const [agents, setAgents] = useState([])

  // initial 바뀔 때(모달 열릴 때) 초기화
  useEffect(() => {
    if (open) {
      if (initial?.length) {
        setAgents(initial.map((a, i) => ({ ...a, _id: a._id ?? newId() })))
      } else {
        setAgents([makeAgent(true, 0), makeAgent(false, 1), makeAgent(false, 2)])
      }
    }
  }, [open])

  if (!open) return null

  const updateAgent = (id, patch) => {
    setAgents(prev => prev.map(a => a._id === id ? { ...a, ...patch } : a))
  }

  const addWorker = () => {
    const workerCount = agents.filter(a => !a.isManager).length
    setAgents(prev => [...prev, makeAgent(false, workerCount + 1)])
  }

  const deleteAgent = (id) => {
    setAgents(prev => prev.filter(a => a._id !== id))
  }

  const handleConfirm = () => {
    const valid = agents.filter(a => a.name.trim())
    if (valid.length === 0) return
    onConfirm(valid.map(({ _id, ...rest }) => rest))
    onClose()
  }

  const workerCount = agents.filter(a => !a.isManager).length
  const canAddMore  = agents.length < 5

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.panel}>
        {/* 헤더 */}
        <div className={styles.header}>
          <span className={styles.headerIcon}>⚙️</span>
          <span className={styles.headerTitle}>에이전트 구성</span>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        {/* 안내 */}
        <div className={styles.desc}>
          에이전트의 이름, 역할, 사용할 AI 모델을 설정합니다.<br />
          관리자 AI가 작업을 나눠 작업자 AI에게 배분합니다.
        </div>

        {/* 에이전트 목록 */}
        <div className={styles.list}>
          {/* 관리자 */}
          {agents.filter(a => a.isManager).map((a, i) => (
            <div key={a._id}>
              <div className={styles.sectionLabel}>관리자 (1명 고정)</div>
              <AgentRow
                agent={a}
                index={i}
                isOnly={false}
                onUpdate={patch => updateAgent(a._id, patch)}
                onDelete={() => {}}
              />
            </div>
          ))}

          {/* 작업자 */}
          <div className={styles.sectionLabel}>
            작업자 ({workerCount}명)
            {canAddMore && (
              <button className={styles.addBtn} onClick={addWorker}>+ 추가</button>
            )}
          </div>
          {agents.filter(a => !a.isManager).map((a, i) => (
            <AgentRow
              key={a._id}
              agent={a}
              index={i}
              isOnly={workerCount <= 1}
              onUpdate={patch => updateAgent(a._id, patch)}
              onDelete={() => deleteAgent(a._id)}
            />
          ))}
          {!canAddMore && (
            <div className={styles.maxHint}>최대 4명의 작업자까지 추가할 수 있습니다</div>
          )}
        </div>

        {/* 프리셋 */}
        <div className={styles.presets}>
          <span className={styles.presetsLabel}>프리셋:</span>
          <button className={styles.presetBtn} onClick={() => setAgents([
            makeAgent(true, 0),
            { ...makeAgent(false, 1), name: '개발자 AI', roleKey: 'executor' },
          ])}>개발 (1+1)</button>
          <button className={styles.presetBtn} onClick={() => setAgents([
            makeAgent(true, 0),
            { ...makeAgent(false, 1), name: '개발자 AI', roleKey: 'executor' },
            { ...makeAgent(false, 2), name: '문서 AI', roleKey: 'writer', color: '#f5a623' },
          ])}>개발+문서 (1+2)</button>
          <button className={styles.presetBtn} onClick={() => setAgents([
            makeAgent(true, 0),
            { ...makeAgent(false, 1), name: '분석 AI', roleKey: 'analyst', color: '#4285f4' },
            { ...makeAgent(false, 2), name: '개발 AI', roleKey: 'executor' },
            { ...makeAgent(false, 3), name: '검토 AI', roleKey: 'reviewer', color: '#e14d6e' },
          ])}>풀팀 (1+3)</button>
        </div>

        {/* 액션 버튼 */}
        <div className={styles.footer}>
          <button className={styles.cancelBtn} onClick={onClose}>취소</button>
          <button className={styles.confirmBtn} onClick={handleConfirm}>
            ✓ 이 구성으로 시작
          </button>
        </div>
      </div>
    </div>
  )
}
