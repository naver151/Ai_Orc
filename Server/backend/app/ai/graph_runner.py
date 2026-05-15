"""
LangGraph 멀티에이전트 오케스트레이션 그래프 (Phase 2)

변경 사항:
  - RunnableConfig로 콜백 전달 (ainvoke 시 더 안정적)
  - WSStreamHandler에 문자 수 기반 진행률 추적 추가
  - 각 노드 진입 시 pause/kill 체크 (agent_manager_ref 사용)
  - plan_node에서 worker 간 공유 컨텍스트 GraphState에 기록

노드 구성:
  plan_node      — 관리자가 조용히 계획 수립
  dispatch_node  — Send API로 서브태스크 병렬 분산
  worker_node    — 개별 워커 스트리밍 실행
  synthesize_node — 관리자 결과 종합
"""

from __future__ import annotations
import json
import os
import re
import asyncio
import random

_SCORE_RE = re.compile(r"⭐\s*점수\s*:\s*(\d+)\s*/\s*10", re.IGNORECASE)

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from app.ai.graph_state import GraphState, SubTask
from app.ai.lc_providers import get_lc_model, WSStreamHandler, ProgressWSStreamHandler, safe_ainvoke
from app.ai.lc_memory import save_agent_memory, build_rag_context

_ORCHESTRATE_RE = re.compile(r"<ORCHESTRATE>(.*?)</ORCHESTRATE>", re.DOTALL)

# ── 적응형 분배 상수 / 유틸 ──────────────────────────────────────────────────

_PERF_N   = 10    # 최근 N건 평균
_MIN_DATA  = 5    # 최소 데이터 건수 (미달 시 LLM 판단 폴백)
_EPSILON   = 0.10 # 10% 탐색


def _classify_task_type(task_text: str) -> str:
    """서브태스크 텍스트를 카테고리 키워드로 분류."""
    t = task_text.lower()
    if any(k in t for k in ['코드', '구현', '개발', '프로그래밍', 'code', 'implement', 'programming']):
        return 'code'
    if any(k in t for k in ['분석', '리서치', '조사', 'analysis', 'research', '검토', '비교']):
        return 'analysis'
    if any(k in t for k in ['작성', '문서', '보고서', '정리', 'writing', 'document', 'report']):
        return 'writing'
    return 'general'


def _get_provider_avg_scores(
    task_type: str,
    providers: list[str],
    db=None,
) -> dict[str, float | None]:
    """
    DB에서 provider별 최근 N건 평균 점수 조회.
    _MIN_DATA 미만이면 None 반환 (데이터 부족 신호).

    Args:
        db: 외부에서 주입할 세션 (테스트용). None이면 내부적으로 SessionLocal 생성.
    """
    from app.models import AgentPerformance

    _own_session = db is None
    if _own_session:
        from app.db import SessionLocal
        db = SessionLocal()

    result: dict[str, float | None] = {}
    try:
        for provider in providers:
            rows = (
                db.query(AgentPerformance.score)
                .filter(
                    AgentPerformance.task_type == task_type,
                    AgentPerformance.provider  == provider,
                )
                .order_by(AgentPerformance.created_at.desc())
                .limit(_PERF_N)
                .all()
            )
            if len(rows) >= _MIN_DATA:
                result[provider] = sum(r.score for r in rows) / len(rows)
            else:
                result[provider] = None
    except Exception:
        pass
    finally:
        if _own_session:
            try:
                db.close()
            except Exception:
                pass
    return result


def _epsilon_greedy_provider(task_type: str, available_providers: list[str]) -> str | None:
    """
    epsilon-greedy로 provider 선택.
    - 10%: 랜덤 탐색
    - 90%: 최고 평균 점수 provider
    데이터 부족 시 None 반환 → LLM 판단 폴백.
    """
    scores = _get_provider_avg_scores(task_type, available_providers)
    scored = {p: s for p, s in scores.items() if s is not None}

    if not scored:
        return None  # 모두 데이터 부족 → 폴백

    if random.random() < _EPSILON:
        return random.choice(available_providers)  # 탐색

    return max(scored, key=lambda p: scored[p])  # 활용


def _save_performance_sync(task_type: str, provider: str, score: int) -> None:
    """성능 점수 동기 저장 (asyncio.to_thread에서 호출)."""
    from app.db import SessionLocal
    from app.models import AgentPerformance

    try:
        db = SessionLocal()
        db.add(AgentPerformance(task_type=task_type, provider=provider, score=score))
        db.commit()
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass


# ── 교차 리뷰 모델 매핑 ───────────────────────────────────────────────────────
# 워커가 쓴 모델과 다른 모델로 리뷰 → 서로 다른 시각 확보
_CROSS_REVIEW_MAP: dict[str, str] = {
    "github": "claude",
    "gpt":    "claude",
    "claude": "github",
    "gemini": "claude",
}

