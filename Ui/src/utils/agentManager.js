const WS_URL = 'ws://localhost:8000/ws'

// Default agents to spawn: manager + 3 workers
const SPAWN_AGENTS = [
  { aiName: '관리자', provider: 'github' },
  { aiName: '분석가', provider: 'github' },
  { aiName: '실행자', provider: 'github' },
  { aiName: '검토자', provider: 'github' },
]

const COLORS = ['#7c6dfa', '#4caf82', '#f5a623', '#1ec8a0', '#a897ff']

export const AI_LABELS = {
  github: { label: 'GitHub AI', color: '#7c6dfa' },
  claude: { label: 'Claude',    color: '#7c6dfa' },
  gpt:    { label: 'GPT-4o',    color: '#4caf82' },
  gemini: { label: 'Gemini',    color: '#f5a623' },
}

// ── Mock fallback (used when backend is unavailable) ─────────────────────────

const MOCK_DATA = {
  analyst:   { logs: ['// 사용자 요청 수신', '▸ 의도 분류: 시장 분석 요청', '▸ 핵심 키워드 추출 완료', '▸ 작업 정의 완료', '// 다음 에이전트로 작업 정의서 전달'], handoffMsg: '작업 정의서 전달 → 관련 데이터 수집 요청' },
  collector: { logs: ['// 작업 정의서 수신 완료', '▸ 소스 연결: 데이터 DB', '▸ 데이터 수집 완료', '▸ 수집 완료: 12건 문서', '// 수집 데이터 패키징 후 전달'], handoffMsg: '수집 데이터 패키지 전달 → 분석 및 인사이트 도출 요청' },
  executor:  { logs: ['// 데이터 패키지 수신, 분석 시작', '▸ 시장 트렌드 분석 완료', '▸ 핵심 기회 도출 완료', '▸ 핵심 리스크 식별 완료', '// 분석 결과 보고서 초안 생성'], handoffMsg: '분석 보고서 초안 전달 → 정확성 검증 요청' },
  reviewer:  { logs: ['// 보고서 초안 검증 시작', '▸ 데이터 출처 검증: ✓', '▸ 수치 일관성: 이상 없음 ✓', '▸ 품질 승인', '// 검증 완료본 전달'], handoffMsg: '검증 완료본 전달 → 최종 사용자 응답 생성 요청' },
  writer:    { logs: ['// 최종 응답 생성 시작', '▸ 요약 작성 완료', '▸ 비교표 생성 완료', '▸ 최종 보고서 완성'], handoffMsg: null },
}

const MOCK_POOL = [
  { roleKey: 'analyst',   name: '요청 분석 AI' },
  { roleKey: 'collector', name: '데이터 수집 AI' },
  { roleKey: 'executor',  name: '처리 실행 AI' },
  { roleKey: 'reviewer',  name: '품질 검토 AI' },
  { roleKey: 'writer',    name: '응답 생성 AI' },
]

function buildMockPlan(text) {
  const len = text.length
  let count = 2
  if (len > 30  || /그리고|또한|추가로/.test(text)) count = 3
  if (len > 60  || /분석|리포트|보고서/.test(text)) count = 4
  if (len > 100 || /전체|종합|시스템|전략/.test(text)) count = 5

  const agents = MOCK_POOL.slice(0, count).map((a, i, arr) => ({
    name:       a.name,
    aiType:     'github',
    color:      COLORS[i % COLORS.length],
    logs:       MOCK_DATA[a.roleKey]?.logs ?? [],
    handoffMsg: i < arr.length - 1 ? MOCK_DATA[a.roleKey]?.handoffMsg ?? null : null,
  }))

  return {
    intro: `요청을 분석한 결과 ${count}개의 에이전트가 필요합니다. 지금 바로 배치하겠습니다.`,
    agents,
  }
}

// ── Real log text → display lines ────────────────────────────────────────────

