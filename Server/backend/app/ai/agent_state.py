"""
AgentState / AgentManager — 에이전트 제어 전용 모듈

graph_runner.py와 agent_runner.py 양쪽에서 import 가능하도록
LangGraph 의존성 없이 분리.
"""

from __future__ import annotations
import asyncio
from typing import Optional


class AgentState:
    """에이전트 슬롯의 제어 상태 (pause / resume / kill)."""

    def __init__(self, ai_name: str, provider_key: str = "github"):
        self.ai_name      = ai_name
        self.provider_key = provider_key
        self.status       = "READY"
        self.current_task: Optional[asyncio.Task] = None
        self.is_killed    = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 기본: 실행 가능 상태

    def pause(self) -> None:
        self._pause_event.clear()
        self.status = "STOPPED"

    def resume(self) -> None:
        self._pause_event.set()
        self.status = "RUNNING"

    def kill(self) -> None:
        self.is_killed = True
        self._pause_event.set()  # 대기 중이면 깨워서 종료
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
        self.status = "STOPPED"

    async def wait_if_paused(self) -> None:
        """pause 상태면 resume 될 때까지 대기."""
        await self._pause_event.wait()

    @property
    def model_name(self) -> str:
        return self.provider_key


class AgentManager:
    """에이전트 슬롯 레지스트리."""

    def __init__(self):
        self._agents: dict[str, AgentState] = {}

    def get_or_create(self, ai_name: str, provider_key: str = "github") -> AgentState:
        if ai_name not in self._agents:
            self._agents[ai_name] = AgentState(ai_name, provider_key)
        else:
            self._agents[ai_name].provider_key = provider_key
        return self._agents[ai_name]

    def get(self, ai_name: str) -> Optional[AgentState]:
        return self._agents.get(ai_name)

    def remove(self, ai_name: str) -> None:
        if ai_name in self._agents:
            self._agents.pop(ai_name).kill()

    def is_manager(self, ai_name: str) -> bool:
        if not self._agents:
            return False
        return list(self._agents.keys())[0] == ai_name

    def get_worker_names(self, manager_name: str) -> list[str]:
        return [n for n in self._agents if n != manager_name]

    def get_provider_map(self) -> dict[str, str]:
        return {name: s.provider_key for name, s in self._agents.items()}


# 싱글턴 — agent_runner, graph_runner 양쪽에서 공유
agent_manager = AgentManager()
