"""
AI Crew Commander — 에이전트 런타임

AgentManager: 에이전트 등록·제어(pause/resume/kill) 관리
LangGraph 오케스트레이션: graph_runner.orchestration_graph 위임
단일 워커 실행: LangChain 직접 호출 (스트리밍 콜백)
"""

from __future__ import annotations
import asyncio
import json
import os
from typing import Optional, Any

from dotenv import load_dotenv
from fastapi import WebSocket
from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.lc_providers import get_lc_model, WSStreamHandler
from app.ai.graph_runner import orchestration_graph
from app.ai.graph_state import GraphState
from app.memory import save_memory_for, search_memory_for
from app.db import SessionLocal
from app.models import OrchestrationLog

load_dotenv(override=True, encoding="utf-8")


# ── AgentState: 에이전트 제어 정보 (LangGraph 실행과 분리) ───────────────────

class AgentState:
    """에이전트 슬롯의 메타 정보 및 pause/resume/kill 제어."""

    def __init__(self, ai_name: str, provider_key: str = "github"):
        self.ai_name      = ai_name
        self.provider_key = provider_key
        self.status       = "READY"
        self.current_task: Optional[asyncio.Task] = None
        self.is_killed    = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()

    def pause(self) -> None:
        self._pause_event.clear()
        self.status = "STOPPED"

    def resume(self) -> None:
        self._pause_event.set()
        self.status = "RUNNING"

    def kill(self) -> None:
        self.is_killed = True
        self._pause_event.set()
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
        self.status = "STOPPED"

    async def wait_if_paused(self) -> None:
        await self._pause_event.wait()

    @property
    def model_name(self) -> str:
        return self.provider_key


# ── AgentManager ─────────────────────────────────────────────────────────────

class AgentManager:

    def __init__(self):
        self._agents: dict[str, AgentState] = {}

    # ── 등록·조회 ────────────────────────────────────────────

    def get_or_create(self, ai_name: str, provider_key: str = "github") -> AgentState:
        if ai_name not in self._agents:
            self._agents[ai_name] = AgentState(ai_name, provider_key)
        else:
            self._agents[ai_name].provider_key = provider_key
        return self._agents[ai_name]

    def get(self, ai_name: str) -> Optional[AgentState]:
        return self._agents.get(ai_name)

    def remove(self, ai_name: str) -> None:
        if ai_name in self._agents:
            self._agents.pop(ai_name).kill()

    def is_manager(self, ai_name: str) -> bool:
        if not self._agents:
            return False
        return list(self._agents.keys())[0] == ai_name

    def get_worker_names(self, manager_name: str) -> list[str]:
        return [n for n in self._agents if n != manager_name]

    def get_provider_map(self) -> dict[str, str]:
        return {name: state.provider_key for name, state in self._agents.items()}

    # ── 단일 워커 실행 ────────────────────────────────────────

    async def run_prompt(self, ai_name: str, text: str, websocket: WebSocket) -> None:
        """워커 에이전트 단독 실행 (오케스트레이션 없이)."""
        state = self.get(ai_name)
        if not state:
            return

        # 메모리 주입
        memories = search_memory_for(ai_name, text, n_results=2)
        enriched = text
        if memories:
            mem_block = "\n".join(
                f"[과거 참고 #{i+1} 관련도:{m['relevance_score']}]\n{m['document']}"
                for i, m in enumerate(memories)
            )
            enriched = f"[이전 유사 작업 참고]\n{mem_block}\n\n[현재 요청]\n{text}"

        # 스트리밍 콜백
        handler = WSStreamHandler(websocket, ai_name)
        model = get_lc_model(state.provider_key, streaming=True, callbacks=[handler])

        await websocket.send_json({"type": "current_task", "aiName": ai_name, "task": text})

        full_response = ""
        try:
            response = await model.ainvoke([HumanMessage(content=enriched)])
            full_response = response.content
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await websocket.send_json({
                "type": "log", "aiName": ai_name,
                "message": f"[오류] {type(e).__name__}: {e}",
            })

        if full_response:
            try:
                save_memory_for(ai_name, text, full_response[:2000])
            except Exception:
                pass

        await websocket.send_json({"type": "current_task", "aiName": ai_name, "task": ""})
        state.status = "COMPLETED"

    # ── LangGraph 오케스트레이션 실행 ─────────────────────────

    async def run_orchestrated_prompt(
        self, manager_name: str, text: str, websocket: WebSocket
    ) -> None:
        """
        LangGraph 그래프 실행.
        plan → dispatch → workers(병렬) → synthesize
        """
        worker_names = self.get_worker_names(manager_name)
        if not worker_names:
            await self.run_prompt(manager_name, text, websocket)
            return

        # 초기 GraphState 구성
        initial_state: GraphState = {
            "user_prompt":         text,
            "manager_name":        manager_name,
            "worker_names":        worker_names,
            "provider_map":        self.get_provider_map(),
            "plan_summary":        "",
            "subtasks":            [],
            "is_direct":           False,
            "direct_answer":       "",
            "worker_results":      {},
            "current_worker_name": "",
            "current_task_text":   "",
            "final_synthesis":     "",
            "review_verdict":      "",
            "review_feedback":     "",
            "retry_count":         0,
            "max_retries":         2,
            "websocket":           websocket,
        }

        # LangGraph 실행
        final_state = await orchestration_graph.ainvoke(initial_state)

        # 오케스트레이션 로그 저장 (직접 답변이 아닌 경우)
        if not final_state.get("is_direct") and final_state.get("plan_summary"):
            await asyncio.to_thread(
                _save_orch_log,
                manager_name,
                worker_names,
                text,
                final_state.get("plan_summary", ""),
                final_state.get("subtasks", []),
                final_state.get("worker_results", {}),
                final_state.get("final_synthesis", ""),
            )


# ── 오케스트레이션 로그 저장 ─────────────────────────────────────────────────

def _save_orch_log(
    manager_name:   str,
    worker_names:   list,
    user_prompt:    str,
    plan_summary:   str,
    subtasks:       list,
    worker_results: dict,
    synthesis:      str,
) -> None:
    try:
        db = SessionLocal()
        log = OrchestrationLog(
            manager_name=manager_name,
            worker_names=json.dumps(worker_names, ensure_ascii=False),
            user_prompt=user_prompt,
            plan_summary=plan_summary,
            subtasks_json=json.dumps(subtasks, ensure_ascii=False),
            worker_results_json=json.dumps(
                [{"worker": k, "result": v} for k, v in worker_results.items()],
                ensure_ascii=False,
            ),
            synthesis_result=synthesis[:4000] if synthesis else "",
        )
        db.add(log)
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


# ── 싱글턴 ───────────────────────────────────────────────────────────────────

agent_manager = AgentManager()
