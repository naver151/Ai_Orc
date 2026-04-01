from abc import ABC, abstractmethod


class BaseAIClient(ABC):
    """모든 AI 클라이언트가 따라야 할 공통 인터페이스"""

    @abstractmethod
    def run(self, role: str, task: str, context: list[str]) -> str:
        """
        AI에게 작업 요청
        - role: 에이전트 역할 (예: "백엔드 개발자")
        - task: 수행할 작업 내용
        - context: 과거 기억 (ChromaDB에서 검색된 유사 작업들)
        """
        pass
