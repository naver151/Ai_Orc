from abc import ABC, abstractmethod
from typing import AsyncGenerator


class AIProvider(ABC):
    """모든 AI 프로바이더가 구현해야 하는 공통 인터페이스."""

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        대화 메시지를 받아 응답을 토큰 단위로 스트리밍합니다.

        Args:
            messages: [{"role": "user"|"assistant", "content": str}, ...] 형식의 대화 이력
            system_prompt: 에이전트에게 부여할 시스템 지시사항 (선택)

        Yields:
            응답 텍스트 조각 (chunk)
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """현재 사용 중인 모델 식별자."""
        ...
