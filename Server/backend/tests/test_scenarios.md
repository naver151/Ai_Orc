# AI Crew Commander — 테스트 시나리오

## 실행 방법

```bash
cd Server/backend
pip install pytest pytest-asyncio httpx
pytest tests/ -v --tb=short

# 특정 클래스만
pytest tests/test_api.py::TestPerformanceAPI -v
pytest tests/test_websocket.py::TestWebSocketProtocol -v
```

---

## 시나리오 1 — 단일 에이전트 기본 실행

**목적:** 관리자 1명만 있을 때 오케스트레이션 없이 직접 답변

**전제 조건:** 백엔드 실행 중, GPT/GitHub 토큰 설정

| 단계 | 동작 | 기대 결과 |
|---|---|---|
| 1 | 랜딩 → 시작 | UserFormPage 또는 ChatPage 이동 |
| 2 | "파이썬이란?" 입력 | 단일 에이전트 스폰 |
| 3 | WS: spawn → prompt | READY → 스트리밍 응답 |
| 4 | 작업 완료 | 결과 패널 표시 |

**확인 포인트:**
- `orchestration_start` 이벤트 없이 바로 `log` 스트리밍
- `orchestration_done` 수신 후 결과 패널 열림
- `<ORCHESTRATE>` 블록 없이 직접 답변

---

## 시나리오 2 — 멀티 에이전트 오케스트레이션

**목적:** 관리자 + 워커 2명의 병렬 실행

| 단계 | 동작 | 기대 결과 |
|---|---|---|
| 1 | 관리자 + 워커2명 등록 | 3개 에이전트 패널 생성 |
| 2 | "삼성전자 투자 분석해줘" 입력 | plan_node 실행 |
| 3 | `orchestration_start` 수신 | 진행률 바 시작 |
| 4 | `subtask_assign` × 2 수신 | 각 워커 섹션에 배정 태스크 표시 |
| 5 | 워커 병렬 스트리밍 | 두 섹션 동시 토큰 출력 |
| 6 | `review_start` 수신 | "교차 검토 중..." 표시 |
| 7 | `review_done` × 2 수신 | 점수 배지 + 피드백 박스 |
| 8 | `user_review_request` 수신 | 검증 패널 열림, 15초 카운트다운 |
| 9 | 15초 타임아웃 | 자동 승인 → 종합 단계 |
| 10 | `orchestration_synthesis` | "종합 중..." |
| 11 | `orchestration_done` | 결과 패널 표시 |

---

## 시나리오 3 — 사용자 검증 피드백 반영

**목적:** 사용자가 피드백 입력 → 재실행

| 단계 | 동작 | 기대 결과 |
|---|---|---|
| 1 | 시나리오2 7단계까지 진행 | 점수 배지 표시 |
| 2 | 검증 패널 열림 | 워커별 점수 표시 |
| 3 | ✏️ 피드백 클릭 | 피드백 입력창 열림, 타이머 중지 |
| 4 | "더 구체적인 데이터를 포함해주세요" 입력 | textarea 활성 |
| 5 | 📨 전송 | `user_review` WS 전송 |
| 6 | 점수 < 7 워커 재실행 | `🔄 사용자 피드백 반영 후 재작업 중...` 로그 |
| 7 | retry 완료 → 종합 | 개선된 결과 포함한 최종 답변 |

**확인 포인트:**
- `retry_worker_names`: 점수 < 7인 워커만 포함
- 피드백 텍스트가 재실행 프롬프트에 주입됨
- 재실행 후 성능 점수 다시 저장 (AgentPerformance)

---

## 시나리오 4 — Non-LLM 워커 실행

**목적:** 웹검색 / 크롤러 / 코드실행 워커 정상 동작

| 단계 | 동작 | 기대 결과 |
|---|---|---|
| 1 | aiType: "search" 워커 등록 | provider_key: "search" |
| 2 | "최신 AI 뉴스 검색해줘" 입력 | DuckDuckGo 검색 실행 |
| 3 | 결과 로그 | 검색 결과 텍스트 스트리밍 |
| 4 | review_node | claude/github가 Non-LLM 결과 검토 |

