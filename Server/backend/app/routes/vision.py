"""
Vision 파이프라인 라우트

YOLO(객체 탐지) → LLM(해석/보고서) 체이닝 엔드포인트.

POST /vision/analyze
  - image_path : 업로드된 이미지 서버 경로
  - question   : LLM에게 던질 질문 (선택)
  - provider   : LLM provider (기본: github)
  - stream     : True면 SSE 스트리밍 응답

응답 흐름:
  1. YOLO로 이미지 분석 → 구조화된 탐지 결과
  2. 탐지 결과를 컨텍스트로 LLM에 전달
  3. LLM이 결과를 해석하여 자연어 보고서 생성
"""

from __future__ import annotations
import asyncio
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai.lc_providers import get_lc_model
from langchain_core.messages import HumanMessage, SystemMessage

router = APIRouter(prefix="/vision", tags=["vision"])

UPLOAD_DIR = "./uploads"

_VISION_SYSTEM = (
    "당신은 컴퓨터 비전 분석 전문가입니다.\n"
    "YOLO 객체 탐지 결과를 바탕으로 이미지의 상황을 명확하게 해석하고,\n"
    "사용자의 질문에 구체적이고 실용적인 답변을 제공합니다.\n"
    "탐지된 객체의 종류, 수량, 신뢰도를 바탕으로 전문적인 분석을 수행하세요."
)


class VisionRequest(BaseModel):
    image_path: str
    question:   str   = "이 이미지에서 무엇이 탐지되었나요? 탐지 결과를 분석하고 상황을 설명해주세요."
    provider:   str   = "github"
    yolo_model: str   = "yolov8n.pt"


async def _run_yolo(image_path: str, model_name: str) -> dict:
    """YOLO 탐지를 비동기로 실행하고 구조화된 결과 반환."""
    try:
        from ultralytics import YOLO
        model = YOLO(model_name)
        loop  = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: model(image_path, verbose=False)
        )

        detections = []
        class_counts: dict[str, int]         = {}
        class_confs:  dict[str, list[float]] = {}

        for r in results:
            for box in r.boxes:
                label = r.names[int(box.cls)]
                conf  = float(box.conf)
                xyxy  = box.xyxy[0].tolist()
                detections.append({
                    "label": label,
                    "confidence": round(conf, 3),
                    "bbox": [round(v, 1) for v in xyxy],
                })
                class_counts[label] = class_counts.get(label, 0) + 1
                class_confs.setdefault(label, []).append(conf)

        summary = []
        for label, count in sorted(class_counts.items(), key=lambda x: -x[1]):
            avg_conf = sum(class_confs[label]) / len(class_confs[label])
            summary.append(f"{label} {count}개 (신뢰도 {avg_conf:.0%})")

        return {
            "total":      len(detections),
            "detections": detections,
            "summary":    summary,
            "model":      model_name,
        }

    except ImportError:
        return {"error": "ultralytics 패키지가 설치되지 않았습니다. pip install ultralytics"}
    except Exception as e:
        return {"error": str(e)}


def _build_yolo_context(yolo_result: dict, image_path: str) -> str:
    """YOLO 결과를 LLM 컨텍스트 텍스트로 변환."""
    if "error" in yolo_result:
        return f"[YOLO 오류] {yolo_result['error']}"

    total   = yolo_result["total"]
    summary = yolo_result["summary"]
    fname   = os.path.basename(image_path)

    if total == 0:
        return f"이미지 파일: {fname}\nYOLO 탐지 결과: 탐지된 객체 없음"

    lines = [
        f"이미지 파일: {fname}",
        f"YOLO 탐지 결과 (총 {total}개 객체):",
    ]
    for item in summary:
        lines.append(f"  - {item}")

    # 상세 탐지 목록 (최대 20개)
    lines.append("\n상세 탐지 목록:")
    for d in yolo_result["detections"][:20]:
        lines.append(
            f"  [{d['label']}] 신뢰도: {d['confidence']:.0%}  위치: {d['bbox']}"
        )
    if total > 20:
        lines.append(f"  ... 외 {total - 20}개")

    return "\n".join(lines)


@router.post("/analyze")
async def analyze_image(req: VisionRequest):
    """
    YOLO → LLM 체이닝 분석 엔드포인트.
    SSE(text/event-stream) 형식으로 실시간 스트리밍 응답.

    이벤트 형식:
      data: {"stage": "yolo",   "result": {...}}
      data: {"stage": "llm",    "chunk":  "..."}
      data: {"stage": "done"}
    """
    # 파일 존재 확인
    if not os.path.exists(req.image_path):
        raise HTTPException(status_code=404, detail=f"이미지 파일을 찾을 수 없습니다: {req.image_path}")

    async def event_stream():
        import json

        # ── 1단계: YOLO 탐지 ──────────────────────────────
        yield f'data: {json.dumps({"stage": "yolo_start"}, ensure_ascii=False)}\n\n'

        yolo_result = await _run_yolo(req.image_path, req.yolo_model)
        yolo_context = _build_yolo_context(yolo_result, req.image_path)

        yield f'data: {json.dumps({"stage": "yolo", "result": yolo_result, "context": yolo_context}, ensure_ascii=False)}\n\n'

        # ── 2단계: LLM 해석 ───────────────────────────────
        yield f'data: {json.dumps({"stage": "llm_start"}, ensure_ascii=False)}\n\n'

        prompt = (
            f"[YOLO 탐지 컨텍스트]\n{yolo_context}\n\n"
            f"[사용자 질문]\n{req.question}"
        )
        messages = [
            SystemMessage(content=_VISION_SYSTEM),
            HumanMessage(content=prompt),
        ]

        model = get_lc_model(req.provider, streaming=False)

        try:
            resp = await model.ainvoke(messages)
            llm_text = resp.content

            # 청크 단위로 스트리밍
            chunk_size = 12
            for i in range(0, len(llm_text), chunk_size):
                chunk = llm_text[i:i + chunk_size]
                yield f'data: {json.dumps({"stage": "llm", "chunk": chunk}, ensure_ascii=False)}\n\n'
                await asyncio.sleep(0.01)

        except Exception as e:
            yield f'data: {json.dumps({"stage": "llm", "chunk": f"[LLM 오류] {e}"}, ensure_ascii=False)}\n\n'

        yield f'data: {json.dumps({"stage": "done"}, ensure_ascii=False)}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/models")
def list_yolo_models():
    """사용 가능한 YOLO 모델 목록."""
    return {
        "models": [
            {"id": "yolov8n.pt",  "name": "YOLOv8 Nano",   "desc": "빠름, 가벼움"},
            {"id": "yolov8s.pt",  "name": "YOLOv8 Small",  "desc": "균형"},
            {"id": "yolov8m.pt",  "name": "YOLOv8 Medium", "desc": "정확도 높음"},
            {"id": "yolov8l.pt",  "name": "YOLOv8 Large",  "desc": "고정밀"},
            {"id": "yolov8x.pt",  "name": "YOLOv8 XLarge", "desc": "최고 정밀도"},
        ]
    }