def _get_reviewer_key(worker_provider: str) -> str:
    """워커 provider와 다른 리뷰어 모델 키 반환. API 키 없으면 github 폴백."""
    reviewer = _CROSS_REVIEW_MAP.get(worker_provider, "github")
    if reviewer == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
        reviewer = "github"
    if reviewer == "gemini" and not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        reviewer = "github"
    return reviewer


# ── 관리자 시스템 프롬프트 ────────────────────────────────────────────────────

_MANAGER_SYSTEM = (
    "당신은 AI 팀의 총괄 관리자입니다.\n"
    "사용자의 요청을 분석하고, 팀원들에게 작업을 분배하여 최고의 결과를 만들어냅니다.\n\n"

    "■ 현재 팀 구성\n"
    "{worker_list}\n\n"

    "{project_context}"

    "■ 작업 분배 판단 기준\n"
    "분배 필요: 서로 독립적으로 병렬 처리 가능한 서브태스크 2개 이상\n"
    "직접 답변: 단순 질문, 짧은 설명, 팀원이 1명뿐인 경우\n\n"

    "■ 출력 형식 (분배 시 이 형식만 사용)\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "한 줄 계획 요약", "subtasks": ['
    '{{"worker_index": 1, "task": "팀원1 작업"}}, '
    '{{"worker_index": 2, "task": "팀원2 작업"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "■ 분야별 예시\n\n"
    "[ 개발 ] 사용자: REST API 서버 만들어줘 / 팀원: 2명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "API 설계·구현 병렬 분리", "subtasks": ['
    '{{"worker_index": 1, "task": "FastAPI 엔드포인트 설계: 리소스 구조, URL, 요청/응답 스키마 정의"}},'
    '{{"worker_index": 2, "task": "FastAPI 코드 구현: 라우터, 모델, CRUD, 예외 처리"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 투자 ] 사용자: 삼성전자 투자 분석 / 팀원: 3명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "재무·시장·리스크 3축 병렬 분석", "subtasks": ['
    '{{"worker_index": 1, "task": "3개년 재무제표 분석: 매출성장률, 영업이익률, ROE, 부채비율"}},'
    '{{"worker_index": 2, "task": "시장 동향·경쟁사 비교: SK하이닉스·TSMC·인텔 점유율·기술력"}},'
    '{{"worker_index": 3, "task": "리스크·밸류에이션: 지정학 리스크, PER·PBR 기반 투자의견"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 직접 답변 예시 ]\n"
    "사용자: 파이썬이란? → <ORCHESTRATE> 없이 바로 답변\n\n"

    "지금 요청을 분석하여 분배가 필요하면 <ORCHESTRATE> 형식으로, 아니면 직접 답변하세요."
)


# ProgressWSStreamHandler는 lc_providers에서 import (중복 정의 제거)

# ── 공통 유틸 ─────────────────────────────────────────────────────────────────

async def _check_control(state: GraphState, ai_name: str) -> bool:
    """pause/kill 상태 확인. kill이면 True 반환 (노드 중단 신호)."""
    am = state.get("agent_manager_ref")
    if not am:
        return False
    ctrl = am.get(ai_name)
    if not ctrl:
        return False
    if ctrl.is_killed:
        return True
    await ctrl.wait_if_paused()
    return ctrl.is_killed


def _build_messages(system: str, text: str) -> list:
    msgs = []
    if system:
        msgs.append(SystemMessage(content=system))
    msgs.append(HumanMessage(content=text))
    return msgs


def _inject_memory(ai_name: str, text: str) -> str:
    """LangChain retriever로 유사 과거 기억 검색 후 프롬프트에 주입."""
    rag = build_rag_context(ai_name, text, k=2)
    if not rag:
        return text
    return f"{rag}[현재 요청]\n{text}"


# ── 마일스톤 DB 헬퍼 (동기 — asyncio.to_thread 전용) ─────────────────────────

def _create_session_milestone(
    project_id:  int,
    plan_summary: str,
    subtasks:    list,
) -> tuple[int | None, list[int | None]]:
    """
    plan_node 이후 호출.
    세션 단위 Milestone 1개 + subtask마다 ProjectTask 생성.
    Returns: (milestone_id, [task_id, ...])
    """
    from app.db import SessionLocal
    from app.models import Milestone, ProjectTask
    try:
        db = SessionLocal()
        ms = Milestone(
            project_id=project_id,
            title=(plan_summary[:100] if plan_summary else "작업 세션"),
            status="in_progress",
            order=0,
        )
        db.add(ms)
        db.flush()   # ms.id 확보

        task_ids: list[int | None] = []
        for i, st in enumerate(subtasks):
            task = ProjectTask(
                milestone_id=ms.id,
                project_id=project_id,
                title=(st.get("task", "")[:200] or f"태스크 {i+1}"),
                description=st.get("task", ""),
                status="todo",
                order=i,
            )
            db.add(task)
            db.flush()
            task_ids.append(task.id)

        db.commit()
        return ms.id, task_ids
    except Exception:
        return None, [None] * len(subtasks)
    finally:
        try:
            db.close()
        except Exception:
            pass


