
const BACKEND = 'http://localhost:8000'

// ── 백엔드 AI 채팅 스트리밍 ─────────────────────────────────
// messages: ChatPage의 messages 배열 (role: 'user'|'ai', text: string)
// onChunk: 글자 조각이 올 때마다 호출되는 콜백
// returns: { isProjectRequest: boolean }
export async function sendChatMessage(userText, messages, onChunk) {
  // ChatPage의 messages → 백엔드 형식(role: user|assistant, content) 변환
  const history = messages
    .filter(m => m.role === 'user' || m.role === 'ai')
    .slice(-12)   // 최근 12개 메시지만 컨텍스트로 전송
    .map(m => ({
      role: m.role === 'ai' ? 'assistant' : 'user',
      content: m.text,
    }))

  const res = await fetch(`${BACKEND}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: userText, history }),
  })

  if (!res.ok) throw new Error(`서버 응답 오류: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let isProjectRequest = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''   // 아직 완성 안 된 줄은 버퍼에 남김

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'text')  { onChunk(data.chunk) }
        else if (data.type === 'done')  { isProjectRequest = data.isProjectRequest }
        else if (data.type === 'error') { const e = new Error(data.message); e.isServerError = true; throw e }
      } catch (e) {
        // 서버가 보낸 error 이벤트는 다시 던지고, JSON 파싱 실패는 무시
        if (e.isServerError) throw e
      }
    }
  }

  return { isProjectRequest }
}

const AI_ROLE_MAP = {
  analyst:   'claude',
  collector: 'gemini',
  executor:  'gpt',
  reviewer:  'claude',
  writer:    'gpt',
}

export const AI_LABELS = {
  claude: { label: 'Claude',  color: '#7c6dfa' },
  gpt:    { label: 'GPT-4o',  color: '#4caf82' },
  gemini: { label: 'Gemini',  color: '#f5a623' },
}

// ── 에이전트 핸드오프 메시지 ─────────────────────────────────
const HANDOFF_MSGS = {
  analyst:   '분석 결과 전달 → 다음 단계로 인계',
  collector: '수집 데이터 전달 → 처리 단계로 인계',
  executor:  '실행 결과 전달 → 검토 단계로 인계',
  reviewer:  '검토 완료본 전달 → 최종 작성 단계로 인계',
  writer:    null,
}

// ── 프로젝트 의도 감지 ────────────────────────────────────────
const PROJECT_PATTERNS = [
  /만들어|개발해|구현해|작성해|설계해|제작해/,
  /분석해|조사해|정리해|자동화|처리해/,
  /만들어줘|해줘|해주세요|만들어주세요|부탁해/,
  /시스템|프로젝트|서비스|앱|봇|플랫폼/,
  /리포트|보고서|코드|스크립트|데이터/,
]

export function detectProjectIntent(text) {
  if (text.trim().length < 6) return false
  return PROJECT_PATTERNS.some(re => re.test(text))
}

// ── 일반 대화 응답 (mock) ─────────────────────────────────────
const CHAT_RULES = [
  {
    pattern: /^(안녕|하이|hello|hi|ㅎㅇ)/i,
    responses: [
      '안녕하세요! AI.Orc 관리자 AI입니다. 어떤 것을 도와드릴까요?',
      '반갑습니다! 무엇이든 편하게 말씀해 주세요.',
    ],
  },
  {
    pattern: /뭐야|뭐예요|어떤|소개|설명|무엇/,
    responses: [
      'AI.Orc는 복잡한 작업을 여러 전문 AI 에이전트들이 분담하여 처리하는 멀티 에이전트 시스템입니다. 개발, 분석, 자동화 등 다양한 작업을 맡겨보세요!',
    ],
  },
  {
    pattern: /어떻게|사용법|어떻게 쓰|어떻게 사용/,
    responses: [
      '원하시는 작업을 자유롭게 말씀해 주시면 됩니다.\n예) "쇼핑몰 재고 관리 시스템 만들어줘" 또는 "경쟁사 시장 분석 리포트 작성해줘"',
    ],
  },
  {
    pattern: /에이전트|AI|기능|할 수 있/,
    responses: [
      '요청 분석, 데이터 수집, 실행, 검토, 최종 작성까지 — 5종의 전문 에이전트가 파이프라인으로 협력합니다. 지원 모델: Claude, GPT-4o, Gemini',
    ],
  },
  {
    pattern: /감사|고마워|고맙|감사합니다|좋아|잘했|최고/,
    responses: [
      '감사합니다! 더 도움이 필요하시면 언제든지 말씀해 주세요.',
      '천만에요! 다른 작업도 도와드릴게요.',
    ],
  },
  {
    pattern: /아니|괜찮|됐어|필요없|취소/,
    responses: [
      '알겠습니다! 다른 것이 필요하시면 편하게 말씀해 주세요.',
    ],
  },
]

export function generateChatResponse(text) {
  for (const { pattern, responses } of CHAT_RULES) {
    if (pattern.test(text)) {
      return responses[Math.floor(Math.random() * responses.length)]
    }
  }
  return '네! 구체적인 작업이 있으시면 말씀해 주세요. 에이전트들이 협력해서 처리해 드릴게요.'
}

// ── 관리자 AI에게 업무 분배 계획 요청 ───────────────────────
export async function analyzeRequest(userText) {
  try {
    const res = await fetch(`${BACKEND}/manager/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request: userText }),
    })
    if (!res.ok) throw new Error(`계획 생성 실패: ${res.status}`)
    const plan = await res.json()

    const agents = plan.agents.map((a, i, arr) => ({
      ...a,
      aiType:     AI_ROLE_MAP[a.roleKey] ?? 'claude',
      color:      AI_LABELS[AI_ROLE_MAP[a.roleKey] ?? 'claude'].color,
      handoffMsg: i < arr.length - 1 ? (HANDOFF_MSGS[a.roleKey] ?? '다음 에이전트로 전달') : null,
    }))

    return {
      intro: `${agents.length}개의 에이전트를 배치해 작업을 시작합니다.`,
      agents,
      summary: '에이전트 협업이 완료됐습니다. 추가로 필요한 사항이 있으시면 말씀해 주세요.',
    }
  } catch {
    // 백엔드 연결 실패 시 폴백 플랜
    const pool = [
      { roleKey: 'analyst',  name: '요청 분석 AI',  task: '사용자 요청의 핵심 의도를 파악하고 세부 작업을 정의합니다.' },
      { roleKey: 'executor', name: '처리 실행 AI',   task: '수집된 정보를 바탕으로 실제 작업을 수행합니다.' },
      { roleKey: 'writer',   name: '응답 생성 AI',   task: '검증된 결과를 사용자에게 최적화된 형태로 정리합니다.' },
    ]
    return {
      intro: '3개의 에이전트를 배치해 작업을 시작합니다.',
      agents: pool.map((a, i, arr) => ({
        ...a,
        aiType:     AI_ROLE_MAP[a.roleKey] ?? 'claude',
        color:      AI_LABELS[AI_ROLE_MAP[a.roleKey] ?? 'claude'].color,
        handoffMsg: i < arr.length - 1 ? (HANDOFF_MSGS[a.roleKey] ?? '다음 에이전트로 전달') : null,
      })),
      summary: '에이전트 협업이 완료됐습니다.',
    }
  }
}
