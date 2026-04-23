from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from datetime import datetime, timezone
from app.db import Base
import json


class UserProfile(Base):
    __tablename__ = "user_profiles"

    uid        = Column(String, primary_key=True)   # 프론트엔드 생성 uid
    name       = Column(String, nullable=False)
    age        = Column(Integer, nullable=True)
    job        = Column(String, nullable=True)
    gender     = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ProjectModel(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)


class AgentModel(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    provider = Column(String, default="openai")   # openai, anthropic, gemini
    model = Column(String, default="gpt-4o")      # 사용할 모델명


class TaskModel(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    task = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending, in_progress, completed, failed


class TaskExecution(Base):
    __tablename__ = "task_executions"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)


class OrchestrationLog(Base):
    """
    오케스트레이션 실행 기록 — 파인튜닝 데이터셋 구축용.
    좋은 케이스(rating >= 4)를 추려 학습 데이터로 활용.
    """
    __tablename__ = "orchestration_logs"

    id            = Column(Integer, primary_key=True)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    manager_name  = Column(String,   nullable=False)
    worker_names  = Column(Text,     nullable=False)  # JSON list
    user_prompt   = Column(Text,     nullable=False)  # 원래 사용자 요청
    plan_summary  = Column(Text,     nullable=True)   # 관리자 계획 한 줄
    subtasks_json = Column(Text,     nullable=True)   # JSON list of {worker, task}
    worker_results_json = Column(Text, nullable=True) # JSON list of {worker, result}
    synthesis_result    = Column(Text, nullable=True) # 관리자 최종 종합
    rating        = Column(Integer,  nullable=True)   # 1-5 사람 평점 (파인튜닝 필터용)
