from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db import Base
import json


def _utcnow():
    return datetime.now(timezone.utc)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    uid        = Column(String, primary_key=True)   # 프론트엔드 생성 uid
    name       = Column(String, nullable=False)
    age        = Column(Integer, nullable=True)
    job        = Column(String, nullable=True)
    gender     = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class ProjectModel(Base):
    __tablename__ = "projects"

    id             = Column(Integer, primary_key=True, index=True)
    title          = Column(String,  nullable=False)
    description    = Column(Text,    nullable=False)
    workspace_path = Column(String,  nullable=True)   # /workspaces/{id}/
    created_at     = Column(DateTime, default=_utcnow)

    milestones = relationship("Milestone",      back_populates="project", cascade="all, delete-orphan")
    sessions   = relationship("ProjectSession", back_populates="project", cascade="all, delete-orphan")


class Milestone(Base):
    """프로젝트 대분류 목표 (예: '인증 시스템', 'API 레이어')"""
    __tablename__ = "milestones"

    id          = Column(Integer, primary_key=True)
    project_id  = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title       = Column(String,  nullable=False)
    description = Column(Text,    nullable=True)
    order       = Column(Integer, default=0)
    status      = Column(String,  default="todo")   # todo | in_progress | done
    created_at  = Column(DateTime, default=_utcnow)

    project = relationship("ProjectModel", back_populates="milestones")
    tasks   = relationship("ProjectTask",  back_populates="milestone", cascade="all, delete-orphan")


class ProjectTask(Base):
    """실제 작업 단위 — 에이전트에게 배정, 파일 결과물 추적"""
    __tablename__ = "project_tasks"

    id             = Column(Integer, primary_key=True)
    milestone_id   = Column(Integer, ForeignKey("milestones.id"), nullable=False)
    project_id     = Column(Integer, ForeignKey("projects.id"),   nullable=False)
    title          = Column(String,  nullable=False)
    description    = Column(Text,    nullable=True)
    status         = Column(String,  default="todo")   # todo | in_progress | done | failed
    assigned_agent = Column(String,  nullable=True)    # 담당 에이전트 이름
    result_files   = Column(JSON,    default=list)     # ["src/auth/jwt.py", ...]
    order          = Column(Integer, default=0)
    created_at     = Column(DateTime, default=_utcnow)
    completed_at   = Column(DateTime, nullable=True)

    milestone = relationship("Milestone", back_populates="tasks")


class WorkspaceFile(Base):
    """워크스페이스 파일 메타데이터 (실제 내용은 디스크)"""
    __tablename__ = "workspace_files"

    id          = Column(Integer, primary_key=True)
    project_id  = Column(Integer, ForeignKey("projects.id"), nullable=False)
    path        = Column(String,  nullable=False)     # "src/auth/jwt.py"
    created_by  = Column(String,  nullable=True)      # 에이전트 이름 or "user"
    task_id     = Column(Integer, ForeignKey("project_tasks.id"), nullable=True)
    created_at  = Column(DateTime, default=_utcnow)
    updated_at  = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class ProjectSession(Base):
    """세션 연속성 — 각 작업 세션에서 무엇을 했는지 기록"""
    __tablename__ = "project_sessions"

    id             = Column(Integer, primary_key=True)
    project_id     = Column(Integer, ForeignKey("projects.id"), nullable=False)
    summary        = Column(Text,  nullable=True)       # 이번 세션 완료 내용 요약
    files_changed  = Column(JSON,  default=list)        # 생성/수정된 파일 목록
    tasks_done     = Column(JSON,  default=list)        # 완료된 task id 목록
    started_at     = Column(DateTime, default=_utcnow)
    ended_at       = Column(DateTime, nullable=True)

    project = relationship("ProjectModel", back_populates="sessions")


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


class AgentPerformance(Base):
    """
    적응형 분배 — AI 성능 이력.
    review_node에서 채점된 점수를 저장하여
    다음 plan_node에서 최고 성능 provider를 epsilon-greedy로 자동 선택.
    """
    __tablename__ = "agent_performance"

    id         = Column(Integer, primary_key=True)
    task_type  = Column(String,  nullable=False, index=True)  # "code" | "analysis" | "writing" | "search" | "general"
    provider   = Column(String,  nullable=False, index=True)  # "claude" | "github" | "gemini" | ...
    score      = Column(Integer, nullable=False)              # AI 리뷰 점수 1~10
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


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
