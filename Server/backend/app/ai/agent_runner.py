import asyncio
import json
import re
from typing import Optional
from fastapi import WebSocket
from .providers.base import AIProvider
from .providers.claude import ClaudeProvider
from .providers.openai_provider import OpenAIProvider
from .providers.gemini import GeminiProvider
from .providers.yolo_provider import YOLOProvider
from .providers.github_provider import GitHubProvider
from app.memory import save_memory_for, search_memory_for
from app.db import SessionLocal
from app.models import OrchestrationLog

PROVIDER_MAP = {
    "gpt": OpenAIProvider, "gpt-4o": OpenAIProvider, "openai": OpenAIProvider,
    "claude": ClaudeProvider, "gemini": GeminiProvider, "github": GitHubProvider,
    "github-gpt4o": lambda: GitHubProvider("gpt-4o"),
    "github-gpt4o-mini": lambda: GitHubProvider("gpt-4o-mini"),
    "github-llama": lambda: GitHubProvider("llama"),
    "github-llama-70b": lambda: GitHubProvider("llama-70b"),
    "github-llama-8b": lambda: GitHubProvider("llama-8b"),
    "github-mistral": lambda: GitHubProvider("mistral"),
    "github-phi": lambda: GitHubProvider("phi"),
    "yolo": YOLOProvider, "yolov8n": YOLOProvider,
}

_MANAGER_SYSTEM_PROMPT = (
    "당신은 AI 팀의 총괄 관리자입니다.\n"
    "사용자의 요청을 분석하고, 팀원들에게 작업을 분배하여 최고의 결과를 만들어냅니다.\n\n"

    "■ 현재 팀 구성\n"
    "{worker_list}\n\n"

    "■ 작업 분배 판단 기준\n"
    "아래 경우에는 팀원들에게 분배하세요:\n"
    "  - 서로 독립적으로 병렬 처리 가능한 서브태스크가 2개 이상인 경우\n"
    "  - 설계 + 구현 + 검토처럼 전문성이 다른 역할이 필요한 경우\n"
    "  - 수집 + 분석 + 작성처럼 순서가 아닌 병렬이 가능한 경우\n"
    "아래 경우에는 직접 답변하세요:\n"
    "  - 단순 질문, 정의, 개념 설명\n"
    "  - 한 문장이나 짧은 목록으로 충분한 답변\n"
    "  - 팀원이 1명뿐이고 분리 이점이 없는 경우\n\n"

    "■ 출력 형식 (분배 시 반드시 이 형식만 사용)\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "한 줄 계획 요약", "subtasks": ['
    '{{"worker_index": 1, "task": "팀원1에게 할당할 구체적이고 독립적인 작업"}}, '
    '{{"worker_index": 2, "task": "팀원2에게 할당할 구체적이고 독립적인 작업"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "■ 서브태스크 작성 원칙\n"
    "  - 각 서브태스크는 다른 팀원의 결과 없이도 독립적으로 수행 가능해야 합니다\n"
    "  - 팀원 수보다 많은 worker_index는 사용하지 마세요\n"
    "  - 태스크 설명은 구체적으로 작성하세요 (무엇을, 어떤 방식으로)\n\n"

    "■ 분야별 분배 예시\n\n"

    "[ 개발 분야 예시 ]\n"
    "사용자: REST API 서버를 만들어줘\n"
    "팀원: 2명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "API 서버를 설계·구현으로 병렬 분리", "subtasks": ['
    '{{"worker_index": 1, "task": "FastAPI 기반 REST API 엔드포인트 설계: 리소스 구조, URL 패턴, 요청/응답 스키마, 에러 코드 정의"}},'
    '{{"worker_index": 2, "task": "설계 스펙에 맞는 FastAPI 코드 구현: 라우터, 모델, CRUD 로직, 예외 처리 포함"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 투자·알파 분야 예시 ]\n"
    "사용자: 삼성전자 투자 분석해줘\n"
    "팀원: 3명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "재무·시장·리스크 3축 병렬 분석", "subtasks": ['
    '{{"worker_index": 1, "task": "삼성전자 최근 3개년 재무제표 분석: 매출 성장률, 영업이익률, ROE, 부채비율 수치 중심으로 작성"}},'
    '{{"worker_index": 2, "task": "반도체 시장 동향 및 경쟁사 비교: SK하이닉스·TSMC·인텔과의 점유율·기술력·가격 경쟁력 비교"}},'
    '{{"worker_index": 3, "task": "투자 리스크 및 포인트 정리: 지정학적 리스크, 업황 사이클, 현재 밸류에이션(PER·PBR) 기반 투자 의견"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 리서치·보고서 분야 예시 ]\n"
    "사용자: 국내 AI 스타트업 시장 현황 보고서 작성해줘\n"
    "팀원: 2명\n"
    "<ORCHESTRATE>\n"
    '{{"plan": "시장 현황 조사와 분석·인사이트 도출을 병렬 처리", "subtasks": ['
    '{{"worker_index": 1, "task": "국내 AI 스타트업 현황 조사: 주요 기업 목록, 투자 규모, 성장률, 정부 지원 정책 데이터 수집 및 정리"}},'
    '{{"worker_index": 2, "task": "AI 스타트업 시장 분석: 글로벌 대비 국내 경쟁력, 유망 섹터(헬스케어·제조·금융), 향후 전망 및 시사점 도출"}}'
    ']}}\n'
    "</ORCHESTRATE>\n\n"

    "[ 직접 답변 예시 (분배 불필요) ]\n"
    "사용자: 파이썬이란 무엇인가요?\n"
    "→ <ORCHESTRATE> 없이 직접 설명 작성\n\n"

    "사용자: 머신러닝과 딥러닝의 차이는?\n"
    "→ <ORCHESTRATE> 없이 직접 비교 설명 작성\n\n"

    "지금 요청을 분석하여 분배가 필요하면 <ORCHESTRATE> 형식으로, "
    "그렇지 않으면 바로 답변하세요."
)

