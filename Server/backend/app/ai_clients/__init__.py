from app.ai_clients.base import BaseAIClient
from app.ai_clients.openai import OpenAIClient
from app.ai_clients.anthropic import AnthropicClient
from app.ai_clients.yolo import YOLOClient


def get_ai_client(provider: str, model: str) -> BaseAIClient:
    """provider에 따라 알맞은 AI 클라이언트 반환 (Celery 백그라운드 작업용 — 비스트리밍)"""
    p = provider.lower()
    if p in ("openai", "gpt", "github", "github-gpt4o", "github-gpt4o-mini"):
        return OpenAIClient(model=model)
    elif p in ("anthropic", "claude"):
        return AnthropicClient(model=model)
    elif p == "yolo":
        return YOLOClient(model=model)
    else:
        # 알 수 없는 provider는 OpenAI로 폴백
        return OpenAIClient(model="gpt-4o")
