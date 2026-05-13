"""
WebSocket 플로우 테스트

에이전트 스폰 → 명령 → 상태 수신 흐름 검증.
실제 LLM 호출 없이 WS 프로토콜만 검증.
"""
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def ws_client():
    with TestClient(app) as c:
        yield c


class TestWebSocketProtocol:

    def test_connect(self, ws_client):
        """WS 연결 수립 확인."""
        with ws_client.websocket_connect("/ws") as ws:
            assert ws is not None   # 연결 성공

    def test_spawn_returns_ready(self, ws_client):
        """spawn 액션 → READY 상태 수신."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({
                "action":    "spawn",
                "aiName":    "TestAgent",
                "provider":  "github",
                "isManager": False,
                "role":      "tester",
            })
            msg = ws.receive_json()
            assert msg["type"]   == "status"
            assert msg["aiName"] == "TestAgent"
            assert msg["status"] == "READY"

    def test_spawn_manager(self, ws_client):
        """관리자 spawn."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({
                "action":    "spawn",
                "aiName":    "Manager",
                "provider":  "github",
                "isManager": True,
                "role":      "manager",
            })
            msg = ws.receive_json()
            assert msg["type"]   == "status"
            assert msg["status"] == "READY"

    def test_pause_resume(self, ws_client):
        """pause → STOPPED, resume → RUNNING."""
        with ws_client.websocket_connect("/ws") as ws:
            # spawn
            ws.send_json({
                "action": "spawn", "aiName": "PauseAgent",
                "provider": "github", "isManager": False, "role": "",
            })
            ws.receive_json()  # READY

            # pause
            ws.send_json({"action": "pause", "aiName": "PauseAgent"})
            msg = ws.receive_json()
            assert msg["type"]   == "status"
            assert msg["status"] == "STOPPED"

            # resume
            ws.send_json({"action": "resume", "aiName": "PauseAgent"})
            msg = ws.receive_json()
            assert msg["type"]   == "status"
            assert msg["status"] == "RUNNING"

    def test_set_distribution_mode(self, ws_client):
        """set_distribution 액션 → distribution_mode_set 수신."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({
                "action": "spawn", "aiName": "DistAgent",
                "provider": "github", "isManager": True, "role": "",
            })
            ws.receive_json()  # READY

            ws.send_json({
                "action": "set_distribution",
                "aiName": "DistAgent",
                "mode":   "manual",
            })
            msg = ws.receive_json()
            assert msg["type"] == "distribution_mode_set"
            assert msg["mode"] == "manual"

    def test_set_distribution_auto(self, ws_client):
        """auto 모드 전환."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({
                "action": "spawn", "aiName": "DistAgent2",
                "provider": "claude", "isManager": True, "role": "",
            })
            ws.receive_json()  # READY

            ws.send_json({
                "action": "set_distribution",
                "aiName": "DistAgent2",
                "mode":   "auto",
            })
            msg = ws.receive_json()
            assert msg["type"] == "distribution_mode_set"
            assert msg["mode"] == "auto"

    def test_invalid_action_ignored(self, ws_client):
        """알 수 없는 액션은 무시되고 연결 유지."""
        with ws_client.websocket_connect("/ws") as ws:
            # 먼저 spawn으로 ai_name 등록 후 무효 액션 전송
            ws.send_json({
                "action": "spawn", "aiName": "IgnoreAgent",
                "provider": "github", "isManager": False, "role": "",
            })
            ws.receive_json()  # READY 소비

            ws.send_json({
                "action": "unknown_action",
                "aiName": "IgnoreAgent",
            })
            # 응답 없음 = 무시됨. 연결은 유지되어야 하므로
            # 다시 정상 액션 전송이 가능해야 함
            ws.send_json({"action": "pause", "aiName": "IgnoreAgent"})
            msg = ws.receive_json()
            assert msg["type"] == "status"

    def test_empty_aiName_ignored(self, ws_client):
        """aiName이 없으면 무시 (연결 유지)."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"action": "spawn", "aiName": ""})
            # 응답 없이 연결 유지 — 타임아웃 방지를 위해 정상 요청 후 확인
            ws.send_json({
                "action": "spawn", "aiName": "ValidAgent",
                "provider": "github", "isManager": False, "role": "",
            })
            msg = ws.receive_json()
            assert msg["aiName"] == "ValidAgent"

    def test_kill_removes_agent(self, ws_client):
        """kill 후 동일 aiName으로 spawn 시 새 슬롯 생성."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({
                "action": "spawn", "aiName": "KillAgent",
                "provider": "github", "isManager": False, "role": "",
            })
            ws.receive_json()  # READY

            ws.send_json({"action": "kill", "aiName": "KillAgent"})
            # kill은 즉시 응답 없음

            # 다시 spawn → 새 READY
            ws.send_json({
                "action": "spawn", "aiName": "KillAgent",
                "provider": "github", "isManager": False, "role": "",
            })
            msg = ws.receive_json()
            assert msg["status"] == "READY"

    def test_user_review_flow(self, ws_client):
        """user_review 액션이 정상 처리됨 (이벤트만 설정, 오류 없음)."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({
                "action": "spawn", "aiName": "ReviewManager",
                "provider": "github", "isManager": True, "role": "",
            })
            ws.receive_json()  # READY

            # user_review 전송 (대기 중인 이벤트가 없어도 오류 없어야 함)
            ws.send_json({
                "action":      "user_review",
                "aiName":      "ReviewManager",
                "managerName": "ReviewManager",
                "approved":    True,
                "feedback":    "",
            })
            # 응답 없음 (이벤트 set만 되고 WS 메시지 없음) — 연결은 유지
            ws.send_json({"action": "pause", "aiName": "ReviewManager"})
            msg = ws.receive_json()
            assert msg["type"] == "status"
