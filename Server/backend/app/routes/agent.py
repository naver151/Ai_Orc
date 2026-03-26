from fastapi import APIRouter
from app.schemas import AgentCreate
from app.db import SessionLocal
from app.models import AgentModel

router = APIRouter()


@router.post("/agents")
def create_agent(agent: AgentCreate):
    db = SessionLocal()
    new_agent = AgentModel(
        project_id=agent.project_id,
        name=agent.name,
        role=agent.role
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    db.close()

    return {
        "id": new_agent.id,
        "project_id": new_agent.project_id,
        "name": new_agent.name,
        "role": new_agent.role
    }


@router.get("/agents")
def get_agents():
    db = SessionLocal()
    agents = db.query(AgentModel).all()
    db.close()

    return agents