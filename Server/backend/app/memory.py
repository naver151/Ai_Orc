import chromadb
from datetime import datetime, timezone

_client = None
_memory_collection = None


def _get_collection():
    global _client, _memory_collection
    if _memory_collection is None:
        _client = chromadb.PersistentClient(path="./chroma_db")
        _memory_collection = _client.get_or_create_collection(name="agent_memory")
    return _memory_collection


def save_memory(agent_id: int, task: str, result: str):
    """에이전트의 작업 결과를 벡터 메모리에 저장"""
    timestamp = datetime.now(timezone.utc).isoformat()
    _get_collection().add(
        documents=[f"task: {task}\nresult: {result}"],
        metadatas=[{"agent_id": agent_id, "task": task, "saved_at": timestamp}],
        ids=[f"agent_{agent_id}_{hash(task)}"]
    )


def search_memory(agent_id: int, query: str, n_results: int = 3) -> list[dict]:
    """과거 기억 중 현재 쿼리와 유사한 것 검색"""
    count = get_memory_count(agent_id)
    if count == 0:
        return []

    actual_n = min(n_results, count)
    results = _get_collection().query(
        query_texts=[query],
        n_results=actual_n,
        where={"agent_id": agent_id},
        include=["documents", "metadatas", "distances"]
    )

    memories = []
    if results["documents"] and results["documents"][0]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            memories.append({
                "document": doc,
                "task": meta.get("task", ""),
                "saved_at": meta.get("saved_at", ""),
                "relevance_score": round(1 - dist, 4)
            })

    return memories


def delete_memory(agent_id: int) -> int:
    """특정 에이전트의 모든 메모리 삭제. 삭제된 개수 반환"""
    existing = _get_collection().get(where={"agent_id": agent_id})
    ids_to_delete = existing["ids"]
    if ids_to_delete:
        _get_collection().delete(ids=ids_to_delete)
    return len(ids_to_delete)


def get_memory_count(agent_id: int) -> int:
    """특정 에이전트의 저장된 메모리 개수 반환"""
    existing = _get_collection().get(where={"agent_id": agent_id})
    return len(existing["ids"])
