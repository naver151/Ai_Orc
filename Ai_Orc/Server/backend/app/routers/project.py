from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ProjectModel
from app.schemas import ProjectCreate, ProjectRead

router = APIRouter()


@router.post("/projects", response_model=ProjectRead)
def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    new_project = ProjectModel(
        title=project.title,
        description=project.description
    )

    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    return new_project


@router.get("/projects", response_model=list[ProjectRead])
def get_projects(db: Session = Depends(get_db)):
    return db.query(ProjectModel).all()


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return project