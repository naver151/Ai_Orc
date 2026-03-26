from pydantic import BaseModel


class ProjectCreate(BaseModel):
    title: str
    description: str


class AgentCreate(BaseModel):
    project_id: int
    name: str
    role: str


class TaskCreate(BaseModel):
    project_id: int
    agent_id: int
    task: str