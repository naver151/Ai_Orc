"""
OpenAI 파인튜닝 제출 및 상태 확인 스크립트

사용법:
  # 1. 데이터셋 생성
  python finetune/generate_dataset.py

  # 2. 파인튜닝 제출
  python finetune/run_finetune.py submit

  # 3. 상태 확인 (완료까지 몇 분~몇 시간 소요)
  python finetune/run_finetune.py status <job_id>

  # 4. 완료된 모델 ID 확인
  python finetune/run_finetune.py result <job_id>
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(override=True, encoding="utf-8")

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DATASET_PATH = os.path.join(os.path.dirname(__file__), "finetune_data.jsonl")
BASE_MODEL = "gpt-4o-mini-2024-07-18"  # 파인튜닝 비용 최소화


def submit():
    if not os.path.exists(DATASET_PATH):
        print("데이터셋 없음. 먼저 실행하세요:")
        print("  python finetune/generate_dataset.py")
        return

    # 파일 업로드
    print(f"파일 업로드 중: {DATASET_PATH}")
    with open(DATASET_PATH, "rb") as f:
        file_resp = client.files.create(file=f, purpose="fine-tune")
    file_id = file_resp.id
    print(f"업로드 완료: {file_id}")

    # 파인튜닝 작업 생성
    job = client.fine_tuning.jobs.create(
        training_file=file_id,
        model=BASE_MODEL,
        suffix="ai-orc-manager",  # 모델 이름에 붙는 접미사
        hyperparameters={
            "n_epochs": 3,  # 데이터가 적으므로 3 에폭
        },
    )
    print(f"\n파인튜닝 시작!")
    print(f"  Job ID : {job.id}")
    print(f"  상태   : {job.status}")
    print(f"\n상태 확인:")
    print(f"  python finetune/run_finetune.py status {job.id}")

    # job_id 로컬 저장
    with open(os.path.join(os.path.dirname(__file__), "job_id.txt"), "w") as f:
        f.write(job.id)
    print(f"\njob_id.txt에 저장됨.")


def status(job_id: str):
    job = client.fine_tuning.jobs.retrieve(job_id)
    print(f"상태: {job.status}")
    print(f"모델: {job.fine_tuned_model or '(미완료)'}")
    if job.status == "succeeded":
        print(f"\n완료! 파인튜닝된 모델 ID:")
        print(f"  {job.fine_tuned_model}")
        print(f"\n.env에 다음을 추가하세요:")
        print(f"  FINETUNED_MODEL={job.fine_tuned_model}")
    elif job.status == "failed":
        print(f"실패 원인: {job.error}")
    else:
        print("아직 진행 중입니다. 몇 분 후 다시 확인하세요.")

    # 최근 이벤트 출력
    events = client.fine_tuning.jobs.list_events(job_id, limit=5)
    print("\n최근 이벤트:")
    for e in reversed(list(events.data)):
        print(f"  [{e.created_at}] {e.message}")


def watch(job_id: str, interval: int = 30):
    """완료까지 주기적으로 상태 확인."""
    print(f"{interval}초마다 상태 확인 중... (Ctrl+C로 중단)")
    while True:
        job = client.fine_tuning.jobs.retrieve(job_id)
        print(f"[{time.strftime('%H:%M:%S')}] 상태: {job.status}")
        if job.status in ("succeeded", "failed", "cancelled"):
            status(job_id)
            break
        time.sleep(interval)


def result(job_id: str):
    job = client.fine_tuning.jobs.retrieve(job_id)
    if job.fine_tuned_model:
        print(f"파인튜닝 모델 ID: {job.fine_tuned_model}")
        print(f"\n.env에 추가:")
        print(f"FINETUNED_MODEL={job.fine_tuned_model}")
    else:
        print(f"아직 완료 안 됨. 상태: {job.status}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "submit":
        submit()
    elif cmd == "status" and len(sys.argv) > 2:
        status(sys.argv[2])
    elif cmd == "watch" and len(sys.argv) > 2:
        interval = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        watch(sys.argv[2], interval)
    elif cmd == "result" and len(sys.argv) > 2:
        result(sys.argv[2])
    else:
        # job_id.txt가 있으면 자동 사용
        job_file = os.path.join(os.path.dirname(__file__), "job_id.txt")
        if cmd == "status" and os.path.exists(job_file):
            status(open(job_file).read().strip())
        elif cmd == "watch" and os.path.exists(job_file):
            watch(open(job_file).read().strip())
        else:
            print(__doc__)
