from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ProjectCreate(BaseModel):
    title: str
    description: str


class ProjectRead(BaseModel):
    id: int
    title: str
    description: str

    class Config:
        from_attributes = True


class AgentCreate(BaseModel):
    project_id: int
    name: str
    role: str
    provider: str = "openai"    # 기본값 openai
    model: str = "gpt-4o"       # 기본값 gpt-4o


class AgentRead(BaseModel):
    id: int
    project_id: int
    name: str
    role: str
    provider: str
    model: str

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    project_id: int
    agent_id: int
    task: str


class TaskStatusUpdate(BaseModel):
    status: str  # "pending", "in_progress", "completed", "failed"


class TaskRead(BaseModel):
    id: int
    project_id: int
    agent_id: int
    task: str
    status: str

    class Config:
        from_attributes = True


class TaskExecutionRead(BaseModel):
    id: int
    task_id: int
    started_at: datetime
    finished_at: Optional[datetime]
    result: Optional[str]
    error: Optional[str]

    class Config:
        from_attributes = True