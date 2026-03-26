from fastapi import APIRouter
from app.schemas import ProjectCreate
from app.db import SessionLocal
from app.models import ProjectModel

router = APIRouter()


@router.post("/projects")
def create_project(project: ProjectCreate):
    db = SessionLocal()
    new_project = ProjectModel(
        title=project.title,
        description=project.description
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    db.close()

    return {
        "id": new_project.id,
        "title": new_project.title,
        "description": new_project.description
    }


@router.get("/projects")
def get_projects():
    db = SessionLocal()
    projects = db.query(ProjectModel).all()
    db.close()

    return projects