def _update_task_status_sync(
    project_id: int,
    task_id:    int,
    status:     str,
    agent_name: str = "",
) -> None:
    """worker_node 시작/완료 시 태스크 상태 업데이트."""
    from app.db import SessionLocal
    from app.models import ProjectTask
    from datetime import datetime, timezone
    try:
        db = SessionLocal()
        task = db.query(ProjectTask).filter(
            ProjectTask.id == task_id,
            ProjectTask.project_id == project_id,
        ).first()
        if task:
            task.status = status
            if agent_name:
                task.assigned_agent = agent_name
            if status == "done" and not task.completed_at:
                task.completed_at = datetime.now(timezone.utc)
            elif status != "done":
                task.completed_at = None
            db.commit()
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def _finish_milestone_sync(project_id: int, milestone_id: int) -> None:
    """모든 태스크 완료 후 마일스톤을 done으로 전환."""
    from app.db import SessionLocal
    from app.models import Milestone, ProjectTask
    try:
        db = SessionLocal()
        ms = db.query(Milestone).filter(
            Milestone.id == milestone_id,
            Milestone.project_id == project_id,
        ).first()
        if ms:
            all_tasks = db.query(ProjectTask).filter(ProjectTask.milestone_id == milestone_id).all()
            if all_tasks and all(t.status in ("done", "failed") for t in all_tasks):
                ms.status = "done"
                db.commit()
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass


# ── 노드 구현 ────────────────────────────────────────────────────────────────

async def plan_node(state: GraphState) -> dict:
    """
    Phase 1: 관리자가 조용히 계획 수립.
    UI에 스트리밍하지 않고 ORCHESTRATE 블록 파싱.
    """
    ws      = state["websocket"]
    manager = state["manager_name"]
    workers = state["worker_names"]
    text    = state["user_prompt"]
    provider_key = state["provider_map"].get(manager, "github")

    # kill 체크
    if await _check_control(state, manager):
        return {"is_direct": True, "direct_answer": "", "plan_summary": "", "subtasks": []}

    # UI 알림
    await ws.send_json({"type": "orchestration_start", "aiName": manager, "workers": workers})
    await ws.send_json({"type": "status",       "aiName": manager, "status": "RUNNING"})
    await ws.send_json({"type": "progress",     "aiName": manager, "percent": 0})
    await ws.send_json({"type": "current_task", "aiName": manager, "task": "작업 분석 중..."})

    # 시스템 프롬프트 (프로젝트 컨텍스트 주입)
    worker_list     = "\n".join(f"- 팀원 {i+1}: {n}" for i, n in enumerate(workers))
    project_context = state.get("project_context", "")
    project_ctx_section = (
        f"■ 프로젝트 현황 (이미 완료된 작업 및 파일 — 중복 작업 금지)\n{project_context}\n\n"
        if project_context else ""
    )
    system = _MANAGER_SYSTEM.format(
        worker_list=worker_list,
        project_context=project_ctx_section,
    )

    # 메모리 주입
    enriched = _inject_memory(manager, text)

    # 조용히 호출 (스트리밍 없음, rate limit 보호)
    model = get_lc_model(provider_key, streaming=False)
    await ws.send_json({"type": "log", "aiName": manager, "message": "⏳ AI 응답 대기 중...\n"})
    try:
        resp = await safe_ainvoke(
            model,
            _build_messages(system, enriched),
            config=RunnableConfig(callbacks=[]),
        )
        plan_text = resp.content
    except asyncio.CancelledError:
        return {"is_direct": True, "direct_answer": "", "plan_summary": "", "subtasks": []}
    except Exception as e:
        await ws.send_json({"type": "log", "aiName": manager,
                            "message": f"[오류] 계획 수립 실패: {e}"})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"is_direct": True, "direct_answer": "", "plan_summary": "", "subtasks": []}

    # ORCHESTRATE 파싱
    match = _ORCHESTRATE_RE.search(plan_text)
    if not match:
        # 직접 답변
        await ws.send_json({"type": "log",          "aiName": manager, "message": plan_text.strip()})
        await ws.send_json({"type": "status",        "aiName": manager, "status": "COMPLETED"})
        await ws.send_json({"type": "progress",      "aiName": manager, "percent": 100})
        await ws.send_json({"type": "current_task",  "aiName": manager, "task": ""})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"is_direct": True, "direct_answer": plan_text.strip(),
                "plan_summary": "", "subtasks": []}

    try:
        data = json.loads(match.group(1).strip())
        subtasks_raw = data.get("subtasks", [])
        plan_summary = data.get("plan", "작업 분배 완료")
    except json.JSONDecodeError:
        await ws.send_json({"type": "log", "aiName": manager,
                            "message": "[오류] 계획 파싱 실패"})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"is_direct": True, "direct_answer": "", "plan_summary": "", "subtasks": []}

    # ── 서브태스크 배정: 자동(adaptive) vs 수동(LLM 판단) ────────
    distribution_mode = state.get("distribution_mode", "manual")
    provider_map      = state["provider_map"]

    # provider → 워커 이름 목록 역매핑
    provider_to_workers: dict[str, list[str]] = {}
    for w in workers:
        p = provider_map.get(w, "github")
        provider_to_workers.setdefault(p, []).append(w)
    available_providers = list(provider_to_workers.keys())

    subtasks: list[SubTask] = []
    for st in subtasks_raw:
        task_text = st.get("task", "")
        task_type = _classify_task_type(task_text)

        chosen_worker: str | None = None

        if distribution_mode == "auto":
            best_provider = _epsilon_greedy_provider(task_type, available_providers)
            if best_provider:
                chosen_worker = provider_to_workers[best_provider][0]

        if not chosen_worker:
            # 데이터 부족 또는 manual 모드 → LLM worker_index 사용
            idx = (st.get("worker_index", 1) - 1) % len(workers)
            chosen_worker = workers[idx]

        subtasks.append({
            "worker_name": chosen_worker,
            "task":        task_text,
            "task_type":   task_type,
        })

    # ── 마일스톤·태스크 자동 생성 (프로젝트 모드) ───────────────────────
    project_id   = state.get("project_id")
    milestone_id = None
    if project_id and subtasks:
        milestone_id, task_ids = await asyncio.to_thread(
            _create_session_milestone, project_id, plan_summary, subtasks
        )
        # subtask에 db_task_id 주입
        subtasks = [
            {**st, "db_task_id": tid}
            for st, tid in zip(subtasks, task_ids)
        ]

    # 계획 요약 + 배분 이벤트
    await ws.send_json({"type": "log", "aiName": manager,
                        "message": f"[계획 완료] {plan_summary}"})
    for st in subtasks:
        await ws.send_json({"type": "subtask_assign",
                            "from": manager, "to": st["worker_name"], "task": st["task"]})

    await ws.send_json({"type": "current_task", "aiName": manager, "task": ""})

    return {
        "is_direct":           False,
        "direct_answer":       "",
        "plan_summary":        plan_summary,
        "subtasks":            subtasks,
        "worker_results":      {},
        "current_milestone_id": milestone_id,
    }




