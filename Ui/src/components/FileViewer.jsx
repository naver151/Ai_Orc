/**
 * FileViewer
 *
 * 워크스페이스 파일 내용 뷰어.
 * 파일 트리에서 파일 클릭 시 오버레이로 표시.
 *
 * Props:
 *   projectId   프로젝트 ID
 *   filePath    표시할 파일 경로 (null이면 닫힘)
 *   onClose     () => void
 */

import { useState, useEffect } from 'react'
import styles from './FileViewer.module.css'

const BACKEND = 'http://localhost:8000'

function getLanguage(filename) {
  const ext = filename?.split('.').pop()?.toLowerCase()
  const map = {
    py: 'python', js: 'javascript', jsx: 'jsx',
    ts: 'typescript', tsx: 'tsx', json: 'json',
    md: 'markdown', html: 'html', css: 'css',
    sh: 'bash', yaml: 'yaml', yml: 'yaml',
    sql: 'sql', txt: 'text',
  }
  return map[ext] ?? 'text'
}

function getFileIcon(name) {
  const ext = name?.split('.').pop()?.toLowerCase()
  const map = {
    py: '🐍', js: '📜', jsx: '⚛️', ts: '📘', tsx: '⚛️',
    json: '📋', md: '📝', txt: '📄', html: '🌐',
    css: '🎨', sh: '⚙️', yaml: '⚙️', yml: '⚙️', sql: '🗄️',
  }
  return map[ext] ?? '📄'
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).catch(() => {})
}

export default function FileViewer({ projectId, filePath, onClose }) {
  const [content,  setContent]  = useState('')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')
  const [copied,   setCopied]   = useState(false)

  useEffect(() => {
    if (!projectId || !filePath) return
    setLoading(true)
    setError('')
    setContent('')

    fetch(`${BACKEND}/projects/${projectId}/workspace/file?path=${encodeURIComponent(filePath)}`)
      .then(r => {
        if (!r.ok) throw new Error(`파일 없음 (${r.status})`)
        return r.json()
      })
      .then(data => setContent(data.content ?? ''))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId, filePath])

  const handleCopy = () => {
    copyToClipboard(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  if (!filePath) return null

  const filename = filePath.split('/').pop()
  const lines    = content.split('\n')

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.panel}>
        {/* 헤더 */}
        <div className={styles.header}>
          <span className={styles.fileIcon}>{getFileIcon(filename)}</span>
          <div className={styles.fileMeta}>
            <span className={styles.filename}>{filename}</span>
            <span className={styles.filepath}>{filePath}</span>
          </div>
          <div className={styles.headerActions}>
            <button className={styles.actionBtn} onClick={handleCopy} title="클립보드에 복사">
              {copied ? '✓ 복사됨' : '복사'}
            </button>
            <button className={styles.closeBtn} onClick={onClose} title="닫기">✕</button>
          </div>
        </div>

        {/* 본문 */}
        <div className={styles.body}>
          {loading && (
            <div className={styles.center}>
              <div className={styles.spinner}>↻</div>
              <span>불러오는 중...</span>
            </div>
          )}

          {error && (
            <div className={styles.center}>
              <div className={styles.errorText}>⚠️ {error}</div>
            </div>
          )}

          {!loading && !error && (
            <div className={styles.codeWrap}>
              {/* 줄 번호 + 코드 */}
              <div className={styles.lineNums}>
                {lines.map((_, i) => (
                  <span key={i}>{i + 1}</span>
                ))}
              </div>
              <pre className={styles.code}>
                <code data-lang={getLanguage(filename)}>
                  {content}
                </code>
              </pre>
            </div>
          )}
        </div>

        {/* 푸터 */}
        {!loading && !error && (
          <div className={styles.footer}>
            <span>{lines.length} 줄</span>
            <span>{content.length} 자</span>
            <span className={styles.lang}>{getLanguage(filename)}</span>
          </div>
        )}
      </div>
    </div>
  )
}
