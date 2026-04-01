import os
import anthropic
from app.ai_clients.base import BaseAIClient


class AnthropicClient(BaseAIClient):
    def __init__(self, model: str = "claude-3-5-sonnet-20241022"):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = model

    def run(self, role: str, task: str, context: list[str]) -> str:
        context_text = "\n".join(context) if context else "없음"

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=(
                f"당신은 {role} 역할의 AI 에이전트입니다.\n"
                f"과거 유사 작업 기억:\n{context_text}"
            ),
            messages=[
                {"role": "user", "content": task}
            ]
        )
        return message.content[0].text
