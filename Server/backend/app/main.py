from fastapi import FastAPI
from pydantic import BaseModel

# 🔥 이게 반드시 먼저 있어야 함
app = FastAPI()

# 데이터 모델
class Project(BaseModel):
    title: str
    description: str

# 임시 저장소
projects = []

# API
@app.post("/projects")
def create_project(project: Project):
    new_project = {
        "id": len(projects) + 1,
        "title": project.title,
        "description": project.description
    }
    projects.append(new_project)
    return new_project


@app.get("/projects")
def get_projects():
    return projects


@app.get("/")
def root():
    return {"message": "backend running"}