"""
LangGraph 멀티에이전트 오케스트레이션 그래프 (Phase 2)

변경 사항:
  - RunnableConfig로 콜백 전달 (ainvoke 시 더 안정적)
  - WSStreamHandler에 문자 수 기반 진행률 추적 추가
  - 각 노드 진입 시 pause/kill 체크 (agent_manager_ref 사용)
  - plan_node에서 worker 간 공유 컨텍스트 GraphState에 기록

노드 구성:
  plan_node      — 관리자가 조용히 계획 수립
  dispatch_node  — Send API로 서브태스크 병렬 분산
  worker_node    — 개별 워커 스트리밍 실행
  synthesize_node — 관리자 결과 종합
"""

from __future__ import annotations
import json
import re
import asyncio
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from app.ai.graph_state import GraphState, SubTask
from app.ai.lc_providers import get_lc_model, WSStreamHandler
from app.ai.lc_memory import save_agent_memory, build_rag_context

_ORCHESTRATE_RE = re.compile(r"<ORCHESTRATE>(.*?)</ORCHESTRATE>", re.DOTALL)

# ── 관리자 시스템 프롬프트 ────────────────────────────────────────────────────

_MANAGER_SYSTEM = (
    "당신은 1인 창업가를 지원하는 AI 팀의 총괄 관리자입니다.\n"
    "사용자의 요청을 분석하고, 팀원들에게 작업을 병렬 분배하여 최고의 결과를 만들어냅니다.\n\n"

    "■ 현재 팀 구성\n"
    "{worker_list}\n\n"

    "■ 작업 분배 판단 기준\n"
    "분배 필요: 서로 독립적으로 병렬 처리 가능한 서브태스크 2개 이상\n"
    "직접 답변: 단순 질문, 짧은 설명, 팀원이 1명뿐인 경우\n\n"

    "■ 출력 형식 (분배 시 이 형식만 사용)\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "한 줄 계획 요약", "subtasks": ['
    '{{"worker_index": 1, "task": "팀원1 작업"}}, '
    '{{"worker_index": 2, "task": "팀원2 작업"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "■ 창업가 특화 예시\n\n"

    "[ 랜딩페이지 ] 사용자: 랜딩페이지 카피와 구조 만들어줘 / 팀원: 3명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "포지셔닝·카피·구조 병렬 작업", "subtasks": ['
    '{{"worker_index": 1, "task": "서비스 포지셔닝 분석: 핵심 가치제안, 타겟 고객, 차별화 포인트 정의"}},'
    '{{"worker_index": 2, "task": "랜딩페이지 섹션별 카피 작성: 헤드라인, 서브카피, CTA, 사회적 증거 문구"}},'
    '{{"worker_index": 3, "task": "랜딩페이지 HTML/CSS 구조 구현: 히어로, 기능소개, 후기, 프라이싱 섹션"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 경쟁사 분석 ] 사용자: 경쟁사 분석하고 차별화 전략 세워줘 / 팀원: 2명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "리서치·전략 병렬 분리", "subtasks": ['
    '{{"worker_index": 1, "task": "경쟁사 3~5곳 분석: 제품 기능, 가격, 타겟, 강약점, 마케팅 채널 비교"}},'
    '{{"worker_index": 2, "task": "차별화 전략 수립: 포지셔닝 갭, 고객 페인포인트 기반 우리만의 강점 도출"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 마케팅 전략 ] 사용자: 저비용 마케팅 전략 세워줘 / 팀원: 3명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "채널·콘텐츠·실행계획 병렬 수립", "subtasks": ['
    '{{"worker_index": 1, "task": "마케팅 채널 분석: SNS, 콘텐츠 마케팅, 커뮤니티, SEO 채널별 효과·비용 비교"}},'
    '{{"worker_index": 2, "task": "콘텐츠 전략: 타겟 고객 페르소나 기반 콘텐츠 주제, 포맷, 게시 빈도 계획"}},'
    '{{"worker_index": 3, "task": "90일 실행 로드맵: 주차별 액션아이템, KPI, 예산 배분 계획"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 투자 피칭 ] 사용자: 투자자 피칭덱 내용 작성해줘 / 팀원: 3명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "시장·사업모델·스토리 병렬 작성", "subtasks": ['
    '{{"worker_index": 1, "task": "시장 분석 슬라이드: TAM/SAM/SOM 규모, 성장률, 시장 진입 타이밍 근거"}},'
    '{{"worker_index": 2, "task": "사업모델 슬라이드: 수익 구조, 유닛 이코노믹스, 확장성 논리"}},'
    '{{"worker_index": 3, "task": "스토리텔링 스크립트: 문제-솔루션-트랙션-팀 흐름의 설득력 있는 내러티브"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 개발 ] 사용자: MVP 기능 설계해줘 / 팀원: 2명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "제품 전략·기술 구현 병렬 분리", "subtasks": ['
    '{{"worker_index": 1, "task": "MVP 범위 정의: 핵심 사용자 스토리, 기능 우선순위(MoSCoW), 성공 지표 설정"}},'
    '{{"worker_index": 2, "task": "기술 스택 및 아키텍처 설계: 개발 환경, API 구조, DB 스키마, 배포 계획"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 직접 답변 예시 ]\n"
    "사용자: 파이썬이란? → <ORCHESTRATE> 없이 바로 답변\n\n"

    "지금 요청을 분석하여 분배가 필요하면 <ORCHESTRATE> 형식으로, 아니면 직접 답변하세요."
)


