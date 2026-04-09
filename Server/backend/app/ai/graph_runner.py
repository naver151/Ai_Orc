"""
LangGraph 멀티에이전트 오케스트레이션 그래프

노드 구성:
  plan_node     — 관리자가 조용히 계획 수립 (UI 스트리밍 없음)
  dispatch_node — 서브태스크를 워커별로 Send API로 분산
  worker_node   — 개별 워커가 병렬 실행 (UI에 실시간 스트리밍)
  synthesize_node — 관리자가 모든 결과를 종합 (UI 스트리밍)

흐름:
  START → plan_node → [is_direct?] → END (직접 답변)
                                   → dispatch_node → worker_node(×N, 병렬)
                                                   → synthesize_node → END
"""

from __future__ import annotations
import json
import re
import asyncio
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from app.ai.graph_state import GraphState, SubTask
from app.ai.lc_providers import get_lc_model, WSStreamHandler
from app.memory import save_memory_for, search_memory_for

_ORCHESTRATE_RE = re.compile(r"<ORCHESTRATE>(.*?)</ORCHESTRATE>", re.DOTALL)

# ── 관리자 시스템 프롬프트 ────────────────────────────────────────────────────

_MANAGER_SYSTEM = (
    "당신은 AI 팀의 총괄 관리자입니다.\n"
    "사용자의 요청을 분석하고, 팀원들에게 작업을 분배하여 최고의 결과를 만들어냅니다.\n\n"

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

    "■ 분야별 예시\n\n"
    "[ 개발 ] 사용자: REST API 서버 만들어줘 / 팀원: 2명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "API 설계·구현 병렬 분리", "subtasks": ['
    '{{"worker_index": 1, "task": "FastAPI 엔드포인트 설계: 리소스 구조, URL, 요청/응답 스키마 정의"}},'
    '{{"worker_index": 2, "task": "FastAPI 코드 구현: 라우터, 모델, CRUD, 예외 처리"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 투자 ] 사용자: 삼성전자 투자 분석 / 팀원: 3명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "재무·시장·리스크 3축 병렬 분석", "subtasks": ['
    '{{"worker_index": 1, "task": "3개년 재무제표 분석: 매출성장률, 영업이익률, ROE, 부채비율"}},'
    '{{"worker_index": 2, "task": "시장 동향·경쟁사 비교: SK하이닉스·TSMC·인텔 점유율·기술력"}},'
    '{{"worker_index": 3, "task": "리스크·밸류에이션: 지정학 리스크, PER·PBR 기반 투자의견"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 직접 답변 예시 ]\n"
    "사용자: 파이썬이란? → <ORCHESTRATE> 없이 바로 답변\n\n"

    "지금 요청을 분석하여 분배가 필요하면 <ORCHESTRATE> 형식으로, 아니면 직접 답변하세요."
)


# ── 유틸: 메모리 주입 ─────────────────────────────────────────────────────────

def _inject_memory(ai_name: str, text: str) -> str:
    """ChromaDB에서 유사 과거 기억을 검색해 프롬프트에 주입."""
    memories = search_memory_for(ai_name, text, n_results=2)
    if not memories:
        return text
    mem_block = "\n".join(
        f"[과거 참고 #{i+1} 관련도:{m['relevance_score']}]\n{m['document']}"
        for i, m in enumerate(memories)
    )
    return f"[이전 유사 작업 참고]\n{mem_block}\n\n[현재 요청]\n{text}"


# ── 노드 구현 ────────────────────────────────────────────────────────────────

async def plan_node(state: GraphState) -> dict:
    """
    Phase 1: 관리자가 조용히 계획 수립.
    UI에 스트리밍하지 않고 내부에서만 처리.
    """
    ws = state["websocket"]
    manager = state["manager_name"]
    workers = state["worker_names"]
    text = state["user_prompt"]
    provider_key = state["provider_map"].get(manager, "github")

    # 상태 알림
    await ws.send_json({"type": "orchestration_start", "aiName": manager, "workers": workers})
    await ws.send_json({"type": "status", "aiName": manager, "status": "RUNNING"})
    await ws.send_json({"type": "current_task", "aiName": manager, "task": "작업 분석 중..."})

    # 관리자 시스템 프롬프트 생성
    worker_list = "\n".join(f"- 팀원 {i+1}: {n}" for i, n in enumerate(workers))
    system = _MANAGER_SYSTEM.format(worker_list=worker_list)

    # 메모리 주입
    enriched_text = _inject_memory(manager, text)

    # 스트리밍 없이 조용히 호출
    model = get_lc_model(provider_key, streaming=False)
    messages = [SystemMessage(content=system), HumanMessage(content=enriched_text)]
    response = await model.ainvoke(messages)
    plan_text = response.content

    # ORCHESTRATE 블록 파싱
    match = _ORCHESTRATE_RE.search(plan_text)

    if not match:
        # 직접 답변 — UI에 표시
        await ws.send_json({"type": "log", "aiName": manager, "message": plan_text.strip()})
        await ws.send_json({"type": "status", "aiName": manager, "status": "COMPLETED"})
        await ws.send_json({"type": "current_task", "aiName": manager, "task": ""})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {
            "is_direct": True,
            "direct_answer": plan_text.strip(),
            "plan_summary": "",
            "subtasks": [],
        }

    try:
        data = json.loads(match.group(1).strip())
        subtasks_raw = data.get("subtasks", [])
        plan_summary = data.get("plan", "작업 분배 완료")
    except json.JSONDecodeError:
        await ws.send_json({"type": "log", "aiName": manager,
                            "message": "[오류] 계획 파싱 실패"})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"is_direct": True, "direct_answer": "", "plan_summary": "", "subtasks": []}

    # worker_index → worker_name 매핑 (라운드로빈 폴백)
    subtasks: list[SubTask] = []
    for st in subtasks_raw:
        idx = (st.get("worker_index", 1) - 1) % len(workers)
        subtasks.append({"worker_name": workers[idx], "task": st.get("task", "")})

    # 계획 요약 UI 표시
    await ws.send_json({"type": "log", "aiName": manager,
                        "message": f"[계획 완료] {plan_summary}"})

    # 서브태스크 배분 이벤트
    for st in subtasks:
        await ws.send_json({
            "type": "subtask_assign",
            "from": manager,
            "to": st["worker_name"],
            "task": st["task"],
        })

    await ws.send_json({"type": "current_task", "aiName": manager, "task": ""})

    return {
        "is_direct": False,
        "direct_answer": "",
        "plan_summary": plan_summary,
        "subtasks": subtasks,
        "worker_results": {},
    }