function textToLogLines(text) {
  if (!text || !text.trim()) return []

  // Split by newlines first
  const byNewline = text.split('\n').map(s => s.trim()).filter(Boolean)
  if (byNewline.length > 1) {
    return byNewline.slice(0, 10).map(l => (l.startsWith('▸') || l.startsWith('//') ? l : `▸ ${l}`))
  }

  // For long single-line text, chunk into ~80-char segments
  const chunks = []
  let remaining = text.trim()
  // Try to split by sentences first
  const sentences = remaining.match(/[^.!?]+[.!?]+/g) ?? [remaining]
  for (const s of sentences) {
    const trimmed = s.trim()
    if (trimmed) chunks.push(`▸ ${trimmed}`)
    if (chunks.length >= 8) break
  }
  return chunks.length ? chunks : [`▸ ${text.trim().slice(0, 120)}`]
}

// ── Main export ───────────────────────────────────────────────────────────────

export async function analyzeRequest(userText) {
  return new Promise((resolve) => {
    let ws
    try {
      ws = new WebSocket(WS_URL)
    } catch {
      resolve(buildMockPlan(userText))
      return
    }

    // Per-agent accumulated streaming text
    const agentText  = {}   // aiName → string
    const agentOrder = []   // ordered by first message
    let managerName = SPAWN_AGENTS[0].aiName
    let intro       = ''
    let finished    = false

    const finish = () => {
      if (finished) return
      finished = true
      try { if (ws.readyState < 2) ws.close() } catch {}
      clearTimeout(timeout)

      // Build agents array from collected data
      const workerNames = agentOrder.filter(n => n !== managerName)

      if (workerNames.length === 0) {
        // No workers received — fall back to mock
        resolve(buildMockPlan(userText))
        return
      }

      const agents = workerNames.map((name, i, arr) => ({
        name,
        aiType: 'github',
        color:  COLORS[i % COLORS.length],
        logs:   textToLogLines(agentText[name] || ''),
        handoffMsg: i < arr.length - 1 ? `${name} 결과 → 다음 단계로 전달` : null,
      }))

      resolve({
        intro: intro || `요청을 분석했습니다. ${agents.length}개의 에이전트가 협업합니다.`,
        agents,
      })
    }

    // Safety timeout: 90 seconds
    const timeout = setTimeout(finish, 90_000)

    ws.onopen = () => {
      // Spawn all agents
      SPAWN_AGENTS.forEach(a =>
        ws.send(JSON.stringify({ action: 'spawn', aiName: a.aiName, provider: a.provider }))
      )
      // Send prompt to manager
      ws.send(JSON.stringify({ action: 'prompt', aiName: managerName, text: userText }))
    }

    ws.onmessage = (event) => {
      let data
      try { data = JSON.parse(event.data) } catch { return }

      const { type, aiName } = data

      if (type === 'orchestration_start') {
        managerName = aiName || managerName
        const workerCount = data.workers?.length ?? 3
        intro = `요청을 분석했습니다. ${workerCount}개의 에이전트가 협업을 시작합니다.`

        // Register workers in order from orchestration_start
        if (Array.isArray(data.workers)) {
          data.workers.forEach(name => {
            if (!agentOrder.includes(name)) {
              agentOrder.push(name)
              agentText[name] = ''
            }
          })
        }

      } else if (type === 'subtask_assign') {
        const worker = data.to
        if (worker && !agentOrder.includes(worker)) {
          agentOrder.push(worker)
          agentText[worker] = ''
        }
        // Prepend task description as first log line
        if (worker && data.task) {
          agentText[worker] = `// 작업 수신: ${data.task}\n` + (agentText[worker] || '')
        }

      } else if (type === 'log') {
        const name = aiName
        if (!name || name === managerName) return   // skip manager's own synthesis logs
        if (!agentOrder.includes(name)) {
          agentOrder.push(name)
          agentText[name] = ''
        }
        agentText[name] = (agentText[name] || '') + (data.message || '')

      } else if (type === 'orchestration_done') {
        finish()
      }
    }

    ws.onerror = () => {
      finished = true
      clearTimeout(timeout)
      resolve(buildMockPlan(userText))
    }

    ws.onclose = () => {
      finish()
    }
  })
}
