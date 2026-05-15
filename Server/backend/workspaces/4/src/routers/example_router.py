from fastapi import APIRouter

example_router = APIRouter(prefix="/examples", tags=["Examples"])

@example_router.get("/", summary="Get all examples")
async def get_examples():
    return {"message": "List of examples"}

@example_router.post("/", summary="Create an example")
async def create_example(example: dict):
    return {"message": "Example created", "data": example}

@example_router.get("/{example_id}", summary="Get specific example")
async def get_example(example_id: int):
    return {"message": "Detail of example", "example_id": example_id}

@example_router.put("/{example_id}", summary="Update specific example")
async def update_example(example_id: int, example: dict):
    return {"message": "Example updated", "example_id": example_id, "data": example}

@example_router.delete("/{example_id}", summary="Delete specific example")
async def delete_example(example_id: int):
    return {"message": "Example deleted", "example_id": example_id}