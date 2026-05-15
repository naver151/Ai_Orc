from fastapi import FastAPI
from src.routers import item_router
from src.routers import example_router

app = FastAPI()

app.include_router(item_router.router)
app.include_router(example_router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the enhanced FastAPI application!"}