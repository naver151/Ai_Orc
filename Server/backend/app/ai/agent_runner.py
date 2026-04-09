"""
AI Crew Commander — 에이전트 런타임 (Phase 2)

AgentManager 싱글턴은 agent_state.py에서 관리.
이 모듈은 WebSocket 연결과 LangGraph/단일 실행을 중계.
"""

from __future__ import annotations
import asyncio
import json

from fastapi import WebSocket
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.ai.agent_state import AgentState, AgentManager, agent_manager   # noqa: F401 (re-export)
from app.ai.lc_providers import get_lc_model, ProgressWSStreamHandler
from app.ai.graph_runner import orchestration_graph
from app.ai.graph_state import GraphState
from app.ai.lc_memory import save_agent_memory, build_rag_context
from app.db import SessionLocal
from app.models import OrchestrationLog

# lc_providers에 없으므로 여기서 import
from app.ai.lc_providers import WSStreamHandler


class _Runner:
    """WebSocket ↔ LangGraph / 단일 워커 실행 중계."""

    # ── 단일 워커 실행 ────────────────────────────────────────

    async def run_prompt(self, ai_name: str, text: str, websocket: WebSocket) -> None:
        state = agent_manager.get(ai_name)
        if not state:
            return

        # 메모리 주입 (LangChain retriever)
        rag = build_rag_context(ai_name, text, k=2)
        enriched = f"{rag}[현재 요청]\n{text}" if rag else text

        handler = ProgressWSStreamHandler(websocket, ai_name)
        cfg = RunnableConfig(callbacks=[handler])
        model = get_lc_model(state.provider_key, streaming=True)

        await websocket.send_json({"type": "current_task", "aiName": ai_name, "task": text})

        result = ""
        try:
            resp = await model.ainvoke([HumanMessage(content=enriched)], config=cfg)
            result = resp.content
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await websocket.send_json({
                "type": "log", "aiName": ai_name,
                "message": f"[오류] {type(e).__name__}: {e}",
            })

        if result:
            try:
                save_agent_memory(ai_name, text, result[:2000])
            except Exception:
                pass

        await websocket.send_json({"type": "current_task", "aiName": ai_name, "task": ""})
        state.status = "COMPLETED"

    # ── LangGraph 오케스트레이션 실행 ─────────────────────────

    async def run_orchestrated_prompt(
        self, manager_name: str, text: str, websocket: WebSocket
    ) -> None:
        worker_names = agent_manager.get_worker_names(manager_name)
        if not worker_names:
            await self.run_prompt(manager_name, text, websocket)
            return

        initial: GraphState = {
            "user_prompt":         text,
            "manager_name":        manager_name,
            "worker_names":        worker_names,
            "provider_map":        agent_manager.get_provider_map(),
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
            "agent_manager_ref":   agent_manager,   # pause/kill 체크용
        }

        final = await orchestration_graph.ainvoke(initial)

        # 오케스트레이션 로그 저장
        if not final.get("is_direct") and final.get("plan_summary"):
            await asyncio.to_thread(
                _save_orch_log,
                manager_name,
                worker_names,
                text,
                final.get("plan_summary", ""),
                final.get("subtasks", []),
                final.get("worker_results", {}),
                final.get("final_synthesis", ""),
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


# ── 외부에 노출되는 싱글턴 ───────────────────────────────────────────────────
# main.py가 import하는 agent_manager는 agent_state.py의 싱글턴과 동일 객체
_runner = _Runner()

# main.py 호환 인터페이스: agent_manager가 run_prompt / run_orchestrated_prompt를 가짐
agent_manager.run_prompt = _runner.run_prompt                           # type: ignore[attr-defined]
agent_manager.run_orchestrated_prompt = _runner.run_orchestrated_prompt # type: ignore[attr-defined]
