from fastapi import FastAPI
from app.db import Base, engine
from app.routes.project import router as project_router
from app.routes.agent import router as agent_router
from app.routes.task import router as task_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Capstone Backend")

@app.get("/")
def root():
    return {"message": "backend running"}

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(project_router)
app.include_router(agent_router)
app.include_router(task_router)