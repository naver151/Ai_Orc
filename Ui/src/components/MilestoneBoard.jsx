/**
 * MilestoneBoard
 *
 * 프로젝트 마일스톤·태스크 트래커.
 * 워크스페이스 헤더 옆에 붙는 슬라이드 패널.
 *
 * Props:
 *   projectId   프로젝트 ID (null이면 렌더 안 함)
 *   visible     표시 여부
 *   onClose     () => void
 */

import { useState, useEffect, useCallback } from 'react'
import styles from './MilestoneBoard.module.css'

const BACKEND = 'http://localhost:8000'

const STATUS_LABEL = { todo: '할 일', in_progress: '진행 중', done: '완료', failed: '실패' }
const STATUS_NEXT  = { todo: 'in_progress', in_progress: 'done', done: 'todo', failed: 'todo' }
const TASK_STATUS_NEXT = { todo: 'in_progress', in_progress: 'done', done: 'failed', failed: 'todo' }

// ── 태스크 행 ─────────────────────────────────────────────────────────────
function TaskRow({ task, projectId, onUpdated, onDeleted }) {
  const [editing, setEditing] = useState(false)
  const [title,   setTitle]   = useState(task.title)

  const cycleStatus = async () => {
    const next = TASK_STATUS_NEXT[task.status] ?? 'todo'
    const res = await fetch(`${BACKEND}/projects/${projectId}/tasks/${task.id}`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ status: next }),
    })
    if (res.ok) onUpdated(await res.json())
  }

  const saveTitle = async () => {
    if (!title.trim() || title === task.title) { setEditing(false); setTitle(task.title); return }
    const res = await fetch(`${BACKEND}/projects/${projectId}/tasks/${task.id}`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ title: title.trim() }),
    })
    if (res.ok) { onUpdated(await res.json()); setEditing(false) }
  }

  const del = async () => {
    if (!window.confirm(`태스크 "${task.title}"을 삭제할까요?`)) return
    const res = await fetch(`${BACKEND}/projects/${projectId}/tasks/${task.id}`, { method: 'DELETE' })
    if (res.ok) onDeleted(task.id)
  }

  return (
    <div className={`${styles.taskRow} ${styles[`task_${task.status}`]}`}>
      {/* 상태 뱃지 (클릭해서 순환) */}
      <button className={`${styles.taskStatus} ${styles[`ts_${task.status}`]}`} onClick={cycleStatus} title="클릭해서 상태 변경">
        {STATUS_LABEL[task.status] ?? task.status}
      </button>

      {/* 제목 */}
      {editing ? (
        <input
          className={styles.taskTitleInput}
          value={title}
          onChange={e => setTitle(e.target.value)}
          onBlur={saveTitle}
          onKeyDown={e => { if (e.key === 'Enter') saveTitle(); if (e.key === 'Escape') { setEditing(false); setTitle(task.title) } }}
          autoFocus
        />
      ) : (
        <span
          className={`${styles.taskTitle} ${task.status === 'done' ? styles.taskTitleDone : ''}`}
          onDoubleClick={() => setEditing(true)}
          title="더블클릭해서 수정"
        >
          {task.title}
        </span>
      )}

      {/* 담당 에이전트 */}
      {task.assigned_agent && (
        <span className={styles.taskAgent} title="담당 에이전트">{task.assigned_agent}</span>
      )}

      {/* 결과 파일 수 */}
      {task.result_files?.length > 0 && (
        <span className={styles.taskFiles} title={task.result_files.join('\n')}>
          📄{task.result_files.length}
        </span>
      )}

      <button className={styles.delBtn} onClick={del} title="삭제">×</button>
    </div>
  )
}