async def worker_node(state: GraphState) -> dict:
    """
    Phase 3: 개별 워커 실행 (병렬).
    ProgressWSStreamHandler → 토큰 단위 WebSocket push + 진행률 업데이트.
    동료 워커들의 결과가 worker_results에 누적되어 있으면 컨텍스트로 주입.
    """
    ws          = state["websocket"]
    worker_name = state["current_worker_name"]
    task_text   = state["current_task_text"]
    provider_key = state["provider_map"].get(worker_name, "github")

    # kill 체크
    if await _check_control(state, worker_name):
        return {"worker_results": {worker_name: ""}}

    # ── 태스크 상태: in_progress ─────────────────────────────────────────
    db_task_id = state.get("current_task_db_id")
    project_id = state.get("project_id")
    if db_task_id and project_id:
        await asyncio.to_thread(
            _update_task_status_sync, project_id, db_task_id, "in_progress", worker_name
        )

    # 이미 완료된 동료 결과를 컨텍스트로 주입 (공유 화이트보드)
    peer_context = ""
    existing = state.get("worker_results", {})
    if existing:
        peer_context = "\n\n[동료 팀원 진행 결과 참고]\n" + "\n".join(
            f"- {name}: {result[:300]}..." if len(result) > 300 else f"- {name}: {result}"
            for name, result in existing.items()
            if result.strip()
        )

    # 메모리 주입
    enriched = _inject_memory(worker_name, task_text)
    if peer_context:
        enriched += peer_context

    await ws.send_json({"type": "current_task", "aiName": worker_name, "task": task_text})

    result = ""

    # ── LLM 실행 (워크스페이스 유무에 따라 도구 바인딩 분기) ─────────────────
    workspace_path = state.get("workspace_path", "")
    project_id     = state.get("project_id")

    handler = ProgressWSStreamHandler(ws, worker_name)
    cfg     = RunnableConfig(callbacks=[handler])

    if workspace_path and project_id:
        # ── 도구 바인딩 모드: LLM이 파일 읽기/쓰기/실행 가능 ──────────────
        from app.ai.workspace_tools import WorkspaceTools
        from langchain_core.messages import ToolMessage

        ws_tools = WorkspaceTools(
            workspace_path=workspace_path,
            project_id=project_id,
            ws=ws,
            agent_name=worker_name,
        )
        tools     = ws_tools.get_tools()
        tool_map  = {t.name: t for t in tools}
        model     = get_lc_model(provider_key, streaming=False).bind_tools(tools)

        worker_system = (
            "당신은 프로젝트 워크스페이스에 실제 파일을 생성하는 AI 개발자입니다.\n\n"
            "⚠️ 절대 규칙 — 반드시 지켜야 합니다:\n"
            "• 코드를 텍스트나 마크다운(``` 블록)으로 출력하면 안 됩니다.\n"
            "• 모든 코드·설정·문서는 반드시 write_file 도구를 호출해 파일로 저장하세요.\n"
            "• 파일을 저장하지 않으면 작업 실패로 간주됩니다.\n\n"
            "■ 작업 순서\n"
            "1. list_files 로 현재 파일 목록 확인\n"
            "2. 필요한 파일마다 write_file 호출 (경로는 워크스페이스 루트 기준 상대경로)\n"
            "   예: write_file(path='src/main.py', content='...')\n"
            "3. 모든 파일 저장 후 '저장 완료: [파일목록]' 형식으로 요약\n\n"
            "■ 경로 규칙\n"
            "• Python 프로젝트: src/main.py, src/models.py, requirements.txt\n"
            "• FastAPI: src/main.py, src/routers/, requirements.txt\n"
            "• 절대경로 사용 금지 — 항상 상대경로\n"
        )
        messages  = _build_messages(worker_system, enriched)

        # 도구 호출 루프 (최대 10회 반복)
        for loop_i in range(10):
            if await _check_control(state, worker_name):
                break
            # 대기 중 상태 알림
            await ws.send_json({
                "type":    "log",
                "aiName":  worker_name,
                "message": f"⏳ AI 응답 대기 중 (단계 {loop_i + 1})...\n",
            })
            try:
                resp = await safe_ainvoke(model, messages, config=RunnableConfig(callbacks=[]))
            except asyncio.CancelledError:
                break
            except Exception as e:
                result = f"[오류] {e}"
                await ws.send_json({"type": "log", "aiName": worker_name, "message": result})
                break

            messages.append(resp)

            if not resp.tool_calls:
                # 도구 호출 없음 → 최종 답변
                result = resp.content or ""
                if result:
                    await ws.send_json({"type": "log", "aiName": worker_name, "message": result})
                break

            # 도구 실행
            for tc in resp.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id   = tc["id"]

                await ws.send_json({
                    "type":    "tool_call",
                    "aiName":  worker_name,
                    "tool":    tool_name,
                    "args":    tool_args,
                    "message": f"🔧 {tool_name}({', '.join(f'{k}={repr(v)[:60]}' for k, v in tool_args.items())})",
                })

                if tool_name in tool_map:
                    try:
                        tool_result = await tool_map[tool_name].ainvoke(tool_args)
                    except Exception as e:
                        tool_result = f"[도구 오류] {e}"
                else:
                    tool_result = f"[오류] 알 수 없는 도구: {tool_name}"

                messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))

    else:
        # ── 기본 모드: 도구 없이 텍스트 생성 (하위 호환) ─────────────────
        model = get_lc_model(provider_key, streaming=True)
        try:
            resp = await safe_ainvoke(model, _build_messages("", enriched), config=cfg)
            result = resp.content
        except asyncio.CancelledError:
            result = ""
        except Exception as e:
            result = f"[오류] {e}"
            await ws.send_json({"type": "log", "aiName": worker_name, "message": result})

    # 메모리 저장
    if result:
        try:
            save_agent_memory(worker_name, task_text, result[:2000])
        except Exception:
            pass

    # ── 태스크 상태: done / failed ────────────────────────────────────────
    if db_task_id and project_id:
        final_status = "failed" if (result or "").startswith("[오류]") else "done"
        await asyncio.to_thread(
            _update_task_status_sync, project_id, db_task_id, final_status
        )
        # 마일스톤 완료 여부 확인
        milestone_id = state.get("current_milestone_id")
        if milestone_id:
            await asyncio.to_thread(_finish_milestone_sync, project_id, milestone_id)

    await ws.send_json({"type": "current_task", "aiName": worker_name, "task": ""})

    return {"worker_results": {worker_name: result}}


