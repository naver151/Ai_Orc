"""
웹 검색 도구

우선순위:
  1. Tavily API (TAVILY_API_KEY 환경변수 설정 시)
  2. DuckDuckGo (무료, API 키 불필요 — 폴백)

에이전트가 실시간 웹 데이터를 조회할 수 있어 창업 리서치·시장 분석에 활용.
"""

from __future__ import annotations
import os
import json


def _search_tavily(query: str, max_results: int = 5) -> list[dict]:
    """Tavily API로 검색. 결과: [{title, url, content}, ...]"""
    import httpx
    api_key = os.getenv("TAVILY_API_KEY", "")
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "max_results": max_results,
              "search_depth": "basic", "include_answer": False},
        timeout=15,
    )
    resp.raise_for_status()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in resp.json().get("results", [])
    ]


def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo DDGS로 검색. API 키 불필요."""
    from duckduckgo_search import DDGS
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title":   r.get("title", ""),
                "url":     r.get("href", ""),
                "content": r.get("body", ""),
            })
    return results


def web_search(query: str, max_results: int = 5) -> str:
    """
    웹 검색 실행 후 결과를 텍스트로 반환.
    Tavily API 키가 있으면 Tavily, 없으면 DuckDuckGo 사용.

    Args:
        query      : 검색 키워드 (한국어/영어 모두 가능)
        max_results: 최대 결과 수 (기본 5)

    Returns:
        검색 결과 텍스트 (번호 목록 형식)
    """
    try:
        if os.getenv("TAVILY_API_KEY"):
            results = _search_tavily(query, max_results)
            source = "Tavily"
        else:
            results = _search_duckduckgo(query, max_results)
            source = "DuckDuckGo"

        if not results:
            return f"[검색 결과 없음] 쿼리: {query}"

        lines = [f"🔍 검색: {query!r} (출처: {source})\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   URL: {r['url']}")
            if r["content"]:
                snippet = r["content"][:300].replace("\n", " ")
                lines.append(f"   {snippet}...")
            lines.append("")

        return "\n".join(lines)

    except ImportError:
        return "[오류] duckduckgo-search 패키지가 설치되지 않았습니다. pip install duckduckgo-search"
    except Exception as e:
        return f"[검색 오류] {type(e).__name__}: {e}"


def get_search_tool():
    """LangChain StructuredTool 형태로 web_search 반환."""
    from langchain_core.tools import StructuredTool
    return StructuredTool.from_function(
        func=web_search,
        name="web_search",
        description=(
            "실시간 웹 검색. 시장 규모·경쟁사·최신 뉴스·트렌드 조사에 사용. "
            "query는 검색할 키워드, max_results는 결과 수(기본 5)."
        ),
    )