**Non-LLM 분류:**
```
search  → DuckDuckGo
crawler → BeautifulSoup4
runner  → subprocess (파이썬)
ocr     → EasyOCR
whisper → openai-whisper
```

---

## 시나리오 5 — 적응형 분배 동작 확인

**목적:** 데이터 누적 후 자동 분배 활성화

**전제 조건:** 동일 조합으로 5건 이상 실행 완료

| 단계 | 동작 | 기대 결과 |
|---|---|---|
| 1 | 관리자 대시보드 → AI 성능 탭 | 리더보드 표시 |
| 2 | claude: avg 8.5, github: avg 6.8 확인 | claude 1위 |
| 3 | UI 분배 모드 "🤖 자동" 선택 | `set_distribution mode=auto` |
| 4 | 코드 작성 태스크 실행 | plan_node에서 claude 워커 배정 |
| 5 | 관리자 대시보드 재확인 | 점수 1건 추가됨 |

**확인 포인트:**
- `distribution_mode = "auto"` 상태에서 실행
- `_epsilon_greedy_provider("code", [...])` 반환값이 claude
- `agent_performance` 테이블에 새 레코드 삽입됨

---

## 시나리오 6 — 실시간 개입 (Intervention)

**목적:** 실행 중 방향 전환

| 단계 | 동작 | 기대 결과 |
|---|---|---|
| 1 | 오케스트레이션 실행 중 | 개입 바 표시 |
| 2 | 대상 선택: 관리자 | 드롭다운에서 선택 |
| 3 | "방향을 바꿔서 실용적인 답변에 집중해줘" 입력 | Enter 또는 전송 |
| 4 | 기존 작업 취소 + 새 prompt 실행 | 스트림에 개입 로그 표시 |
| 5 | 새 방향으로 재시작 | 오케스트레이션 재실행 |

---

## 시나리오 7 — 관리자 대시보드

**목적:** 전체 탭 기능 확인

| 탭 | 확인 항목 |
|---|---|
| 📋 실행 로그 | 목록 조회, 상세 클릭, 평점 1~5 저장, "저장됨 ✓" 표시 |
| 📊 AI 성능 | 리더보드 바 차트, 히트맵 색상 정확성, 선 그래프 범례 |
| 🖥️ 시스템 | KPI 카드 4개, 도넛 차트, 일별 현황 바 차트 |

**데이터 없을 때 처리:**
- AI 성능 탭: "아직 성능 데이터가 없습니다" 안내 메시지
- 도넛/바 차트: "데이터 없음" 플레이스홀더

---

## 시나리오 8 — 일시정지 / 재개 / 종료

| 단계 | 동작 | 기대 결과 |
|---|---|---|
| 1 | 오케스트레이션 실행 중 | 스피너 회전 |
| 2 | ⏸ 클릭 (특정 워커) | 해당 에이전트 패널 dim 처리 |
| 3 | 백엔드 pause 상태 | LLM 토큰 생성 일시 중지 |
| 4 | ▶ 클릭 | 정상 재개 |
| 5 | ✕ 클릭 | 해당 에이전트 즉시 종료, killed 상태 |
| 6 | 나머지 에이전트는 계속 실행 | 종합 단계는 정상 진행 |

---

## 회귀 테스트 체크리스트

```
[ ] 서버 시작 시 agent_performance 테이블 자동 생성
[ ] /performance/stats 200 응답 (데이터 없어도)
[ ] /performance/trend 200 응답
[ ] /performance/summary 200 응답
[ ] WS spawn → READY 1초 이내
[ ] WS set_distribution → distribution_mode_set 수신
[ ] review_node 후 AgentPerformance 레코드 증가
[ ] 대시보드 AI성능 탭: 데이터 없으면 안내 메시지
[ ] 대시보드 AI성능 탭: 데이터 있으면 리더보드 표시
[ ] 히트맵 셀 hover시 tooltip 표시 (score/count)
[ ] 도넛 차트 hover시 tooltip 표시
[ ] 실행 로그 평점 1~5 저장 후 "저장됨 ✓" 표시
[ ] JSONL 내보내기 파일 다운로드 (rating >= 4)
```
