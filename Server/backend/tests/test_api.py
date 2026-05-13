"""
REST API 단위 테스트

커버리지:
  - 오케스트레이션 로그 CRUD
  - 성능 통계 API (stats / trend / summary)
  - 적응형 분배 DB 저장 로직
  - 프로젝트 / 에이전트 / 태스크 CRUD
"""
import pytest
from app.models import AgentPerformance, OrchestrationLog


# ═══════════════════════════════════════════════════════════════
# 헬스체크
# ═══════════════════════════════════════════════════════════════

class TestHealth:
    def test_root(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "running" in res.json()["message"].lower()

    def test_health(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


# ═══════════════════════════════════════════════════════════════
# 오케스트레이션 로그
# ═══════════════════════════════════════════════════════════════

class TestOrchestrationLogs:
    def test_list_empty(self, client):
        res = client.get("/orchestration-logs")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_save_ui_log(self, client):
        payload = {
            "request": "파이썬으로 REST API 만들어줘",
            "agents": [
                {"name": "Alpha", "roleKey": "developer", "task": "API 설계", "aiType": "claude"},
                {"name": "Beta",  "roleKey": "coder",     "task": "코드 구현", "aiType": "gpt"},
            ],
            "worker_results": ["FastAPI 엔드포인트 설계 완료", "코드 구현 완료"],
            "synthesis_result": "REST API 전체 구현 완료",
        }
        res = client.post("/orchestration-logs/ui", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["user_prompt"] == payload["request"]
        assert data["id"] is not None
        return data["id"]

    def test_get_log_detail(self, client):
        # 먼저 로그 생성
        payload = {
            "request": "상세 테스트 로그",
            "agents": [{"name": "Test", "roleKey": "r", "task": "t", "aiType": "claude"}],
            "worker_results": ["결과"],
            "synthesis_result": "종합",
        }
        create_res = client.post("/orchestration-logs/ui", json=payload)
        log_id = create_res.json()["id"]

        res = client.get(f"/orchestration-logs/{log_id}")
        assert res.status_code == 200
        assert res.json()["id"] == log_id

    def test_get_log_not_found(self, client):
        res = client.get("/orchestration-logs/99999")
        assert res.status_code == 404

    def test_update_rating(self, client):
        # 로그 생성
        payload = {
            "request": "평점 테스트",
            "agents": [{"name": "A", "roleKey": "r", "task": "t", "aiType": "gpt"}],
            "worker_results": ["ok"],
            "synthesis_result": "",
        }
        log_id = client.post("/orchestration-logs/ui", json=payload).json()["id"]

        # 평점 업데이트
        res = client.patch(f"/orchestration-logs/{log_id}/rating", json={"rating": 5})
        assert res.status_code == 200
        assert res.json()["rating"] == 5

    def test_rating_out_of_range(self, client):
        # 1~5 범위 초과
        payload = {
            "request": "범위 테스트",
            "agents": [{"name": "A", "roleKey": "r", "task": "t", "aiType": "gpt"}],
            "worker_results": ["ok"],
            "synthesis_result": "",
        }
        log_id = client.post("/orchestration-logs/ui", json=payload).json()["id"]
        res = client.patch(f"/orchestration-logs/{log_id}/rating", json={"rating": 6})
        assert res.status_code == 422    # 유효성 오류

    def test_list_pagination(self, client):
        res = client.get("/orchestration-logs?skip=0&limit=5")
        assert res.status_code == 200
        assert len(res.json()) <= 5


# ═══════════════════════════════════════════════════════════════
# 성능 통계 API
# ═══════════════════════════════════════════════════════════════

class TestPerformanceAPI:

    def _seed_performance(self, db):
        """테스트용 성능 데이터 삽입."""
        records = [
            # claude — code (6건)
            *[AgentPerformance(task_type="code", provider="claude", score=s)
              for s in [9, 8, 9, 7, 8, 9]],
            # github — code (6건)
            *[AgentPerformance(task_type="code", provider="github", score=s)
              for s in [7, 6, 8, 7, 6, 7]],
            # claude — analysis (5건)
            *[AgentPerformance(task_type="analysis", provider="claude", score=s)
              for s in [8, 9, 7, 8, 9]],
        ]
        db.add_all(records)
        db.commit()

    def test_stats_empty(self, client):
        res = client.get("/performance/stats")
        assert res.status_code == 200
        data = res.json()
        assert "leaderboard" in data
        assert "task_matrix" in data
        assert "total_evaluations" in data

    def test_stats_with_data(self, client, db):
        self._seed_performance(db)

        res = client.get("/performance/stats")
        assert res.status_code == 200
        data = res.json()

        assert data["total_evaluations"] >= 17
        assert len(data["leaderboard"]) >= 2

        # claude가 github보다 높아야 함 (code: 8.33 vs 6.83)
        providers = [l["provider"] for l in data["leaderboard"]]
        assert providers.index("claude") < providers.index("github")

        # task_matrix에 code 항목 존재
        assert "code" in data["task_matrix"]

    def test_trend_empty(self, client):
        res = client.get("/performance/trend")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_trend_with_limit(self, client, db):
        self._seed_performance(db)

        res = client.get("/performance/trend?limit=5")
        assert res.status_code == 200
        data = res.json()
        assert len(data) <= 5
        # 각 항목에 필수 필드 존재
        for item in data:
            assert "provider" in item
            assert "score" in item
            assert "task_type" in item
            assert 1 <= item["score"] <= 10

    def test_trend_provider_filter(self, client, db):
        self._seed_performance(db)

        res = client.get("/performance/trend?provider=claude&limit=20")
        assert res.status_code == 200
        data = res.json()
        assert all(d["provider"] == "claude" for d in data)

    def test_summary(self, client):
        res = client.get("/performance/summary")
        assert res.status_code == 200
        data = res.json()
        assert "total_evaluations" in data
        assert "total_orchestrations" in data
        assert "avg_score" in data
        assert "provider_distribution" in data
        assert "task_distribution" in data
        assert "daily_counts" in data


# ═══════════════════════════════════════════════════════════════
# 적응형 분배 로직 단위 테스트
# ═══════════════════════════════════════════════════════════════

class TestAdaptiveDistribution:
    """graph_runner의 분배 유틸 함수 직접 테스트."""

    def test_classify_task_type_code(self):
        from app.ai.graph_runner import _classify_task_type
        assert _classify_task_type("파이썬 코드 구현해줘") == "code"
        assert _classify_task_type("REST API 개발") == "code"
        assert _classify_task_type("implement login function") == "code"

    def test_classify_task_type_analysis(self):
        from app.ai.graph_runner import _classify_task_type
        assert _classify_task_type("시장 동향 분석") == "analysis"
        assert _classify_task_type("리서치 해줘") == "analysis"
        assert _classify_task_type("경쟁사 비교 검토") == "analysis"

    def test_classify_task_type_writing(self):
        from app.ai.graph_runner import _classify_task_type
        assert _classify_task_type("보고서 작성") == "writing"
        assert _classify_task_type("문서 정리해줘") == "writing"

    def test_classify_task_type_search(self):
        from app.ai.graph_runner import _classify_task_type
        assert _classify_task_type("웹 검색해서 수집") == "search"
        assert _classify_task_type("크롤링 해줘") == "search"

    def test_classify_task_type_general(self):
        from app.ai.graph_runner import _classify_task_type
        assert _classify_task_type("안녕하세요") == "general"
        assert _classify_task_type("뭐든 해줘") == "general"

    def test_get_provider_avg_scores_insufficient_data(self, db):
        """데이터 5건 미만 → None 반환."""
        # 4건만 삽입
        for s in [7, 8, 9, 6]:
            db.add(AgentPerformance(task_type="general", provider="test_prov", score=s))
        db.commit()

        from app.ai.graph_runner import _get_provider_avg_scores
        scores = _get_provider_avg_scores("general", ["test_prov"])
        assert scores["test_prov"] is None   # 데이터 부족

    def test_get_provider_avg_scores_sufficient_data(self, db):
        """데이터 5건 이상 → 평균값 반환."""
        for s in [8, 9, 7, 8, 9, 8]:
            db.add(AgentPerformance(task_type="code_test", provider="claude_t", score=s))
        db.commit()

        from app.ai.graph_runner import _get_provider_avg_scores
        scores = _get_provider_avg_scores("code_test", ["claude_t"], db=db)
        avg = scores["claude_t"]
        assert avg is not None
        assert 7.0 <= avg <= 9.5

    def test_epsilon_greedy_returns_valid_provider(self, db):
        """epsilon-greedy가 항상 available_providers 중 하나를 반환."""
        providers = ["claude", "github"]
        for p in providers:
            for s in [8, 7, 9, 8, 7, 8]:   # 6건씩
                db.add(AgentPerformance(task_type="eg_test", provider=p, score=s))
        db.commit()

        from app.ai.graph_runner import _epsilon_greedy_provider
        for _ in range(20):   # 여러 번 호출해도 유효한 provider
            result = _epsilon_greedy_provider("eg_test", providers)
            if result is not None:
                assert result in providers

    def test_save_performance_sync(self, db):
        """점수 저장 함수 정상 동작 확인."""
        from app.ai.graph_runner import _save_performance_sync
        _save_performance_sync("code", "claude", 9)

        row = db.query(AgentPerformance).filter(
            AgentPerformance.provider == "claude",
            AgentPerformance.task_type == "code",
            AgentPerformance.score == 9,
        ).first()
        assert row is not None


# ═══════════════════════════════════════════════════════════════
# 프로젝트 / 에이전트 / 태스크 CRUD
# ═══════════════════════════════════════════════════════════════

class TestProjectCRUD:
    def test_create_project(self, client):
        res = client.post("/projects/", json={
            "title": "테스트 프로젝트",
            "description": "pytest에서 생성된 테스트 프로젝트",
        })
        assert res.status_code in (200, 201)
        assert res.json()["title"] == "테스트 프로젝트"

    def test_list_projects(self, client):
        res = client.get("/projects/")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_get_project_not_found(self, client):
        res = client.get("/projects/99999")
        assert res.status_code == 404
