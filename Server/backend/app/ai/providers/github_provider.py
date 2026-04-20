"""
GitHub Models 프로바이더 (스트리밍 지원).

GitHub Personal Access Token(PAT)으로 인증하며
OpenAI SDK를 그대로 사용합니다 (base_url만 변경).

지원 모델 목록 (GITHUB_MODEL 환경변수로 교체 가능):
  - gpt-4o                          (OpenAI)
  - gpt-4o-mini                     (OpenAI)
  - meta-llama-3.1-405b-instruct    (Meta)
  - meta-llama-3.1-70b-instruct     (Meta)
  - meta-llama-3.1-8b-instruct      (Meta)
  - mistral-large                   (Mistral)
  - mistral-nemo                    (Mistral)
  - phi-3.5-mini-instruct           (Microsoft)
  - phi-3.5-moe-instruct            (Microsoft)
  - cohere-command-r-plus           (Cohere)
"""

import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from openai import AsyncOpenAI

from .base import AIProvider

# .env 파일 명시적 로드 (서버 시작 순서와 무관하게 항상 반영)
load_dotenv(override=True, encoding='utf-8')

# GitHub Models API 엔드포인트
GITHUB_MODELS_ENDPOINT = "https://models.inference.ai.azure.com"

# 단축 이름 → 실제 모델 ID 매핑
MODEL_ALIASES: dict[str, str] = {
    "gpt-4o":           "gpt-4o",
    "gpt-4o-mini":      "gpt-4o-mini",
    "llama-405b":       "meta-llama-3.1-405b-instruct",
    "llama-70b":        "meta-llama-3.1-70b-instruct",
    "llama-8b":         "meta-llama-3.1-8b-instruct",
    "llama":            "meta-llama-3.1-70b-instruct",
    "mistral-large":    "mistral-large",
    "mistral-nemo":     "mistral-nemo",
    "mistral":          "mistral-large",
    "phi-mini":         "phi-3.5-mini-instruct",
    "phi-moe":          "phi-3.5-moe-instruct",
    "phi":              "phi-3.5-mini-instruct",
    "cohere":           "cohere-command-r-plus",
}


def _resolve_model(name: str) -> str:
    """단축 이름을 실제 모델 ID로 변환합니다."""
    return MODEL_ALIASES.get(name.lower(), name)


class GitHubProvider(AIProvider):
    """GitHub Models 프로바이더 (스트리밍 지원)."""

    def __init__(self, model: str | None = None):
        # 우선순위: 생성자 인수 > GITHUB_MODEL 환경변수 > 기본값 gpt-4o
        raw_model = model or os.getenv("GITHUB_MODEL", "gpt-4o")
        self._model = _resolve_model(raw_model)

        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise RuntimeError(
                "GITHUB_TOKEN 환경변수가 설정되지 않았습니다.\n"
                "GitHub → Settings → Developer Settings → Personal access tokens 에서 발급하세요."
            )

        self._client = AsyncOpenAI(
            base_url=GITHUB_MODELS_ENDPOINT,
            api_key=token,
        )

    @property
    def model_name(self) -> str:
        return f"github/{self._model}"

    async def stream_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> AsyncGenerator[str, None]:
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
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