_ORCHESTRATE_RE = re.compile(r"<ORCHESTRATE>(.*?)</ORCHESTRATE>", re.DOTALL)


def _save_orch_log(
    manager_name: str,
    worker_names: list,
    user_prompt: str,
    plan_summary: str,
    assignments: list,
    worker_results: list,
    synthesis_result: str,
) -> None:
    """동기 함수 — asyncio.to_thread()로 호출해 블로킹 방지."""
    try:
        db = SessionLocal()
        log = OrchestrationLog(
            manager_name=manager_name,
            worker_names=json.dumps(worker_names, ensure_ascii=False),
            user_prompt=user_prompt,
            plan_summary=plan_summary,
            subtasks_json=json.dumps(
                [{"worker": w, "task": t} for w, t in assignments],
                ensure_ascii=False
            ),
            worker_results_json=json.dumps(worker_results, ensure_ascii=False),
            synthesis_result=synthesis_result[:4000] if synthesis_result else "",
        )
        db.add(log)
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


def get_provider(name: str) -> AIProvider:
    entry = PROVIDER_MAP.get(name.lower(), GitHubProvider)
    return entry() if callable(entry) else entry()


class AgentState:
    def __init__(self, ai_name: str, provider_name: str = "github"):
        self.ai_name = ai_name
        self.provider: AIProvider = get_provider(provider_name)
        self.history: list[dict] = []
        self.system_prompt: str = ""
        self.status: str = "READY"
        self.current_task: Optional[asyncio.Task] = None
        self.current_task_text: str = ""
        self.is_killed: bool = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()

    def pause(self) -> None:
        self._pause_event.clear()
        self.status = "STOPPED"

    def resume(self) -> None:
        self._pause_event.set()
        self.status = "RUNNING"

    def kill(self) -> None:
        self.is_killed = True
        self._pause_event.set()
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
        self.status = "STOPPED"

    async def wait_if_paused(self) -> None:
        await self._pause_event.wait()


