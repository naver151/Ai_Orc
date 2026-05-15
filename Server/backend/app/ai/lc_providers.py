"""
LangChain ChatModel 팩토리 + WebSocket 스트리밍 콜백 핸들러

기존 custom provider들을 LangChain BaseChatModel로 통합.
- get_lc_model(provider_key) → BaseChatModel
- WSStreamHandler: on_llm_new_token 이벤트를 WebSocket으로 push
"""

from __future__ import annotations
import asyncio
import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv(override=True, encoding="utf-8")

# GitHub Models 동시 요청 제한
# GitHub 무료 티어 rate limit이 빡빡하므로 순차 실행(1)으로 충돌 방지
# 유료 API(Claude/GPT/Gemini) 사용 시 2~4로 늘려도 됨
_LLM_SEMAPHORE = asyncio.Semaphore(1)


async def safe_ainvoke(
    model: BaseChatModel,
    messages: list,
    config: RunnableConfig | None = None,
    max_retries: int = 4,
    base_delay: float = 2.0,
    timeout: float = 120.0,
):
    """
    Rate limit(429) 보호 래퍼.
    - Semaphore(2): 동시 호출을 2개 이하로 제한
    - 지수 백오프: 429 발생 시 2s → 4s → 8s → 16s 후 재시도
    - timeout: 단일 호출 최대 대기 시간 (기본 120초)
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with _LLM_SEMAPHORE:
                coro = (
                    model.ainvoke(messages, config=config)
                    if config is not None
                    else model.ainvoke(messages)
                )
                return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"LLM 응답 시간 초과 ({timeout}초)")
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RateLimit" in msg or "rate_limit" in msg.lower():
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
                last_exc = e
                continue
            raise   # 429 외 오류는 즉시 재발생
    raise last_exc  # type: ignore[misc]

GITHUB_ENDPOINT = "https://models.inference.ai.azure.com"

_GITHUB_ALIASES: dict[str, str] = {
    "github":             os.getenv("GITHUB_MODEL", "gpt-4.1"),  # .env의 GITHUB_MODEL 우선
    "github-gpt41":       "gpt-4.1",
    "github-gpt41-mini":  "gpt-4.1-mini",
    "github-gpt41-nano":  "gpt-4.1-nano",
    "github-gpt4o":       "gpt-4o",
    "github-gpt4o-mini":  "gpt-4o-mini",
    "github-o1":          "o1",
    "github-o1-mini":     "o1-mini",
    "github-o3-mini":     "o3-mini",
    "github-llama":       "Meta-Llama-3.1-70B-Instruct",
    "github-llama-70b":   "Meta-Llama-3.1-70B-Instruct",
    "github-llama-8b":    "Meta-Llama-3.1-8B-Instruct",
    "github-mistral":     "Mistral-large",
    "github-phi":         "Phi-3.5-mini-instruct",
}


# ── WebSocket 스트리밍 콜백 ────────────────────────────────────────────────────

class WSStreamHandler(AsyncCallbackHandler):
    """
    LangChain LLM이 토큰을 생성할 때마다 WebSocket으로 실시간 push.
    on_llm_new_token → { type: "log", aiName, message: token }
    """

    def __init__(self, websocket: Any, ai_name: str):
        self.ws = websocket
        self.ai_name = ai_name

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        if token:
            await self.ws.send_json({
                "type": "log",
                "aiName": self.ai_name,
                "message": token,
            })

    async def on_llm_start(self, serialized: dict, prompts: list, **kwargs) -> None:
        await self.ws.send_json({
            "type": "status",
            "aiName": self.ai_name,
            "status": "RUNNING",
        })
        await self.ws.send_json({
            "type": "progress",
            "aiName": self.ai_name,
            "percent": 0,
        })

    async def on_llm_end(self, response: Any, **kwargs) -> None:
        await self.ws.send_json({
            "type": "status",
            "aiName": self.ai_name,
            "status": "COMPLETED",
        })
        await self.ws.send_json({
            "type": "progress",
            "aiName": self.ai_name,
            "percent": 100,
        })

    async def on_llm_error(self, error: Exception, **kwargs) -> None:
        await self.ws.send_json({
            "type": "log",
            "aiName": self.ai_name,
            "message": f"[오류] {type(error).__name__}: {error}",
        })


# ── 진행률 추적 핸들러 ────────────────────────────────────────────────────────

class ProgressWSStreamHandler(WSStreamHandler):
    """문자 수 기반 진행률을 함께 전송."""

    def __init__(self, websocket: Any, ai_name: str):
        super().__init__(websocket, ai_name)
        self._char_count = 0

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        if token:
            self._char_count += len(token)
            await self.ws.send_json({"type": "log", "aiName": self.ai_name, "message": token})
            pct = min(int(self._char_count / 20), 99)
            await self.ws.send_json({"type": "progress", "aiName": self.ai_name, "percent": pct})


# ── LangChain 모델 팩토리 ─────────────────────────────────────────────────────

def _github_model(streaming: bool, cb: list) -> BaseChatModel:
    """GitHub Models 기본 모델 (폴백용)."""
    return ChatOpenAI(
        model=os.getenv("GITHUB_MODEL", "gpt-4o"),
        api_key=os.getenv("GITHUB_TOKEN", ""),
        base_url=GITHUB_ENDPOINT,
        streaming=streaming,
        callbacks=cb,
    )


def get_lc_model(
    provider_key: str,
    streaming: bool = False,
    callbacks: list | None = None,
) -> BaseChatModel:
    """
    provider_key → LangChain BaseChatModel 반환.
    API 키가 없는 provider는 GitHub Models로 자동 폴백.

    streaming=True + callbacks=[WSStreamHandler(...)] 조합으로
    on_llm_new_token 이벤트를 WebSocket으로 push.
    """
    pk = provider_key.lower()
    cb = callbacks or []

    # ── GitHub Models (OpenAI 호환 엔드포인트) ──
    if pk in _GITHUB_ALIASES:
        return ChatOpenAI(
            model=_GITHUB_ALIASES[pk],
            api_key=os.getenv("GITHUB_TOKEN", ""),
            base_url=GITHUB_ENDPOINT,
            streaming=streaming,
            callbacks=cb,
        )

    # ── OpenAI ──
    if pk in ("gpt", "gpt-4o", "openai"):
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return _github_model(streaming, cb)
        return ChatOpenAI(
            model=os.getenv("FINETUNED_MODEL", "gpt-4o"),
            api_key=api_key,
            streaming=streaming,
            callbacks=cb,
        )

    # ── Anthropic Claude ──
    if pk == "claude":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return _github_model(streaming, cb)   # 키 없으면 GitHub 폴백
        return ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            api_key=api_key,
            streaming=streaming,
            callbacks=cb,
        )

    # ── Google Gemini ──
    if pk == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return _github_model(streaming, cb)   # 키 없으면 GitHub 폴백
        return ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",             # gemini-pro 지원 종료 대응
            google_api_key=api_key,
            streaming=streaming,
            callbacks=cb,
        )

    # ── 기본값: GitHub GPT-4o ──
    return _github_model(streaming, cb)
