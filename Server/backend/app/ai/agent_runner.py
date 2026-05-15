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
from app.ai.lc_providers import get_lc_model, WSStreamHandler, ProgressWSStreamHandler, safe_ainvoke
from app.ai.graph_runner import orchestration_graph
from app.ai.graph_state import GraphState
from app.ai.lc_memory import save_agent_memory, build_rag_context
from app.db import SessionLocal
from app.models import OrchestrationLog, ProjectSession


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
            resp = await safe_ainvoke(model, [HumanMessage(content=enriched)], config=cfg)
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
        self,
        manager_name: str,
        text: str,
        websocket: WebSocket,
        project_id: int | None = None,
    ) -> None:
        worker_names = agent_manager.get_worker_names(manager_name)
        if not worker_names:
            await self.run_prompt(manager_name, text, websocket)
            return

        # 프로젝트 워크스페이스 경로 조회
        workspace_path   = ""
        project_context  = ""
        if project_id:
            try:
                import os
                from pathlib import Path
                from app.db import SessionLocal
                from app.models import ProjectModel

                # WORKSPACE_ROOT: workspace.py와 동일한 기본값 사용
                _ws_root = Path(
                    os.getenv("WORKSPACE_ROOT",
                              str(Path(__file__).resolve().parents[2] / "workspaces"))
                )

                db = SessionLocal()
                project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
                if project:
                    if project.workspace_path:
                        workspace_path = project.workspace_path
                    else:
                        # workspace_path 가 NULL인 경우 — 자동 복구
                        fallback = _ws_root / str(project_id)
                        fallback.mkdir(parents=True, exist_ok=True)
                        for sub in ["src", "tests", "docs", ".aiorc"]:
                            (fallback / sub).mkdir(exist_ok=True)
                        workspace_path = str(fallback)
                        project.workspace_path = workspace_path
                        db.commit()
                db.close()
            except Exception:
                pass

            # plan_node 주입용 컨텍스트 로드
            if workspace_path:
                try:
                    from app.routes.workspace import get_project_context
                    from app.db import SessionLocal
                    db = SessionLocal()
                    ctx = get_project_context(project_id, db)
                    project_context = ctx.get("context", "")
                    db.close()
                except Exception:
                    pass

        # ── Phase 4: 세션 시작 ─────────────────────────────
        session_id: int | None = None
        if project_id:
            session_id = await asyncio.to_thread(_start_session, project_id)

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
            "review_feedback":     "",
            "review_scores":       {},
            "retry_count":         0,
            "max_retries":         2,
            # 사용자 교차검증
            "user_feedback":       "",
            "user_approved":       True,
            "review_timed_out":    False,
            "retry_worker_names":  [],
            # 적응형 분배 모드
            "distribution_mode":   agent_manager.get_distribution_mode(manager_name),
            # 프로젝트 워크스페이스
            "project_id":           project_id,
            "workspace_path":       workspace_path,
            "project_context":      project_context,
            "created_files":        [],
            # 마일스톤 자동 추적
            "current_milestone_id": None,
            "current_task_db_id":   None,
            "websocket":           websocket,
            "agent_manager_ref":   agent_manager,
        }

        final = await orchestration_graph.ainvoke(initial)

        # ── Phase 4: 세션 종료 ─────────────────────────────
        if project_id and session_id:
            summary = (final.get("final_synthesis", "") or "")[:3000]
            # WorkspaceFile 테이블에서 이 세션 이후 변경된 파일 목록을 조회
            await asyncio.to_thread(_end_session, project_id, session_id, summary)

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


# ── Phase 4: 세션 헬퍼 ───────────────────────────────────────────────────────

def _start_session(project_id: int) -> int | None:
    """동기 함수 — asyncio.to_thread로 호출. 세션 ID 반환."""
    try:
        db = SessionLocal()
        session = ProjectSession(project_id=project_id)
        db.add(session)
        db.commit()
        return session.id
    except Exception:
        return None
    finally:
        db.close()


def _end_session(
    project_id: int,
    session_id: int,
    summary:    str,
) -> None:
    """
    동기 함수 — asyncio.to_thread로 호출. 세션 종료 처리.
    변경된 파일 목록은 WorkspaceFile 테이블에서 세션 시작 이후 updated_at 기준으로 수집.
    """
    from datetime import datetime, timezone
    from app.models import WorkspaceFile
    try:
        db = SessionLocal()
        session = db.query(ProjectSession).filter(
            ProjectSession.id == session_id,
            ProjectSession.project_id == project_id,
        ).first()
        if session:
            # 세션 시작 이후 생성/수정된 파일
            started = session.started_at
            files = (
                db.query(WorkspaceFile.path)
                .filter(
                    WorkspaceFile.project_id == project_id,
                    WorkspaceFile.updated_at  >= started,
                )
                .all()
            )
            session.summary       = summary
            session.files_changed = [f.path for f in files]
            session.ended_at      = datetime.now(timezone.utc)
            db.commit()
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass


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
