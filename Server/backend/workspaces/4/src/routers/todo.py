from fastapi import APIRouter, HTTPException
from typing import List, Optional
from models import TodoCreate, TodoResponse
from crud import create_todo, get_todos, get_todo, update_todo, delete_todo

router = APIRouter(prefix="/todos", tags=["todos"])

# Create
@router.post("/", response_model=TodoResponse)
def create_todo_route(todo: TodoCreate):
    return create_todo(todo.title, todo.description)

# Read all
@router.get("/", response_model=List[TodoResponse])
def get_todos_route():
    return get_todos()

# Read one
@router.get("/{todo_id}", response_model=TodoResponse)
def get_todo_route(todo_id: int):
    todo = get_todo(todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo

# Update
@router.put("/{todo_id}", response_model=TodoResponse)
def update_todo_route(todo_id: int, todo: TodoCreate):
    updated_todo = update_todo(todo_id, todo.title, todo.description)
    if not updated_todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return updated_todo

# Delete
@router.delete("/{todo_id}", response_model=dict)
def delete_todo_route(todo_id: int):
    deleted = delete_todo(todo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Todo not found")
    return {"message": "Todo deleted successfully"}