# ── 개선된 WebSocket 스트리밍 핸들러 (진행률 추적 포함) ───────────────────────

class ProgressWSStreamHandler(WSStreamHandler):
    """문자 수 기반 진행률을 함께 전송하는 스트리밍 핸들러."""

    def __init__(self, websocket: Any, ai_name: str):
        super().__init__(websocket, ai_name)
        self._char_count = 0

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        if token:
            self._char_count += len(token)
            await self.ws.send_json({"type": "log", "aiName": self.ai_name, "message": token})
            # 약 2000자를 100%로 환산 (긴 응답도 부드럽게 표시)
            pct = min(int(self._char_count / 20), 99)
            await self.ws.send_json({"type": "progress", "aiName": self.ai_name, "percent": pct})


# ── 공통 유틸 ─────────────────────────────────────────────────────────────────

async def _check_control(state: GraphState, ai_name: str) -> bool:
    """pause/kill 상태 확인. kill이면 True 반환 (노드 중단 신호)."""
    am = state.get("agent_manager_ref")
    if not am:
        return False
    ctrl = am.get(ai_name)
    if not ctrl:
        return False
    if ctrl.is_killed:
        return True
    await ctrl.wait_if_paused()
    return ctrl.is_killed


def _build_messages(system: str, text: str) -> list:
    msgs = []
    if system:
        msgs.append(SystemMessage(content=system))
    msgs.append(HumanMessage(content=text))
    return msgs


def _inject_memory(ai_name: str, text: str) -> str:
    """LangChain retriever로 유사 과거 기억 검색 후 프롬프트에 주입."""
    rag = build_rag_context(ai_name, text, k=2)
    if not rag:
        return text
    return f"{rag}[현재 요청]\n{text}"


# ── 노드 구현 ────────────────────────────────────────────────────────────────

