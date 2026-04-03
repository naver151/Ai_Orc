import os
from app.ai_clients.base import BaseAIClient


class YOLOClient(BaseAIClient):
    """Celery 백그라운드 작업용 YOLO 객체 탐지 클라이언트."""

    def __init__(self, model: str = "yolov8n.pt"):
        from ultralytics import YOLO
        self.model = YOLO(model)
        self.model_name = model

    def run(self, role: str, task: str, context: list[str]) -> str:
        """
        task: 이미지 파일 경로
        """
        image_path = task.strip()

        if not os.path.exists(image_path):
            return f"[오류] 이미지 파일을 찾을 수 없습니다: {image_path}"

        results = self.model(image_path, verbose=False)

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

        if total == 0:
            return "탐지된 객체가 없습니다."

        lines = [f"[YOLO 탐지 완료] 총 {total}개 객체:\n"]
        for label, count in sorted(class_counts.items(), key=lambda x: -x[1]):
            avg_conf = sum(class_confs[label]) / len(class_confs[label])
            lines.append(f"  - {label}: {count}개 (신뢰도 {avg_conf:.0%})")

        return "\n".join(lines)
