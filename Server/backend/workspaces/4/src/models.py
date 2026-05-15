from pydantic import BaseModel
from typing import Optional

# Pydantic 모델
class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = None

class TodoResponse(TodoCreate):
    id: int

# 메모리 데이터베이스 시뮬레이션을 위한 Mock 데이터베이스 모델
class Todo:
    def __init__(self, id: int, title: str, description: Optional[str] = None):
        self.id = id
        self.title = title
        self.description = description