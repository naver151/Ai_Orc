import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.ai_clients import get_ai_client

router = APIRouter()

# 연결된 WebSocket 클라이언트 관리
connected_clients: list[WebSocket] = []

# 에이전트 상태 저장 (aiName → status)
agent_states: dict[str, str] = {}


async def broadcast(message: dict):
    """모든 연결된 클라이언트에게 메시지 전송"""
    for client in connected_clients:
        try:
            await client.send_json(message)
        except Exception:
            pass


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            action = data.get("action")
            ai_name = data.get("aiName")

            if action == "spawn":
                agent_states[ai_name] = "READY"
                await broadcast({
                    "type": "status",
                    "aiName": ai_name,
                    "status": "READY"
                })
                await broadcast({
                    "type": "log",
                    "aiName": ai_name,
                    "message": f"[{ai_name}] 서버에 에이전트 등록 완료."
                })

            elif action == "prompt":
                task_text = data.get("text", "")
                agent_states[ai_name] = "RUNNING"

                await broadcast({"type": "status", "aiName": ai_name, "status": "RUNNING"})
                await broadcast({"type": "progress", "aiName": ai_name, "percent": 10})
                await broadcast({"type": "log", "aiName": ai_name, "message": f"[{ai_name}] 작업 시작: {task_text}"})

                try:
                    await broadcast({"type": "progress", "aiName": ai_name, "percent": 40})

                    # OpenAI 호출 (기본 provider: openai)
                    ai_client = get_ai_client(provider="openai", model="gpt-4o")
                    result = ai_client.run(role=ai_name, task=task_text, context=[])

                    await broadcast({"type": "progress", "aiName": ai_name, "percent": 90})
                    await broadcast({"type": "log", "aiName": ai_name, "message": f"[{ai_name}] 결과: {result}"})
                    await broadcast({"type": "progress", "aiName": ai_name, "percent": 100})
                    await broadcast({"type": "status", "aiName": ai_name, "status": "COMPLETED"})
                    agent_states[ai_name] = "COMPLETED"

                except Exception as e:
                    await broadcast({"type": "log", "aiName": ai_name, "message": f"[오류] {str(e)}"})
                    await broadcast({"type": "status", "aiName": ai_name, "status": "STOPPED"})
                    agent_states[ai_name] = "STOPPED"

            elif action == "pause":
                agent_states[ai_name] = "STOPPED"
                await broadcast({"type": "status", "aiName": ai_name, "status": "STOPPED"})

            elif action == "resume":
                agent_states[ai_name] = "RUNNING"
                await broadcast({"type": "status", "aiName": ai_name, "status": "RUNNING"})

            elif action == "kill":
                agent_states.pop(ai_name, None)

    except WebSocketDisconnect:
        connected_clients.remove(websocket)
