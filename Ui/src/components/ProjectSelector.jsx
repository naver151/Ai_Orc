/**
 * ProjectSelector
 *
 * 프로젝트 선택 드롭다운 — 생성 / 수정 / 삭제 통합.
 * 채팅 topbar 및 워크스페이스 헤더 양쪽에서 사용.
 *
 * Props:
 *   projectId        현재 선택된 프로젝트 ID (null = 미선택)
 *   onProjectChange  (id: number|null) => void
 */

import { useState, useEffect, useRef } from 'react'
import styles from './ProjectSelector.module.css'

const BACKEND = 'http://localhost:8000'

export default function ProjectSelector({ projectId, onProjectChange }) {
  const [projects,   setProjects]   = useState([])
  const [open,       setOpen]       = useState(false)
  const [creating,   setCreating]   = useState(false)
  const [form,       setForm]       = useState({ title: '', description: '' })
  const [saving,     setSaving]     = useState(false)
  const [error,      setError]      = useState('')

  // 수정
  const [editingId,  setEditingId]  = useState(null)   // 수정 중인 프로젝트 id
  const [editForm,   setEditForm]   = useState({ title: '', description: '' })
  const [editSaving, setEditSaving] = useState(false)

  // 삭제
  const [confirmDelId, setConfirmDelId] = useState(null) // 삭제 확인 중인 id
  const [deleting,     setDeleting]     = useState(false)

  const dropRef = useRef(null)

  /* ── 목록 로드 ──────────────────────────────────────────── */
  const loadProjects = async () => {
    try {
      const res = await fetch(`${BACKEND}/projects/`)
      if (!res.ok) return
      setProjects(await res.json())
    } catch { /* 백엔드 미실행 시 무시 */ }
  }

  useEffect(() => { loadProjects() }, [])

  /* ── 외부 클릭 닫기 ─────────────────────────────────────── */
  useEffect(() => {
    const handler = (e) => {
      if (dropRef.current && !dropRef.current.contains(e.target)) {
        closeAll()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const closeAll = () => {
    setOpen(false)
    setCreating(false)
    setEditingId(null)
    setConfirmDelId(null)
    setError('')
  }

  /* ── 선택 ───────────────────────────────────────────────── */
  const handleSelect = (id) => {
    onProjectChange(id)
    closeAll()
  }

  /* ── 생성 ───────────────────────────────────────────────── */
  const handleCreate = async (e) => {
    e.preventDefault()
    if (!form.title.trim()) { setError('프로젝트 이름을 입력하세요'); return }
    setSaving(true); setError('')
    try {
      const res = await fetch(`${BACKEND}/projects/`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ title: form.title.trim(), description: form.description.trim() }),
      })
      if (!res.ok) throw new Error('생성 실패')
      const created = await res.json()
      await loadProjects()
      onProjectChange(created.id)
      setForm({ title: '', description: '' })
      setCreating(false)
      setOpen(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  /* ── 수정 시작 ──────────────────────────────────────────── */
  const startEdit = (e, project) => {
    e.stopPropagation()
    setEditingId(project.id)
    setEditForm({ title: project.title, description: project.description ?? '' })
    setConfirmDelId(null)
    setCreating(false)
    setError('')
  }

  /* ── 수정 저장 ──────────────────────────────────────────── */
  const handleEdit = async (e) => {
    e.preventDefault()
    if (!editForm.title.trim()) return
    setEditSaving(true)
    try {
      const res = await fetch(`${BACKEND}/projects/${editingId}`, {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ title: editForm.title.trim(), description: editForm.description.trim() }),
      })
      if (!res.ok) throw new Error('수정 실패')
      await loadProjects()
      setEditingId(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setEditSaving(false)
    }
  }

  /* ── 삭제 ───────────────────────────────────────────────── */
  const handleDelete = async (id) => {
    setDeleting(true)
    try {
      const res = await fetch(`${BACKEND}/projects/${id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('삭제 실패')
      await loadProjects()
      if (projectId === id) onProjectChange(null)
      setConfirmDelId(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setDeleting(false)
    }
  }

  const selectedProject = projects.find(p => p.id === projectId)

  /* ── 렌더 ───────────────────────────────────────────────── */
  return (
    <div className={styles.wrap} ref={dropRef}>
      {/* 트리거 버튼 */}
      <button
        className={`${styles.trigger} ${projectId ? styles.active : ''}`}
        onClick={() => { setOpen(o => !o); setCreating(false); setEditingId(null) }}
        title={projectId ? `프로젝트: ${selectedProject?.title}` : '프로젝트 선택'}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <span>{selectedProject ? selectedProject.title : '프로젝트'}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
          style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>

      {/* 드롭다운 */}
      {open && (
        <div className={styles.dropdown}>

          {/* 미선택 옵션 */}
          <button
            className={`${styles.item} ${!projectId ? styles.selected : ''}`}
            onClick={() => handleSelect(null)}
          >
            <span className={styles.itemIcon}>💬</span>
            <span className={styles.itemText}>프로젝트 없이 실행</span>
            {!projectId && <span className={styles.check}>✓</span>}
          </button>

          {/* 프로젝트 목록 */}
          {projects.length > 0 && <div className={styles.divider} />}

          {projects.map(p => (
            <div key={p.id} className={styles.itemWrap}>
              {editingId === p.id ? (
                /* ── 인라인 수정 폼 ── */
                <form className={styles.createForm} onSubmit={handleEdit}>
                  <input
                    className={styles.input}
                    placeholder="프로젝트 이름"
                    value={editForm.title}
                    onChange={e => setEditForm(f => ({ ...f, title: e.target.value }))}
                    autoFocus
                  />
                  <input
                    className={styles.input}
                    placeholder="설명 (선택)"
                    value={editForm.description}
                    onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                  />
                  <div className={styles.formBtns}>
                    <button type="submit" className={styles.submitBtn} disabled={editSaving}>
                      {editSaving ? '저장 중...' : '저장'}
                    </button>
                    <button type="button" className={styles.cancelBtn}
                      onClick={() => { setEditingId(null); setError('') }}>
                      취소
                    </button>
                  </div>
                </form>
              ) : confirmDelId === p.id ? (
                /* ── 삭제 확인 ── */
                <div className={styles.deleteConfirm}>
                  <span className={styles.deleteMsg}>
                    <span className={styles.deleteIcon}>⚠️</span>
                    「{p.title}」 삭제할까요?
                  </span>
                  <div className={styles.formBtns}>
                    <button
                      className={styles.deleteBtn}
                      onClick={() => handleDelete(p.id)}
                      disabled={deleting}
                    >
                      {deleting ? '삭제 중...' : '삭제'}
                    </button>
                    <button className={styles.cancelBtn}
                      onClick={() => setConfirmDelId(null)}>
                      취소
                    </button>
                  </div>
                </div>
              ) : (
                /* ── 일반 항목 ── */
                <div className={styles.itemRow}>
                  <button
                    className={`${styles.item} ${projectId === p.id ? styles.selected : ''}`}
                    onClick={() => handleSelect(p.id)}
                  >
                    <span className={styles.itemIcon}>📁</span>
                    <div className={styles.itemMeta}>
                      <span className={styles.itemText}>{p.title}</span>
                      {p.description && <span className={styles.itemDesc}>{p.description}</span>}
                    </div>
                    {projectId === p.id && <span className={styles.check}>✓</span>}
                  </button>
                  {/* 수정 / 삭제 아이콘 */}
                  <div className={styles.itemActions}>
                    <button
                      className={styles.actionBtn}
                      onClick={(e) => startEdit(e, p)}
                      title="이름 수정"
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                      </svg>
                    </button>
                    <button
                      className={`${styles.actionBtn} ${styles.actionBtnDel}`}
                      onClick={(e) => { e.stopPropagation(); setConfirmDelId(p.id); setEditingId(null) }}
                      title="삭제"
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                        <path d="M10 11v6M14 11v6"/>
                        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                      </svg>
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* 새 프로젝트 생성 */}
          <div className={styles.divider} />
          {error && <div className={styles.error}>{error}</div>}
          {!creating ? (
            <button
              className={`${styles.item} ${styles.createBtn}`}
              onClick={() => { setCreating(true); setEditingId(null); setConfirmDelId(null) }}
            >
              <span className={styles.itemIcon}>＋</span>
              <span className={styles.itemText}>새 프로젝트 만들기</span>
            </button>
          ) : (
            <form className={styles.createForm} onSubmit={handleCreate}>
              <input
                className={styles.input}
                placeholder="프로젝트 이름 *"
                value={form.title}
                onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                autoFocus
              />
              <input
                className={styles.input}
                placeholder="설명 (선택)"
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              />
              <div className={styles.formBtns}>
                <button type="submit" className={styles.submitBtn} disabled={saving}>
                  {saving ? '생성 중...' : '생성'}
                </button>
                <button type="button" className={styles.cancelBtn}
                  onClick={() => { setCreating(false); setError('') }}>
                  취소
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  )
}
