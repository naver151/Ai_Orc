import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db import get_db, SessionLocal
from app.models import TaskModel, AgentModel, TaskExecution, ProjectModel
from app.schemas import TaskExecutionRead
from app.memory import search_memory, save_memory, delete_memory, get_memory_count
from app.tasks import run_ai_task

router = APIRouter()

# ── roleKey → DB provider 매핑 ───────────────────────────────────
_ROLE_PROVIDER = {
    "analyst":   "openai",
    "collector": "openai",
    "executor":  "openai",
    "reviewer":  "openai",
    "writer":    "openai",
}


class SubmitRequest(BaseModel):
    request: str
    agents: list[dict]   # [{name, roleKey, task}]


@router.post("/orchestrator/run")
def run_orchestrator(db: Session = Depends(get_db)):
    """pending 태스크를 담당 에이전트에 배분하고 Celery 큐에 등록"""
    pending_tasks = db.query(TaskModel).filter(TaskModel.status == "pending").all()

    if not pending_tasks:
        return {"message": "처리할 태스크가 없습니다.", "dispatched": []}

    dispatched = []

    for task in pending_tasks:
        agent = db.query(AgentModel).filter(AgentModel.id == task.agent_id).first()
        if not agent:
            continue

        task.status = "in_progress"

        execution = TaskExecution(task_id=task.id)
        db.add(execution)
        db.commit()
        db.refresh(task)
        db.refresh(execution)

        run_ai_task.delay(
            task_id=task.id,
            agent_id=agent.id,
            task_text=task.task,
            provider=agent.provider,
            model=agent.model,
            role=agent.role,
        )

        dispatched.append({
            "task_id": task.id,
            "task": task.task,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "agent_role": agent.role,
            "status": task.status,
            "execution_id": execution.id,
            "started_at": execution.started_at,
            "message": "Celery 큐에 등록됨. Worker가 처리합니다.",
        })

    return {
        "message": f"{len(dispatched)}개의 태스크를 배분했습니다.",
        "dispatched": dispatched,
    }


@router.post("/orchestrator/memory/save")
def save_agent_memory(agent_id: int, task: str, result: str):
    save_memory(agent_id=agent_id, task=task, result=result)
    return {"message": "메모리 저장 완료", "agent_id": agent_id}


@router.get("/orchestrator/memory/search")
def search_agent_memory(agent_id: int, query: str):
    memories = search_memory(agent_id=agent_id, query=query)
    return {"agent_id": agent_id, "query": query, "memories": memories}


@router.delete("/orchestrator/memory/{agent_id}")
def delete_agent_memory(agent_id: int):
    deleted_count = delete_memory(agent_id=agent_id)
    return {"message": f"{deleted_count}개의 메모리를 삭제했습니다.", "agent_id": agent_id}


@router.get("/orchestrator/memory/count")
def get_agent_memory_count(agent_id: int):
    count = get_memory_count(agent_id=agent_id)
    return {"agent_id": agent_id, "memory_count": count}


@router.get("/orchestrator/executions", response_model=list[TaskExecutionRead])
def get_executions(db: Session = Depends(get_db)):
    return db.query(TaskExecution).all()


@router.get("/orchestrator/status")
def get_orchestrator_status(db: Session = Depends(get_db)):
    total = db.query(TaskModel).count()
    pending = db.query(TaskModel).filter(TaskModel.status == "pending").count()
    in_progress = db.query(TaskModel).filter(TaskModel.status == "in_progress").count()
    completed = db.query(TaskModel).filter(TaskModel.status == "completed").count()
    failed = db.query(TaskModel).filter(TaskModel.status == "failed").count()

    return {
        "total": total,
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "failed": failed,
    }


