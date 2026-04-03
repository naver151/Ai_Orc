from app.ai_clients.base import BaseAIClient
from app.ai_clients.openai import OpenAIClient
from app.ai_clients.anthropic import AnthropicClient
from app.ai_clients.yolo import YOLOClient


def get_ai_client(provider: str, model: str) -> BaseAIClient:
    """provider에 따라 알맞은 AI 클라이언트 반환 (Celery 백그라운드 작업용 — 비스트리밍)"""
    if provider == "openai":
        return OpenAIClient(model=model)
    elif provider == "anthropic":
        return AnthropicClient(model=model)
    elif provider == "yolo":
        return YOLOClient(model=model)
    else:
        raise ValueError(f"지원하지 않는 AI provider: {provider}")
