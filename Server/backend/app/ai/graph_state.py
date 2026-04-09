"""
LangGraph 공유 상태 정의 (화이트보드)

GraphState는 오케스트레이션 실행 전 과정에서 모든 노드가 공유하는 단일 진실의 원천.
- 관리자 계획, 워커 결과, 종합 결과 등 모든 데이터가 여기에 누적됨
- worker_results는 병렬 워커가 동시에 쓸 수 있도록 merge reducer 적용
"""

from __future__ import annotations
from typing import Annotated, Any
from typing_extensions import TypedDict


def _merge_dict(a: dict, b: dict) -> dict:
    """병렬 워커 결과를 순서대로 합침 (LangGraph Send API용 reducer)."""
    return {**a, **b}


class SubTask(TypedDict):
    worker_name: str
    task: str


class GraphState(TypedDict):
    # ── 입력 ──────────────────────────────────────────────────
    user_prompt:   str
    manager_name:  str
    worker_names:  list[str]          # 등록된 워커 이름 목록
    provider_map:  dict[str, str]     # {ai_name: provider_key}

    # ── 계획 단계 ──────────────────────────────────────────────
    plan_summary:  str
    subtasks:      list[SubTask]      # [{worker_name, task}, ...]
    is_direct:     bool               # True면 오케스트레이션 없이 직접 답변
    direct_answer: str

    # ── 실행 단계 (병렬 워커 결과 누적) ──────────────────────
    # Send API로 병렬 실행되는 워커들이 각자 결과를 추가
    worker_results: Annotated[dict[str, str], _merge_dict]

    # ── 현재 실행 중인 워커 정보 (Send로 전달되는 서브 상태) ──
    current_worker_name: str
    current_task_text:   str

    # ── 종합 단계 ──────────────────────────────────────────────
    final_synthesis: str

    # ── 리뷰 단계 (Phase 4) ────────────────────────────────────
    review_verdict:  str   # "pass" | "fail"
    review_feedback: str
    retry_count:     int
    max_retries:     int

    # ── 런타임 전용 (직렬화 안 함 — 체크포인터 미사용) ────────
    websocket:        Any  # FastAPI WebSocket
    agent_manager_ref: Any # AgentManager 참조 (pause/kill 체크용)
