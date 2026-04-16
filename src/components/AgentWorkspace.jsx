import { useEffect, useRef } from 'react'
import styles from './AgentWorkspace.module.css'

const sleep = ms => new Promise(r => setTimeout(r, ms))


const BACKEND = 'http://localhost:8000'

// ── 파일명 추론 ────────────────────────────────────────────
function inferFilename(lang) {
  const map = {
    javascript: 'app.js', js: 'app.js',
    typescript: 'app.ts', ts: 'app.ts',
    jsx: 'App.jsx', tsx: 'App.tsx',
    python: 'script.py', py: 'script.py',
    css: 'styles.css', html: 'index.html',
    java: 'Main.java', go: 'main.go',
    rust: 'main.rs', bash: 'script.sh', sh: 'script.sh',
    sql: 'query.sql', json: 'data.json',
    yaml: 'config.yaml', yml: 'config.yml',
  }
  return map[lang?.toLowerCase()] || `file.${lang || 'txt'}`
}

// ── 코드 블록 파싱 ─────────────────────────────────────────
function parseCodeBlocks(text) {
  const blocks = []
  const regex = /```(\w*)\n([\s\S]*?)```/g
  let lastIndex = 0
  let match
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      blocks.push({ type: 'text', content: text.slice(lastIndex, match.index) })
    }
    const lang = match[1] || 'text'
    const rawCode = match[2]
    const lines = rawCode.split('\n')
    const firstLine = lines[0]?.trim() ?? ''
    let filename = null
    let code = rawCode
    const commentMatch = firstLine.match(/^(?:\/\/|#)\s*(.+)/)
    if (commentMatch) {
      const candidate = commentMatch[1].trim()
      if (candidate.includes('.') || candidate.includes('/')) {
        filename = candidate
        code = lines.slice(1).join('\n').replace(/^\n/, '')
      }
    }
    if (!filename) filename = inferFilename(lang)
    blocks.push({ type: 'code', lang, filename, content: code })
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    blocks.push({ type: 'text', content: text.slice(lastIndex) })
  }
  return blocks
}

// ── 결과를 파일 뷰어 형태로 렌더링 ────────────────────────
function renderResult(container, text, stylesModule) {
  const s = stylesModule
  const blocks = parseCodeBlocks(text)
  container.innerHTML = ''

  blocks.forEach(block => {
    if (block.type === 'text') {
      const trimmed = block.content.trim()
      if (!trimmed) return
      const p = document.createElement('p')
      p.className = s.resultText
      p.textContent = trimmed
      container.appendChild(p)
      return
    }

    // ── 파일 뷰어 ──
    const viewer = document.createElement('div')
    viewer.className = s.fileViewer

    // 헤더 (경로 + 복사 버튼)
    const header = document.createElement('div')
    header.className = s.fileViewerHeader

    const pathParts = block.filename.split('/')
    const breadcrumb = document.createElement('div')
    breadcrumb.className = s.filePath
    pathParts.forEach((part, i) => {
      const span = document.createElement('span')
      span.className = i === pathParts.length - 1 ? s.filePathFile : s.filePathDir
      span.textContent = part
      breadcrumb.appendChild(span)
      if (i < pathParts.length - 1) {
        const sep = document.createElement('span')
        sep.className = s.filePathSep
        sep.textContent = ' / '
        breadcrumb.appendChild(sep)
      }
    })
    header.appendChild(breadcrumb)

    const copyBtn = document.createElement('button')
    copyBtn.className = s.copyBtn
    copyBtn.textContent = 'Copy'
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(block.content).then(() => {
        copyBtn.textContent = 'Copied!'
        setTimeout(() => { copyBtn.textContent = 'Copy' }, 1500)
      })
    }
    header.appendChild(copyBtn)
    viewer.appendChild(header)

    // 본문 (줄번호 + 코드)
    const body = document.createElement('div')
    body.className = s.fileViewerBody

    const lineNums = document.createElement('div')
    lineNums.className = s.lineNums

    const codeContent = document.createElement('div')
    codeContent.className = s.codeContent

    const codeLines = block.content.split('\n')
    if (codeLines[codeLines.length - 1] === '') codeLines.pop()

    codeLines.forEach((line, i) => {
      const numEl = document.createElement('div')
      numEl.className = s.lineNum
      numEl.textContent = i + 1
      lineNums.appendChild(numEl)

      const lineEl = document.createElement('div')
      lineEl.className = s.codeLine
      lineEl.textContent = line === '' ? '\u00A0' : line
      codeContent.appendChild(lineEl)
    })

    body.appendChild(lineNums)
    body.appendChild(codeContent)
    viewer.appendChild(body)
    container.appendChild(viewer)
  })
}

