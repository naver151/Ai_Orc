from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AgentModel, ProjectModel
from app.schemas import AgentCreate, AgentRead

router = APIRouter()


@router.post("/agents", response_model=AgentRead)
def create_agent(agent: AgentCreate, db: Session = Depends(get_db)):
    project = db.query(ProjectModel).filter(ProjectModel.id == agent.project_id).first()
    if not project:
        raise HTTPException(status_code=400, detail="Project not found")

    new_agent = AgentModel(
        project_id=agent.project_id,
        name=agent.name,
        role=agent.role,
        provider=agent.provider,
        model=agent.model,
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return new_agent


@router.get("/agents", response_model=list[AgentRead])
def get_agents(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(AgentModel)
    if project_id is not None:
        query = query.filter(AgentModel.project_id == project_id)
    return query.all()


@router.get("/agents/{agent_id}", response_model=AgentRead)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"message": "Agent deleted successfully"}
