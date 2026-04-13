import { useEffect, useRef } from 'react'
import styles from './AgentWorkspace.module.css'

const sleep = ms => new Promise(r => setTimeout(r, ms))

export default function AgentWorkspace({ agents, onDone }) {
  const sceneRef   = useRef(null)
  const dotContRef = useRef(null)
  const workRef    = useRef(null)
  const listRef    = useRef(null)
  const streamRef  = useRef(null)
  const runningRef = useRef(false)

  useEffect(() => {
    if (!agents?.length || runningRef.current) return
    runningRef.current = true
    runAnimation()
  }, [agents])

  async function runAnimation() {
    const scene   = sceneRef.current
    const dotCont = dotContRef.current
    const work    = workRef.current
    const list    = listRef.current
    const stream  = streamRef.current
    if (!scene || !dotCont || !work || !list || !stream) return

    const { width: W, height: H } = scene.getBoundingClientRect()
    const cx = W / 2
    const cy = H / 2
    const count = agents.length

    dotCont.innerHTML = ''
    list.innerHTML = ''
    stream.innerHTML = ''

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

    for (let i = 0; i < count; i++) {
      await sleep(i * 110)
      dots[i].style.transition = 'transform 0.5s cubic-bezier(0.34,1.56,0.64,1)'
      dots[i].style.transform  = 'translate(-50%,-50%) scale(1)'
    }
    await sleep(450)

    const spread = Math.min(300, W * 0.68)
    const xs = count === 1
      ? [cx]
      : Array.from({ length: count }, (_, i) => cx - spread/2 + (spread/(count-1))*i)

    for (let i = 0; i < count; i++) {
      dots[i].style.transition = 'left 0.65s cubic-bezier(0.76,0,0.24,1)'
      dots[i].style.left = xs[i] + 'px'
      ovs[i].style.left  = xs[i] + 'px'
      lbls[i].style.left = xs[i] + 'px'
    }
    await sleep(750)
    lbls.forEach(l => { l.style.transition = 'opacity 0.3s'; l.style.opacity = '0.85' })
    await sleep(300)

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

    const panelEls = []
    agents.forEach((a, i) => {
      const el = document.createElement('div')
      el.className = styles.agentItem
      el.innerHTML = `
        <div class="${styles.aDot} ${styles.pulse}" style="background:${a.color}"></div>
        <div class="${styles.aInfo}">
          <div class="${styles.aName}">${a.name}</div>
          <div class="${styles.aAi}" style="color:${a.color}">${a.aiType?.toUpperCase() ?? 'AI'}</div>
        </div>
        <div class="${styles.aSpinner}" style="border-top-color:${a.color}"></div>
      `
      list.appendChild(el)
      panelEls.push(el)
    })

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
    scene.querySelector(`.${styles.dotScene}`).style.opacity = '0'
    await sleep(300)

    for (let i = 0; i < count; i++) {
      panelEls[i].classList.add(styles.show)
      await sleep(80)
    }
    await sleep(200)

    const liveTag = work.querySelector(`.${styles.liveTag}`)
    if (liveTag) liveTag.classList.add(styles.liveShow)

    const totalLines = agents.reduce((s, a) => s + (a.logs?.length ?? 0), 0) || 1
    let doneLines = 0
    const progFill = work.querySelector(`.${styles.progFill}`)
    const progText = work.querySelector(`.${styles.progText}`)

    for (let i = 0; i < count; i++) {
      const a = agents[i]
      panelEls[i].classList.add(styles.running)

      const section = document.createElement('div')
      section.className = styles.section
      section.innerHTML = `
        <div class="${styles.sectionLabel}">
          <div class="${styles.sectionDot}" style="background:${a.color}"></div>
          <span class="${styles.sectionName}" style="color:${a.color}88">${a.name}</span>
          <span class="${styles.sectionBadge}" style="background:${a.color}18;color:${a.color}">${a.aiType?.toUpperCase() ?? 'AI'}</span>
          ${i < count - 1 ? `<span class="${styles.sectionArrow}">↓ 다음으로 전달</span>` : ''}
        </div>
        <div class="${styles.sectionBody}" id="sb-${i}"></div>
      `
      stream.appendChild(section)
      await sleep(30)
      section.classList.add(styles.sectionShow)
      stream.scrollTop = stream.scrollHeight

      const sb = document.getElementById(`sb-${i}`)

      for (const line of (a.logs ?? [])) {
        const el = document.createElement('div')
        const isDim = line.startsWith('//')
        const isKey = line.startsWith('▸') && (line.includes('완료') || line.includes('핵심') || line.includes('승인'))
        el.className = `${styles.logLine} ${isDim ? styles.dim : isKey ? styles.key : ''}`
        el.style.color = isDim ? 'rgba(255,255,255,0.2)' : a.color
        el.textContent = line
        sb.appendChild(el)
        await sleep(20)
        el.classList.add(styles.logShow)
        stream.scrollTop = stream.scrollHeight
        doneLines++
        if (progFill) progFill.style.width = Math.round((doneLines / totalLines) * 100) + '%'
        if (progText) progText.textContent = `${i + 1} / ${count}`
        await sleep(isDim ? 180 : isKey ? 400 : 300)
      }

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
        await sleep(500)
      }
    }

    if (liveTag) liveTag.classList.remove(styles.liveShow)
    if (progText) progText.textContent = '완료'
    await sleep(1200)
    onDone?.('모든 에이전트가 협업을 완료했습니다. 추가로 필요한 사항이 있으시면 말씀해 주세요.')
  }

  return (
    <div ref={sceneRef} className={styles.scene}>
      <div className={styles.dotScene}>
        <div ref={dotContRef} className={styles.dotContainer} />
      </div>
      <div ref={workRef} className={styles.workScene}>
        <div className={styles.agentList}>
          <div className={styles.listHeader}>에이전트</div>
          <div ref={listRef} className={styles.listItems} />
        </div>
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
        </div>
      </div>
    </div>
  )
}
