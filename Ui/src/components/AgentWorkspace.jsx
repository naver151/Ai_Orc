import { useEffect, useRef, useState } from 'react'
import styles from './AgentWorkspace.module.css'

const sleep = ms => new Promise(r => setTimeout(r, ms))

const WS_URL  = 'ws://localhost:8000/ws'

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

    const viewer = document.createElement('div')
    viewer.className = s.fileViewer

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
      lineEl.textContent = line === '' ? ' ' : line
      codeContent.appendChild(lineEl)
    })

    body.appendChild(lineNums)
    body.appendChild(codeContent)
    viewer.appendChild(body)
    container.appendChild(viewer)
  })
}

// ── 결과 패널 표시 ────────────────────────────────────────
function showResult(result, stream, work, styles, agents, lastAgentOutput) {
  const resultContent = result.querySelector(`.${styles.resultContent}`)
  if (resultContent) {
    if (lastAgentOutput) {
      renderResult(resultContent, lastAgentOutput, styles)
    } else {
      const p = document.createElement('p')
      p.className = styles.resultText
      p.textContent = `${agents.length}개의 에이전트가 협업하여 작업을 완료했습니다.`
      resultContent.appendChild(p)
    }
  }

  result.classList.add(styles.resultOverlay)
  result.scrollTop = 0

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      result.style.opacity = '1'
      result.style.transition = 'opacity 0.4s ease'
    })
  })

  const header = work.querySelector(`.${styles.workHeader}`)
  if (header && !header.querySelector(`.${styles.logViewBtn}`)) {
    const logBtn = document.createElement('button')
    logBtn.className = styles.logViewBtn
    logBtn.textContent = '로그 확인'
    header.appendChild(logBtn)

    let logVisible = false
    logBtn.addEventListener('click', () => {
      logVisible = !logVisible
      if (logVisible) {
        result.style.opacity = '0'
        result.style.pointerEvents = 'none'
        result.style.zIndex = '-1'
        logBtn.textContent = '결과 보기'
        stream.scrollTop = stream.scrollHeight
      } else {
        result.style.opacity = '1'
        result.style.pointerEvents = 'auto'
        result.style.zIndex = '10'
        logBtn.textContent = '로그 확인'
      }
    })
  }
}

// ── provider 키 변환 ──────────────────────────────────────
function toProviderKey(aiType) {
  if (aiType === 'claude')  return 'claude'
  if (aiType === 'gemini')  return 'gemini'
  if (aiType === 'gpt')     return 'github'
  return 'github'
}

function _getUid() {
  try { return JSON.parse(localStorage.getItem('aiorc_user'))?.uid ?? null } catch { return null }
}

// ── 에이전트 패널 HTML 템플릿 ─────────────────────────────
function makePanelHTML(a, s) {
  return `
    <div class="${s.aDot} ${s.pulse}" style="background:${a.color}"></div>
    <div class="${s.aInfo}">
      <div class="${s.aName}">${a.name}</div>
      <div class="${s.aAi}" style="color:${a.color}">${a.aiType?.toUpperCase() ?? 'AI'}</div>
      ${a.task ? `<div class="${s.aTask}">${a.task}</div>` : ''}
    </div>
    <div class="${s.aControls}">
      <button class="${s.ctrlBtn} ${s.pauseBtn}" data-name="${a.name}" data-paused="false" title="일시정지">⏸</button>
      <button class="${s.ctrlBtn} ${s.killBtn}"  data-name="${a.name}" title="종료">✕</button>
    </div>
    <div class="${s.aSpinner}" style="border-top-color:${a.color}"></div>
  `
}