def dispatch_node(state: GraphState) -> list[Send] | dict:
    """
    Phase 2: 서브태스크를 워커 노드로 병렬 분산.
    LangGraph Send API → 각 서브태스크가 독립적인 worker_node 인스턴스로 실행.
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
    on_llm_new_token → WebSocket으로 실시간 스트리밍.
    """
    ws = state["websocket"]
    worker_name = state["current_worker_name"]
    task_text   = state["current_task_text"]
    provider_key = state["provider_map"].get(worker_name, "github")

    # 메모리 주입
    enriched_task = _inject_memory(worker_name, task_text)

    # 스트리밍 콜백 연결
    handler = WSStreamHandler(ws, worker_name)
    model = get_lc_model(provider_key, streaming=True, callbacks=[handler])

    await ws.send_json({"type": "current_task", "aiName": worker_name, "task": task_text})

    messages = [HumanMessage(content=enriched_task)]
    try:
        response = await model.ainvoke(messages)
        result = response.content
    except asyncio.CancelledError:
        result = ""
    except Exception as e:
        result = f"[오류] {e}"
        await ws.send_json({"type": "log", "aiName": worker_name, "message": result})

    # 메모리 저장
    if result:
        try:
            save_memory_for(worker_name, task_text, result[:2000])
        except Exception:
            pass

    await ws.send_json({"type": "current_task", "aiName": worker_name, "task": ""})

    return {"worker_results": {worker_name: result}}


async def synthesize_node(state: GraphState) -> dict:
    """
    Phase 4: 관리자가 모든 워커 결과를 종합하여 최종 답변 생성.
    UI에 실시간 스트리밍.
    """
    ws = state["websocket"]
    manager = state["manager_name"]
    provider_key = state["provider_map"].get(manager, "github")

    results = state.get("worker_results", {})
    valid = [
        f"### {name} 결과:\n{result}"
        for name, result in results.items()
        if result and result.strip()
    ]

    if not valid:
        await ws.send_json({"type": "log", "aiName": manager,
                            "message": "[오류] 팀원 결과가 없습니다."})
        await ws.send_json({"type": "status", "aiName": manager, "status": "COMPLETED"})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"final_synthesis": ""}

    synthesis_prompt = (
        "팀원들의 작업이 완료되었습니다. 결과를 종합하여 사용자에게 최종 답변을 작성해주세요.\n\n"
        f"원래 요청: {state['user_prompt']}\n\n" + "\n\n".join(valid)
    )

    # 종합 단계 알림
    await ws.send_json({"type": "orchestration_synthesis", "aiName": manager})
    await ws.send_json({"type": "current_task", "aiName": manager, "task": "결과 종합 중..."})

    # 스트리밍 콜백 연결
    handler = WSStreamHandler(ws, manager)
    model = get_lc_model(provider_key, streaming=True, callbacks=[handler])

    worker_list = "\n".join(f"- 팀원 {i+1}: {n}" for i, n in enumerate(state["worker_names"]))
    system = _MANAGER_SYSTEM.format(worker_list=worker_list)

    messages = [SystemMessage(content=system), HumanMessage(content=synthesis_prompt)]
    try:
        response = await model.ainvoke(messages)
        synthesis = response.content
    except asyncio.CancelledError:
        synthesis = ""
    except Exception as e:
        synthesis = f"[오류] {e}"

    # 메모리 저장
    if synthesis:
        try:
            save_memory_for(manager, state["user_prompt"], synthesis[:2000])
        except Exception:
            pass

    await ws.send_json({"type": "current_task", "aiName": manager, "task": ""})
    await ws.send_json({"type": "orchestration_done", "aiName": manager})

    return {"final_synthesis": synthesis}


# ── 라우팅 함수 ───────────────────────────────────────────────────────────────

def route_after_plan(state: GraphState) -> str:
    """plan_node 이후: 직접 답변이면 END, 아니면 dispatch_node."""
    return END if state.get("is_direct") else "dispatch_node"


# ── 그래프 빌드 ───────────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(GraphState)

    g.add_node("plan_node",       plan_node)
    g.add_node("dispatch_node",   dispatch_node)
    g.add_node("worker_node",     worker_node)
    g.add_node("synthesize_node", synthesize_node)

    g.add_edge(START, "plan_node")

    # plan 이후 분기: 직접 답변 or 오케스트레이션
    g.add_conditional_edges(
        "plan_node",
        route_after_plan,
        {"dispatch_node": "dispatch_node", END: END},
    )

    # dispatch → worker (Send API가 실제 병렬 분기 담당)
    g.add_edge("dispatch_node", "worker_node")

    # 모든 worker 완료 → synthesize
    g.add_edge("worker_node", "synthesize_node")

    g.add_edge("synthesize_node", END)

    return g.compile()


# 싱글턴 그래프 인스턴스
orchestration_graph = build_graph()