# ── POST /orchestrator/submit ─────────────────────────────────────
@router.post("/orchestrator/submit")
def submit_orchestration(req: SubmitRequest, db: Session = Depends(get_db)):
    """
    UI의 에이전트 계획을 받아 DB에 저장하고 Celery 큐에 등록.

    흐름:
      1. 임시 Project 생성
      2. 각 에이전트마다 AgentModel + TaskModel(pending) 생성
      3. Celery run_ai_task.delay() 로 백그라운드 실행
      4. project_id 반환 → 프론트엔드가 /orchestrator/poll/{id} 로 결과 수신
    """
    title = req.request[:50] if len(req.request) > 50 else req.request
    project = ProjectModel(title=f"[자동] {title}", description=req.request)
    db.add(project)
    db.commit()
    db.refresh(project)

    dispatched = []
    for agent_info in req.agents:
        role_key = agent_info.get("roleKey", "executor")
        provider  = _ROLE_PROVIDER.get(role_key, "openai")
        agent_name = agent_info.get("name", f"에이전트-{role_key}")
        task_text  = agent_info.get("task", req.request)

        agent = AgentModel(
            project_id=project.id,
            name=agent_name,
            role=task_text,
            provider=provider,
            model="gpt-4o",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        task = TaskModel(
            project_id=project.id,
            agent_id=agent.id,
            task=task_text,
            status="in_progress",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        execution = TaskExecution(task_id=task.id)
        db.add(execution)
        db.commit()
        db.refresh(execution)

        # Celery 큐 등록 (Redis 미실행 시에도 서버가 죽지 않도록 예외 처리)
        try:
            run_ai_task.delay(
                task_id=task.id,
                agent_id=agent.id,
                task_text=task_text,
                provider=provider,
                model="gpt-4o",
                role=task_text,
            )
            celery_ok = True
        except Exception as e:
            task.status = "failed"
            db.commit()
            celery_ok = False

        dispatched.append({
            "task_id":    task.id,
            "agent_id":   agent.id,
            "agent_name": agent_name,
            "role_key":   role_key,
            "celery_ok":  celery_ok,
        })

    return {
        "project_id": project.id,
        "tasks":      dispatched,
        "message":    f"{len(dispatched)}개 Celery 큐에 등록됨",
    }


# ── GET /orchestrator/poll/{project_id} (SSE) ────────────────────
@router.get("/orchestrator/poll/{project_id}")
async def poll_results(project_id: int, timeout: int = 120):
    """
    Celery 작업 완료를 SSE로 스트리밍.

    이벤트 형식:
      data: {"type": "agent_done",  "task_id": int, "agent_name": str,
             "role_key": str, "status": str, "result": str}
      data: {"type": "agent_error", "task_id": int, "agent_name": str, "error": str}
      data: {"type": "all_done",    "project_id": int}
      data: {"type": "timeout"}
    """
    async def generate():
        deadline = asyncio.get_event_loop().time() + timeout
        sent_ids: set[int] = set()

        while asyncio.get_event_loop().time() < deadline:
            db = SessionLocal()
            try:
                tasks = (
                    db.query(TaskModel)
                    .filter(TaskModel.project_id == project_id)
                    .all()
                )

                for task in tasks:
                    if task.id in sent_ids:
                        continue
                    if task.status not in ("completed", "failed"):
                        continue

                    agent = db.query(AgentModel).filter(AgentModel.id == task.agent_id).first()
                    execution = (
                        db.query(TaskExecution)
                        .filter(TaskExecution.task_id == task.id)
                        .order_by(TaskExecution.id.desc())
                        .first()
                    )

                    if task.status == "completed":
                        payload = {
                            "type":       "agent_done",
                            "task_id":    task.id,
                            "agent_name": agent.name if agent else "",
                            "role_key":   (agent.role[:20] if agent else ""),
                            "status":     "completed",
                            "result":     execution.result if execution else "",
                        }
                    else:
                        payload = {
                            "type":       "agent_error",
                            "task_id":    task.id,
                            "agent_name": agent.name if agent else "",
                            "error":      execution.error if execution else "알 수 없는 오류",
                        }

                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    sent_ids.add(task.id)

                # 모든 태스크 완료?
                if tasks and all(t.id in sent_ids for t in tasks):
                    yield f"data: {json.dumps({'type': 'all_done', 'project_id': project_id})}\n\n"
                    return

            finally:
                db.close()

            await asyncio.sleep(2)

        yield f"data: {json.dumps({'type': 'timeout'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
