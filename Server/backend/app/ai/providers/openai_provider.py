import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

from .base import AIProvider


class OpenAIProvider(AIProvider):
    """OpenAI GPT 프로바이더 (스트리밍 지원)."""

    def __init__(self, model: str = "gpt-4o"):
        self._model = model
        self._client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    @property
    def model_name(self) -> str:
        return self._model

    async def stream_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> AsyncGenerator[str, None]:
        # OpenAI는 system 메시지를 messages 리스트 맨 앞에 포함
        all_messages: list[dict] = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=all_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
