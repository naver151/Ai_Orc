import os
from openai import OpenAI
from app.ai_clients.base import BaseAIClient


class OpenAIClient(BaseAIClient):
    def __init__(self, model: str = "gpt-4o"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model

    def run(self, role: str, task: str, context: list[str]) -> str:
        context_text = "\n".join(context) if context else "없음"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"당신은 {role} 역할의 AI 에이전트입니다.\n"
                        f"과거 유사 작업 기억:\n{context_text}"
                    )
                },
                {"role": "user", "content": task}
            ]
        )
        return response.choices[0].message.content
