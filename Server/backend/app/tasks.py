import os
from dotenv import load_dotenv
load_dotenv(override=True, encoding='utf-8')
from celery import Celery
from app.ai_clients import get_ai_client
from app.memory import save_memory, search_memory

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "ai_orc",
    broker=REDIS_URL,
    backend=REDIS_URL,
)


@celery_app.task
def run_ai_task(task_id: int, agent_id: int, task_text: str, provider: str, model: str, role: str):
    """
    Redis 큐에서 꺼내 실행되는 AI 작업 (비동기 백그라운드 처리)
    """
    from app.db import SessionLocal
    from app.models import TaskModel, TaskExecution
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        # 과거 기억 검색 → AI context로 전달
        past_memories = search_memory(agent_id=agent_id, query=task_text)
        context_texts = [m["document"] for m in past_memories]

        # AI 호출
        ai_client = get_ai_client(provider=provider, model=model)
        result = ai_client.run(role=role, task=task_text, context=context_texts)

        # 실행 결과 저장
        execution = db.query(TaskExecution).filter(
            TaskExecution.task_id == task_id
        ).order_by(TaskExecution.id.desc()).first()

        if execution:
            execution.result = result
            execution.finished_at = datetime.now(timezone.utc)

        # 태스크 상태 완료로 변경
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if task:
            task.status = "completed"

        db.commit()

        # 결과를 벡터 메모리에 저장
        save_memory(agent_id=agent_id, task=task_text, result=result)

        return {"status": "completed", "result": result}

    except Exception as e:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if task:
            task.status = "failed"
        db.commit()
        return {"status": "failed", "error": str(e)}

    finally:
        db.close()
