from sqlalchemy import Column, Integer, String, Text, ForeignKey
from app.db import Base


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


class TaskModel(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    task = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")