async def plan_node(state: GraphState) -> dict:
    """
    Phase 1: 관리자가 조용히 계획 수립.
    UI에 스트리밍하지 않고 ORCHESTRATE 블록 파싱.
    """
    ws      = state["websocket"]
    manager = state["manager_name"]
    workers = state["worker_names"]
    text    = state["user_prompt"]
    provider_key = state["provider_map"].get(manager, "github")

    # kill 체크
    if await _check_control(state, manager):
        return {"is_direct": True, "direct_answer": "", "plan_summary": "", "subtasks": []}

    # UI 알림
    await ws.send_json({"type": "orchestration_start", "aiName": manager, "workers": workers})
    await ws.send_json({"type": "status",       "aiName": manager, "status": "RUNNING"})
    await ws.send_json({"type": "progress",     "aiName": manager, "percent": 0})
    await ws.send_json({"type": "current_task", "aiName": manager, "task": "작업 분석 중..."})

    # 시스템 프롬프트
    worker_list = "\n".join(f"- 팀원 {i+1}: {n}" for i, n in enumerate(workers))
    system = _MANAGER_SYSTEM.format(worker_list=worker_list)

    # 메모리 주입
    enriched = _inject_memory(manager, text)

    # 조용히 호출 (스트리밍 없음)
    model = get_lc_model(provider_key, streaming=False)
    try:
        resp = await model.ainvoke(
            _build_messages(system, enriched),
            config=RunnableConfig(callbacks=[]),
        )
        plan_text = resp.content
    except asyncio.CancelledError:
        return {"is_direct": True, "direct_answer": "", "plan_summary": "", "subtasks": []}
    except Exception as e:
        await ws.send_json({"type": "log", "aiName": manager,
                            "message": f"[오류] 계획 수립 실패: {e}"})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"is_direct": True, "direct_answer": "", "plan_summary": "", "subtasks": []}

    # ORCHESTRATE 파싱
    match = _ORCHESTRATE_RE.search(plan_text)
    if not match:
        # 직접 답변
        await ws.send_json({"type": "log",          "aiName": manager, "message": plan_text.strip()})
        await ws.send_json({"type": "status",        "aiName": manager, "status": "COMPLETED"})
        await ws.send_json({"type": "progress",      "aiName": manager, "percent": 100})
        await ws.send_json({"type": "current_task",  "aiName": manager, "task": ""})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"is_direct": True, "direct_answer": plan_text.strip(),
                "plan_summary": "", "subtasks": []}

    try:
        data = json.loads(match.group(1).strip())
        subtasks_raw = data.get("subtasks", [])
        plan_summary = data.get("plan", "작업 분배 완료")
    except json.JSONDecodeError:
        await ws.send_json({"type": "log", "aiName": manager,
                            "message": "[오류] 계획 파싱 실패"})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"is_direct": True, "direct_answer": "", "plan_summary": "", "subtasks": []}

    # worker_index → 이름 (라운드로빈 폴백)
    subtasks: list[SubTask] = []
    for st in subtasks_raw:
        idx = (st.get("worker_index", 1) - 1) % len(workers)
        subtasks.append({"worker_name": workers[idx], "task": st.get("task", "")})

    # 계획 요약 + 배분 이벤트
    await ws.send_json({"type": "log", "aiName": manager,
                        "message": f"[계획 완료] {plan_summary}"})
    for st in subtasks:
        await ws.send_json({"type": "subtask_assign",
                            "from": manager, "to": st["worker_name"], "task": st["task"]})

    await ws.send_json({"type": "current_task", "aiName": manager, "task": ""})

    return {
        "is_direct":    False,
        "direct_answer": "",
        "plan_summary": plan_summary,
        "subtasks":     subtasks,
        "worker_results": {},
    }


def dispatch_node(state: GraphState) -> list[Send] | dict:
    """
    Phase 2: LangGraph Send API로 서브태스크를 병렬 워커에 분산.
    각 Send → 독립적인 worker_node 인스턴스로 병렬 실행.
    """
    if state.get("is_direct"):
        return {}

    return [
        Send("worker_node", {
            **state,
            "current_worker_name": st["worker_name"],
            "current_task_text":   st["task"],
        })
        for st in state["subtasks"]
    ]


async def worker_node(state: GraphState) -> dict:
    """
    Phase 3: 개별 워커 실행 (병렬).
    ProgressWSStreamHandler → 토큰 단위 WebSocket push + 진행률 업데이트.
    동료 워커들의 결과가 worker_results에 누적되어 있으면 컨텍스트로 주입.
    """
    ws          = state["websocket"]
    worker_name = state["current_worker_name"]
    task_text   = state["current_task_text"]
    provider_key = state["provider_map"].get(worker_name, "github")

    # kill 체크
    if await _check_control(state, worker_name):
        return {"worker_results": {worker_name: ""}}

    # 이미 완료된 동료 결과를 컨텍스트로 주입 (공유 화이트보드)
    peer_context = ""
    existing = state.get("worker_results", {})
    if existing:
        peer_context = "\n\n[동료 팀원 진행 결과 참고]\n" + "\n".join(
            f"- {name}: {result[:300]}..." if len(result) > 300 else f"- {name}: {result}"
            for name, result in existing.items()
            if result.strip()
        )

    # 메모리 주입
    enriched = _inject_memory(worker_name, task_text)
    if peer_context:
        enriched += peer_context

    # 스트리밍 핸들러 + RunnableConfig
    handler = ProgressWSStreamHandler(ws, worker_name)
    cfg = RunnableConfig(callbacks=[handler])
    model = get_lc_model(provider_key, streaming=True)

    await ws.send_json({"type": "current_task", "aiName": worker_name, "task": task_text})

    result = ""
    try:
        resp = await model.ainvoke(_build_messages("", enriched), config=cfg)
        result = resp.content
    except asyncio.CancelledError:
        result = ""
    except Exception as e:
        result = f"[오류] {e}"
        await ws.send_json({"type": "log", "aiName": worker_name, "message": result})

    # 메모리 저장
    if result:
        try:
            save_agent_memory(worker_name, task_text, result[:2000])
        except Exception:
            pass

    await ws.send_json({"type": "current_task", "aiName": worker_name, "task": ""})

    return {"worker_results": {worker_name: result}}


