from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from datetime import datetime, timezone
from app.db import Base


class ProjectModel(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    title = Column(String)
    description = Column(Text)
    

class AgentModel(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String)
    role = Column(String)


class TaskModel(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    agent_id = Column(Integer, ForeignKey("agents.id"))
    task = Column(Text)
    status = Column(String, default="pending")


class TaskExecution(Base):
    __tablename__ = "task_executions"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    result = Column(Text, nullable=True)   # 실행 결과 (나중에 OpenAI 응답 저장)
    error = Column(Text, nullable=True)    # 에러 메시지