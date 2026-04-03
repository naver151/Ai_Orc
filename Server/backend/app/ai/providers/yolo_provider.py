"""
YOLO 객체 탐지 프로바이더.
이미지 경로를 입력받아 탐지 결과를 스트리밍 형태로 반환합니다.
"""

import asyncio
import os
from typing import AsyncGenerator

from .base import AIProvider


class YOLOProvider(AIProvider):
    """Ultralytics YOLO 객체 탐지 프로바이더."""

    def __init__(self, model: str = "yolov8n.pt"):
        from ultralytics import YOLO  # 임포트 지연 (설치 안 된 경우 대비)
        self._model_name = model
        self._model = YOLO(model)  # 최초 실행 시 자동 다운로드

    @property
    def model_name(self) -> str:
        return self._model_name

    async def stream_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        마지막 메시지의 content를 이미지 경로로 사용해 YOLO 탐지 실행.
        결과를 청크 단위로 스트리밍합니다.
        """
        image_path = messages[-1]["content"].strip()

        if not os.path.exists(image_path):
            yield f"[오류] 이미지 파일을 찾을 수 없습니다: {image_path}"
            return

        # YOLO 탐지 실행 (동기 함수 → 비동기 루프에서 실행)
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: self._model(image_path, verbose=False)
        )

        # 탐지 결과 집계
        class_counts: dict[str, int] = {}
        class_confs: dict[str, list[float]] = {}
        total = 0

        for r in results:
            for box in r.boxes:
                label = r.names[int(box.cls)]
                conf = float(box.conf)
                class_counts[label] = class_counts.get(label, 0) + 1
                class_confs.setdefault(label, []).append(conf)
                total += 1

        # 결과 텍스트 구성
        lines: list[str] = []
        lines.append(f"[YOLO 탐지 완료] 모델: {self._model_name}\n")
        lines.append(f"이미지: {os.path.basename(image_path)}\n\n")

        if total == 0:
            lines.append("탐지된 객체가 없습니다.")
        else:
            lines.append(f"총 {total}개 객체 탐지됨:\n\n")
            for label, count in sorted(class_counts.items(), key=lambda x: -x[1]):
                avg_conf = sum(class_confs[label]) / len(class_confs[label])
                lines.append(f"  - {label}: {count}개 (평균 신뢰도 {avg_conf:.0%})\n")

        # 줄 단위로 스트리밍
        full_text = "".join(lines)
        chunk_size = 8
        for i in range(0, len(full_text), chunk_size):
            yield full_text[i:i + chunk_size]
            await asyncio.sleep(0.01)
