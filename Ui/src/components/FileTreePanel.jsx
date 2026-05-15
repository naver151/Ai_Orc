/**
 * FileTreePanel
 *
 * 워크스페이스 실시간 파일 트리 패널.
 * - AgentWorkspace에서 file_written WS 이벤트를 받으면 나타남
 * - 서버 API에서 최신 트리를 주기적으로 갱신
 * - 파일 클릭 시 onFileSelect 콜백 호출
 *
 * Props:
 *   projectId      연결된 프로젝트 ID
 *   visible        패널 표시 여부
 *   onFileSelect   (path: string) => void
 *   newFilePath    마지막으로 생성된 파일 경로 (하이라이트용)
 */

import { useState, useEffect, useCallback } from 'react'
import styles from './FileTreePanel.module.css'

const BACKEND = 'http://localhost:8000'

// ── 트리 노드 컴포넌트 ────────────────────────────────────────
function TreeNode({ node, depth, onFileSelect, highlightPath, expandedDirs, toggleDir }) {
  const isDir  = node.type === 'directory'
  const isOpen = expandedDirs.has(node.path)
  const isNew  = node.path === highlightPath

  const icon = isDir
    ? (isOpen ? '📂' : '📁')
    : getFileIcon(node.name)

  return (
    <div>
      <button
        className={`${styles.node} ${isNew ? styles.newFile : ''}`}
        style={{ paddingLeft: `${12 + depth * 14}px` }}
        onClick={() => isDir ? toggleDir(node.path) : onFileSelect(node.path)}
        title={node.path}
      >
        <span className={styles.nodeIcon}>{icon}</span>
        <span className={styles.nodeName}>{node.name}</span>
        {isNew && <span className={styles.newBadge}>new</span>}
        {!isDir && node.size != null && (
          <span className={styles.nodeSize}>{fmtSize(node.size)}</span>
        )}
      </button>

      {isDir && isOpen && node.children?.map(child => (
        <TreeNode
          key={child.path}
          node={child}
          depth={depth + 1}
          onFileSelect={onFileSelect}
          highlightPath={highlightPath}
          expandedDirs={expandedDirs}
          toggleDir={toggleDir}
        />
      ))}
    </div>
  )
}

function getFileIcon(name) {
  const ext = name.split('.').pop()?.toLowerCase()
  const map = {
    py: '🐍', js: '📜', jsx: '⚛️', ts: '📘', tsx: '⚛️',
    json: '📋', md: '📝', txt: '📄', html: '🌐', css: '🎨',
    sh: '⚙️', yaml: '⚙️', yml: '⚙️', sql: '🗄️',
    png: '🖼️', jpg: '🖼️', svg: '🎨',
  }
  return map[ext] ?? '📄'
}

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

// ── 메인 컴포넌트 ────────────────────────────────────────────
export default function FileTreePanel({ projectId, visible, onFileSelect, newFilePath }) {
  const [tree,         setTree]         = useState([])
  const [loading,      setLoading]      = useState(false)
  const [expandedDirs, setExpandedDirs] = useState(new Set())

  const fetchTree = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const res = await fetch(`${BACKEND}/projects/${projectId}/workspace/tree`)
      if (!res.ok) return
      const data = await res.json()
      setTree(data.tree ?? [])

      // 새 파일이 생기면 해당 디렉터리 자동 펼침
      if (newFilePath) {
        const parts = newFilePath.split('/')
        if (parts.length > 1) {
          setExpandedDirs(prev => {
            const next = new Set(prev)
            // 모든 부모 디렉터리 펼침
            for (let i = 1; i < parts.length; i++) {
              next.add(parts.slice(0, i).join('/'))
            }
            return next
          })
        }
      }
    } catch { /* 무시 */ }
    finally { setLoading(false) }
  }, [projectId, newFilePath])

  // 마운트 시, newFilePath 변경 시 트리 갱신
  useEffect(() => {
    if (visible && projectId) fetchTree()
  }, [visible, projectId, newFilePath, fetchTree])

  const toggleDir = (path) => {
    setExpandedDirs(prev => {
      const next = new Set(prev)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })
  }

  if (!visible) return null

  return (
    <div className={styles.panel}>
      {/* 헤더 */}
      <div className={styles.header}>
        <span className={styles.headerIcon}>📂</span>
        <span className={styles.headerTitle}>워크스페이스</span>
        {loading && <span className={styles.spinner}>↻</span>}
        <button className={styles.refreshBtn} onClick={fetchTree} title="새로고침">⟳</button>
      </div>

      {/* 트리 */}
      <div className={styles.tree}>
        {tree.length === 0 ? (
          <div className={styles.empty}>
            에이전트가 파일을 생성하면<br />여기에 표시됩니다
          </div>
        ) : (
          tree.map(node => (
            <TreeNode
              key={node.path}
              node={node}
              depth={0}
              onFileSelect={onFileSelect}
              highlightPath={newFilePath}
              expandedDirs={expandedDirs}
              toggleDir={toggleDir}
            />
          ))
        )}
      </div>
    </div>
  )
}