// ── 에이전트 작업 실행 스트리밍 ──────────────────────────────
async function streamAgentOutput(originalRequest, agentTask, roleKey, onChunk) {
  const res = await fetch(`${BACKEND}/agent/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      original_request: originalRequest,
      agent_task: agentTask,
      role_key: roleKey,
    }),
  })
  if (!res.ok) throw new Error(`에이전트 실행 오류: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'text') onChunk(data.chunk)
        else if (data.type === 'error') { const e = new Error(data.message); e.isServerError = true; throw e }
      } catch (e) {
        if (e.isServerError) throw e
      }
    }
  }
}

export default function AgentWorkspace({ agents, request, onDone }) {
  const sceneRef   = useRef(null)
  const dotContRef = useRef(null)
  const workRef    = useRef(null)
  const listRef    = useRef(null)
  const streamRef  = useRef(null)
  const resultRef  = useRef(null)
  const runningRef = useRef(false)

  useEffect(() => {
    if (!agents?.length || runningRef.current) return
    runningRef.current = true
    runAnimation(request)
  }, [agents])

  async function runAnimation(taskRequest) {
    const scene   = sceneRef.current
    const dotCont = dotContRef.current
    const work    = workRef.current
    const list    = listRef.current
    const stream  = streamRef.current
    const result  = resultRef.current
    if (!scene || !dotCont || !work || !list || !stream || !result) return

    const { width: W, height: H } = scene.getBoundingClientRect()
    const cx = W / 2
    const cy = H / 2
    const count = agents.length

    dotCont.innerHTML = ''
    list.innerHTML = ''
    stream.innerHTML = ''

    // ── 1. 도트 생성 ──────────────────────────────────
    const dots = [], lbls = [], ovs = []
    agents.forEach((a, i) => {
      const dot = document.createElement('div')
      dot.className = styles.dotEl
      dot.style.cssText = `background:${a.color};left:${cx}px;top:${cy}px;`
      dotCont.appendChild(dot); dots.push(dot)

      const lbl = document.createElement('div')
      lbl.className = styles.dotLbl
      lbl.textContent = a.name
      lbl.style.cssText = `color:${a.color};left:${cx}px;top:${cy + 24}px;`
      dotCont.appendChild(lbl); lbls.push(lbl)

      const ov = document.createElement('div')
      ov.className = styles.dotOv
      ov.style.cssText = `background:${a.color};left:${cx}px;top:${cy}px;z-index:${count - i};`
      dotCont.appendChild(ov); ovs.push(ov)
    })

    // ── 2. 도트 등장 ──────────────────────────────────
    for (let i = 0; i < count; i++) {
      await sleep(i * 110)
      dots[i].style.transition = 'transform 0.5s cubic-bezier(0.34,1.56,0.64,1)'
      dots[i].style.transform  = 'translate(-50%,-50%) scale(1)'
    }
    await sleep(450)

    // ── 3. 도트 펼침 ──────────────────────────────────
    const spread = Math.min(300, W * 0.68)
    const xs = count === 1
      ? [cx]
      : Array.from({ length: count }, (_, i) => cx - spread / 2 + (spread / (count - 1)) * i)

    for (let i = 0; i < count; i++) {
      dots[i].style.transition = 'left 0.65s cubic-bezier(0.76,0,0.24,1)'
      dots[i].style.left = xs[i] + 'px'
      ovs[i].style.left  = xs[i] + 'px'
      lbls[i].style.left = xs[i] + 'px'
    }
    await sleep(750)
    lbls.forEach(l => { l.style.transition = 'opacity 0.3s'; l.style.opacity = '0.85' })
    await sleep(300)

    // ── 4. 도트 협업 바운스 ───────────────────────────
    const B = 20, P = 360
    for (let c = 0; c < 3; c++) {
      dots.forEach((d, i) => setTimeout(() => {
        d.style.transition = `top ${P}ms cubic-bezier(0.4,0,0.2,1)`
        d.style.top = (cy - B) + 'px'
        lbls[i].style.transition = `top ${P}ms`
        lbls[i].style.top = (cy - B + 24) + 'px'
      }, i * 70))
      await sleep(P + count * 70 + 60)

      dots.forEach((d, i) => setTimeout(() => {
        d.style.transition = `top ${P}ms cubic-bezier(0.4,0,0.2,1)`
        d.style.top = (cy + B) + 'px'
        lbls[i].style.top = (cy + B + 24) + 'px'
      }, i * 70))
      await sleep(P + count * 70 + 60)

      dots.forEach((d, i) => setTimeout(() => {
        d.style.transition = `top ${P * 0.7}ms cubic-bezier(0.4,0,0.2,1)`
        d.style.top = cy + 'px'
        lbls[i].style.top = (cy + 24) + 'px'
      }, i * 55))
      await sleep(P * 0.7 + count * 55 + 100)
    }

    lbls.forEach(l => { l.style.transition = 'opacity 0.25s'; l.style.opacity = '0' })
    await sleep(300)

    // ── 5. 에이전트 패널 생성 (배정된 업무 표시) ─────────
    const panelEls = []
    agents.forEach((a) => {
      const el = document.createElement('div')
      el.className = styles.agentItem
      el.innerHTML = `
        <div class="${styles.aDot} ${styles.pulse}" style="background:${a.color}"></div>
        <div class="${styles.aInfo}">
          <div class="${styles.aName}">${a.name}</div>
          <div class="${styles.aAi}" style="color:${a.color}">${a.aiType?.toUpperCase() ?? 'AI'}</div>
          ${a.task ? `<div class="${styles.aTask}">${a.task}</div>` : ''}
        </div>
        <div class="${styles.aSpinner}" style="border-top-color:${a.color}"></div>
      `
      list.appendChild(el)
      panelEls.push(el)
    })

    // ── 6. 도트 → 배경 전환 ───────────────────────────
    const maxDim = Math.sqrt(W * W + H * H) * 2.2
    const sv = maxDim / 20

    for (let i = 0; i < count; i++) {
      dots[i].style.transition = 'transform 0.18s ease'
      dots[i].style.transform  = 'translate(-50%,-50%) scale(2.8)'
      await sleep(130)
      dots[i].style.transform  = 'translate(-50%,-50%) scale(0)'
      ovs[i].style.transition  = 'transform 0.7s cubic-bezier(0.76,0,0.24,1)'
      ovs[i].style.transform   = `translate(-50%,-50%) scale(${sv})`
      await sleep(i === count - 1 ? 420 : 160)
    }
    await sleep(200)

    work.style.opacity = '1'
    work.style.pointerEvents = 'all'
    const dotSceneEl = scene.querySelector(`.${styles.dotScene}`)
    dotSceneEl.style.opacity = '0'
    dotSceneEl.style.pointerEvents = 'none'
    await sleep(300)

    // ── 7. 에이전트 패널 등장 ─────────────────────────
    for (let i = 0; i < count; i++) {
      panelEls[i].classList.add(styles.show)
      await sleep(80)
    }
    await sleep(200)

    const liveTag = work.querySelector(`.${styles.liveTag}`)
    if (liveTag) liveTag.classList.add(styles.liveShow)

    // ── 8. 에이전트별 실시간 작업 실행 ──────────────────
    const progFill = work.querySelector(`.${styles.progFill}`)
    const progText = work.querySelector(`.${styles.progText}`)
    let lastAgentOutput = ''

    for (let i = 0; i < count; i++) {
      const a = agents[i]
      panelEls[i].classList.add(styles.running)

      const section = document.createElement('div')
      section.className = styles.section
      section.innerHTML = `
        <div class="${styles.sectionLabel}">
          <div class="${styles.sectionDot}" style="background:${a.color}"></div>
          <span class="${styles.sectionName}" style="color:${a.color}cc">${a.name}</span>
          <span class="${styles.sectionBadge}" style="background:${a.color}18;color:${a.color}">${a.aiType?.toUpperCase() ?? 'AI'}</span>
          ${i < count - 1 ? `<span class="${styles.sectionArrow}">↓ 다음으로 전달</span>` : ''}
        </div>
        ${a.task ? `<div class="${styles.sectionTask}" style="border-left-color:${a.color}40">배정 업무: ${a.task}</div>` : ''}
        <div class="${styles.sectionBody}" id="sb-${i}"></div>
      `
      stream.appendChild(section)
      await sleep(30)
      section.classList.add(styles.sectionShow)
      stream.scrollTop = stream.scrollHeight

      const sb = document.getElementById(`sb-${i}`)

      // 에이전트가 task를 가지면 실제 AI 실행, 없으면 건너뜀
      if (a.task) {
        let agentFullText = ''
        let lineBuffer = ''
        let currentLineEl = null

        const flushLine = (text, isLive = false) => {
          if (isLive) {
            if (!currentLineEl) {
              currentLineEl = document.createElement('div')
              currentLineEl.className = `${styles.logLine} ${styles.logShow}`
              currentLineEl.style.color = `${a.color}99`
              sb.appendChild(currentLineEl)
            }
            currentLineEl.textContent = text
          } else {
            if (text.trim()) {
              const el = document.createElement('div')
              el.className = `${styles.logLine} ${styles.logShow}`
              el.style.color = a.color
              el.textContent = text
              sb.appendChild(el)
            }
            currentLineEl = null
          }
          stream.scrollTop = stream.scrollHeight
        }

        try {
          await streamAgentOutput(taskRequest, a.task, a.roleKey, (chunk) => {
            agentFullText += chunk
            lineBuffer += chunk
            const parts = lineBuffer.split('\n')
            if (parts.length > 1) {
              for (let j = 0; j < parts.length - 1; j++) flushLine(parts[j], false)
              lineBuffer = parts[parts.length - 1]
              if (lineBuffer) flushLine(lineBuffer, true)
            } else {
              if (lineBuffer.trim()) flushLine(lineBuffer, true)
            }
          })
          if (lineBuffer.trim()) flushLine(lineBuffer, false)
        } catch (e) {
          flushLine(`오류: ${e.message}`, false)
        }

        lastAgentOutput = agentFullText
      }

      if (progFill) progFill.style.width = Math.round(((i + 1) / count) * 100) + '%'
      if (progText) progText.textContent = `${i + 1} / ${count}`

      panelEls[i].classList.remove(styles.running)
      panelEls[i].classList.add(styles.done)
      const spinner = panelEls[i].querySelector(`.${styles.aSpinner}`)
      if (spinner) {
        spinner.outerHTML = `<span class="${styles.aCheck}" style="color:${a.color}">✓</span>`
      }

      if (a.handoffMsg && i < count - 1) {
        const nextColor = agents[i + 1].color
        const banner = document.createElement('div')
        banner.className = styles.handoff
        banner.style.cssText = `background:${nextColor}10;border:1px solid ${nextColor}30;color:${nextColor};`
        banner.innerHTML = `<span class="${styles.handoffArrow}">→</span><span>${a.handoffMsg}</span>`
        stream.appendChild(banner)
        await sleep(30)
        banner.classList.add(styles.handoffShow)
        stream.scrollTop = stream.scrollHeight
        await sleep(400)
      }
    }

    // ── 9. 완료 → 결과를 전체 영역 오버레이로 표시 ──
    if (liveTag) liveTag.classList.remove(styles.liveShow)
    if (progText) progText.textContent = '완료 ✓'
    if (progFill) progFill.style.background = 'var(--teal)'

    await sleep(600)

    // resultPanel을 streamArea 전체를 덮는 오버레이로 전환
    result.classList.add(styles.resultShow)
    result.classList.add(styles.resultOverlay)

    const resultContent = result.querySelector(`.${styles.resultContent}`)
    if (resultContent) {
      if (lastAgentOutput) {
        renderResult(resultContent, lastAgentOutput, styles)
      } else {
        resultContent.textContent = `${agents.length}개의 에이전트가 협업하여 작업을 완료했습니다.`
      }
    }

    result.scrollTop = 0


  }

  return (
    <div ref={sceneRef} className={styles.scene}>

      {/* 도트 애니메이션 씬 */}
      <div className={styles.dotScene}>
        <div ref={dotContRef} className={styles.dotContainer} />
      </div>

      {/* 워크 씬 */}
      <div ref={workRef} className={styles.workScene}>

        {/* 상단 헤더 */}
        <div className={styles.workHeader} />

        {/* 본문 */}
        <div className={styles.workBody}>

          {/* 왼쪽: 에이전트 목록 */}
          <div className={styles.agentList}>
            <div className={styles.listHeader}>에이전트</div>
            <div ref={listRef} className={styles.listItems} />
          </div>

          {/* 오른쪽: 스트림 + 결과 */}
          <div className={styles.streamArea}>
            <div className={styles.streamHeader}>
              <div className={styles.streamTitle}>협업 스트림</div>
              <div className={styles.liveTag}>
                <div className={styles.liveDot} />
                LIVE
              </div>
              <div className={styles.progText} />
            </div>

            <div ref={streamRef} className={styles.streamBody} />

            <div className={styles.progressBar}>
              <div className={styles.progFill} />
            </div>

            {/* 결과 패널 */}
            <div ref={resultRef} className={styles.resultPanel}>
              <div className={styles.resultHeader}>
                <div className={styles.resultCheck}>✓</div>
                <span className={styles.resultTitle}>작업 완료</span>
              </div>
              <div className={styles.resultContent} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
