"""
오케스트레이션 로그 REST API
- GET  /orchestration-logs          전체 목록 (최신순, 페이지네이션)
- GET  /orchestration-logs/{id}     단건 상세
- PATCH /orchestration-logs/{id}/rating   평점 업데이트 (파인튜닝 필터용)
- GET  /orchestration-logs/export   rating >= threshold 인 레코드를 JSONL로 다운로드
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from io import StringIO

from app.db import get_db
from app.models import OrchestrationLog

router = APIRouter(prefix="/orchestration-logs", tags=["orch-logs"])


# ── 응답 스키마 ─────────────────────────────────────────────────

class OrchLogSummary(BaseModel):
    id: int
    created_at: str
    manager_name: str
    user_prompt: str
    plan_summary: str | None
    rating: int | None

    class Config:
        from_attributes = True


class OrchLogDetail(OrchLogSummary):
    worker_names: list
    subtasks: list
    worker_results: list
    synthesis_result: str | None


class RatingUpdate(BaseModel):
    rating: int = Field(..., ge=1, le=5)


# ── 헬퍼 ───────────────────────────────────────────────────────

def _to_detail(log: OrchestrationLog) -> OrchLogDetail:
    return OrchLogDetail(
        id=log.id,
        created_at=log.created_at.isoformat() if log.created_at else "",
        manager_name=log.manager_name,
        user_prompt=log.user_prompt,
        plan_summary=log.plan_summary,
        rating=log.rating,
        worker_names=json.loads(log.worker_names or "[]"),
        subtasks=json.loads(log.subtasks_json or "[]"),
        worker_results=json.loads(log.worker_results_json or "[]"),
        synthesis_result=log.synthesis_result,
    )


# ── 엔드포인트 ─────────────────────────────────────────────────

@router.get("", response_model=list[OrchLogSummary])
def list_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(OrchestrationLog)
        .order_by(OrchestrationLog.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        OrchLogSummary(
            id=log.id,
            created_at=log.created_at.isoformat() if log.created_at else "",
            manager_name=log.manager_name,
            user_prompt=log.user_prompt,
            plan_summary=log.plan_summary,
            rating=log.rating,
        )
        for log in logs
    ]


@router.get("/export")
def export_logs(
    min_rating: int = Query(4, ge=1, le=5, description="이 평점 이상인 레코드만 내보내기"),
    db: Session = Depends(get_db),
):
    """파인튜닝용 JSONL 내보내기. 각 줄 = {prompt, completion} 형식."""
    logs = (
        db.query(OrchestrationLog)
        .filter(OrchestrationLog.rating >= min_rating)
        .order_by(OrchestrationLog.created_at.desc())
        .all()
    )

    buf = StringIO()
    for log in logs:
        record = {
            "prompt": log.user_prompt,
            "plan": log.plan_summary,
            "subtasks": json.loads(log.subtasks_json or "[]"),
            "worker_results": json.loads(log.worker_results_json or "[]"),
            "completion": log.synthesis_result or "",
            "rating": log.rating,
            "created_at": log.created_at.isoformat() if log.created_at else "",
        }
        buf.write(json.dumps(record, ensure_ascii=False) + "\n")

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=orchestration_logs.jsonl"},
    )


@router.get("/{log_id}", response_model=OrchLogDetail)
def get_log(log_id: int, db: Session = Depends(get_db)):
    log = db.query(OrchestrationLog).filter(OrchestrationLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="로그를 찾을 수 없습니다.")
    return _to_detail(log)


@router.patch("/{log_id}/rating", response_model=OrchLogDetail)
def update_rating(log_id: int, body: RatingUpdate, db: Session = Depends(get_db)):
    log = db.query(OrchestrationLog).filter(OrchestrationLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="로그를 찾을 수 없습니다.")
    log.rating = body.rating
    db.commit()
    db.refresh(log)
    return _to_detail(log)
