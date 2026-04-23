"""
POST /orchestrate/stream  - LangGraph 병렬 에이전트 실행 → SSE 스트리밍

흐름:
  1. 요청에서 agents 목록을 받아 각각 worker_node로 병렬 실행
  2. 모든 worker 완료 후 synthesize_node로 종합
  3. 각 단계에서 발생하는 이벤트를 SSE로 스트리밍

이벤트 형식 (LangGraph graph_runner.py 기준):
  { type: "status",               aiName, status }
  { type: "log",                  aiName, message }
  { type: "progress",             aiName, percent }
  { type: "current_task",         aiName, task }
  { type: "orchestration_synthesis", aiName }
  { type: "orchestration_done",   aiName }
"""

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai.graph_runner import worker_node, synthesize_node

router = APIRouter()

MANAGER_NAME = "AI.Orc 관리자"


class AgentPlan(BaseModel):
    name: str
    roleKey: str = "executor"
    task: str
    aiType: str = "github"


class OrchestrateRequest(BaseModel):
    request: str
    agents: list[AgentPlan]
    user_uid: str | None = None


class _EventQueue:
    """WebSocket.send_json() 인터페이스를 asyncio.Queue로 구현 — LangGraph 노드 재사용."""

    def __init__(self, queue: asyncio.Queue):
        self._q = queue

    async def send_json(self, data: dict) -> None:
        await self._q.put(data)


@router.post("/orchestrate/stream")
async def orchestrate_stream(req: OrchestrateRequest):
    """
    LangGraph worker_node(병렬) → synthesize_node 실행.
    각 노드가 send_json()으로 방출하는 이벤트를 SSE로 그대로 흘려보냄.
    """

    async def generate():
        queue: asyncio.Queue = asyncio.Queue()
        ws = _EventQueue(queue)
        sentinel = object()

        provider_map = {a.name: "github" for a in req.agents}
        provider_map[MANAGER_NAME] = "github"

        async def run_all():
            # ── 워커 병렬 실행 ──────────────────────────────────────
            async def run_worker(agent: AgentPlan) -> dict:
                state = {
                    "websocket":            ws,
                    "current_worker_name":  agent.name,
                    "current_task_text":    agent.task,
                    "provider_map":         provider_map,
                    "worker_results":       {},
                    "user_prompt":          req.request,
                    "agent_manager_ref":    None,
                }
                return await worker_node(state)

            results_list = await asyncio.gather(
                *[run_worker(a) for a in req.agents],
                return_exceptions=True,
            )

            combined: dict[str, str] = {}
            for r in results_list:
                if isinstance(r, dict):
                    combined.update(r.get("worker_results", {}))

            # ── 종합 ─────────────────────────────────────────────────
            synth_state = {
                "websocket":         ws,
                "manager_name":      MANAGER_NAME,
                "worker_names":      [a.name for a in req.agents],
                "user_prompt":       req.request,
                "worker_results":    combined,
                "provider_map":      provider_map,
                "agent_manager_ref": None,
            }
            await synthesize_node(synth_state)
            await queue.put(sentinel)

        task = asyncio.create_task(run_all())

        try:
            while True:
                item = await asyncio.wait_for(queue.get(), timeout=300)
                if item is sentinel:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type':'error','message':'타임아웃 (5분)'})}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
