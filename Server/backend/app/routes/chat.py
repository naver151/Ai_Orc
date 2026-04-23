"""
UI 연동 엔드포인트

POST /chat/stream    - 관리자 AI 채팅 SSE 스트리밍
POST /manager/plan   - 에이전트 작업 계획 반환
POST /agent/execute  - 에이전트별 실행 SSE 스트리밍
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


# ── 역할키 → 시스템 프롬프트 ─────────────────────────────────────
ROLE_PROMPTS: dict[str, str] = {
    "analyst":   "당신은 요청 분석 전문가입니다. 사용자 요청의 핵심 의도와 세부 작업을 명확하게 파악하고 실행 계획을 수립합니다.",
    "collector": "당신은 정보 수집 전문가입니다. 요청과 관련된 정보와 데이터를 체계적으로 수집·정리합니다.",
    "executor":  "당신은 실행 전문가입니다. 주어진 작업을 직접 수행하여 구체적인 결과물(코드·문서·분석 등)을 생성합니다.",
    "reviewer":  "당신은 검토 전문가입니다. 생성된 결과물을 꼼꼼히 검토하고 품질을 보장합니다.",
    "writer":    "당신은 문서 작성 전문가입니다. 최종 결과물을 사용자에게 최적화된 형태로 정리하여 제시합니다.",
}

# ── 프로젝트 의도 감지 ────────────────────────────────────────────
_PROJECT_RE = re.compile(
    r"만들어|개발해|구현해|작성해|설계해|제작해|"
    r"분석해|조사해|정리해|자동화|처리해|"
    r"만들어줘|해줘|해주세요|만들어주세요|부탁해|"
    r"시스템|프로젝트|서비스|앱|봇|플랫폼|"
    r"리포트|보고서|코드|스크립트|데이터"
)

def _is_project_request(text: str) -> bool:
    return len(text.strip()) >= 6 and bool(_PROJECT_RE.search(text))

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

class PreviousResult(BaseModel):
    agentName: str
    result: str

class ExecuteRequest(BaseModel):
    original_request: str
    agent_task: str
    role_key: str
    previous_results: list[PreviousResult] = []
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
            model = get_lc_model(provider, streaming=False)

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
            is_project = _is_project_request(req.message)

            async for chunk in model.astream(messages):
                if chunk.content:
                    yield f"data: {json.dumps({'type':'text','chunk':chunk.content}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)

            yield f"data: {json.dumps({'type':'done','isProjectRequest':is_project})}\n\n"

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
        "roleKey 선택: analyst, collector, executor, reviewer, writer\n"
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


# ── 3. POST /agent/execute ────────────────────────────────────────

@router.post("/agent/execute")
async def agent_execute(req: ExecuteRequest, db: Session = Depends(get_db)):
    provider = _get_provider()
    user_ctx = _get_user_context(req.user_uid, db)

    async def generate():
        try:
            model = get_lc_model(provider, streaming=False)

            system_prompt = (
                f"{user_ctx}"
                + ROLE_PROMPTS.get(req.role_key, "당신은 AI 전문 에이전트입니다. 주어진 작업을 성실히 수행합니다.")
            )

            pipeline_context = ""
            if req.previous_results:
                parts = [f"[{pr.agentName} 결과]\n{pr.result}" for pr in req.previous_results]
                pipeline_context = "\n\n".join(parts) + "\n\n"

            human_content = (
                f"[원래 사용자 요청]\n{req.original_request}\n\n"
                + (f"[이전 에이전트 작업 결과 — 이를 기반으로 작업하세요]\n{pipeline_context}" if pipeline_context else "")
                + f"[배정된 작업]\n{req.agent_task}\n\n"
                "위 작업을 수행해주세요. 한국어로 답변하세요."
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_content),
            ]

            async for chunk in model.astream(messages):
                if chunk.content:
                    yield f"data: {json.dumps({'type':'text','chunk':chunk.content}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)

        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 4. POST /users ────────────────────────────────────────────────

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
