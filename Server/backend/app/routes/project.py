from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas import ProjectCreate
from app.db import get_db
from app.models import ProjectModel

router = APIRouter()


@router.post("/projects/")
def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    new_project = ProjectModel(
        title=project.title,
        description=project.description,
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return {
        "id":          new_project.id,
        "title":       new_project.title,
        "description": new_project.description,
    }


@router.get("/projects/")
def get_projects(db: Session = Depends(get_db)):
    return db.query(ProjectModel).all()


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project