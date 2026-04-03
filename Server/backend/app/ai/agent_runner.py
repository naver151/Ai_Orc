"""
에이전트 상태 관리 및 AI 스트리밍 실행 모듈.

각 AI 에이전트는 AgentState 객체로 표현되며,
- 대화 이력 (history)
- 일시 정지 / 재개 (asyncio.Event)
- 현재 실행 중인 asyncio Task
를 독립적으로 관리합니다.
"""

import asyncio
from typing import Optional

from fastapi import WebSocket

from .providers.base import AIProvider
from .providers.claude import ClaudeProvider
from .providers.openai_provider import OpenAIProvider
from .providers.gemini import GeminiProvider
from .providers.yolo_provider import YOLOProvider
from .providers.github_provider import GitHubProvider

# 프로바이더 이름 → 클래스 매핑
PROVIDER_MAP: dict[str, type[AIProvider]] = {
    # OpenAI
    "gpt": OpenAIProvider,
    "gpt-4o": OpenAIProvider,
    "openai": OpenAIProvider,
    # Anthropic
    "claude": ClaudeProvider,
    # Google
    "gemini": GeminiProvider,
    # GitHub Models (PAT 인증, 무료 할당량)
    "github": GitHubProvider,
    "github-gpt4o": lambda: GitHubProvider("gpt-4o"),
    "github-gpt4o-mini": lambda: GitHubProvider("gpt-4o-mini"),
    "github-llama": lambda: GitHubProvider("llama"),
    "github-llama-70b": lambda: GitHubProvider("llama-70b"),
    "github-llama-8b": lambda: GitHubProvider("llama-8b"),
    "github-mistral": lambda: GitHubProvider("mistral"),
    "github-phi": lambda: GitHubProvider("phi"),
    # YOLO
    "yolo": YOLOProvider,
    "yolov8n": YOLOProvider,
}


def get_provider(name: str) -> AIProvider:
    """프로바이더 이름으로 인스턴스를 생성합니다. 없으면 GitHubProvider 기본값."""
    entry = PROVIDER_MAP.get(name.lower(), GitHubProvider)
    # lambda(callable이지만 type이 아닌 경우)도 처리
    return entry() if callable(entry) else entry()


# ──────────────────────────────────────────────
# 에이전트 상태 클래스
# ──────────────────────────────────────────────

class AgentState:
    """단일 AI 에이전트의 실행 상태를 담는 객체."""

    def __init__(self, ai_name: str, provider_name: str = "claude"):
        self.ai_name = ai_name
        self.provider: AIProvider = get_provider(provider_name)
        self.history: list[dict] = []          # 대화 이력 {"role", "content"}
        self.system_prompt: str = ""           # 커스텀 페르소나
        self.status: str = "READY"
        self.current_task: Optional[asyncio.Task] = None
        self.current_task_text: str = ""       # 현재 수행 중인 작업 텍스트 (마우스오버용)
        self.is_killed: bool = False

        # Event가 set → 실행 중, clear → 일시 정지(대기)
        self._pause_event = asyncio.Event()
        self._pause_event.set()

    # ── 제어 메서드 ──────────────────────────────

    def pause(self) -> None:
        """스트리밍 루프를 다음 청크 이후 대기 상태로 만든다."""
        self._pause_event.clear()
        self.status = "STOPPED"

    def resume(self) -> None:
        """대기 중인 스트리밍 루프를 재개한다."""
        self._pause_event.set()
        self.status = "RUNNING"

    def kill(self) -> None:
        """실행 중인 Task를 취소하고 에이전트를 종료한다."""
        self.is_killed = True
        self._pause_event.set()  # 대기 중이면 언블록
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
        self.status = "STOPPED"

    async def wait_if_paused(self) -> None:
        """일시 정지 상태면 resume될 때까지 대기."""
        await self._pause_event.wait()


# ──────────────────────────────────────────────
# 에이전트 매니저
# ──────────────────────────────────────────────

class AgentManager:
    """모든 에이전트의 생성·조회·삭제를 담당하는 싱글턴 매니저."""

    def __init__(self):
        self._agents: dict[str, AgentState] = {}

    def get_or_create(self, ai_name: str, provider_name: str = "claude") -> AgentState:
        if ai_name not in self._agents:
            self._agents[ai_name] = AgentState(ai_name, provider_name)
        return self._agents[ai_name]

    def get(self, ai_name: str) -> Optional[AgentState]:
        return self._agents.get(ai_name)

    def remove(self, ai_name: str) -> None:
        if ai_name in self._agents:
            state = self._agents.pop(ai_name)
            state.kill()

    # ── 스트리밍 실행 ────────────────────────────

    async def run_prompt(
        self,
        ai_name: str,
        text: str,
        websocket: WebSocket,
    ) -> None:
        """
        사용자 메시지를 AI에 전송하고 응답을 청크 단위로 WebSocket에 스트리밍.

        WebSocket 메시지 형식:
          { type: "log",      aiName, message }   ← 응답 텍스트 조각
          { type: "progress", aiName, percent }   ← 진행률 (0~100)
          { type: "status",   aiName, status  }   ← RUNNING / COMPLETED
        """
        state = self.get(ai_name)
        if not state:
            return

        # 대화 이력에 사용자 메시지 추가
        state.history.append({"role": "user", "content": text})
        state.status = "RUNNING"
        state.current_task_text = text

        await websocket.send_json({"type": "status",   "aiName": ai_name, "status": "RUNNING"})
        await websocket.send_json({"type": "progress", "aiName": ai_name, "percent": 0})
        await websocket.send_json({"type": "current_task", "aiName": ai_name, "task": text})

        full_response = ""
        char_count = 0

        try:
            async for chunk in state.provider.stream_chat(
                state.history, state.system_prompt
            ):
                if state.is_killed:
                    break

                # 일시 정지 중이면 재개될 때까지 대기
                await state.wait_if_paused()

                if state.is_killed:
                    break

                full_response += chunk
                char_count += len(chunk)

                # 텍스트 조각 전송
                await websocket.send_json({
                    "type": "log",
                    "aiName": ai_name,
                    "message": chunk,
                })

                # 진행률: 2000자를 100%로 간주하는 러프한 추정치
                progress = min(int(char_count / 20), 99)
                await websocket.send_json({
                    "type": "progress",
                    "aiName": ai_name,
                    "percent": progress,
                })

        except asyncio.CancelledError:
            # kill() 호출로 취소된 경우 — 정상 처리
            pass
        except Exception as e:
            await websocket.send_json({
                "type": "log",
                "aiName": ai_name,
                "message": f"[오류] {type(e).__name__}: {e}",
            })
        finally:
            if full_response:
                state.history.append({"role": "assistant", "content": full_response})

            if not state.is_killed:
                state.status = "COMPLETED"
                state.current_task_text = ""
                await websocket.send_json({"type": "status",      "aiName": ai_name, "status": "COMPLETED"})
                await websocket.send_json({"type": "progress",    "aiName": ai_name, "percent": 100})
                await websocket.send_json({"type": "current_task","aiName": ai_name, "task": ""})


# 애플리케이션 전역 싱글턴
agent_manager = AgentManager()
