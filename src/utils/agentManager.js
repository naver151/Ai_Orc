import { callClaude } from './providers/claudeProvider'
import { callGPT }    from './providers/gptProvider'
import { callGemini } from './providers/geminiProvider'

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

const DUMMY_DATA = {
  analyst: {
    logs: [
      '// 사용자 요청 수신',
      '▸ 의도 분류: 시장 분석 요청',
      '▸ 핵심 키워드 추출 완료',
      '▸ 작업 정의: 경쟁사 Q3 점유율 비교 분석',
      '// 다음 에이전트로 작업 정의서 전달',
    ],
    handoffMsg: '작업 정의서 전달 → 관련 데이터 수집 요청',
  },
  collector: {
    logs: [
      '// 작업 정의서 수신 완료',
      '▸ 소스 연결: 시장 데이터 DB, 공시 자료',
      '▸ Q3 당사 점유율: 23.4% (전분기 +2.1%)',
      '▸ Q3 경쟁사A 점유율: 31.2% (전분기 -0.8%)',
      '▸ 수집 완료: 12건 문서, 4.2MB',
      '// 수집 데이터 패키징 후 전달',
    ],
    handoffMsg: '수집 데이터 패키지 전달 → 분석 및 인사이트 도출 요청',
  },
  executor: {
    logs: [
      '// 데이터 패키지 수신, 분석 시작',
      '▸ 시장 트렌드: 모바일 채널 +34% 급성장',
      '▸ 핵심 기회: 동남아 채널 미진입 공백 존재',
      '▸ 핵심 리스크: 원가 상승 압력 Q4 지속 예상',
      '// 분석 결과 보고서 초안 생성',
    ],
    handoffMsg: '분석 보고서 초안 전달 → 정확성 검증 요청',
  },
  reviewer: {
    logs: [
      '// 보고서 초안 검증 시작',
      '▸ 데이터 출처 검증: 12/12 ✓',
      '▸ 수치 일관성: 이상 없음 ✓',
      '▸ 품질 승인 — 최종 작성 단계 진행',
      '// 검증 완료본 전달',
    ],
    handoffMsg: '검증 완료본 전달 → 최종 사용자 응답 생성 요청',
  },
  writer: {
    logs: [
      '// 최종 응답 생성 시작',
      '▸ Q3 시장 점유율 요약 작성 완료',
      '▸ 경쟁사 비교표 생성 완료',
      '▸ 기회/리스크 매트릭스 작성 완료',
      '▸ 최종 보고서 완성 (1,240 tokens)',
    ],
    handoffMsg: null,
  },
}

function buildMockPlan(text) {
  const len = text.length
  let count = 2
  if (len > 30  || /그리고|또한|추가로/.test(text)) count = 3
  if (len > 60  || /분석|리포트|보고서/.test(text)) count = 4
  if (len > 100 || /전체|종합|시스템|전략/.test(text)) count = 5

  const pool = [
    { roleKey: 'analyst',   name: '요청 분석 AI',  task: '사용자 요청의 핵심 의도를 파악하고 세부 작업을 정의합니다.' },
    { roleKey: 'collector', name: '데이터 수집 AI', task: '요청 처리에 필요한 데이터와 참고 자료를 수집합니다.' },
    { roleKey: 'executor',  name: '처리 실행 AI',   task: '수집된 정보를 바탕으로 실제 작업을 수행합니다.' },
    { roleKey: 'reviewer',  name: '품질 검토 AI',   task: '처리 결과의 정확성과 품질을 검토합니다.' },
    { roleKey: 'writer',    name: '응답 생성 AI',   task: '검증된 결과를 사용자에게 최적화된 형태로 정리합니다.' },
  ]

  return {
    intro: `요청을 분석한 결과 ${count}개의 에이전트가 필요합니다. 지금 바로 배치하겠습니다.`,
    agents: pool.slice(0, count),
    summary: '모든 에이전트가 협업을 완료했습니다. 추가로 필요한 사항이 있으시면 말씀해 주세요.',
  }
}

export async function analyzeRequest(userText) {
  // TODO: 파트너가 아래 주석 해제 후 API 연동
  /*
  const system = `사용자 요청을 분석해 필요한 에이전트 수(1~5개)를 결정하고
아래 JSON 형식으로만 응답하세요:
{
  "intro": "...",
  "agents": [{ "roleKey": "analyst", "name": "...", "task": "..." }],
  "summary": "..."
}`
  const raw = await callClaude(system, userText)
  const plan = JSON.parse(raw)
  */

  await new Promise(r => setTimeout(r, 200))
  const plan = buildMockPlan(userText)

  return {
    intro: plan.intro,
    agents: plan.agents.map((a, i, arr) => ({
      ...a,
      aiType:     AI_ROLE_MAP[a.roleKey] ?? 'claude',
      color:      AI_LABELS[AI_ROLE_MAP[a.roleKey] ?? 'claude'].color,
      logs:       DUMMY_DATA[a.roleKey]?.logs ?? [],
      handoffMsg: i < arr.length - 1 ? DUMMY_DATA[a.roleKey]?.handoffMsg ?? null : null,
    })),
    summary: plan.summary,
  }
}