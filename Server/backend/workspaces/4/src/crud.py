from typing import List, Optional
from models import Todo

# Mock 데이터베이스
database: List[Todo] = []
next_id = 1

# Create
def create_todo(title: str, description: Optional[str] = None) -> Todo:
    global next_id
    new_todo = Todo(id=next_id, title=title, description=description)
    database.append(new_todo)
    next_id += 1
    return new_todo

# Read all
def get_todos() -> List[Todo]:
    return database

# Read one
def get_todo(todo_id: int) -> Optional[Todo]:
    return next((todo for todo in database if todo.id == todo_id), None)

# Update
def update_todo(todo_id: int, title: str, description: Optional[str] = None) -> Optional[Todo]:
    todo = get_todo(todo_id)
    if todo:
        todo.title = title
        todo.description = description
        return todo
    return None

# Delete
def delete_todo(todo_id: int) -> bool:
    global database
    todo = get_todo(todo_id)
    if todo:
        database = [t for t in database if t.id != todo_id]
        return True
    return False