class AgentManager:
    def __init__(self):
        self._agents: dict[str, AgentState] = {}

    def get_or_create(self, ai_name: str, provider_name: str = "github") -> AgentState:
        if ai_name not in self._agents:
            self._agents[ai_name] = AgentState(ai_name, provider_name)
        else:
            self._agents[ai_name].provider = get_provider(provider_name)
        return self._agents[ai_name]

    def get(self, ai_name: str) -> Optional[AgentState]:
        return self._agents.get(ai_name)

    def remove(self, ai_name: str) -> None:
        if ai_name in self._agents:
            self._agents.pop(ai_name).kill()

    def is_manager(self, ai_name: str) -> bool:
        if not self._agents:
            return False
        return list(self._agents.keys())[0] == ai_name

    def get_worker_names(self, manager_name: str) -> list[str]:
        return [n for n in self._agents if n != manager_name]

    async def _stream(
        self,
        ai_name: str,
        text: str,
        websocket: WebSocket,
        system_override: Optional[str] = None,
    ) -> str:
        state = self.get(ai_name)
        if not state:
            return ""

        # ── 메모리 검색: 유사한 과거 작업이 있으면 컨텍스트로 주입 ──
        memories = search_memory_for(ai_name, text, n_results=2)
        user_content = text
        if memories:
            mem_block = "\n".join(
                f"[과거 참고 #{i+1} (관련도: {m['relevance_score']})]\n{m['document']}"
                for i, m in enumerate(memories)
            )
            user_content = (
                f"[참고: 이전에 유사한 작업을 처리한 기록이 있습니다]\n{mem_block}\n\n"
                f"[현재 요청]\n{text}"
            )

        state.history.append({"role": "user", "content": user_content})
        state.status = "RUNNING"
        state.current_task_text = text
        system = system_override if system_override is not None else state.system_prompt

        await websocket.send_json({"type": "status",       "aiName": ai_name, "status": "RUNNING"})
        await websocket.send_json({"type": "progress",     "aiName": ai_name, "percent": 0})
        await websocket.send_json({"type": "current_task", "aiName": ai_name, "task": text})

        full_response = ""
        char_count = 0

        try:
            async for chunk in state.provider.stream_chat(state.history, system):
                if state.is_killed:
                    break
                await state.wait_if_paused()
                if state.is_killed:
                    break
                full_response += chunk
                char_count += len(chunk)
                await websocket.send_json({"type": "log",      "aiName": ai_name, "message": chunk})
                await websocket.send_json({"type": "progress", "aiName": ai_name,
                                           "percent": min(int(char_count / 20), 99)})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await websocket.send_json({"type": "log", "aiName": ai_name,
                                       "message": f"[오류] {type(e).__name__}: {e}"})
        finally:
            if full_response:
                state.history.append({"role": "assistant", "content": full_response})
                # ── 메모리 저장: 완료된 작업과 결과를 ChromaDB에 저장 ──
                try:
                    save_memory_for(ai_name, text, full_response[:2000])
                except Exception:
                    pass  # 메모리 저장 실패는 무시
            if not state.is_killed:
                state.status = "COMPLETED"
                state.current_task_text = ""
                await websocket.send_json({"type": "status",       "aiName": ai_name, "status": "COMPLETED"})
                await websocket.send_json({"type": "progress",     "aiName": ai_name, "percent": 100})
                await websocket.send_json({"type": "current_task", "aiName": ai_name, "task": ""})

        return full_response

    async def _plan_silent(self, ai_name: str, text: str, system: str) -> str:
        """UI에 스트리밍하지 않고 AI 응답만 수집 (계획 수립 전용)."""
        state = self.get(ai_name)
        if not state:
            return ""

        messages = state.history + [{"role": "user", "content": text}]
        full_response = ""
        try:
            async for chunk in state.provider.stream_chat(messages, system):
                if state.is_killed:
                    break
                full_response += chunk
        except Exception:
            pass

        # 히스토리 반영
        state.history.append({"role": "user",      "content": text})
        state.history.append({"role": "assistant",  "content": full_response})
        return full_response

    async def run_prompt(self, ai_name: str, text: str, websocket: WebSocket) -> None:
        await self._stream(ai_name, text, websocket)

    async def run_orchestrated_prompt(
        self,
        manager_name: str,
        text: str,
        websocket: WebSocket,
    ) -> None:
        worker_names = self.get_worker_names(manager_name)
        if not worker_names:
            await self.run_prompt(manager_name, text, websocket)
            return

        worker_list = "\n".join(f"- 팀원 {i+1}: {n}" for i, n in enumerate(worker_names))
        manager_system = _MANAGER_SYSTEM_PROMPT.format(worker_list=worker_list)

        # Phase 1: 관리자 계획 수립 (UI에 원본 노출 없이 내부 처리)
        await websocket.send_json({
            "type": "orchestration_start",
            "aiName": manager_name,
            "workers": worker_names,
        })
        await websocket.send_json({
            "type": "status", "aiName": manager_name, "status": "RUNNING",
        })
        await websocket.send_json({
            "type": "current_task", "aiName": manager_name, "task": "작업 분석 중...",
        })

        plan_text = await self._plan_silent(manager_name, text, manager_system)

        match = _ORCHESTRATE_RE.search(plan_text)
        if not match:
            # 오케스트레이션 없이 직접 답변한 경우 — 히스토리의 마지막 응답을 UI에 표시
            direct_answer = plan_text.strip()
            await websocket.send_json({
                "type": "log", "aiName": manager_name, "message": direct_answer,
            })
            await websocket.send_json({
                "type": "status", "aiName": manager_name, "status": "COMPLETED",
            })
            await websocket.send_json({
                "type": "current_task", "aiName": manager_name, "task": "",
            })
            await websocket.send_json({"type": "orchestration_done", "aiName": manager_name})
            return

        try:
            plan_data = json.loads(match.group(1).strip())
            subtasks: list[dict] = plan_data.get("subtasks", [])
            plan_summary = plan_data.get("plan", "작업 분배 완료")
        except json.JSONDecodeError:
            await websocket.send_json({
                "type": "log", "aiName": manager_name,
                "message": "[오류] 계획 파싱 실패 — 직접 처리합니다.",
            })
            await websocket.send_json({"type": "orchestration_done", "aiName": manager_name})
            return

        if not subtasks:
            await websocket.send_json({"type": "orchestration_done", "aiName": manager_name})
            return

        # 계획 요약을 UI에 깔끔하게 표시
        await websocket.send_json({
            "type": "log", "aiName": manager_name,
            "message": f"[계획 완료] {plan_summary}",
        })

        # Phase 2: 서브태스크 배분
        assignments: list[tuple[str, str]] = []
        for subtask in subtasks:
            idx = subtask.get("worker_index", 1) - 1
            if idx < len(worker_names):
                wname = worker_names[idx]
                wtask = subtask.get("task", "")
                await websocket.send_json({
                    "type": "subtask_assign",
                    "from": manager_name,
                    "to": wname,
                    "task": wtask,
                })
                assignments.append((wname, wtask))
            else:
                # 워커 수 부족 — 가용 워커에게 라운드로빈 배분
                fallback_idx = idx % len(worker_names)
                wname = worker_names[fallback_idx]
                wtask = subtask.get("task", "")
                await websocket.send_json({
                    "type": "log", "aiName": manager_name,
                    "message": f"[재배분] 팀원 {idx+1} 없음 → {wname}에게 추가 배분",
                })
                assignments.append((wname, wtask))

        # Phase 3: 워커 병렬 실행
        results: list = await asyncio.gather(
            *[self._stream(wn, wt, websocket) for wn, wt in assignments],
            return_exceptions=True,
        )

        # Phase 4: 관리자 결과 종합
        valid = [
            f"### {assignments[i][0]} 결과:\n{r}"
            for i, r in enumerate(results)
            if isinstance(r, str) and r.strip()
        ]
        if valid:
            synthesis = (
                "팀원들의 작업이 완료되었습니다. 결과를 종합하여 사용자에게 최종 답변을 작성해주세요.\n\n"
                f"원래 요청: {text}\n\n" + "\n\n".join(valid)
            )
            await websocket.send_json({"type": "orchestration_synthesis", "aiName": manager_name})
            await self._stream(manager_name, synthesis, websocket, system_override=manager_system)
        else:
            # 유효한 워커 결과가 없는 경우
            await websocket.send_json({
                "type": "log", "aiName": manager_name,
                "message": "[오류] 팀원 결과를 받지 못했습니다. 워커 모델이 설정되어 있는지 확인하세요.",
            })
            await websocket.send_json({"type": "status", "aiName": manager_name, "status": "COMPLETED"})

        await websocket.send_json({"type": "orchestration_done", "aiName": manager_name})

        # ── 오케스트레이션 로그 저장 (파인튜닝 데이터셋용) ──
        synthesis_text = ""
        manager_state = self.get(manager_name)
        if manager_state and manager_state.history:
            synthesis_text = manager_state.history[-1].get("content", "")

        worker_results_for_log = [
            {"worker": assignments[i][0], "result": r if isinstance(r, str) else ""}
            for i, r in enumerate(results)
        ] if 'results' in dir() and results else []

        await asyncio.to_thread(
            _save_orch_log,
            manager_name,
            worker_names,
            text,
            plan_summary,
            assignments,
            worker_results_for_log,
            synthesis_text,
        )


agent_manager = AgentManager()