async def synthesize_node(state: GraphState) -> dict:
    """
    Phase 4: 관리자가 모든 워커 결과를 종합하여 최종 답변 생성.
    ProgressWSStreamHandler → 실시간 스트리밍.
    """
    ws       = state["websocket"]
    manager  = state["manager_name"]
    provider_key = state["provider_map"].get(manager, "github")

    # kill 체크
    if await _check_control(state, manager):
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"final_synthesis": ""}

    results = state.get("worker_results", {})
    valid = [
        f"### {name} 결과:\n{result}"
        for name, result in results.items()
        if result and result.strip()
    ]

    if not valid:
        await ws.send_json({"type": "log", "aiName": manager,
                            "message": "[오류] 팀원 결과가 없습니다."})
        await ws.send_json({"type": "status",   "aiName": manager, "status": "COMPLETED"})
        await ws.send_json({"type": "orchestration_done", "aiName": manager})
        return {"final_synthesis": ""}

    # 리뷰 피드백이 있으면 종합 프롬프트에 포함
    review_fb = state.get("review_feedback", "")
    review_section = f"\n\n[리뷰어 피드백]\n{review_fb}" if review_fb else ""

    synthesis_prompt = (
        "팀원들의 작업이 완료되었습니다. 결과를 종합하여 사용자에게 최종 답변을 작성해주세요.\n\n"
        f"원래 요청: {state['user_prompt']}\n\n"
        + "\n\n".join(valid)
        + review_section
    )

    # 종합 단계 알림
    await ws.send_json({"type": "orchestration_synthesis", "aiName": manager})
    await ws.send_json({"type": "current_task", "aiName": manager, "task": "결과 종합 중..."})

    # 시스템 프롬프트
    worker_list = "\n".join(f"- 팀원 {i+1}: {n}" for i, n in enumerate(state["worker_names"]))
    system = _MANAGER_SYSTEM.format(worker_list=worker_list, project_context="")

    # 스트리밍
    handler = ProgressWSStreamHandler(ws, manager)
    cfg = RunnableConfig(callbacks=[handler])
    model = get_lc_model(provider_key, streaming=True)

    synthesis = ""
    try:
        resp = await safe_ainvoke(model, _build_messages(system, synthesis_prompt), config=cfg)
        synthesis = resp.content
    except asyncio.CancelledError:
        synthesis = ""
    except Exception as e:
        synthesis = f"[오류] {e}"

    # 메모리 저장
    if synthesis:
        try:
            save_agent_memory(manager, state["user_prompt"], synthesis[:2000])
        except Exception:
            pass

    await ws.send_json({"type": "current_task",      "aiName": manager, "task": ""})
    await ws.send_json({"type": "orchestration_done", "aiName": manager})

    return {"final_synthesis": synthesis}


