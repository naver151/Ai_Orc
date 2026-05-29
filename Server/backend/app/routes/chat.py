"""
UI 연동 엔드포인트

POST /chat/stream    - 관리자 AI 채팅 SSE 스트리밍
POST /manager/plan   - 에이전트 작업 계획 반환
POST /users          - 사용자 정보 저장
"""

import json
import asyncio
import re
import os

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.ai.lc_providers import get_lc_model
from app.db import get_db
from app.models import UserProfile

router = APIRouter()


def _get_provider() -> str:
    if os.getenv("GITHUB_TOKEN"):
        return "github"
    if os.getenv("OPENAI_API_KEY"):
        return "gpt"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    return "github"

def _get_user_context(uid: str | None, db: Session) -> str:
    """uid로 유저 프로필 조회 → 시스템 프롬프트 주입용 문자열."""
    if not uid:
        return ""
    user = db.query(UserProfile).filter(UserProfile.uid == uid).first()
    if not user:
        return ""
    parts = [f"이름: {user.name}"]
    if user.age:
        parts.append(f"나이: {user.age}세")
    if user.job:
        parts.append(f"직업: {user.job}")
    if user.gender:
        parts.append(f"성별: {user.gender}")
    return "[사용자 정보]\n" + ", ".join(parts) + "\n위 정보를 참고해 답변 수준과 톤을 조정하세요.\n\n"


# ── Pydantic 요청 스키마 ──────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    user_uid: str | None = None

class PlanRequest(BaseModel):
    request: str
    user_uid: str | None = None

class UserData(BaseModel):
    uid: str | None = None
    name: str
    age: int | None = None
    job: str | None = None
    gender: str | None = None


# ── 1. POST /chat/stream ──────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, db: Session = Depends(get_db)):
    provider = _get_provider()
    user_ctx = _get_user_context(req.user_uid, db)

    async def generate():
        try:
            model = get_lc_model(provider, streaming=True)

            system_content = (
                f"{user_ctx}"
                "당신은 AI.Orc의 관리자 AI입니다. "
                "사용자와 친근하게 대화하며 도움을 제공합니다. "
                "한국어로 간결하고 명확하게 답변하세요."
            )
            messages: list = [SystemMessage(content=system_content)]

            for msg in req.history[-10:]:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

            messages.append(HumanMessage(content=req.message))

            async for chunk in model.astream(messages):
                if chunk.content:
                    yield f"data: {json.dumps({'type':'text','chunk':chunk.content}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)

            yield f"data: {json.dumps({'type':'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 2. POST /manager/plan ─────────────────────────────────────────

@router.post("/manager/plan")
async def manager_plan(req: PlanRequest, db: Session = Depends(get_db)):
    provider = _get_provider()
    model = get_lc_model(provider, streaming=False)
    user_ctx = _get_user_context(req.user_uid, db)

    system = (
        f"{user_ctx}"
        "당신은 멀티 에이전트 시스템의 관리자 AI입니다.\n"
        "사용자 요청을 분석하여 에이전트 작업 계획을 순수 JSON으로만 반환하세요 (마크다운 금지).\n\n"
        "형식:\n"
        '{"agents": [{"name": "에이전트 이름", "roleKey": "역할키", "task": "구체적 작업 설명"}, ...]}\n\n'
        "roleKey 선택:\n"
        "  analyst  — 분석·계획 수립\n"
        "  collector — 정보 정리·구조화\n"
        "  executor  — 실행·코드 생성\n"
        "  reviewer  — 검토·품질 확인\n"
        "  writer    — 최종 문서 작성\n\n"
        "에이전트 수: 2~4개, 작업 흐름 순서대로 배치.\n"
        "task는 해당 에이전트가 실제로 수행할 내용을 구체적으로 기술."
    )

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=f"요청: {req.request}"),
    ]

    try:
        resp = await model.ainvoke(messages)
        text = resp.content.strip()
        text = re.sub(r"```(?:json)?\n?", "", text).strip("`").strip()
        return json.loads(text)
    except Exception:
        return {
            "agents": [
                {"name": "요청 분석 AI", "roleKey": "analyst",
                 "task": f"'{req.request}' 요청의 핵심 의도를 파악하고 세부 실행 계획을 수립합니다."},
                {"name": "처리 실행 AI", "roleKey": "executor",
                 "task": "분석 결과를 바탕으로 실제 작업을 수행하고 결과물을 생성합니다."},
                {"name": "응답 생성 AI", "roleKey": "writer",
                 "task": "완성된 결과물을 사용자에게 최적화된 형태로 정리합니다."},
            ]
        }


# ── 3. POST /users ────────────────────────────────────────────────

@router.post("/users")
def save_user(user: UserData, db: Session = Depends(get_db)):
    """사용자 프로필을 DB에 저장 (uid 기준 upsert)."""
    if not user.uid:
        return {"message": "uid 없음 — 저장 생략"}

    existing = db.query(UserProfile).filter(UserProfile.uid == user.uid).first()
    if existing:
        existing.name   = user.name
        existing.age    = user.age
        existing.job    = user.job
        existing.gender = user.gender
    else:
        db.add(UserProfile(
            uid=user.uid,
            name=user.name,
            age=user.age,
            job=user.job,
            gender=user.gender,
        ))
    db.commit()
    return {"message": "ok", "uid": user.uid}
