"""
적응형 분배 성능 통계 API

- GET /performance/stats    provider × task_type 평균 점수 + 리더보드
- GET /performance/trend    최근 N건 점수 시계열
- GET /performance/summary  시스템 전체 요약 (오케스트레이션 포함)
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import get_db
from app.models import AgentPerformance, OrchestrationLog

router = APIRouter(prefix="/performance", tags=["performance"])

# ── 메타데이터 ────────────────────────────────────────────────────────────────

PROVIDER_LABELS: dict[str, str] = {
    "github":  "GPT-4o",
    "claude":  "Claude",
    "gemini":  "Gemini",
    "search":  "웹검색",
    "crawler": "크롤러",
    "runner":  "코드실행",
    "ocr":     "OCR",
    "whisper": "Whisper",
}

PROVIDER_COLORS: dict[str, str] = {
    "github":  "#4caf82",
    "claude":  "#7c6dfa",
    "gemini":  "#f5a623",
    "search":  "#00b4d8",
    "crawler": "#0077b6",
    "runner":  "#06d6a0",
    "ocr":     "#ffd166",
    "whisper": "#ef476f",
}

TASK_TYPE_LABELS: dict[str, str] = {
    "code":     "코드 작성",
    "analysis": "분석·조사",
    "writing":  "문서 작성",
    "search":   "정보 수집",
    "general":  "일반",
}


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """
    provider × task_type 기준 평균 점수 집계.
    반환:
      leaderboard  — provider별 전체 평균 (내림차순)
      task_matrix  — task_type별 provider 점수 비교
      total_evaluations / overall_avg_score
    """
    rows = (
        db.query(
            AgentPerformance.provider,
            AgentPerformance.task_type,
            func.avg(AgentPerformance.score).label("avg_score"),
            func.count(AgentPerformance.id).label("count"),
        )
        .group_by(AgentPerformance.provider, AgentPerformance.task_type)
        .all()
    )

    # ── provider별 집계 ──────────────────────────────────────────
    provider_stats: dict[str, dict] = {}
    for row in rows:
        p = row.provider
        if p not in provider_stats:
            provider_stats[p] = {
                "provider":        p,
                "label":           PROVIDER_LABELS.get(p, p.upper()),
                "color":           PROVIDER_COLORS.get(p, "#888"),
                "total_count":     0,
                "total_score_sum": 0.0,
                "task_types":      {},
            }
        provider_stats[p]["total_count"]     += row.count
        provider_stats[p]["total_score_sum"] += float(row.avg_score) * row.count
        provider_stats[p]["task_types"][row.task_type] = {
            "avg":   round(float(row.avg_score), 2),
            "count": row.count,
            "label": TASK_TYPE_LABELS.get(row.task_type, row.task_type),
        }

    # leaderboard 정렬
    leaderboard = []
    for p, s in provider_stats.items():
        avg = s["total_score_sum"] / s["total_count"] if s["total_count"] else 0
        leaderboard.append({
            "provider":   p,
            "label":      s["label"],
            "color":      s["color"],
            "avg_score":  round(avg, 2),
            "count":      s["total_count"],
            "task_types": s["task_types"],
        })
    leaderboard.sort(key=lambda x: x["avg_score"], reverse=True)

    # ── task_type × provider 매트릭스 ────────────────────────────
    task_matrix: dict[str, dict] = {}
    for row in rows:
        tt = row.task_type
        if tt not in task_matrix:
            task_matrix[tt] = {
                "label":     TASK_TYPE_LABELS.get(tt, tt),
                "providers": {},
            }
        task_matrix[tt]["providers"][row.provider] = {
            "avg":   round(float(row.avg_score), 2),
            "count": row.count,
            "color": PROVIDER_COLORS.get(row.provider, "#888"),
        }

    # ── 전체 집계 ─────────────────────────────────────────────────
    total_count = sum(s["total_count"] for s in provider_stats.values())
    total_avg   = (
        sum(s["total_score_sum"] for s in provider_stats.values()) / total_count
        if total_count else 0
    )

    return {
        "leaderboard":       leaderboard,
        "task_matrix":       task_matrix,
        "total_evaluations": total_count,
        "overall_avg_score": round(total_avg, 2),
    }


@router.get("/trend")
def get_trend(
    limit: int = Query(60, ge=1, le=200),
    provider: str | None = Query(None, description="특정 provider만 필터 (없으면 전체)"),
    db: Session = Depends(get_db),
):
    """최근 N건 점수 시계열 (오래된 순)."""
    q = db.query(AgentPerformance).order_by(AgentPerformance.created_at.desc())
    if provider:
        q = q.filter(AgentPerformance.provider == provider)
    rows = q.limit(limit).all()
    rows.reverse()   # 오래된 것 → 최신

    return [
        {
            "id":         r.id,
            "provider":   r.provider,
            "label":      PROVIDER_LABELS.get(r.provider, r.provider.upper()),
            "color":      PROVIDER_COLORS.get(r.provider, "#888"),
            "task_type":  r.task_type,
            "task_label": TASK_TYPE_LABELS.get(r.task_type, r.task_type),
            "score":      r.score,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """시스템 전체 요약 — 상단 KPI 카드용."""
    total_perf = db.query(func.count(AgentPerformance.id)).scalar() or 0
    avg_perf   = db.query(func.avg(AgentPerformance.score)).scalar()

    total_orch  = db.query(func.count(OrchestrationLog.id)).scalar() or 0
    avg_rating  = db.query(func.avg(OrchestrationLog.rating)).scalar()

    # 오늘 UTC 기준
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_perf  = (
        db.query(func.count(AgentPerformance.id))
        .filter(AgentPerformance.created_at >= today_start)
        .scalar() or 0
    )
    today_orch  = (
        db.query(func.count(OrchestrationLog.id))
        .filter(OrchestrationLog.created_at >= today_start)
        .scalar() or 0
    )

    # provider 분포 (실행 횟수 기준)
    dist_rows = (
        db.query(
            AgentPerformance.provider,
            func.count(AgentPerformance.id).label("count"),
        )
        .group_by(AgentPerformance.provider)
        .all()
    )

    # task_type 분포
    task_rows = (
        db.query(
            AgentPerformance.task_type,
            func.count(AgentPerformance.id).label("count"),
        )
        .group_by(AgentPerformance.task_type)
        .all()
    )

    # 최근 7일 일별 실행 수 (SQLite 호환: func.date 사용)
    daily_rows = (
        db.query(
            func.date(AgentPerformance.created_at).label("day"),
            func.count(AgentPerformance.id).label("count"),
        )
        .group_by("day")
        .order_by("day")
        .limit(7)
        .all()
    )

    return {
        "total_evaluations":   total_perf,
        "avg_score":           round(float(avg_perf), 2) if avg_perf else 0,
        "total_orchestrations": total_orch,
        "avg_rating":          round(float(avg_rating), 2) if avg_rating else 0,
        "today_evaluations":   today_perf,
        "today_orchestrations": today_orch,
        "provider_distribution": [
            {
                "provider": r.provider,
                "label":    PROVIDER_LABELS.get(r.provider, r.provider.upper()),
                "color":    PROVIDER_COLORS.get(r.provider, "#888"),
                "count":    r.count,
            }
            for r in dist_rows
        ],
        "task_distribution": [
            {
                "task_type": r.task_type,
                "label":     TASK_TYPE_LABELS.get(r.task_type, r.task_type),
                "count":     r.count,
            }
            for r in task_rows
        ],
        "daily_counts": [
            {"day": str(r.day), "count": r.count}
            for r in daily_rows
        ],
    }
