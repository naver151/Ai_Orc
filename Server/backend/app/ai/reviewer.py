"""
리뷰어 AI 모듈 — LangChain 기반

graph_runner.py의 review_node에서 호출됩니다.
오케스트레이션 최종 결과물을 검토하여 PASS/FAIL 판정을 내립니다.
"""

from __future__ import annotations
import re

REVIEWER_SYSTEM_PROMPT = """당신은 AI 팀의 결과물을 검토하는 전문 리뷰어입니다.
주어진 사용자 요청과 AI 팀의 최종 결과물을 꼼꼼히 평가하여 아래 형식으로 리뷰를 작성하세요.

📋 **작업 이해도**: 요청을 정확히 이해하고 수행했는지 평가
✅ **잘 된 점**: 결과물에서 우수한 부분을 구체적으로 서술
⚠️ **개선 필요**: 부족하거나 잘못된 부분을 구체적으로 서술
🎯 **품질 점수**: X / 10
📌 **최종 판정**: PASS 또는 FAIL

판정 기준:
- PASS: 점수 7점 이상, 사용자 요구사항을 충분히 충족
- FAIL: 점수 6점 이하, 중요한 오류·누락·오해 존재

⚠️ 반드시 마지막 줄을 아래 형식 중 하나로 끝내세요:
📌 **최종 판정**: PASS
📌 **최종 판정**: FAIL"""

# 판정 추출 정규식
_VERDICT_RE = re.compile(r"최종\s*판정[^\n]*?(PASS|FAIL)", re.IGNORECASE)


def build_review_prompt(user_prompt: str, synthesis: str, retry_count: int) -> str:
    """리뷰 요청 프롬프트를 생성합니다."""
    retry_note = f"\n\n⚠️ 이번이 {retry_count + 1}번째 시도입니다. 더욱 엄격하게 검토해주세요." if retry_count > 0 else ""
    return (
        f"## 사용자 요청\n{user_prompt}\n\n"
        f"## AI 팀 최종 결과물\n{synthesis}"
        f"{retry_note}\n\n"
        "위 결과물을 꼼꼼히 검토하고 리뷰를 작성해주세요."
    )


def parse_verdict(review_text: str) -> str:
    """리뷰 텍스트에서 PASS/FAIL 판정을 추출합니다."""
    match = _VERDICT_RE.search(review_text)
    if match:
        return match.group(1).lower()
    # 판정을 찾지 못하면 기본적으로 pass
    return "pass"
    