async def synthesize_node(state: GraphState) -> dict:
    """
    Phase 4: 관리자가 모든 워커 결과를 종합하여 최종 답변 생성.
    ProgressWSStreamHandler → 실시간 스트리밍.
    """
    ws       = state["websocket"]
    manager  = state["manager_name"]
    provider_key = state["provider_map"].get(manager, "github")

    # kill 체크
    if await _check_control(state, manager):
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"final_synthesis": ""}

    results = state.get("worker_results", {})
    valid = [
        f"### {name} 결과:\n{result}"
        for name, result in results.items()
        if result and result.strip()
    ]

    if not valid:
        await ws.send_json({"type": "log", "aiName": manager,
                            "message": "[오류] 팀원 결과가 없습니다."})
        await ws.send_json({"type": "status",   "aiName": manager, "status": "COMPLETED"})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"final_synthesis": ""}

    synthesis_prompt = (
        "팀원들의 작업이 완료되었습니다. 결과를 종합하여 사용자에게 최종 답변을 작성해주세요.\n\n"
        f"원래 요청: {state['user_prompt']}\n\n" + "\n\n".join(valid)
    )

    # 종합 단계 알림
    await ws.send_json({"type": "orchestration_synthesis", "aiName": manager})
    await ws.send_json({"type": "current_task", "aiName": manager, "task": "결과 종합 중..."})

    # 시스템 프롬프트
    worker_list = "\n".join(f"- 팀원 {i+1}: {n}" for i, n in enumerate(state["worker_names"]))
    system = _MANAGER_SYSTEM.format(worker_list=worker_list)

    # 스트리밍
    handler = ProgressWSStreamHandler(ws, manager)
    cfg = RunnableConfig(callbacks=[handler])
    model = get_lc_model(provider_key, streaming=True)

    synthesis = ""
    try:
        resp = await model.ainvoke(_build_messages(system, synthesis_prompt), config=cfg)
        synthesis = resp.content
    except asyncio.CancelledError:
        synthesis = ""
    except Exception as e:
        synthesis = f"[오류] {e}"

    # 메모리 저장
    if synthesis:
        try:
            save_agent_memory(manager, state["user_prompt"], synthesis[:2000])
        except Exception:
            pass

    await ws.send_json({"type": "current_task",      "aiName": manager, "task": ""})
    await ws.send_json({"type": "orchestration_done", "aiName": manager})

    return {"final_synthesis": synthesis}


# ── 라우팅 ────────────────────────────────────────────────────────────────────

def route_after_plan(state: GraphState) -> str:
    return END if state.get("is_direct") else "dispatch_node"


# ── 그래프 빌드 ───────────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(GraphState)

    g.add_node("plan_node",       plan_node)
    g.add_node("dispatch_node",   dispatch_node)
    g.add_node("worker_node",     worker_node)
    g.add_node("synthesize_node", synthesize_node)

    g.add_edge(START, "plan_node")
    g.add_conditional_edges(
        "plan_node",
        route_after_plan,
        {"dispatch_node": "dispatch_node", END: END},
    )
    g.add_edge("dispatch_node",   "worker_node")
    g.add_edge("worker_node",     "synthesize_node")
    g.add_edge("synthesize_node", END)

    return g.compile()


orchestration_graph = build_graph()
