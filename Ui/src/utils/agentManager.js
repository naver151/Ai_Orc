
const BACKEND = 'http://localhost:8000'

function _getUid() {
  try { return JSON.parse(localStorage.getItem('aiorc_user'))?.uid ?? null } catch { return null }
}

// ── 백엔드 AI 채팅 스트리밍 ─────────────────────────────────
// messages: ChatPage의 messages 배열 (role: 'user'|'ai', text: string)
// onChunk: 글자 조각이 올 때마다 호출되는 콜백
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
    body: JSON.stringify({ message: userText, history, user_uid: _getUid() }),
  })

  if (!res.ok) throw new Error(`서버 응답 오류: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

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
        if (data.type === 'text')       { onChunk(data.chunk) }
        else if (data.type === 'error') { const e = new Error(data.message); e.isServerError = true; throw e }
      } catch (e) {
        // 서버가 보낸 error 이벤트는 다시 던지고, JSON 파싱 실패는 무시
        if (e.isServerError) throw e
      }
    }
  }
}

export const AI_ROLE_MAP = {
  analyst:    'claude',
  collector:  'gemini',
  executor:   'gpt',
  reviewer:   'claude',
  writer:     'gpt',
  // 창업가 특화
  strategist: 'claude',
  marketer:   'gpt',
  developer:  'gpt',
  researcher: 'gemini',
  copywriter: 'claude',
}

export const AI_LABELS = {
  claude:  { label: 'Claude',  color: '#7c6dfa' },
  gpt:     { label: 'GPT-4o',  color: '#4caf82' },
  gemini:  { label: 'Gemini',  color: '#f5a623' },
}

// ── 창업가 역할 메타 ─────────────────────────────────────────
export const FOUNDER_ROLES = {
  strategist: { label: '전략가',    desc: '비즈니스 전략·포지셔닝·방향 설계', icon: '🎯' },
  marketer:   { label: '마케터',    desc: '마케팅 채널·캠페인·고객 메시지',   icon: '📣' },
  developer:  { label: '개발자',    desc: '기능 설계·코드 구현·기술 스택',    icon: '💻' },
  researcher: { label: '리서처',    desc: '시장조사·경쟁사 분석·트렌드',      icon: '🔍' },
  copywriter: { label: '카피라이터', desc: '랜딩페이지·투자 피칭·세일즈 문서', icon: '✍️' },
}

// ── 에이전트 핸드오프 메시지 ─────────────────────────────────
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

// ── 1인 스타트업 에이전트 템플릿 프리셋 ──────────────────────
export const AGENT_TEMPLATES = [
  // ── 기획·검증 ──────────────────────────────────────────────
  {
    id:    'startup_validate',
    label: '🚀 사업 검증 팀',
    desc:  '시장성·경쟁사·초기 고객을 30분 안에 동시 분석',
    agents: [
      {
        roleKey: 'analyst',
        name: '시장 분석가',
        task: `아래 순서로 시장을 분석하고 마크다운 표와 수치로 정리하세요.
1. web_search로 "[분야] 시장규모 2024 한국" 및 "[industry] market size 2024" 검색
2. TAM(전체 시장) / SAM(유효 시장) / SOM(획득 가능 시장)을 수치로 추정
3. 연평균 성장률(CAGR)과 5년 후 예상 규모
4. 시장을 키우는 핵심 드라이버 3가지
5. 리스크 요인 2가지
출처 URL을 반드시 포함하세요.`,
      },
      {
        roleKey: 'collector',
        name: '경쟁사 조사관',
        task: `웹 검색으로 경쟁사 3~5개를 찾아 비교표를 작성하세요.
1. web_search로 "[서비스명] 경쟁사", "[category] startup Korea" 등 검색
2. 아래 형식으로 비교표 작성:
   | 경쟁사 | 주요 기능 | 가격 | 타겟 고객 | 강점 | 약점 |
3. 각 경쟁사 홈페이지·앱스토어 리뷰·기사를 검색해 실제 사용자 반응 확인
4. "우리가 비집고 들어갈 수 있는 틈새" 2가지를 명시하세요.`,
      },
      {
        roleKey: 'reviewer',
        name: '고객 리서처',
        task: `초기 타겟 고객 페르소나를 구체적으로 정의하세요.
1. 1차 타겟 고객 프로파일 (나이·직업·소득·라이프스타일)
2. web_search로 이 고객군의 실제 불만·요구사항을 커뮤니티/블로그/SNS에서 검색
3. 핵심 페인포인트 TOP 3 (현재 어떻게 해결하고 있는지 포함)
4. 기꺼이 돈을 낼 이유(WTP)와 적정 가격대 추정
5. 첫 10명 고객을 어디서 찾을 수 있는지 구체적 채널 제시`,
      },
    ],
  },
  {
    id:    'pitch_prep',
    label: '📊 투자자 피치 팀',
    desc:  '시장 데이터·경쟁 우위·재무 모델을 동시에 준비',
    agents: [
      {
        roleKey: 'analyst',
        name: '시장 데이터 수집가',
        task: `투자자가 납득할 시장 데이터를 수집하세요.
1. web_search로 공신력 있는 시장 조사 보고서 검색 (Statista, McKinsey, 한국 관련 기관 등)
2. 투자자 피치에 쓸 수 있는 핵심 통계 5개를 수치·출처와 함께 정리
3. 국내외 유사 서비스의 투자·성장 사례 2~3개 조사
4. "왜 지금이 적기인가" 근거 (규제 변화, 기술 성숙도, 행동 변화 등)`,
      },
      {
        roleKey: 'collector',
        name: '경쟁 우위 분석가',
        task: `"왜 우리가 이길 수 있는가"를 투자자 언어로 작성하세요.
1. 핵심 차별점 3가지를 경쟁사 대비 구체적으로 설명
2. 지속 가능한 경쟁 우위(Moat) — 기술·네트워크·데이터·브랜드 중 해당 항목
3. 팀의 강점 (창업자가 이 문제를 푸는 데 왜 최적인지)
4. 위험 요소와 대응 전략 (투자자가 반드시 물어볼 것들)`,
      },
      {
        roleKey: 'writer',
        name: '재무 모델 작성자',
        task: `초기 스타트업 재무 모델을 표로 작성하세요.
1. 수익 구조 설명 (구독/건당결제/광고 등 모델 근거)
2. 보수·기본·낙관 3가지 시나리오별 1~3년차 예상 매출 (표 형식)
3. 주요 비용 항목 (인건비·서버비·마케팅비 등) 월별 추정
4. 손익분기점(BEP) 도달 예상 시점
5. 조달 희망 금액과 사용처 계획 (6개월/12개월 runway)`,
      },
    ],
  },

  // ── 운영·모니터링 ────────────────────────────────────────────
  {
    id:    'weekly_brief',
    label: '📰 주간 브리핑 팀',
    desc:  '업계 뉴스·경쟁사 동향·인사이트를 매주 자동 정리',
    agents: [
      {
        roleKey: 'collector',
        name: '업계 뉴스 수집가',
        task: `지난 7일간 관련 업계 주요 뉴스를 수집하세요.
1. web_search로 "[업계 키워드] 뉴스 2024", "[industry] news this week" 검색
2. 중요도 순으로 뉴스 5~7건을 정리 (제목·요약·출처·날짜)
3. 각 뉴스가 우리 사업에 미치는 영향을 한 줄로 평가
4. 이번 주 핵심 트렌드 키워드 3개 선정`,
      },
      {
        roleKey: 'analyst',
        name: '경쟁사 모니터',
        task: `주요 경쟁사의 최근 변화를 조사하세요.
1. web_search로 경쟁사별 최근 업데이트 검색 (신기능·가격 변경·채용 공고·언론 보도)
2. 경쟁사 SNS·블로그·앱스토어 리뷰 변화 확인
3. 변화 내용 요약과 "우리가 대응해야 하는가" 판단
4. 경쟁사 중 가장 주목할 움직임 1개를 강조`,
      },
      {
        roleKey: 'writer',
        name: '인사이트 도출가',
        task: `수집된 정보를 창업가 관점의 실행 가능한 인사이트로 정리하세요.
1. 이번 주 핵심 인사이트 3가지 (각각 근거·시사점·액션 포함)
2. 우선 대응이 필요한 사항과 그 이유
3. 다음 주 집중해야 할 과제 TOP 3
4. 월별 트렌드 변화 메모 (이번 주 특이점)`,
      },
    ],
  },
  {
    id:    'customer_research',
    label: '👥 고객 리서치 팀',
    desc:  '인터뷰·설문 분석 → 제품 방향과 MVP 기능 도출',
    agents: [
      {
        roleKey: 'analyst',
        name: '인터뷰 분석가',
        task: `제공된 고객 인터뷰/설문 데이터를 분석하세요.
1. 반복 언급된 키워드·문구를 빈도 기준으로 정리
2. 고객의 현재 해결 방법과 그 불만족 포인트
3. "있으면 좋겠다"와 "반드시 있어야 한다"를 구분
4. 고객 여정(Customer Journey)에서 가장 큰 마찰 지점
5. 세그먼트별 니즈 차이가 있다면 구분해 정리`,
      },
      {
        roleKey: 'collector',
        name: '시장 검증 조사관',
        task: `고객 니즈를 시장 데이터로 뒷받침하세요.
1. web_search로 유사한 니즈를 다루는 해외 사례·서비스 조사
2. 이 니즈가 얼마나 보편적인지 커뮤니티/포럼/SNS에서 검색
3. 유사 서비스의 실제 사용자 리뷰에서 가장 많이 나오는 불만 파악
4. "이 문제를 해결한 서비스가 얼마나 성장했는가" 사례 제시`,
      },
      {
        roleKey: 'writer',
        name: 'MVP 기획 작성자',
        task: `분석 결과를 바탕으로 MVP 기획안을 작성하세요.
1. 핵심 가설 3가지 (이 가설이 맞다면 제품이 성공한다)
2. MVP에 반드시 있어야 할 기능 TOP 5 (우선순위·이유 포함)
3. MVP에서 제외할 기능과 제외 이유
4. 2주 안에 검증할 수 있는 최소 실험 방법 제안
5. 성공 기준(Success Metric) — 무엇을 측정해야 하는가`,
      },
    ],
  },

  // ── 마케팅·영업 ──────────────────────────────────────────────
  {
    id:    'cold_email',
    label: '📧 영업·콘텐츠 팀',
    desc:  '콜드 메일·SNS 콘텐츠·블로그 초안을 동시에 작성',
    agents: [
      {
        roleKey: 'analyst',
        name: '잠재 고객 리서처',
        task: `타겟 잠재 고객을 조사하세요.
1. web_search로 타겟 기업·개인의 정보·채널 검색
2. 잠재 고객이 현재 겪는 문제를 SNS·커뮤니티·뉴스에서 확인
3. 접근 가능한 잠재 고객 채널 5개 (LinkedIn, 커뮤니티, 이메일 등)
4. 각 채널별 접근 전략 한 줄씩`,
      },
      {
        roleKey: 'writer',
        name: '콜드 메일 작성자',
        task: `B2B 콜드 메일 3가지 버전을 작성하세요.
1. [짧은 버전] 3문장 이내 — 모바일에서 읽기 좋은 초간단 버전
2. [일반 버전] 150자 이내 — 문제 공감 → 솔루션 한 줄 → CTA
3. [긴 버전] 300자 이내 — 사례·데이터 포함 설득형
각 버전마다 제목(Subject line) 3개씩 A/B 테스트용으로 작성하세요.`,
      },
      {
        roleKey: 'collector',
        name: 'SNS 콘텐츠 기획자',
        task: `마케팅 콘텐츠 초안을 작성하세요.
1. 타겟 고객의 페인포인트를 다루는 블로그 제목 5개 (SEO 고려)
2. 링크드인용 게시물 초안 2개 (인사이트 공유 형식)
3. 인스타그램/스레드용 짧은 콘텐츠 3개 (후킹 문장 + 본문)
4. 커뮤니티 (디스코드·오픈카톡·네이버카페) 참여용 질문글 2개`,
      },
    ],
  },

  // ── 행정·법무 ────────────────────────────────────────────────
  {
    id:    'legal_docs',
    label: '📋 법무 문서 팀',
    desc:  '이용약관·개인정보처리방침·사업자 등록 안내 초안 작성',
    agents: [
      {
        roleKey: 'writer',
        name: '이용약관 작성자',
        task: `서비스 이용약관 초안을 작성하세요.
1. web_search로 유사 서비스의 이용약관 구조 참고
2. 필수 항목: 서비스 정의, 회원 가입·탈퇴, 금지 행위, 면책 조항, 분쟁 해결
3. 한국 전자상거래법·정보통신망법 기준 준수 문구 포함
4. 마크다운 형식으로 섹션 구분하여 작성
⚠️ 법적 효력은 변호사 검토가 필요하며 본 초안은 참고용입니다.`,
      },
      {
        roleKey: 'analyst',
        name: '개인정보처리방침 작성자',
        task: `개인정보처리방침 초안을 작성하세요.
1. web_search로 한국 개인정보보호법(PIPA) 필수 기재 항목 확인
2. 수집 항목·목적·보유 기간·제3자 제공·파기 방법 등 필수 항목 작성
3. 개인정보 보호책임자 정보 플레이스홀더 포함
4. 이용자 권리(열람·수정·삭제·이의제기) 안내
5. 마크다운 형식으로 작성
⚠️ 법적 효력은 전문가 검토 필요.`,
      },
      {
        roleKey: 'collector',
        name: '창업 행정 가이드',
        task: `1인 창업 초기 행정 체크리스트를 작성하세요.
1. web_search로 2024년 기준 사업자 등록 절차 검색
2. 업종별 필요 신고 (통신판매업, 전자금융업 등) 확인
3. 정부24 기준 필요 서류 목록
4. 초기 창업가에게 유리한 세금 혜택·공제 항목 조사
5. 무료 법률 상담 가능한 기관 안내 (법률구조공단 등)`,
      },
    ],
  },

  // ── 자금 조달 ────────────────────────────────────────────────
  {
    id:    'gov_funding',
    label: '🏛️ 정부 지원사업 팀',
    desc:  '예비창업패키지·초기창업패키지 지원서 초안 작성',
    agents: [
      {
        roleKey: 'analyst',
        name: '지원사업 리서처',
        task: `현재 신청 가능한 창업 지원사업을 조사하세요.
1. web_search로 "2024 2025 창업 지원사업 모집" 검색
2. 예비창업패키지·초기창업패키지·TIPS·지역 지원사업 현황 정리
3. 각 사업별: 지원 금액, 지원 자격, 마감일, 선발 기준
4. 우리 서비스에 가장 적합한 지원사업 TOP 3 추천 (이유 포함)`,
      },
      {
        roleKey: 'writer',
        name: '사업계획서 작성자',
        task: `정부 지원사업 사업계획서 핵심 섹션을 작성하세요.
1. 문제 정의: 현재 시장에서 어떤 문제가 있는가 (데이터·사례 포함)
2. 솔루션: 우리 서비스가 어떻게 해결하는가 (기존 방식 대비 차별점)
3. 시장성: 목표 시장 규모와 성장 가능성
4. 팀 역량: 왜 이 팀이 이 문제를 풀 수 있는가
5. 사업화 전략: 어떻게 수익을 낼 것인가
각 섹션은 400~600자로 작성하세요.`,
      },
      {
        roleKey: 'reviewer',
        name: '지원서 검토자',
        task: `사업계획서가 심사위원을 설득할 수 있는지 검토하세요.
1. web_search로 예비창업패키지 심사 기준·평가 항목 검색
2. 심사위원이 자주 지적하는 약점 유형 조사
3. 작성된 계획서에서 보완이 필요한 부분 지적
4. 강화해야 할 근거나 추가할 내용 제안
5. 경쟁 지원자 대비 차별화 포인트 제안`,
      },
    ],
  },

  // ── 전략 ────────────────────────────────────────────────────
  {
    id:    'biz_strategy',
    label: '🎯 비즈니스 전략 팀',
    desc:  '현재 방향이 맞는지 지표 분석 + 피벗 여부 검토',
    agents: [
      {
        roleKey: 'analyst',
        name: '지표 분석가',
        task: `비즈니스 핵심 지표를 분석하세요. (제공된 데이터가 있으면 그것을 기준으로)
1. 현재 주요 지표 현황 정리 (MAU, 전환율, 이탈률, LTV, CAC 등)
2. web_search로 동종업계 벤치마크 지표 조사 (업계 평균 이탈률, 전환율 등)
3. 우리 지표가 업계 대비 어느 수준인지 평가
4. 가장 시급하게 개선해야 할 지표 2가지와 이유`,
      },
      {
        roleKey: 'collector',
        name: '시장 방향 조사관',
        task: `현재 사업 방향의 시장 적합성을 검토하세요.
1. web_search로 유사 서비스의 최근 성공·실패 사례 조사
2. 목표 고객군의 행동 변화나 새로운 니즈가 생겼는지 검색
3. 새로운 경쟁자나 대체재가 등장했는지 확인
4. 현재 방향을 위협하는 외부 변화 3가지 정리`,
      },
      {
        roleKey: 'writer',
        name: '전략 시나리오 기획자',
        task: `현재 상황에서의 전략 옵션을 작성하세요.
1. 현재 방향 유지 시 예상 시나리오 (6개월 후)
2. 피벗(Pivot) 검토 — 어떤 방향으로 바꿀 수 있는가 (2~3가지 옵션)
3. 각 옵션의 장단점과 필요 리소스
4. 의사결정 기준: "이 조건이 충족되면 피벗, 아니면 유지"
5. 다음 30일 안에 실행할 우선순위 액션 3개`,
      },
    ],
  },
]

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

// ── 관리자 AI에게 업무 분배 계획 요청 ───────────────────────
export async function analyzeRequest(userText) {
  try {
    const res = await fetch(`${BACKEND}/manager/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request: userText, user_uid: _getUid() }),
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

// ── WebSocket 에이전트 등록 ──────────────────────────────────
// ws        : 이미 열려 있는 WebSocket 인스턴스
// aiName    : 에이전트 이름 (고유)
// provider  : 'github' | 'claude' | 'gemini' | 'gpt'
// isManager : 관리자 여부
// role      : 역할 설명 문자열
export function spawnAgent(ws, { aiName, provider = 'github', isManager = false, role = '' } = {}) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return
  ws.send(JSON.stringify({ action: 'spawn', aiName, provider, isManager, role }))
}
