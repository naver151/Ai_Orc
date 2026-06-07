
const BACKEND = 'http://localhost:8000'

// ── 백엔드 AI 채팅 스트리밍 ─────────────────────────────────
export async function sendChatMessage(userText, messages, onChunk) {
  const history = messages
    .filter(m => m.role === 'user' || m.role === 'ai')
    .slice(-12)
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
    buf = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'text')  { onChunk(data.chunk) }
        else if (data.type === 'done')  { isProjectRequest = data.isProjectRequest }
        else if (data.type === 'error') { const e = new Error(data.message); e.isServerError = true; throw e }
      } catch (e) {
        if (e.isServerError) throw e
      }
    }
  }

  return { isProjectRequest }
}

// ── 역할 → AI 모델 매핑 ────────────────────────────────────
const AI_ROLE_MAP = {
  // 기존
  analyst:   'claude',
  collector: 'gemini',
  executor:  'gpt',
  reviewer:  'claude',
  writer:    'gpt',
  // 창업가 특화
  strategist:  'claude',   // 전략·포지셔닝
  marketer:    'gpt',      // 마케팅 카피·채널
  developer:   'gpt',      // 코드·기술 구현
  researcher:  'gemini',   // 시장조사·경쟁사
  copywriter:  'claude',   // 세일즈 카피·스토리텔링
}

export const AI_LABELS = {
  claude: { label: 'Claude',  color: '#7c6dfa' },
  gpt:    { label: 'GPT-4o',  color: '#4caf82' },
  gemini: { label: 'Gemini',  color: '#f5a623' },
}

// ── 창업가 역할 메타 ──────────────────────────────────────
export const FOUNDER_ROLES = {
  strategist: {
    label: '전략가',
    desc:  '비즈니스 전략·포지셔닝·방향 설계',
    icon:  '🎯',
  },
  marketer: {
    label: '마케터',
    desc:  '마케팅 채널·캠페인·고객 메시지',
    icon:  '📣',
  },
  developer: {
    label: '개발자',
    desc:  '기능 설계·코드 구현·기술 스택',
    icon:  '💻',
  },
  researcher: {
    label: '리서처',
    desc:  '시장조사·경쟁사 분석·트렌드',
    icon:  '🔍',
  },
  copywriter: {
    label: '카피라이터',
    desc:  '랜딩페이지·투자 피칭·세일즈 문서',
    icon:  '✍️',
  },
}

// ── 창업가 퀵 템플릿 ─────────────────────────────────────
export const QUICK_TEMPLATES = [
  {
    label: '랜딩페이지 만들기',
    icon: '🚀',
    text: '우리 서비스의 랜딩페이지 카피와 구조를 만들어줘',
    roles: ['strategist', 'copywriter', 'developer'],
  },
  {
    label: '경쟁사 분석',
    icon: '🔍',
    text: '우리 시장의 경쟁사를 분석하고 차별화 전략을 세워줘',
    roles: ['researcher', 'strategist'],
  },
  {
    label: 'MVP 기능 설계',
    icon: '💻',
    text: '우리 서비스의 MVP 핵심 기능을 설계하고 개발 계획을 세워줘',
    roles: ['strategist', 'developer'],
  },
  {
    label: '투자자 피칭덱',
    icon: '📊',
    text: '투자자에게 보여줄 피칭덱 스크립트와 핵심 슬라이드 내용을 작성해줘',
    roles: ['strategist', 'researcher', 'copywriter'],
  },
  {
    label: '마케팅 전략',
    icon: '📣',
    text: '초기 스타트업을 위한 저비용 마케팅 전략과 채널별 실행 계획을 세워줘',
    roles: ['marketer', 'researcher', 'copywriter'],
  },
  {
    label: '블로그 콘텐츠',
    icon: '✍️',
    text: '우리 서비스와 관련된 SEO 최적화 블로그 포스트를 작성해줘',
    roles: ['researcher', 'copywriter'],
  },
]

// ── 핸드오프 메시지 ─────────────────────────────────────────
const HANDOFF_MSGS = {
  analyst:    '분석 결과 전달 → 다음 단계로 인계',
  collector:  '수집 데이터 전달 → 처리 단계로 인계',
  executor:   '실행 결과 전달 → 검토 단계로 인계',
  reviewer:   '검토 완료본 전달 → 최종 작성 단계로 인계',
  writer:     null,
  strategist: '전략 방향 전달 → 실행 단계로 인계',
  marketer:   '마케팅 플랜 전달 → 다음 단계로 인계',
  developer:  '기술 구현안 전달 → 검토 단계로 인계',
  researcher: '리서치 결과 전달 → 전략 수립으로 인계',
  copywriter: null,
}

// ── 프로젝트 의도 감지 ────────────────────────────────────────
const PROJECT_PATTERNS = [
  /만들어|개발해|구현해|작성해|설계해|제작해/,
  /분석해|조사해|정리해|자동화|처리해/,
  /만들어줘|해줘|해주세요|만들어주세요|부탁해/,
  /시스템|프로젝트|서비스|앱|봇|플랫폼/,
  /리포트|보고서|코드|스크립트|데이터/,
  /전략|피칭|랜딩|마케팅|투자|창업|스타트업/,
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
      'AI.Orc는 1인 창업가를 위한 AI 팀입니다. 전략가, 마케터, 개발자, 리서처, 카피라이터 에이전트가 함께 작업을 처리해드립니다.',
    ],
  },
  {
    pattern: /어떻게|사용법|어떻게 쓰|어떻게 사용/,
    responses: [
      '원하시는 작업을 자유롭게 말씀해 주시면 됩니다.\n예) "랜딩페이지 만들어줘" 또는 "경쟁사 분석하고 전략 세워줘"',
    ],
  },
  {
    pattern: /에이전트|AI|기능|할 수 있/,
    responses: [
      '전략가, 마케터, 개발자, 리서처, 카피라이터 — 5종의 창업가 특화 에이전트가 병렬로 협력합니다. 지원 모델: Claude, GPT-4o, Gemini',
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
      { roleKey: 'strategist', name: '전략가 AI',    task: '핵심 방향과 포지셔닝을 설계합니다.' },
      { roleKey: 'researcher', name: '리서처 AI',    task: '시장과 경쟁 환경을 조사합니다.' },
      { roleKey: 'copywriter', name: '카피라이터 AI', task: '최종 결과물을 설득력 있게 작성합니다.' },
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
