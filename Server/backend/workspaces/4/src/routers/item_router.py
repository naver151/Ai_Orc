from fastapi import APIRouter, HTTPException
from src.models.item_model import Item

router = APIRouter(prefix="/items")

# Mock data
todo_items = []

@router.post("/add")
async def add_item(item: Item):
    todo_items.append(item)
    return {"message": "Item added successfully!", "item": item}

@router.get("/list")
async def list_items():
    return todo_items

@router.get("/{item_id}")
def read_item(item_id: int):
    for item in todo_items:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")

@router.put("/{item_id}")
async def update_item(item_id: int, updated_item: Item):
    for idx, item in enumerate(todo_items):
        if item.id == item_id:
            todo_items[idx] = updated_item
            return {"message": "Item updated successfully", "item": updated_item}
    raise HTTPException(status_code=404, detail="Item not found")

@router.delete("/{item_id}")
async def delete_item(item_id: int):
    global todo_items
    todo_items = [item for item in todo_items if item.id != item_id]
    return {"message": "Item deleted successfully"}