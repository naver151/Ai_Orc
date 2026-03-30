from fastapi import FastAPI
from sqlalchemy import text
from app.routers import project, agent, task, orchestrator
from app import models
from app.db import Base, engine

Base.metadata.create_all(bind=engine)


app = FastAPI()

@app.get("/")
def root():
    return {"message": "server running"}

@app.get("/db-test")
def db_test():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        return {"db_result": result.scalar()}

app.include_router(project.router)
app.include_router(agent.router)
app.include_router(task.router)
app.include_router(orchestrator.router)