_REVIEWER_SYSTEM = (
    "당신은 AI 팀의 전문 검토자입니다.\n"
    "팀원의 작업 결과물을 검토하고 명확하고 건설적인 피드백을 제공합니다.\n"
    "반드시 아래 형식을 그대로 사용하세요:\n\n"
    "✅ 잘된 점: (2-3줄)\n"
    "⚠️ 개선 필요: (2-3줄, 없으면 '없음')\n"
    "📋 종합: 합격 / 보완 필요 (한 줄)\n"
    "⭐ 점수: X/10  ← 반드시 이 형식으로, X는 1~10 사이 정수\n\n"
    "점수 기준: 10=완벽, 8-9=우수, 6-7=양호, 4-5=보통, 1-3=미흡"
)


async def review_node(state: GraphState) -> dict:
    """
    교차 리뷰: 워커가 쓴 모델과 다른 모델로 각 결과물 검토.
    review_scores 딕셔너리에 점수를 누적하여 user_review_node로 전달.
    """
    ws      = state["websocket"]
    manager = state["manager_name"]
    results = state.get("worker_results", {})

    if not results:
        return {"review_feedback": "", "review_scores": {}}

    await ws.send_json({"type": "review_start", "aiName": manager})

    all_feedback: list[str] = []
    review_scores: dict[str, int | None] = {}

    for worker_name, result in results.items():
        if not result or not result.strip():
            review_scores[worker_name] = None
            continue

        if await _check_control(state, manager):
            break

        # ── 교차 리뷰: 워커와 다른 모델 선택 ──────────────────
        worker_provider  = state["provider_map"].get(worker_name, "github")
        reviewer_key     = _get_reviewer_key(worker_provider)

        prompt = (
            f"원래 요청: {state['user_prompt']}\n\n"
            f"[{worker_name}]의 작업 결과:\n{result[:2500]}\n\n"
            "위 결과물을 검토하고 형식에 맞춰 피드백해주세요."
        )

        handler = ProgressWSStreamHandler(ws, worker_name)
        cfg     = RunnableConfig(callbacks=[handler])
        model   = get_lc_model(reviewer_key, streaming=True)

        await ws.send_json({
            "type":         "review_begin",
            "aiName":       worker_name,
            "reviewerModel": reviewer_key.upper(),
        })

        feedback = ""
        try:
            resp     = await safe_ainvoke(
                model, _build_messages(_REVIEWER_SYSTEM, prompt), config=cfg
            )
            feedback = resp.content
        except asyncio.CancelledError:
            break
        except Exception as e:
            feedback = f"[검토 오류] {e}"
            await ws.send_json({"type": "log", "aiName": worker_name, "message": feedback})

        score_match = _SCORE_RE.search(feedback)
        score = int(score_match.group(1)) if score_match else None
        review_scores[worker_name] = score

        await ws.send_json({
            "type":          "review_done",
            "aiName":        worker_name,
            "feedback":      feedback,
            "score":         score,
            "reviewerModel": reviewer_key.upper(),
        })

        all_feedback.append(f"[{worker_name} 검토 — {reviewer_key.upper()}]\n{feedback}")

    # ── 점수 DB 저장 (적응형 분배용) ──────────────────────────
    subtask_map: dict[str, str] = {
        st["worker_name"]: st.get("task_type", "general")
        for st in state.get("subtasks", [])
    }
    for worker_name, score in review_scores.items():
        if score is not None:
            worker_provider = state["provider_map"].get(worker_name, "github")
            task_type       = subtask_map.get(worker_name, "general")
            try:
                await asyncio.to_thread(
                    _save_performance_sync, task_type, worker_provider, score
                )
            except Exception:
                pass

    return {
        "review_feedback": "\n\n".join(all_feedback),
        "review_scores":   review_scores,
    }


