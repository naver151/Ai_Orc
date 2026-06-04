"""
LangChain VectorStore 기반 메모리 (Phase 3)

기존 memory.py의 chromadb 직접 호출을 LangChain Chroma 래퍼로 교체.
- save_agent_memory()   : 에이전트 결과를 벡터 DB에 저장
- retrieve_context()    : 쿼리와 유사한 과거 기억을 retriever로 검색
- build_rag_context()   : 검색 결과를 프롬프트용 문자열로 변환

임베딩 우선순위:
  1. GitHub Token  → text-embedding-3-small (Azure AI Inference)
  2. OpenAI API Key → text-embedding-3-small
  3. SentenceTransformers → all-MiniLM-L6-v2 (로컬, API 키 불필요, 90MB)
  4. FakeEmbeddings → 의미 검색 불가 (최후 폴백)
"""

from __future__ import annotations
import os
from typing import Optional

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore


def _get_embeddings():
    """
    임베딩 모델을 우선순위에 따라 선택한다.
    3번 SentenceTransformers까지는 실제 의미 기반 유사도 검색이 가능하다.
    """
    # 1순위: GitHub Token으로 Azure AI Inference 엔드포인트 사용
    github_token = os.getenv("GITHUB_TOKEN", "")
    if github_token:
        try:
            from langchain_openai import OpenAIEmbeddings
            emb = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=github_token,
                base_url="https://models.inference.ai.azure.com",
            )
            print("[메모리] 임베딩: GitHub Models (text-embedding-3-small)")
            return emb
        except Exception:
            pass

    # 2순위: OpenAI API 키
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key and not openai_key.startswith("your"):
        try:
            from langchain_openai import OpenAIEmbeddings
            emb = OpenAIEmbeddings(model="text-embedding-3-small", api_key=openai_key)
            print("[메모리] 임베딩: OpenAI (text-embedding-3-small)")
            return emb
        except Exception:
            pass

    # 3순위: 로컬 SentenceTransformers (API 키 불필요, 실제 의미 검색 가능)
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        emb = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        print("[메모리] 임베딩: SentenceTransformers (all-MiniLM-L6-v2, 로컬)")
        return emb
    except Exception as e:
        print(f"[메모리] SentenceTransformers 로드 실패: {e}")

    # 4순위: 최후 폴백 — 의미 검색 불가
    print(
        "[경고] 사용 가능한 임베딩 모델 없음 — FakeEmbeddings 사용. "
        "RAG 유사도 검색이 비활성화됩니다.\n"
        "  해결: pip install sentence-transformers"
    )
    from langchain_core.embeddings import FakeEmbeddings
    return FakeEmbeddings(size=384)


# VectorStore 싱글턴 (Chroma)
_vectorstore: Optional[VectorStore] = None


def _get_vectorstore() -> VectorStore:
    global _vectorstore
    if _vectorstore is None:
        try:
            from langchain_chroma import Chroma          # 신버전 패키지
        except ImportError:
            from langchain_community.vectorstores import Chroma  # 구버전 폴백
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
