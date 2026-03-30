from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas import TaskCreate, TaskRead, TaskStatusUpdate
from app.db import get_db
from app.models import TaskModel, ProjectModel, AgentModel

router = APIRouter()


@router.post("/tasks", response_model=TaskRead)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    project = db.query(ProjectModel).filter(ProjectModel.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=400, detail="Project not found")

    agent = db.query(AgentModel).filter(AgentModel.id == task.agent_id).first()
    if not agent:
        raise HTTPException(status_code=400, detail="Agent not found")

    if agent.project_id != task.project_id:
        raise HTTPException(status_code=400, detail="Agent not in this project")

    new_task = TaskModel(
        project_id=task.project_id,
        agent_id=task.agent_id,
        task=task.task,
        status="pending"
    )

    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return new_task


@router.get("/tasks", response_model=list[TaskRead])
def get_tasks(db: Session = Depends(get_db)):
    return db.query(TaskModel).all()


VALID_STATUSES = {"pending", "in_progress", "completed", "failed"}

@router.patch("/tasks/{task_id}/status", response_model=TaskRead)
def update_task_status(task_id: int, body: TaskStatusUpdate, db: Session = Depends(get_db)):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")

    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = body.status
    db.commit()
    db.refresh(task)
    return task