# ── 사용자 교차검증 노드 ──────────────────────────────────────────────────────

_USER_REVIEW_TIMEOUT = 15   # 초

async def user_review_node(state: GraphState) -> dict:
    """
    AI 리뷰 완료 후 사용자에게 15초 검증 기회 제공.
    - 승인: 바로 synthesize
    - 피드백 입력: 점수 낮은 워커 재실행
    - 타임아웃: 자동 승인 후 synthesize
    """
    ws      = state["websocket"]
    manager = state["manager_name"]
    am      = state["agent_manager_ref"]
    scores  = state.get("review_scores", {})

    # 사용자 리뷰 요청 전송
    await ws.send_json({
        "type":    "user_review_request",
        "aiName":  manager,
        "scores":  scores,
        "timeout": _USER_REVIEW_TIMEOUT,
    })

    # 이벤트 대기 (15초 타임아웃)
    event = am.request_user_review(manager)
    timed_out = False
    try:
        await asyncio.wait_for(event.wait(), timeout=float(_USER_REVIEW_TIMEOUT))
    except asyncio.TimeoutError:
        timed_out = True

    result = am.get_user_review_result(manager)
    am.clear_user_review(manager)

    await ws.send_json({
        "type":     "user_review_done",
        "aiName":   manager,
        "timedOut": timed_out,
    })

    # ── 재실행 워커 결정 ─────────────────────────────────────────
    retry_workers: list[str] = []
    if not timed_out and not result["approved"] and result["feedback"].strip():
        # 피드백이 있고 승인 안 된 경우 → 점수 낮은 워커만 재실행
        for worker, score in scores.items():
            if score is None or score < 7:
                retry_workers.append(worker)
        # 전부 점수 높으면(사용자만 불만) 전체 재실행
        if not retry_workers:
            retry_workers = list(scores.keys())

    return {
        "user_feedback":      result["feedback"],
        "user_approved":      result["approved"],
        "review_timed_out":   timed_out,
        "retry_worker_names": retry_workers,
    }


# ── 재실행 워커 노드 ──────────────────────────────────────────────────────────

