"""
리뷰어 AI 모듈

각 에이전트의 결과물을 자동으로 검토하고 품질을 검증합니다.
에이전트 응답이 완료되면 리뷰어가 호출되어 스트리밍으로 리뷰를 제공합니다.
"""

from .providers.base import AIProvider

REVIEWER_SYSTEM_PROMPT = """당신은 AI 에이전트의 결과물을 검토하는 전문 리뷰어입니다.
주어진 작업 지시와 AI의 응답을 꼼꼼히 평가하여 아래 형식으로 리뷰를 작성하세요.

📋 **작업 이해도**: 에이전트가 작업을 제대로 이해했는지 평가
✅ **잘 된 점**: 응답에서 우수한 부분을 구체적으로 서술
⚠️ **개선 필요**: 부족하거나 잘못된 부분을 구체적으로 서술
🎯 **품질 점수**: X / 10
📌 **최종 판정**: PASS 또는 FAIL

판정 기준:
- PASS: 점수 7점 이상, 작업 요구사항을 충분히 충족
- FAIL: 점수 6점 이하, 중요한 오류·누락·오해가 존재

반드시 위 형식을 지켜 작성하세요."""


class ReviewerAgent:
    """결과물 검증을 담당하는 리뷰어 AI."""

    def __init__(self, provider: AIProvider):
        self.provider = provider

    async def review(
        self,
        original_task: str,
        agent_response: str,
        agent_name: str,
    ):
        """
        에이전트 응답을 스트리밍으로 리뷰합니다.

        Args:
            original_task: 에이전트에게 주어진 원래 작업 지시
            agent_response: 에이전트의 전체 응답 텍스트
            agent_name: 리뷰 대상 에이전트 이름
        """
        review_prompt = (
            f"아래는 [{agent_name}] 에이전트가 수행한 작업과 그 결과입니다.\n\n"
            f"## 작업 지시\n{original_task}\n\n"
            f"## 에이전트 응답\n{agent_response}\n\n"
            f"위 결과물을 꼼꼼히 검토하고 리뷰를 작성해주세요."
        )

        messages = [{"role": "user", "content": review_prompt}]

        async for chunk in self.provider.stream_chat(messages, REVIEWER_SYSTEM_PROMPT):
            yield chunk
