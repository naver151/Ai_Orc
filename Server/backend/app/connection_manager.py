"""
WebSocket 연결 관리 모듈.
복수의 클라이언트 연결을 추적하고 브로드캐스트 기능을 제공합니다.
"""

from fastapi import WebSocket


class ConnectionManager:
    """활성 WebSocket 연결 목록을 관리하는 싱글턴 클래스."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        """연결된 모든 클라이언트에 메시지를 전송."""
        dead: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)


# 애플리케이션 전역 싱글턴
connection_manager = ConnectionManager()