async def retry_node(state: GraphState) -> dict:
    """
    사용자 피드백을 반영하여 특정 워커를 재실행.
    worker_node와 동일하지만 user_feedback를 컨텍스트에 주입.
    review_node를 거치지 않고 synthesize_node로 직행.
    """
    ws          = state["websocket"]
    worker_name = state["current_worker_name"]
    task_text   = state["current_task_text"]
    provider_key = state["provider_map"].get(worker_name, "github")
    user_fb     = state.get("user_feedback", "")

    if await _check_control(state, worker_name):
        return {"worker_results": {worker_name: ""}}

    # 사용자 피드백을 태스크에 주입
    enriched = _inject_memory(worker_name, task_text)
    if user_fb:
        enriched += f"\n\n[사용자 검토 의견 — 반드시 반영하세요]\n{user_fb}"

    # 기존 결과도 컨텍스트로 제공
    prev = state.get("worker_results", {}).get(worker_name, "")
    if prev:
        enriched += f"\n\n[이전 작성 내용 (수정 필요)]\n{prev[:800]}"

    await ws.send_json({
        "type":   "log",
        "aiName": worker_name,
        "message": f"\n🔄 사용자 피드백 반영 후 재작업 중...\n",
    })
    await ws.send_json({"type": "current_task", "aiName": worker_name, "task": task_text})

    result = ""

    workspace_path = state.get("workspace_path", "")
    project_id     = state.get("project_id")

    handler = ProgressWSStreamHandler(ws, worker_name)
    cfg = RunnableConfig(callbacks=[handler])

    if workspace_path and project_id:
        # 워크스페이스 모드 재실행 (도구 바인딩)
        from app.ai.workspace_tools import WorkspaceTools
        from langchain_core.messages import ToolMessage

        ws_tools = WorkspaceTools(
            workspace_path=workspace_path,
            project_id=project_id,
            ws=ws,
            agent_name=worker_name,
        )
        tools    = ws_tools.get_tools()
        tool_map = {t.name: t for t in tools}
        model    = get_lc_model(provider_key, streaming=False).bind_tools(tools)

        worker_system = (
            "당신은 프로젝트 워크스페이스에 실제 파일을 생성하는 AI 개발자입니다.\n\n"
            "⚠️ 절대 규칙 — 반드시 지켜야 합니다:\n"
            "• 코드를 텍스트나 마크다운(``` 블록)으로 출력하면 안 됩니다.\n"
            "• 모든 코드·설정·문서는 반드시 write_file 도구를 호출해 파일로 저장하세요.\n"
            "• 파일을 저장하지 않으면 작업 실패로 간주됩니다.\n\n"
            "■ 작업 순서\n"
            "1. list_files 로 현재 파일 목록 확인\n"
            "2. 필요한 파일마다 write_file 호출 (경로는 워크스페이스 루트 기준 상대경로)\n"
            "   예: write_file(path='src/main.py', content='...')\n"
            "3. 모든 파일 저장 후 '저장 완료: [파일목록]' 형식으로 요약\n\n"
            "■ 경로 규칙\n"
            "• Python 프로젝트: src/main.py, src/models.py, requirements.txt\n"
            "• FastAPI: src/main.py, src/routers/, requirements.txt\n"
            "• 절대경로 사용 금지 — 항상 상대경로\n"
        )
        messages = _build_messages(worker_system, enriched)

        for _ in range(10):
            if await _check_control(state, worker_name):
                break
            try:
                resp = await safe_ainvoke(model, messages, config=RunnableConfig(callbacks=[]))
            except asyncio.CancelledError:
                break
            except Exception as e:
                result = f"[재실행 오류] {e}"
                break

            messages.append(resp)
            if not resp.tool_calls:
                result = resp.content or ""
                if result:
                    await ws.send_json({"type": "log", "aiName": worker_name, "message": result})
                break

            for tc in resp.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id   = tc["id"]
                await ws.send_json({
                    "type": "tool_call", "aiName": worker_name,
                    "tool": tool_name, "args": tool_args,
                    "message": f"🔧 {tool_name}({', '.join(f'{k}={repr(v)[:60]}' for k, v in tool_args.items())})",
                })
                tool_result = (
                    await tool_map[tool_name].ainvoke(tool_args)
                    if tool_name in tool_map
                    else f"[오류] 알 수 없는 도구: {tool_name}"
                )
                messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))
    else:
        model = get_lc_model(provider_key, streaming=True)
        try:
            resp = await safe_ainvoke(model, _build_messages("", enriched), config=cfg)
            result = resp.content
        except Exception as e:
            result = f"[재실행 오류] {e}"

    await ws.send_json({"type": "current_task", "aiName": worker_name, "task": ""})
    return {"worker_results": {worker_name: result}}


# ── 라우팅 ────────────────────────────────────────────────────────────────────

def route_after_plan(state: GraphState):
    """plan_node 이후: 직접 답변 → END, 분배 → worker_node 병렬 실행."""
    if state.get("is_direct"):
        return END
    return [
        Send("worker_node", {
            **state,
            "current_worker_name": st["worker_name"],
            "current_task_text":   st["task"],
            "current_task_db_id":  st.get("db_task_id"),   # 마일스톤 태스크 추적
        })
        for st in state["subtasks"]
    ]


def route_after_user_review(state: GraphState):
    """
    user_review_node 이후 라우팅.
    - 재실행 필요 워커 있음 → retry_node 병렬 실행
    - 없음 → synthesize_node
    """
    retry_workers = state.get("retry_worker_names", [])
    if not retry_workers:
        return "synthesize_node"

    subtask_map = {st["worker_name"]: st["task"] for st in state.get("subtasks", [])}
    return [
        Send("retry_node", {
            **state,
            "current_worker_name": name,
            "current_task_text":   subtask_map.get(name, ""),
        })
        for name in retry_workers
    ]


# ── 그래프 빌드 ───────────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(GraphState)

    g.add_node("plan_node",        plan_node)
    g.add_node("worker_node",      worker_node)
    g.add_node("review_node",      review_node)        # 교차 AI 리뷰
    g.add_node("user_review_node", user_review_node)   # 사용자 교차검증 (15초)
    g.add_node("retry_node",       retry_node)         # 피드백 반영 재실행
    g.add_node("synthesize_node",  synthesize_node)

    g.add_edge(START, "plan_node")
    g.add_conditional_edges("plan_node",        route_after_plan)
    g.add_edge("worker_node",      "review_node")
    g.add_edge("review_node",      "user_review_node")
    g.add_conditional_edges("user_review_node", route_after_user_review)
    g.add_edge("retry_node",       "synthesize_node")
    g.add_edge("synthesize_node",  END)

    return g.compile()


orchestration_graph = build_graph()
