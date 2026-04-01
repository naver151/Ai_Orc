from app.ai_clients.base import BaseAIClient
from app.ai_clients.openai import OpenAIClient
from app.ai_clients.anthropic import AnthropicClient


def get_ai_client(provider: str, model: str) -> BaseAIClient:
    """provider에 따라 알맞은 AI 클라이언트 반환"""
    if provider == "openai":
        return OpenAIClient(model=model)
    elif provider == "anthropic":
        return AnthropicClient(model=model)
    # 나중에 추가 예정
    # elif provider == "gemini":
    #     return GeminiClient(model=model)
    else:
        raise ValueError(f"지원하지 않는 AI provider: {provider}")
