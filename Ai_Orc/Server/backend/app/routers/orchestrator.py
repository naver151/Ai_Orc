from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TaskModel, AgentModel, TaskExecution
from app.schemas import TaskExecutionRead
from app.memory import save_memory, search_memory
from app.ai_clients import get_ai_client
from datetime import datetime, timezone

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

        # 에이전트의 과거 유사 작업 기억 검색
        past_memories = search_memory(agent_id=agent.id, query=task.task)

        # AI 클라이언트 선택 및 실행
        ai_result = None
        error_msg = None
        try:
            ai_client = get_ai_client(provider=agent.provider, model=agent.model)
            ai_result = ai_client.run(role=agent.role, task=task.task, context=past_memories)

            # 실행 완료 기록 업데이트
            execution.result = ai_result
            execution.finished_at = datetime.now(timezone.utc)
            task.status = "completed"

            # AI 결과를 메모리에 저장 (다음 작업에서 참고)
            save_memory(agent_id=agent.id, task=task.task, result=ai_result)

        except Exception as e:
            error_msg = str(e)
            execution.error = error_msg
            execution.finished_at = datetime.now(timezone.utc)
            task.status = "failed"

        db.commit()
        db.refresh(execution)

        dispatched.append({
            "task_id": task.id,
            "task": task.task,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "agent_role": agent.role,
            "status": task.status,
            "execution_id": execution.id,
            "started_at": execution.started_at,
            "finished_at": execution.finished_at,
            "past_memories": past_memories,
            "result": ai_result,
            "error": error_msg,
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
    """에이전트의 과거 기억에서 유사한 작업 검색"""
    memories = search_memory(agent_id=agent_id, query=query)
    return {"agent_id": agent_id, "query": query, "memories": memories}


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
