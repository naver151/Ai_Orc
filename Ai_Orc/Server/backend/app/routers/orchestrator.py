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
    # pending 상태인 태스크 전부 조회
    pending_tasks = db.query(TaskModel).filter(TaskModel.status == "pending").all()

    if not pending_tasks:
        return {"message": "처리할 태스크가 없습니다.", "dispatched": []}

    dispatched = []

    for task in pending_tasks:
        # 해당 태스크를 담당할 에이전트 조회
        agent = db.query(AgentModel).filter(AgentModel.id == task.agent_id).first()

        if not agent:
            continue

        # 상태를 in_progress로 변경 (에이전트가 작업 시작)
        task.status = "in_progress"

        # 실행 기록 생성
        execution = TaskExecution(task_id=task.id)
        db.add(execution)
        db.commit()
        db.refresh(task)
        db.refresh(execution)

        # Redis 큐에 AI 작업 등록 (비동기 처리)
        run_ai_task.delay(
            task_id=task.id,
            agent_id=agent.id,
            task_text=task.task,
            provider=agent.provider,
            model=agent.model,
            role=agent.role
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
            "message": "Redis 큐에 등록됨. Celery worker가 처리합니다."
        })

    return {
        "message": f"{len(dispatched)}개의 태스크를 에이전트에 배분했습니다.",
        "dispatched": dispatched
    }


@router.post("/orchestrator/memory/save")
def save_agent_memory(agent_id: int, task: str, result: str):
    """에이전트의 작업 결과를 메모리에 저장"""
    save_memory(agent_id=agent_id, task=task, result=result)
    return {"message": "메모리 저장 완료", "agent_id": agent_id, "task": task}


@router.get("/orchestrator/memory/search")
def search_agent_memory(agent_id: int, query: str):
    """에이전트의 과거 기억에서 유사한 작업 검색 (유사도 점수 포함)"""
    memories = search_memory(agent_id=agent_id, query=query)
    return {"agent_id": agent_id, "query": query, "memories": memories}


@router.delete("/orchestrator/memory/{agent_id}")
def delete_agent_memory(agent_id: int):
    """특정 에이전트의 모든 메모리 삭제"""
    deleted_count = delete_memory(agent_id=agent_id)
    return {"message": f"{deleted_count}개의 메모리를 삭제했습니다.", "agent_id": agent_id, "deleted_count": deleted_count}


@router.get("/orchestrator/memory/count")
def get_agent_memory_count(agent_id: int):
    """특정 에이전트의 저장된 메모리 개수 조회"""
    count = get_memory_count(agent_id=agent_id)
    return {"agent_id": agent_id, "memory_count": count}


@router.get("/orchestrator/executions", response_model=list[TaskExecutionRead])
def get_executions(db: Session = Depends(get_db)):
    return db.query(TaskExecution).all()


@router.get("/orchestrator/status")
def get_orchestrator_status(db: Session = Depends(get_db)):
    # 전체 태스크 상태 요약
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
        "failed": failed
    }
