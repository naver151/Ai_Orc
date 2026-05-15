"""
에이전트 워크스페이스 도구 (LangChain Tool)

에이전트(LLM)가 직접 호출할 수 있는 파일시스템 + 코드실행 도구 모음.
WorkspaceTools를 생성한 뒤 .get_tools()로 LangChain 도구 목록을 받아
model.bind_tools(tools)로 LLM에 바인딩한다.

보안:
  - 모든 파일 접근은 workspace_root 내부로 제한 (_safe_path)
  - 코드 실행은 subprocess + timeout 30초 제한
  - .aiorc/ 내부 메타데이터 디렉터리는 에이전트가 접근 불가
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket


class WorkspaceTools:
    """
    프로젝트 워크스페이스에 바인딩된 도구 모음.

    Args:
        workspace_path: 프로젝트 루트 절대경로 (예: /workspaces/3/)
        project_id    : DB 프로젝트 ID (파일 메타데이터 저장용)
        ws            : WebSocket 인스턴스 (실시간 이벤트 전송용)
        agent_name    : 도구를 사용하는 에이전트 이름
    """

    def __init__(
        self,
        workspace_path: str,
        project_id: int,
        ws: "WebSocket",
        agent_name: str,
    ) -> None:
        self.root       = Path(workspace_path).resolve()
        self.project_id = project_id
        self.ws         = ws
        self.agent_name = agent_name

        # 워크스페이스 루트 보장
        self.root.mkdir(parents=True, exist_ok=True)

    # ── 내부 유틸 ──────────────────────────────────────────────────────────

    def _safe_path(self, path: str) -> Path:
        """워크스페이스 밖 접근 시도를 차단한다."""
        target = (self.root / path).resolve()
        if not str(target).startswith(str(self.root)):
            raise PermissionError(f"워크스페이스 밖 접근 금지: {path}")
        if ".aiorc" in target.parts:
            raise PermissionError(f"메타데이터 디렉터리 접근 금지: {path}")
        return target

    async def _notify(self, event_type: str, extra: dict | None = None) -> None:
        """WebSocket으로 실시간 이벤트 전송."""
        payload = {"type": event_type, "aiName": self.agent_name, **(extra or {})}
        try:
            await self.ws.send_json(payload)
        except Exception:
            pass  # WS 끊겨도 도구 실행은 계속

    # ── 도구 구현 ──────────────────────────────────────────────────────────

    async def read_file(self, path: str) -> str:
        """
        파일 내용을 읽어 반환한다.
        path는 워크스페이스 루트 기준 상대경로 (예: 'src/auth/jwt.py').
        """
        try:
            target = self._safe_path(path)
            if not target.exists():
                return f"[오류] 파일이 존재하지 않습니다: {path}"
            if not target.is_file():
                return f"[오류] 파일이 아닙니다: {path}"
            content = target.read_text(encoding="utf-8")
            await self._notify("tool_read_file", {"path": path})
            return content
        except PermissionError as e:
            return f"[오류] 접근 거부: {e}"
        except Exception as e:
            return f"[오류] 파일 읽기 실패: {e}"

    async def write_file(self, path: str, content: str) -> str:
        """
        파일을 생성하거나 덮어쓴다. 중간 디렉터리가 없으면 자동 생성.
        path는 워크스페이스 루트 기준 상대경로 (예: 'src/auth/jwt.py').
        """
        try:
            target = self._safe_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

            # UI 파일트리 실시간 업데이트
            await self._notify("file_written", {
                "path":    path,
                "message": f"📄 {path} 저장됨",
            })

            # DB 파일 메타데이터 기록 (비동기 — 실패해도 무시)
            try:
                import asyncio
                asyncio.create_task(self._save_file_meta(path))
            except Exception:
                pass

            return f"✅ 저장 완료: {path}"
        except PermissionError as e:
            return f"[오류] 접근 거부: {e}"
        except Exception as e:
            return f"[오류] 파일 쓰기 실패: {e}"

    async def list_files(self, directory: str = "") -> str:
        """
        워크스페이스 파일 목록을 반환한다.
        directory가 비어 있으면 전체 워크스페이스를 탐색.
        """
        try:
            target = self._safe_path(directory) if directory else self.root
            if not target.is_dir():
                return f"[오류] 디렉터리가 존재하지 않습니다: {directory}"

            files = sorted(
                str(p.relative_to(self.root))
                for p in target.rglob("*")
                if p.is_file() and ".aiorc" not in p.parts
            )
            await self._notify("tool_list_files", {"directory": directory or "/"})
            return "\n".join(files) if files else "(비어 있음)"
        except PermissionError as e:
            return f"[오류] 접근 거부: {e}"
        except Exception as e:
            return f"[오류] 목록 조회 실패: {e}"

    async def execute_code(self, code: str, language: str = "python") -> str:
        """
        코드를 실행하고 결과를 반환한다.
        language: 'python' | 'bash'
        실행 제한: 30초 타임아웃, 워크스페이스 디렉터리 내에서 실행.
        """
        await self._notify("code_executing", {"message": "⚙️ 코드 실행 중..."})

        try:
            if language == "python":
                cmd = ["python", "-c", code]
            elif language == "bash":
                cmd = ["bash", "-c", code]
            else:
                return f"[오류] 지원하지 않는 언어: {language} (python | bash만 지원)"

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.root),
            )

            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()

            if proc.returncode == 0:
                output = stdout or "(출력 없음)"
                status = "✅"
            else:
                output = stderr or stdout or "(오류 출력 없음)"
                status = "❌"

            # 출력 길이 제한 (토큰 낭비 방지)
            if len(output) > 2000:
                output = output[:2000] + "\n...(이하 생략)"

            await self._notify("code_executed", {
                "message": f"{status} 실행 결과 (returncode={proc.returncode}):\n{output}",
            })
            return output

        except subprocess.TimeoutExpired:
            msg = "[오류] 실행 시간 초과 (30초 제한)"
            await self._notify("code_executed", {"message": msg})
            return msg
        except FileNotFoundError:
            return f"[오류] '{language}' 런타임을 찾을 수 없습니다"
        except Exception as e:
            return f"[오류] 코드 실행 실패: {e}"

    # ── 마일스톤 도구 ──────────────────────────────────────────────────────

    async def list_milestones(self) -> str:
        """
        현재 프로젝트의 마일스톤과 태스크 현황을 텍스트로 반환한다.
        작업 시작 전 현황 파악에 사용.
        """
        try:
            from app.db import SessionLocal
            from app.models import Milestone, ProjectTask
            db = SessionLocal()
            milestones = (
                db.query(Milestone)
                .filter(Milestone.project_id == self.project_id)
                .order_by(Milestone.order, Milestone.id)
                .all()
            )
            if not milestones:
                return "(마일스톤 없음)"
            lines = []
            for ms in milestones:
                tasks = (
                    db.query(ProjectTask)
                    .filter(ProjectTask.milestone_id == ms.id)
                    .order_by(ProjectTask.order)
                    .all()
                )
                lines.append(f"[{ms.status.upper()}] 마일스톤 #{ms.id}: {ms.title}")
                for t in tasks:
                    lines.append(f"  - [{t.status.upper():11s}] 태스크 #{t.id}: {t.title}")
            db.close()
            return "\n".join(lines)
        except Exception as e:
            return f"[오류] 마일스톤 조회 실패: {e}"

    async def update_task_status(self, task_id: int, status: str) -> str:
        """
        태스크 상태를 업데이트한다.
        task_id: list_milestones로 확인한 태스크 번호.
        status: todo | in_progress | done | failed
        """
        allowed = {"todo", "in_progress", "done", "failed"}
        if status not in allowed:
            return f"[오류] 허용된 상태: {', '.join(sorted(allowed))}"
        try:
            from app.db import SessionLocal
            from app.models import ProjectTask
            from datetime import datetime, timezone
            db = SessionLocal()
            task = db.query(ProjectTask).filter(
                ProjectTask.id == task_id,
                ProjectTask.project_id == self.project_id,
            ).first()
            if not task:
                db.close()
                return f"[오류] 태스크 #{task_id} 없음 (이 프로젝트에 속하지 않음)"
            task.status = status
            task.assigned_agent = self.agent_name
            if status == "done" and not task.completed_at:
                task.completed_at = datetime.now(timezone.utc)
            elif status != "done":
                task.completed_at = None
            db.commit()
            db.close()
            await self._notify("task_status_updated", {
                "task_id": task_id,
                "status":  status,
                "message": f"✅ 태스크 #{task_id} → {status}",
            })
            return f"✅ 태스크 #{task_id} 상태를 '{status}'로 변경했습니다."
        except Exception as e:
            return f"[오류] 태스크 상태 업데이트 실패: {e}"

    # ── DB 저장 ────────────────────────────────────────────────────────────

    async def _save_file_meta(self, path: str) -> None:
        """WorkspaceFile 레코드 upsert (생성 또는 updated_at 갱신)."""
        try:
            from app.db import SessionLocal
            from app.models import WorkspaceFile
            from datetime import datetime, timezone

            db = SessionLocal()
            existing = (
                db.query(WorkspaceFile)
                .filter(
                    WorkspaceFile.project_id == self.project_id,
                    WorkspaceFile.path == path,
                )
                .first()
            )
            now = datetime.now(timezone.utc)
            if existing:
                existing.updated_at  = now
                existing.created_by  = self.agent_name
            else:
                db.add(WorkspaceFile(
                    project_id = self.project_id,
                    path       = path,
                    created_by = self.agent_name,
                ))
            db.commit()
        except Exception:
            pass
        finally:
            try:
                db.close()
            except Exception:
                pass

    # ── LangChain 통합 ────────────────────────────────────────────────────

    def get_tools(self) -> list:
        """
        LangChain 도구 목록 반환.
        model.bind_tools(workspace_tools.get_tools()) 으로 LLM에 바인딩.
        """
        from langchain_core.tools import StructuredTool
        import inspect

        tools = []
        definitions = [
            (
                "read_file",
                "파일 내용을 읽는다. path는 워크스페이스 루트 기준 상대경로.",
                self.read_file,
            ),
            (
                "write_file",
                "파일을 생성하거나 수정한다. path는 상대경로, content는 전체 파일 내용.",
                self.write_file,
            ),
            (
                "list_files",
                "워크스페이스 파일 목록을 반환한다. directory가 비어 있으면 전체 탐색.",
                self.list_files,
            ),
            (
                "execute_code",
                "코드를 실행하고 결과를 반환한다. language는 'python' 또는 'bash'.",
                self.execute_code,
            ),
            (
                "list_milestones",
                "현재 프로젝트의 마일스톤·태스크 현황을 반환한다. 작업 시작 전 현황 파악에 사용.",
                self.list_milestones,
            ),
            (
                "update_task_status",
                (
                    "태스크 상태를 업데이트한다. "
                    "task_id: list_milestones로 확인한 태스크 번호. "
                    "status: todo | in_progress | done | failed"
                ),
                self.update_task_status,
            ),
        ]

        for name, description, func in definitions:
            tools.append(
                StructuredTool.from_function(
                    coroutine=func,
                    name=name,
                    description=description,
                )
            )
        return tools
