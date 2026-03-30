import chromadb

# ChromaDB 클라이언트 (로컬 파일로 저장)
client = chromadb.PersistentClient(path="./chroma_db")

# 에이전트 메모리 컬렉션 (에이전트별로 과거 작업 결과 저장)
memory_collection = client.get_or_create_collection(name="agent_memory")


def save_memory(agent_id: int, task: str, result: str):
    """에이전트의 작업 결과를 메모리에 저장"""
    memory_collection.add(
        documents=[f"task: {task}\nresult: {result}"],
        metadatas=[{"agent_id": agent_id, "task": task}],
        ids=[f"agent_{agent_id}_{hash(task)}"]
    )


def search_memory(agent_id: int, query: str, n_results: int = 3):
    """에이전트의 과거 기억 중 현재 쿼리와 유사한 것 검색"""
    results = memory_collection.query(
        query_texts=[query],
        n_results=n_results,
        where={"agent_id": agent_id}
    )
    return results["documents"][0] if results["documents"] else []
