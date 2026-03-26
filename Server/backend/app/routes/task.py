from fastapi import APIRouter
from app.schemas import TaskCreate

router = APIRouter()

tasks = []


@router.post("/tasks")
def create_task(task: TaskCreate):
    new_task = {
        "id": len(tasks) + 1,
        "project_id": task.project_id,
        "agent_id": task.agent_id,
        "task": task.task,
        "status": "running"
    }
    tasks.append(new_task)
    return new_task


@router.get("/tasks")
def get_tasks():
    return tasks