// ── 메인 컴포넌트 ─────────────────────────────────────────
export default function AgentWorkspace({ agents, request, onDone, instant = false }) {
  const sceneRef   = useRef(null)
  const dotContRef = useRef(null)
  const workRef    = useRef(null)
  const listRef    = useRef(null)
  const streamRef  = useRef(null)
  const resultRef  = useRef(null)
  const runningRef = useRef(false)
  const wsRef      = useRef(null)      // WebSocket (컨트롤 버튼·개입 입력에서 공유)
  const agentsRef  = useRef([])        // 현재 에이전트 목록 (개입 UI용)

  // ── 실시간 개입 UI 상태 ───────────────────────────────
  const [ivOpen,   setIvOpen]   = useState(false)   // 개입 패널 표시 여부
  const [ivTarget, setIvTarget] = useState('')       // 개입 대상 에이전트 이름
  const [ivText,   setIvText]   = useState('')       // 입력 텍스트

  // 개입 전송
  const sendIntervention = () => {
    const ws   = wsRef.current
    const text = ivText.trim()
    if (!ws || ws.readyState !== WebSocket.OPEN || !text || !ivTarget) return

    // 스트림에 개입 로그 표시
    const stream = streamRef.current
    if (stream) {
      const el = document.createElement('div')
      el.className = styles.ivLog
      el.innerHTML =
        `<span class="${styles.ivLogIcon}">✎</span>` +
        `<span class="${styles.ivLogTarget}">${ivTarget}</span>` +
        `<span class="${styles.ivLogText}">${text}</span>`
      stream.appendChild(el)
      stream.scrollTop = stream.scrollHeight
    }

    // 백엔드로 전송 — prompt 액션이 실행 중 태스크를 취소하고 새 방향으로 재시작
    ws.send(JSON.stringify({ action: 'prompt', aiName: ivTarget, text }))
    setIvText('')
  }

  // 컴포넌트 언마운트 시 WebSocket 정리
  useEffect(() => {
    return () => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close()
      }
    }
  }, [])

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

    result.style.opacity = '0'
    result.style.transition = ''
    result.style.pointerEvents = ''
    result.style.zIndex = ''
    result.className = styles.resultPanel

    if (!instant) {
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

      // ── 5. 에이전트 패널 생성 ─────────────────────────
      const panelEls = []
      agents.forEach(a => {
        const el = document.createElement('div')
        el.className = styles.agentItem
        el.innerHTML = makePanelHTML(a, styles)
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

      await runAgents(taskRequest, agents, panelEls, stream, work, result)

    } else {
      // ── instant 모드: 도트 없이 바로 로그 화면 ────────
      const dotSceneEl = scene.querySelector(`.${styles.dotScene}`)
      if (dotSceneEl) {
        dotSceneEl.style.opacity = '0'
        dotSceneEl.style.pointerEvents = 'none'
      }
      work.style.opacity = '1'
      work.style.pointerEvents = 'all'

      const panelEls = []
      agents.forEach(a => {
        const el = document.createElement('div')
        el.className = `${styles.agentItem} ${styles.show}`
        el.innerHTML = makePanelHTML(a, styles)
        list.appendChild(el)
        panelEls.push(el)
      })

      const liveTag = work.querySelector(`.${styles.liveTag}`)
      if (liveTag) liveTag.classList.add(styles.liveShow)

      await runAgents(taskRequest, agents, panelEls, stream, work, result)
    }
  }

  // ── WebSocket 기반 에이전트 실행 ──────────────────────────
  async function runAgents(taskRequest, agents, panelEls, stream, work, result) {
    const count    = agents.length
    const progFill = work.querySelector(`.${styles.progFill}`)
    const progText = work.querySelector(`.${styles.progText}`)
    const liveTag  = work.querySelector(`.${styles.liveTag}`)

    // 에이전트 이름 → 패널/섹션바디 맵
    const nameToPanel = {}
    const nameToSb    = {}
    const nameToState = {}

    agents.forEach((a, i) => {
      nameToPanel[a.name] = panelEls[i]

      const section = document.createElement('div')
      section.className = styles.section
      section.innerHTML = `
        <div class="${styles.sectionLabel}">
          <div class="${styles.sectionDot}" style="background:${a.color}"></div>
          <span class="${styles.sectionName}" style="color:${a.color}cc">${a.name}</span>
          <span class="${styles.sectionBadge}" style="background:${a.color}18;color:${a.color}">${(a.aiType || 'AI').toUpperCase()}</span>
        </div>
        ${a.task ? `<div class="${styles.sectionTask}" style="border-left-color:${a.color}40">배정 업무: ${a.task}</div>` : ''}
        <div class="${styles.sectionBody}" id="lgsb-${i}"></div>
      `
      stream.appendChild(section)
      section.classList.add(styles.sectionShow)

      const sb = document.getElementById(`lgsb-${i}`)
      nameToSb[a.name]    = sb
      nameToState[a.name] = { lineBuffer: '', currentLineEl: null, fullText: '' }
    })
    stream.scrollTop = stream.scrollHeight

    agents.forEach((_, i) => panelEls[i].classList.add(styles.running))

    let doneCount     = 0
    let lastOutput    = ''
    let synthesisText = ''

    // 토큰 단위 스트리밍을 라인 버퍼로 렌더링
    const flushChunk = (agentName, chunk) => {
      const a     = agents.find(x => x.name === agentName)
      const sb    = nameToSb[agentName]
      const state = nameToState[agentName]
      if (!sb || !state) return

      state.fullText   += chunk
      state.lineBuffer += chunk
      lastOutput        = state.fullText

      const parts = state.lineBuffer.split('\n')
      const flush = (text, live) => {
        if (live) {
          if (!state.currentLineEl) {
            state.currentLineEl = document.createElement('div')
            state.currentLineEl.className = `${styles.logLine} ${styles.logShow}`
            state.currentLineEl.style.color = a ? `${a.color}99` : '#888'
            sb.appendChild(state.currentLineEl)
          }
          state.currentLineEl.textContent = text
        } else {
          if (state.currentLineEl) {
            state.currentLineEl.style.color = a?.color ?? '#ccc'
            if (text.trim()) state.currentLineEl.textContent = text
            state.currentLineEl = null
          } else if (text.trim()) {
            const el = document.createElement('div')
            el.className = `${styles.logLine} ${styles.logShow}`
            el.style.color = a?.color ?? '#ccc'
            el.textContent = text
            sb.appendChild(el)
          }
        }
        stream.scrollTop = stream.scrollHeight
      }

      if (parts.length > 1) {
        for (let j = 0; j < parts.length - 1; j++) flush(parts[j], false)
        state.lineBuffer = parts[parts.length - 1]
        if (state.lineBuffer) flush(state.lineBuffer, true)
      } else if (state.lineBuffer.trim()) {
        flush(state.lineBuffer, true)
      }
    }

    // 에이전트 완료 처리
    const markDone = (agentName) => {
      const panel = nameToPanel[agentName]
      if (!panel || panel.classList.contains(styles.done)) return
      panel.classList.remove(styles.running, styles.paused)
      panel.classList.add(styles.done)
      const spinner = panel.querySelector(`.${styles.aSpinner}`)
      if (spinner) {
        const a = agents.find(x => x.name === agentName)
        spinner.outerHTML = `<span class="${styles.aCheck}" style="color:${a?.color ?? '#4caf82'}">✓</span>`
      }
      // 완료된 에이전트의 컨트롤 버튼 비활성화
      panel.querySelectorAll(`.${styles.ctrlBtn}`).forEach(btn => {
        btn.disabled = true
        btn.style.opacity = '0.3'
      })
      doneCount++
      if (progFill) progFill.style.width = Math.round((doneCount / count) * 100) + '%'
      if (progText) progText.textContent  = `${doneCount} / ${count}`
    }

    // ── WebSocket 연결 ────────────────────────────────────
    let ws
    try {
      ws = new WebSocket(WS_URL)
      wsRef.current = ws

      await new Promise((resolve, reject) => {
        ws.onopen  = resolve
        ws.onerror = () => reject(new Error('WebSocket 연결 실패'))
        setTimeout(() => reject(new Error('연결 타임아웃')), 5000)
      })
    } catch (e) {
      console.error('[WS 연결 실패]', e)
      // 연결 실패 시 fallback 메시지
      agents.forEach(a => {
        if (nameToSb[a.name]) flushChunk(a.name, `[오류] 백엔드 서버에 연결할 수 없습니다.\n`)
      })
      if (liveTag) liveTag.classList.remove(styles.liveShow)
      if (progText) progText.textContent = '연결 실패'
      return
    }

    // ── 개입 UI 활성화 ────────────────────────────────────
    agentsRef.current = agents
    setIvTarget(agents[0]?.name ?? '')
    setIvOpen(true)

    // ── 에이전트 등록 (관리자 → 워커 순) ─────────────────
    agents.forEach((a, i) => {
      ws.send(JSON.stringify({
        action:    'spawn',
        aiName:    a.name,
        provider:  toProviderKey(a.aiType),
        isManager: i === 0,
        role:      a.roleKey ?? '',
      }))
    })

    await sleep(150)  // spawn 처리 대기

    // ── 컨트롤 버튼 이벤트 연결 ──────────────────────────
    agents.forEach(a => {
      const panel = nameToPanel[a.name]
      if (!panel) return

      const pauseBtn = panel.querySelector(`.${styles.pauseBtn}`)
      const killBtn  = panel.querySelector(`.${styles.killBtn}`)

      if (pauseBtn) {
        pauseBtn.addEventListener('click', () => {
          if (!ws || ws.readyState !== WebSocket.OPEN) return
          const isPaused = pauseBtn.dataset.paused === 'true'
          if (isPaused) {
            ws.send(JSON.stringify({ action: 'resume', aiName: a.name }))
            pauseBtn.textContent       = '⏸'
            pauseBtn.dataset.paused    = 'false'
            pauseBtn.title             = '일시정지'
            panel.classList.remove(styles.paused)
          } else {
            ws.send(JSON.stringify({ action: 'pause', aiName: a.name }))
            pauseBtn.textContent       = '▶'
            pauseBtn.dataset.paused    = 'true'
            pauseBtn.title             = '재개'
            panel.classList.add(styles.paused)
          }
        })
      }

      if (killBtn) {
        killBtn.addEventListener('click', () => {
          if (!ws || ws.readyState !== WebSocket.OPEN) return
          ws.send(JSON.stringify({ action: 'kill', aiName: a.name }))
          // UI 즉시 반영
          panel.classList.remove(styles.running, styles.paused)
          panel.classList.add(styles.killed)
          panel.querySelectorAll(`.${styles.ctrlBtn}`).forEach(b => {
            b.disabled = true; b.style.opacity = '0.3'
          })
          flushChunk(a.name, '\n[종료됨]\n')
        })
      }
    })

    // ── 관리자에게 프롬프트 전송 ──────────────────────────
    ws.send(JSON.stringify({
      action: 'prompt',
      aiName: agents[0].name,
      text:   taskRequest,
    }))

    // ── 메시지 수신 루프 ──────────────────────────────────
    await new Promise((resolve) => {
      ws.onmessage = (event) => {
        let evt
        try { evt = JSON.parse(event.data) } catch { return }

        const { type, aiName, message, status, task, from, to } = evt

        switch (type) {

          // 토큰 스트리밍
          case 'log':
            if (!aiName || !message) break
            if (nameToSb[aiName]) {
              flushChunk(aiName, message)
            } else {
              // 관리자 종합 단계 텍스트
              synthesisText += message
            }
            break

          // 에이전트 상태 변경
          case 'status':
            if (!aiName) break
            if (status === 'COMPLETED') {
              markDone(aiName)
            } else if (status === 'STOPPED') {
              nameToPanel[aiName]?.classList.add(styles.paused)
            } else if (status === 'RUNNING') {
              nameToPanel[aiName]?.classList.remove(styles.paused)
            }
            break

          // 현재 수행 중인 태스크 표시
          case 'current_task':
            if (!aiName) break
            if (task) {
              // 섹션 태스크 라벨 업데이트
              const sb = nameToSb[aiName]
              if (sb) {
                const taskEl = sb.parentElement?.querySelector(`.${styles.sectionTask}`)
                if (taskEl) taskEl.textContent = task
              }
            }
            break

          // 서브태스크 배정 이벤트
          case 'subtask_assign': {
            const targetSb = nameToSb[to] || nameToSb[from]
            if (targetSb) {
              const el = document.createElement('div')
              el.className = `${styles.logLine} ${styles.logShow} ${styles.assignLog}`
              el.textContent = `▸ [${from} → ${to}] ${message || ''}`
              targetSb.appendChild(el)
              stream.scrollTop = stream.scrollHeight
            }
            break
          }

          // 오케스트레이션 시작
          case 'orchestration_start':
            if (progText) progText.textContent = '실행 중...'
            break

          // 종합 단계 시작
          case 'orchestration_synthesis':
            if (progText) progText.textContent = '종합 중...'
            break

          // 오케스트레이션 완료
          case 'orchestration_done':
            ws.close()
            resolve()
            break

          case 'error':
            console.error('[WS 서버 오류]', message)
            break

          default:
            break
        }
      }

      ws.onerror = (e) => { console.error('[WS 오류]', e); resolve() }
      ws.onclose = ()  => resolve()
    })

    wsRef.current = null
    setIvOpen(false)   // 개입 패널 닫기

    // ── 미완료 패널 정리 ─────────────────────────────────
    agents.forEach(a => {
      if (nameToPanel[a.name]?.classList.contains(styles.running)) {
        markDone(a.name)
      }
      const state = nameToState[a.name]
      if (state?.lineBuffer?.trim()) flushChunk(a.name, '')
    })

    // ── 완료 처리 ─────────────────────────────────────────
    if (liveTag) liveTag.classList.remove(styles.liveShow)
    if (progText) progText.textContent = '완료 ✓'
    if (progFill) progFill.style.background = 'var(--teal)'

    const finalOutput = synthesisText || lastOutput
    await sleep(400)
    showResult(result, stream, work, styles, agents, finalOutput)

    onDone?.({
      request:         taskRequest,
      agents,
      workerResults:   agents.map(a => nameToState[a.name]?.fullText ?? ''),
      synthesisResult: finalOutput,
    })
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

            {/* ── 실시간 개입 입력 바 ── */}
            {ivOpen && (
              <div className={styles.ivBar}>
                <span className={styles.ivBarLabel}>✎ 개입</span>

                {/* 대상 에이전트 선택 */}
                <select
                  className={styles.ivSelect}
                  value={ivTarget}
                  onChange={e => setIvTarget(e.target.value)}
                >
                  {agentsRef.current.map((a, i) => (
                    <option key={a.name} value={a.name}>
                      {i === 0 ? `${a.name} (관리자)` : a.name}
                    </option>
                  ))}
                </select>

                {/* 개입 텍스트 입력 */}
                <input
                  className={styles.ivInput}
                  value={ivText}
                  onChange={e => setIvText(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      sendIntervention()
                    }
                  }}
                  placeholder={
                    ivTarget === agentsRef.current[0]?.name
                      ? '전체 방향을 바꾸려면 입력하세요... (재시작됩니다)'
                      : `${ivTarget}에게 새 지시를 입력하세요...`
                  }
                />

                <button
                  className={styles.ivBtn}
                  onClick={sendIntervention}
                  disabled={!ivText.trim()}
                >
                  전송
                </button>
              </div>
            )}

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
