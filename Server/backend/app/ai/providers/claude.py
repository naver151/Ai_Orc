import os
from typing import AsyncGenerator

from anthropic import AsyncAnthropic

from .base import AIProvider


class ClaudeProvider(AIProvider):
    """Anthropic Claude 프로바이더 (스트리밍 지원)."""

    def __init__(self, model: str = "claude-3-5-sonnet-20241022"):
        self._model = model
        self._client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    @property
    def model_name(self) -> str:
        return self._model

    async def stream_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> AsyncGenerator[str, None]:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
