import os
from typing import AsyncGenerator

import google.generativeai as genai

from .base import AIProvider


class GeminiProvider(AIProvider):
    """Google Gemini 프로바이더 (스트리밍 지원)."""

    def __init__(self, model: str = "gemini-1.5-pro"):
        self._model_name = model
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self._client = genai.GenerativeModel(model)

    @property
    def model_name(self) -> str:
        return self._model_name

    async def stream_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> AsyncGenerator[str, None]:
        # Gemini 대화 이력 포맷으로 변환 (마지막 메시지 제외)
        gemini_history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            gemini_history.append({"role": role, "parts": [msg["content"]]})

        # system_prompt는 첫 번째 user 턴 앞에 prepend
        last_content = messages[-1]["content"]
        if system_prompt and not gemini_history:
            last_content = f"{system_prompt}\n\n{last_content}"

        chat = self._client.start_chat(history=gemini_history)
        response = await chat.send_message_async(last_content, stream=True)

        async for chunk in response:
            if chunk.text:
                yield chunk.text
