import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine
from app.routes.project import router as project_router
from app.routes.agent import router as agent_router
from app.routes.task import router as task_router
from app.routes.orchestrator import router as orchestrator_router
from app.routes.upload import router as upload_router
from app.connection_manager import connection_manager
from app.ai.agent_runner import agent_manager

# DB 테이블 초기화
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Crew Commander Backend")

# ── CORS 설정 (React 개발 서버 허용) ─────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── REST 라우터 ───────────────────────────────────────────────
app.include_router(project_router)
app.include_router(agent_router)
app.include_router(task_router)
app.include_router(orchestrator_router)
app.include_router(upload_router)


# ── 헬스 체크 ─────────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "AI Crew Commander backend running"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ── WebSocket 엔드포인트 ──────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    프론트엔드와의 실시간 양방향 통신 허브.

    수신 액션 (frontend → backend):
      spawn   : 에이전트 슬롯 생성  { action, aiName, provider? }
      prompt  : 명령 전송           { action, aiName, text }
      pause   : 일시 정지           { action, aiName }
      resume  : 재개                { action, aiName }
      kill    : 에이전트 종료       { action, aiName }

    송신 메시지 (backend → frontend):
      { type: "log",      aiName, message }
      { type: "progress", aiName, percent }
      { type: "status",   aiName, status  }
    """
    await connection_manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action: str = data.get("action", "")
            ai_name: str = data.get("aiName", "").strip()

            if not ai_name:
                continue

            # ── spawn: 에이전트 등록 ─────────────────────────
            if action == "spawn":
                provider = data.get("provider", "claude")
                state = agent_manager.get_or_create(ai_name, provider)
                await websocket.send_json({
                    "type": "status",
                    "aiName": ai_name,
                    "status": "READY",
                })
                await websocket.send_json({
                    "type": "log",
                    "aiName": ai_name,
                    "message": f"[{ai_name}] 에이전트 준비 완료 — 모델: {state.provider.model_name}",
                })

            # ── prompt: AI 호출 및 스트리밍 ──────────────────
            elif action == "prompt":
                text: str = data.get("text", "").strip()
                if not text:
                    continue

                state = agent_manager.get_or_create(ai_name)

                # 이전 작업이 실행 중이면 취소 후 새 작업 시작
                if state.current_task and not state.current_task.done():
                    state.current_task.cancel()
                    await asyncio.sleep(0)  # 취소가 처리될 틈을 줌

                state.is_killed = False
                state._pause_event.set()

                state.current_task = asyncio.create_task(
                    agent_manager.run_prompt(ai_name, text, websocket)
                )

            # ── pause: 일시 정지 ──────────────────────────────
            elif action == "pause":
                state = agent_manager.get(ai_name)
                if state:
                    state.pause()
                    await websocket.send_json({
                        "type": "status",
                        "aiName": ai_name,
                        "status": "STOPPED",
                    })

            # ── resume: 재개 ──────────────────────────────────
            elif action == "resume":
                state = agent_manager.get(ai_name)
                if state:
                    state.resume()
                    await websocket.send_json({
                        "type": "status",
                        "aiName": ai_name,
                        "status": "RUNNING",
                    })

            # ── kill: 에이전트 종료 ───────────────────────────
            elif action == "kill":
                agent_manager.remove(ai_name)

    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception:
        connection_manager.disconnect(websocket)
