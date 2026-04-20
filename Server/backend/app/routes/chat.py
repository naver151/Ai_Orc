"""
채팅 및 플래닝 엔드포인트

ChatPage.jsx ↔ agentManager.js 가 호출하는 두 엔드포인트:

  POST /chat/stream    — 일반 대화 SSE 스트리밍 (관리자 AI)
  POST /manager/plan   — 멀티에이전트 작업 분배 계획 생성
"""

from __future__ import annotations
import asyncio
import json
import re

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai.lc_providers import get_lc_model
from langchain_core.messages import HumanMessage, SystemMessage

router = APIRouter()

# ── 시스템 프롬프트 ───────────────────────────────────────────

_CHAT_SYSTEM = (
    "당신은 AI.Orc의 관리자 AI입니다.\n"
    "사용자와 자연스럽게 대화하고, 복잡한 작업 요청이 들어오면\n"
    "멀티에이전트 오케스트레이션으로 처리할 수 있다고 안내하세요.\n"
    "항상 친절하고 간결하게 답변하세요.\n\n"
    "⚠️ 중요 규칙:\n"
    "- 마크다운 문법(**, __, `, ```코드블록, # 제목 등)을 절대 사용하지 마세요.\n"
    "- 코드 예시나 코드 블록을 출력하지 마세요.\n"
    "- 순수한 한국어 문장으로만 응답하세요.\n"
    "- 목록은 '•' 기호나 번호(1. 2. 3.)만 사용하세요.\n"
    "- 이모지는 사용해도 됩니다."
)

_PLAN_SYSTEM = (
    "당신은 AI 팀의 총괄 관리자입니다.\n"
    "사용자의 요청을 분석하여 최적의 에이전트 팀 구성과 역할을 JSON으로 반환하세요.\n\n"
    "가능한 roleKey: analyst, collector, executor, reviewer, writer\n\n"
    "반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):\n"
    '{"agents": ['
    '{"roleKey": "analyst", "name": "분석 AI", "task": "구체적인 작업 설명"},'
    '{"roleKey": "executor", "name": "실행 AI", "task": "구체적인 작업 설명"}'
    ']}'
)

# 프로젝트 의도 감지 패턴
_PROJECT_PATTERNS = [
    r"만들어|개발해|구현해|작성해|설계해|제작해",
    r"분석해|조사해|정리해|자동화|처리해",
    r"만들어줘|해줘|해주세요|만들어주세요|부탁해",
    r"시스템|프로젝트|서비스|앱|봇|플랫폼",
    r"리포트|보고서|코드|스크립트|데이터",
]
_PROJECT_RE = re.compile("|".join(_PROJECT_PATTERNS))


def _detect_project_intent(text: str) -> bool:
    return len(text.strip()) >= 6 and bool(_PROJECT_RE.search(text))


def _strip_markdown(text: str) -> str:
    """마크다운 코드 블록과 인라인 코드를 제거합니다."""
    # 펜스드 코드 블록 제거 (```...```)
    text = re.sub(r'```[\s\S]*?```', '', text)
    # 인라인 코드 제거 (`...`)
    text = re.sub(r'`[^`\n]+`', lambda m: m.group()[1:-1], text)
    # 굵기/이탤릭 마크다운 제거 (**...**)
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    # 제목 마크다운 제거 (# ...)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # 연속 빈 줄 정리
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── 요청 모델 ─────────────────────────────────────────────────

class ChatStreamRequest(BaseModel):
    message: str
    history: list[dict] = []   # [{"role": "user"|"assistant", "content": "..."}]
    provider: str = "github"


class PlanRequest(BaseModel):
    request: str
    provider: str = "github"


# ── /chat/stream ─────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(req: ChatStreamRequest):
    """
    일반 대화 SSE 스트리밍.

    이벤트:
      data: {"type": "text",  "chunk": "..."}
      data: {"type": "done",  "isProjectRequest": true|false}
      data: {"type": "error", "message": "..."}
    """
    is_project = _detect_project_intent(req.message)

    async def event_stream():
        try:
            from langchain_core.messages import AIMessage

            # 메시지 히스토리 구성 (user + assistant 모두 포함)
            msgs = [SystemMessage(content=_CHAT_SYSTEM)]
            for h in req.history[-10:]:   # 최근 10개
                role = h.get("role", "")
                content = h.get("content", "")
                if role == "user":
                    msgs.append(HumanMessage(content=content))
                elif role == "assistant":
                    msgs.append(AIMessage(content=content))
            msgs.append(HumanMessage(content=req.message))

            model = get_lc_model(req.provider, streaming=False)
            resp  = await model.ainvoke(msgs)
            text  = _strip_markdown(resp.content)

            # 청크 단위 스트리밍 (자연스러운 속도감을 위해 5자씩)
            chunk_size = 5
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                yield f'data: {json.dumps({"type": "text", "chunk": chunk}, ensure_ascii=False)}\n\n'
                await asyncio.sleep(0.02)

            yield f'data: {json.dumps({"type": "done", "isProjectRequest": is_project}, ensure_ascii=False)}\n\n'

        except Exception as e:
            yield f'data: {json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── /manager/plan ─────────────────────────────────────────────

@router.post("/manager/plan")
async def manager_plan(req: PlanRequest):
    """
    멀티에이전트 작업 분배 계획 생성.

    반환:
      { "agents": [{"roleKey", "name", "task"}, ...] }
    """
    try:
        messages = [
            SystemMessage(content=_PLAN_SYSTEM),
            HumanMessage(content=f"사용자 요청: {req.request}"),
        ]

        model = get_lc_model(req.provider, streaming=False)
        resp  = await model.ainvoke(messages)
        text  = resp.content.strip()

        # JSON 파싱
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            plan = json.loads(json_match.group())
            return plan

    except Exception:
        pass

    # 폴백: 기본 3-에이전트 플랜
    return {
        "agents": [
            {"roleKey": "analyst",  "name": "요청 분석 AI",  "task": f"'{req.request}' 요청의 핵심 의도와 세부 요구사항 분석"},
            {"roleKey": "executor", "name": "처리 실행 AI",  "task": "분석된 요구사항을 바탕으로 실제 작업 수행"},
            {"roleKey": "writer",   "name": "응답 생성 AI",  "task": "결과를 사용자에게 최적화된 형태로 정리 및 전달"},
        ]
    }
