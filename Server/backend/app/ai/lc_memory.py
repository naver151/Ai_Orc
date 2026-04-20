"""
LangChain VectorStore 기반 메모리 (Phase 3)

기존 memory.py의 chromadb 직접 호출을 LangChain Chroma 래퍼로 교체.
- save_agent_memory()   : 에이전트 결과를 벡터 DB에 저장
- retrieve_context()    : 쿼리와 유사한 과거 기억을 retriever로 검색
- build_rag_context()   : 검색 결과를 프롬프트용 문자열로 변환

임베딩: langchain-community의 FakeEmbeddings (무료, 테스트용)
        → OPENAI_API_KEY 있으면 OpenAIEmbeddings로 자동 교체
"""

from __future__ import annotations
import os
from typing import Optional

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore

# 임베딩 선택: OpenAI 키 있으면 실제 임베딩, 없으면 테스트용 가짜 임베딩
def _get_embeddings():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key and not api_key.startswith("your"):
        try:
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(api_key=api_key)
        except Exception:
            pass
    # 폴백: 차원 고정 가짜 임베딩 (의미 검색 불가, 구조 테스트용)
    from langchain_core.embeddings import FakeEmbeddings
    return FakeEmbeddings(size=1536)


# VectorStore 싱글턴 (Chroma)
_vectorstore: Optional[VectorStore] = None


def _get_vectorstore() -> VectorStore:
    global _vectorstore
    if _vectorstore is None:
        from langchain_chroma import Chroma
        _vectorstore = Chroma(
            collection_name="agent_memory_lc",
            embedding_function=_get_embeddings(),
            persist_directory="./chroma_db_lc",
        )
    return _vectorstore


# ── 저장 ─────────────────────────────────────────────────────────────────────

def save_agent_memory(agent_name: str, task: str, result: str) -> None:
    """에이전트 이름 + 작업 + 결과를 벡터 DB에 저장."""
    try:
        vs = _get_vectorstore()
        doc = Document(
            page_content=f"task: {task}\nresult: {result[:1500]}",
            metadata={"agent_name": agent_name, "task": task},
        )
        vs.add_documents([doc])
    except Exception:
        pass


# ── 검색 ─────────────────────────────────────────────────────────────────────

def retrieve_context(agent_name: str, query: str, k: int = 2) -> list[Document]:
    """
    에이전트 이름 필터 + 쿼리 유사도로 과거 기억 검색.
    LangChain retriever.invoke() 사용.
    """
    try:
        vs = _get_vectorstore()
        retriever = vs.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": k,
                "filter": {"agent_name": agent_name},
            },
        )
        return retriever.invoke(query)
    except Exception:
        return []


def build_rag_context(agent_name: str, query: str, k: int = 2) -> str:
    """
    retrieve_context() 결과를 프롬프트 삽입용 문자열로 변환.
    결과가 없으면 빈 문자열 반환.
    """
    docs = retrieve_context(agent_name, query, k)
    if not docs:
        return ""
    lines = [
        f"[과거 참고 #{i+1}]\n{doc.page_content}"
        for i, doc in enumerate(docs)
    ]
    return "[이전 유사 작업 참고]\n" + "\n\n".join(lines) + "\n\n"
