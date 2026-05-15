"""
워크스페이스 파일시스템 API

프로젝트마다 /workspaces/{project_id}/ 디렉터리를 관리한다.

엔드포인트:
  POST   /projects/                                   프로젝트 생성 (워크스페이스 자동 생성)
  GET    /projects/                                   프로젝트 목록
  GET    /projects/{id}                               프로젝트 상세
  GET    /projects/{id}/workspace/tree                파일 트리 (JSON)
  GET    /projects/{id}/workspace/file                파일 내용 읽기 (?path=src/main.py)
  DELETE /projects/{id}/workspace/file                파일 삭제 (?path=src/main.py)
  GET    /projects/{id}/context                       plan_node 주입용 프로젝트 요약

  GET    /projects/{id}/milestones                    마일스톤 목록 (태스크 포함)
  POST   /projects/{id}/milestones                    마일스톤 생성
  PATCH  /projects/{id}/milestones/{ms_id}            마일스톤 수정
  DELETE /projects/{id}/milestones/{ms_id}            마일스톤 삭제
  POST   /projects/{id}/milestones/{ms_id}/tasks      태스크 생성
  PATCH  /projects/{id}/tasks/{task_id}               태스크 수정
  DELETE /projects/{id}/tasks/{task_id}               태스크 삭제

  POST   /projects/{id}/sessions/start                세션 시작
  PATCH  /projects/{id}/sessions/{sid}/end            세션 종료 + 요약 저장
  GET    /projects/{id}/sessions                      최근 세션 목록
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ProjectModel, WorkspaceFile, Milestone, ProjectTask, ProjectSession

router = APIRouter(tags=["workspace"])

# ── 워크스페이스 루트 경로 ────────────────────────────────────────────────────
WORKSPACE_ROOT = Path(
    os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[2] / "workspaces"))
)
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)


def _project_root(project_id: int) -> Path:
    return WORKSPACE_ROOT / str(project_id)


def _get_project_or_404(project_id: int, db: Session) -> ProjectModel:
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    return project


# ── 프로젝트 생성 (워크스페이스 디렉터리 자동 생성) ────────────────────────

class ProjectCreate(BaseModel):
    title:       str
    description: str = ""


@router.post("/projects/")
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    """
    프로젝트를 생성하고 워크스페이스 디렉터리를 초기화한다.

    생성 구조:
      workspaces/{id}/
        src/          소스 코드
        tests/        테스트 코드
        docs/         문서
        .aiorc/       메타데이터 (에이전트 접근 불가)
    """
    project = ProjectModel(
        title=body.title,
        description=body.description,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # 워크스페이스 디렉터리 초기화
    root = _project_root(project.id)
    for subdir in ["src", "tests", "docs", ".aiorc"]:
        (root / subdir).mkdir(parents=True, exist_ok=True)

    # workspace_path DB 저장
    project.workspace_path = str(root)
    db.commit()

    return {
        "id":             project.id,
        "title":          project.title,
        "description":    project.description,
        "workspace_path": project.workspace_path,
        "created_at":     project.created_at.isoformat() if project.created_at else None,
    }


@router.get("/projects/")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(ProjectModel).order_by(ProjectModel.id.desc()).all()
    return [
        {
            "id":          p.id,
            "title":       p.title,
            "description": p.description,
            "created_at":  p.created_at.isoformat() if p.created_at else None,
        }
        for p in projects
    ]


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = _get_project_or_404(project_id, db)
    return {
        "id":             project.id,
        "title":          project.title,
        "description":    project.description,
        "workspace_path": project.workspace_path,
        "created_at":     project.created_at.isoformat() if project.created_at else None,
    }


class ProjectUpdate(BaseModel):
    title:       str | None = None
    description: str | None = None


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)):
    """프로젝트 이름·설명 수정."""
    project = _get_project_or_404(project_id, db)
    if body.title is not None:
        project.title = body.title.strip() or project.title
    if body.description is not None:
        project.description = body.description.strip()
    db.commit()
    db.refresh(project)
    return {
        "id":          project.id,
        "title":       project.title,
        "description": project.description,
        "created_at":  project.created_at.isoformat() if project.created_at else None,
    }


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """프로젝트 및 관련 데이터 전체 삭제."""
    import shutil
    project = _get_project_or_404(project_id, db)
    # 워크스페이스 디렉터리 삭제
    if project.workspace_path:
        ws = Path(project.workspace_path)
        if ws.exists():
            shutil.rmtree(ws, ignore_errors=True)
    db.delete(project)
    db.commit()
    return {"ok": True, "id": project_id}


# ── 파일 트리 ──────────────────────────────────────────────────────────────

def _build_tree(root: Path, current: Path) -> list[dict[str, Any]]:
    """디렉터리를 재귀 탐색해 트리 구조로 반환."""
    result = []
    try:
        entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return result

    for entry in entries:
        if entry.name.startswith("."):
            continue
        rel = str(entry.relative_to(root))
        if entry.is_dir():
            result.append({
                "type":     "directory",
                "name":     entry.name,
                "path":     rel,
                "children": _build_tree(root, entry),
            })
        else:
            result.append({
                "type": "file",
                "name": entry.name,
                "path": rel,
                "size": entry.stat().st_size,
            })
    return result


@router.get("/projects/{project_id}/workspace/tree")
def get_file_tree(project_id: int, db: Session = Depends(get_db)):
    """
    워크스페이스 파일 트리를 반환한다.
    숨김 파일(.aiorc 등)은 포함하지 않는다.
    """
    project = _get_project_or_404(project_id, db)
    root = Path(project.workspace_path) if project.workspace_path else _project_root(project_id)
    if not root.exists():
        return {"tree": [], "root": str(root)}

    return {
        "tree":       _build_tree(root, root),
        "root":       str(root),
        "project_id": project_id,
    }


# ── 파일 읽기 ──────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/workspace/file")
def read_workspace_file(
    project_id: int,
    path: str = Query(..., description="워크스페이스 루트 기준 상대경로"),
    db: Session = Depends(get_db),
):
    """
    워크스페이스 파일 내용을 반환한다.
    path 예시: src/auth/jwt.py
    """
    project = _get_project_or_404(project_id, db)
    root = Path(project.workspace_path) if project.workspace_path else _project_root(project_id)

    target = (root / path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="워크스페이스 밖 접근 금지")
    if ".aiorc" in target.parts:
        raise HTTPException(status_code=403, detail="메타데이터 접근 금지")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"파일 없음: {path}")
    if not target.is_file():
        raise HTTPException(status_code=400, detail=f"파일이 아닙니다: {path}")

    content = target.read_text(encoding="utf-8", errors="replace")
    return {
        "path":    path,
        "content": content,
        "size":    target.stat().st_size,
    }


# ── 파일 삭제 ──────────────────────────────────────────────────────────────

@router.delete("/projects/{project_id}/workspace/file")
def delete_workspace_file(
    project_id: int,
    path: str = Query(..., description="삭제할 파일의 상대경로"),
    db: Session = Depends(get_db),
):
    """워크스페이스 파일을 삭제하고 DB 메타데이터도 정리한다."""
    project = _get_project_or_404(project_id, db)
    root = Path(project.workspace_path) if project.workspace_path else _project_root(project_id)

    target = (root / path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="워크스페이스 밖 접근 금지")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"파일 없음: {path}")

    target.unlink()

    # DB 메타데이터 삭제
    db.query(WorkspaceFile).filter(
        WorkspaceFile.project_id == project_id,
        WorkspaceFile.path == path,
    ).delete()
    db.commit()

    return {"deleted": path}


# ── 프로젝트 컨텍스트 (plan_node 주입용) ─────────────────────────────────

@router.get("/projects/{project_id}/context")
def get_project_context(project_id: int, db: Session = Depends(get_db)):
    """
    plan_node가 오케스트레이션 시작 시 읽는 프로젝트 현황 요약.

    반환:
      - 현재 파일 트리 (텍스트)
      - 마일스톤별 태스크 현황
      - 마지막 세션 요약
    """
    project = _get_project_or_404(project_id, db)
    root = Path(project.workspace_path) if project.workspace_path else _project_root(project_id)

    # 파일 트리 (텍스트)
    files: list[str] = []
    if root.exists():
        files = sorted(
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.is_file() and ".aiorc" not in p.parts
        )
    file_tree_text = "\n".join(files) if files else "(아직 파일 없음)"

    # 마일스톤 + 태스크 현황
    milestones = (
        db.query(Milestone)
        .filter(Milestone.project_id == project_id)
        .order_by(Milestone.order)
        .all()
    )
    milestone_text = ""
    for ms in milestones:
        tasks = (
            db.query(ProjectTask)
            .filter(ProjectTask.milestone_id == ms.id)
            .order_by(ProjectTask.order)
            .all()
        )
        task_lines = "\n".join(
            f"    [{t.status.upper():11s}] {t.title}"
            for t in tasks
        )
        milestone_text += f"  [{ms.status.upper():11s}] {ms.title}\n{task_lines}\n"

    # 마지막 세션 요약
    last_session = (
        db.query(ProjectSession)
        .filter(ProjectSession.project_id == project_id)
        .order_by(ProjectSession.started_at.desc())
        .first()
    )
    last_summary = last_session.summary if last_session and last_session.summary else "(이전 세션 없음)"

    context_text = (
        f"[현재 파일 구조]\n{file_tree_text}\n\n"
        f"[마일스톤 / 태스크 현황]\n{milestone_text or '(아직 없음)'}\n"
        f"[마지막 세션 요약]\n{last_summary}"
    )

    return {
        "project_id":    project_id,
        "context":       context_text,
        "file_count":    len(files),
        "milestone_count": len(milestones),
    }


# ── 마일스톤 CRUD ──────────────────────────────────────────────────────────

class MilestoneCreate(BaseModel):
    title:       str
    description: str = ""
    order:       int = 0


class MilestoneUpdate(BaseModel):
    title:       str | None = None
    description: str | None = None
    status:      str | None = None   # todo | in_progress | done
    order:       int | None = None


def _ms_to_dict(ms: Milestone) -> dict:
    return {
        "id":          ms.id,
        "project_id":  ms.project_id,
        "title":       ms.title,
        "description": ms.description,
        "status":      ms.status,
        "order":       ms.order,
        "created_at":  ms.created_at.isoformat() if ms.created_at else None,
        "tasks": [
            {
                "id":             t.id,
                "milestone_id":   t.milestone_id,
                "title":          t.title,
                "description":    t.description,
                "status":         t.status,
                "assigned_agent": t.assigned_agent,
                "result_files":   t.result_files or [],
                "order":          t.order,
                "created_at":     t.created_at.isoformat() if t.created_at else None,
                "completed_at":   t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in sorted(ms.tasks, key=lambda x: x.order)
        ],
    }


@router.get("/projects/{project_id}/milestones")
def list_milestones(project_id: int, db: Session = Depends(get_db)):
    """마일스톤 목록 (태스크 포함)."""
    _get_project_or_404(project_id, db)
    milestones = (
        db.query(Milestone)
        .filter(Milestone.project_id == project_id)
        .order_by(Milestone.order, Milestone.id)
        .all()
    )
    return [_ms_to_dict(ms) for ms in milestones]


@router.post("/projects/{project_id}/milestones", status_code=201)
def create_milestone(project_id: int, body: MilestoneCreate, db: Session = Depends(get_db)):
    """마일스톤 생성."""
    _get_project_or_404(project_id, db)
    ms = Milestone(
        project_id=project_id,
        title=body.title,
        description=body.description,
        order=body.order,
    )
    db.add(ms)
    db.commit()
    db.refresh(ms)
    return _ms_to_dict(ms)


@router.patch("/projects/{project_id}/milestones/{ms_id}")
def update_milestone(
    project_id: int,
    ms_id:      int,
    body:       MilestoneUpdate,
    db:         Session = Depends(get_db),
):
    """마일스톤 제목·설명·상태·순서 수정."""
    ms = db.query(Milestone).filter(
        Milestone.id == ms_id,
        Milestone.project_id == project_id,
    ).first()
    if not ms:
        raise HTTPException(status_code=404, detail="마일스톤 없음")
    if body.title       is not None: ms.title       = body.title
    if body.description is not None: ms.description = body.description
    if body.status      is not None: ms.status      = body.status
    if body.order       is not None: ms.order       = body.order
    db.commit()
    db.refresh(ms)
    return _ms_to_dict(ms)


@router.delete("/projects/{project_id}/milestones/{ms_id}")
def delete_milestone(project_id: int, ms_id: int, db: Session = Depends(get_db)):
    """마일스톤과 하위 태스크 삭제."""
    ms = db.query(Milestone).filter(
        Milestone.id == ms_id,
        Milestone.project_id == project_id,
    ).first()
    if not ms:
        raise HTTPException(status_code=404, detail="마일스톤 없음")
    db.delete(ms)
    db.commit()
    return {"deleted": ms_id}


# ── 태스크 CRUD ────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title:       str
    description: str = ""
    order:       int = 0


class TaskUpdate(BaseModel):
    title:          str | None = None
    description:    str | None = None
    status:         str | None = None   # todo | in_progress | done | failed
    assigned_agent: str | None = None
    result_files:   list[str] | None = None
    order:          int | None = None


def _task_to_dict(t: ProjectTask) -> dict:
    return {
        "id":             t.id,
        "milestone_id":   t.milestone_id,
        "project_id":     t.project_id,
        "title":          t.title,
        "description":    t.description,
        "status":         t.status,
        "assigned_agent": t.assigned_agent,
        "result_files":   t.result_files or [],
        "order":          t.order,
        "created_at":     t.created_at.isoformat() if t.created_at else None,
        "completed_at":   t.completed_at.isoformat() if t.completed_at else None,
    }


@router.post("/projects/{project_id}/milestones/{ms_id}/tasks", status_code=201)
def create_task(
    project_id: int,
    ms_id:      int,
    body:       TaskCreate,
    db:         Session = Depends(get_db),
):
    """태스크 생성."""
    _get_project_or_404(project_id, db)
    ms = db.query(Milestone).filter(
        Milestone.id == ms_id,
        Milestone.project_id == project_id,
    ).first()
    if not ms:
        raise HTTPException(status_code=404, detail="마일스톤 없음")
    task = ProjectTask(
        milestone_id=ms_id,
        project_id=project_id,
        title=body.title,
        description=body.description,
        order=body.order,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_to_dict(task)


@router.patch("/projects/{project_id}/tasks/{task_id}")
def update_task(
    project_id: int,
    task_id:    int,
    body:       TaskUpdate,
    db:         Session = Depends(get_db),
):
    """태스크 수정."""
    task = db.query(ProjectTask).filter(
        ProjectTask.id == task_id,
        ProjectTask.project_id == project_id,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="태스크 없음")
    if body.title          is not None: task.title          = body.title
    if body.description    is not None: task.description    = body.description
    if body.assigned_agent is not None: task.assigned_agent = body.assigned_agent
    if body.result_files   is not None: task.result_files   = body.result_files
    if body.order          is not None: task.order          = body.order
    if body.status         is not None:
        task.status = body.status
        if body.status == "done" and not task.completed_at:
            task.completed_at = datetime.now(timezone.utc)
        elif body.status != "done":
            task.completed_at = None
    db.commit()
    db.refresh(task)
    return _task_to_dict(task)


@router.delete("/projects/{project_id}/tasks/{task_id}")
def delete_task(project_id: int, task_id: int, db: Session = Depends(get_db)):
    """태스크 삭제."""
    task = db.query(ProjectTask).filter(
        ProjectTask.id == task_id,
        ProjectTask.project_id == project_id,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="태스크 없음")
    db.delete(task)
    db.commit()
    return {"deleted": task_id}


# ── 세션 관리 ──────────────────────────────────────────────────────────────

class SessionEndBody(BaseModel):
    summary:       str       = ""
    files_changed: list[str] = []
    tasks_done:    list[int] = []


@router.post("/projects/{project_id}/sessions/start", status_code=201)
def start_session(project_id: int, db: Session = Depends(get_db)):
    """
    오케스트레이션 시작 시 호출. 세션 레코드를 생성하고 session_id를 반환.
    agent_runner.py가 이 ID를 사용해 나중에 end를 호출한다.
    """
    _get_project_or_404(project_id, db)
    session = ProjectSession(project_id=project_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.id, "started_at": session.started_at.isoformat()}


@router.patch("/projects/{project_id}/sessions/{session_id}/end")
def end_session(
    project_id: int,
    session_id: int,
    body:       SessionEndBody,
    db:         Session = Depends(get_db),
):
    """세션 종료: 요약·변경 파일·완료 태스크 저장."""
    session = db.query(ProjectSession).filter(
        ProjectSession.id == session_id,
        ProjectSession.project_id == project_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션 없음")
    session.summary       = body.summary
    session.files_changed = body.files_changed
    session.tasks_done    = body.tasks_done
    session.ended_at      = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "session_id": session_id}


@router.get("/projects/{project_id}/sessions")
def list_sessions(project_id: int, db: Session = Depends(get_db)):
    """최근 10개 세션 목록."""
    _get_project_or_404(project_id, db)
    sessions = (
        db.query(ProjectSession)
        .filter(ProjectSession.project_id == project_id)
        .order_by(ProjectSession.started_at.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "id":            s.id,
            "summary":       s.summary,
            "files_changed": s.files_changed or [],
            "tasks_done":    s.tasks_done or [],
            "started_at":    s.started_at.isoformat() if s.started_at else None,
            "ended_at":      s.ended_at.isoformat()   if s.ended_at   else None,
        }
        for s in sessions
    ]