// ── 마일스톤 행 ───────────────────────────────────────────────────────────
function MilestoneRow({ ms, projectId, onUpdated, onDeleted }) {
  const [open,    setOpen]    = useState(true)
  const [adding,  setAdding]  = useState(false)
  const [newTask, setNewTask] = useState('')
  const [editing, setEditing] = useState(false)
  const [title,   setTitle]   = useState(ms.title)
  const [tasks,   setTasks]   = useState(ms.tasks ?? [])

  const doneCount = tasks.filter(t => t.status === 'done').length

  const cycleStatus = async () => {
    const next = STATUS_NEXT[ms.status] ?? 'todo'
    const res = await fetch(`${BACKEND}/projects/${projectId}/milestones/${ms.id}`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ status: next }),
    })
    if (res.ok) onUpdated(await res.json())
  }

  const saveMsTitle = async () => {
    if (!title.trim() || title === ms.title) { setEditing(false); setTitle(ms.title); return }
    const res = await fetch(`${BACKEND}/projects/${projectId}/milestones/${ms.id}`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ title: title.trim() }),
    })
    if (res.ok) { onUpdated(await res.json()); setEditing(false) }
  }

  const delMs = async () => {
    if (!window.confirm(`마일스톤 "${ms.title}"과 하위 태스크를 모두 삭제할까요?`)) return
    const res = await fetch(`${BACKEND}/projects/${projectId}/milestones/${ms.id}`, { method: 'DELETE' })
    if (res.ok) onDeleted(ms.id)
  }

  const addTask = async () => {
    if (!newTask.trim()) { setAdding(false); return }
    const res = await fetch(`${BACKEND}/projects/${projectId}/milestones/${ms.id}/tasks`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ title: newTask.trim(), order: tasks.length }),
    })
    if (res.ok) {
      const t = await res.json()
      setTasks(prev => [...prev, t])
      setNewTask('')
      setAdding(false)
    }
  }

  const handleTaskUpdated = (updated) => {
    setTasks(prev => prev.map(t => t.id === updated.id ? updated : t))
    // 태스크가 모두 완료되면 마일스톤도 done으로 자동 전환 제안
    const allDone = tasks.filter(t => t.id !== updated.id).concat(updated).every(t => t.status === 'done')
    if (allDone && ms.status !== 'done') {
      fetch(`${BACKEND}/projects/${projectId}/milestones/${ms.id}`, {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ status: 'done' }),
      }).then(r => r.ok && r.json()).then(updated => updated && onUpdated(updated))
    }
  }

  const handleTaskDeleted = (taskId) => {
    setTasks(prev => prev.filter(t => t.id !== taskId))
  }

  return (
    <div className={`${styles.msCard} ${styles[`ms_${ms.status}`]}`}>
      {/* 마일스톤 헤더 */}
      <div className={styles.msHeader}>
        <button className={styles.msToggle} onClick={() => setOpen(o => !o)}>
          {open ? '▾' : '▸'}
        </button>

        <button className={`${styles.msStatus} ${styles[`mss_${ms.status}`]}`} onClick={cycleStatus} title="클릭해서 상태 변경">
          {STATUS_LABEL[ms.status] ?? ms.status}
        </button>

        {editing ? (
          <input
            className={styles.msTitleInput}
            value={title}
            onChange={e => setTitle(e.target.value)}
            onBlur={saveMsTitle}
            onKeyDown={e => { if (e.key === 'Enter') saveMsTitle(); if (e.key === 'Escape') { setEditing(false); setTitle(ms.title) } }}
            autoFocus
          />
        ) : (
          <span
            className={styles.msTitle}
            onDoubleClick={() => setEditing(true)}
            title="더블클릭해서 수정"
          >
            {ms.title}
          </span>
        )}

        {tasks.length > 0 && (
          <span className={styles.msProgress}>
            {doneCount}/{tasks.length}
          </span>
        )}

        <button className={styles.msAddTaskBtn} onClick={() => { setAdding(true); setOpen(true) }} title="태스크 추가">+</button>
        <button className={styles.delBtn} onClick={delMs} title="마일스톤 삭제">×</button>
      </div>

      {/* 태스크 목록 */}
      {open && (
        <div className={styles.taskList}>
          {tasks.map(t => (
            <TaskRow
              key={t.id}
              task={t}
              projectId={projectId}
              onUpdated={handleTaskUpdated}
              onDeleted={handleTaskDeleted}
            />
          ))}

          {/* 태스크 추가 입력 */}
          {adding && (
            <div className={styles.addTaskRow}>
              <input
                className={styles.addTaskInput}
                placeholder="태스크 이름..."
                value={newTask}
                onChange={e => setNewTask(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') addTask(); if (e.key === 'Escape') { setAdding(false); setNewTask('') } }}
                autoFocus
              />
              <button className={styles.addTaskConfirm} onClick={addTask}>추가</button>
              <button className={styles.addTaskCancel} onClick={() => { setAdding(false); setNewTask('') }}>취소</button>
            </div>
          )}

          {tasks.length === 0 && !adding && (
            <div className={styles.emptyTasks}>태스크 없음 — + 로 추가</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────
export default function MilestoneBoard({ projectId, visible, onClose }) {
  const [milestones, setMilestones] = useState([])
  const [loading,    setLoading]    = useState(false)
  const [adding,     setAdding]     = useState(false)
  const [newMs,      setNewMs]      = useState('')

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const res = await fetch(`${BACKEND}/projects/${projectId}/milestones`)
      if (res.ok) setMilestones(await res.json())
    } catch { /* 무시 */ }
    finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { if (visible && projectId) load() }, [visible, projectId, load])

  const addMilestone = async () => {
    if (!newMs.trim()) { setAdding(false); return }
    const res = await fetch(`${BACKEND}/projects/${projectId}/milestones`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ title: newMs.trim(), order: milestones.length }),
    })
    if (res.ok) {
      const created = await res.json()
      setMilestones(prev => [...prev, created])
      setNewMs('')
      setAdding(false)
    }
  }

  const handleMsUpdated = (updated) => {
    setMilestones(prev => prev.map(m => m.id === updated.id ? { ...m, ...updated } : m))
  }
  const handleMsDeleted = (id) => {
    setMilestones(prev => prev.filter(m => m.id !== id))
  }

  if (!visible) return null

  const totalTasks = milestones.reduce((s, m) => s + (m.tasks?.length ?? 0), 0)
  const doneTasks  = milestones.reduce((s, m) => s + (m.tasks?.filter(t => t.status === 'done').length ?? 0), 0)

  return (
    <div className={styles.panel}>
      {/* 헤더 */}
      <div className={styles.header}>
        <span className={styles.headerIcon}>📋</span>
        <span className={styles.headerTitle}>마일스톤</span>
        {loading && <span className={styles.spinner}>↻</span>}
        {totalTasks > 0 && (
          <span className={styles.totalProgress}>{doneTasks}/{totalTasks}</span>
        )}
        <button className={styles.addMsBtn} onClick={() => setAdding(true)} title="마일스톤 추가">+ 추가</button>
        <button className={styles.closeBtn} onClick={onClose} title="닫기">✕</button>
      </div>

      {/* 마일스톤 추가 입력 */}
      {adding && (
        <div className={styles.addMsRow}>
          <input
            className={styles.addMsInput}
            placeholder="마일스톤 이름..."
            value={newMs}
            onChange={e => setNewMs(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') addMilestone(); if (e.key === 'Escape') { setAdding(false); setNewMs('') } }}
            autoFocus
          />
          <button className={styles.addMsConfirm} onClick={addMilestone}>생성</button>
          <button className={styles.addMsCancel} onClick={() => { setAdding(false); setNewMs('') }}>취소</button>
        </div>
      )}

      {/* 목록 */}
      <div className={styles.list}>
        {milestones.length === 0 && !loading ? (
          <div className={styles.empty}>
            마일스톤이 없습니다<br />
            <span className={styles.emptyHint}>+ 추가 버튼으로 목표를 세워보세요</span>
          </div>
        ) : (
          milestones.map(ms => (
            <MilestoneRow
              key={ms.id}
              ms={ms}
              projectId={projectId}
              onUpdated={handleMsUpdated}
              onDeleted={handleMsDeleted}
            />
          ))
        )}
      </div>
    </div>
  )
}
