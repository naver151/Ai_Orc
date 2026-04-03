from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TaskModel, AgentModel, TaskExecution
from app.schemas import TaskExecutionRead
from app.memory import search_memory, save_memory, delete_memory, get_memory_count
from app.tasks import run_ai_task

router = APIRouter()


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
