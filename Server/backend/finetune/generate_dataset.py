"""
관리자 AI 파인튜닝용 합성 데이터셋 생성기
- 개발 / 투자·알파 / 리서치 도메인 예시 + 직접 답변 예시 생성
- 출력: finetune_data.jsonl  (OpenAI fine-tuning 포맷)

사용법:
    python finetune/generate_dataset.py
    python finetune/generate_dataset.py --from-db   # DB 로그도 포함
"""

import json
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SYSTEM_PROMPT = (
    "당신은 AI 팀의 총괄 관리자입니다. "
    "사용자의 요청을 분석하여 팀원들에게 작업을 분배하거나 직접 답변합니다. "
    "분배 시에는 반드시 <ORCHESTRATE>{...}</ORCHESTRATE> 형식만 사용하세요."
)

# ── 합성 훈련 예시 ────────────────────────────────────────────────────────────
# 형식: (user_prompt, n_workers, assistant_response)
# assistant_response가 None이면 직접 답변 케이스

ORCHESTRATE_EXAMPLES = [

    # ── 개발 ──────────────────────────────────────────────────────────────────
    (
        "팀원: 2명\n\n사용자 요청: REST API 서버를 만들어줘",
        """<ORCHESTRATE>
{"plan": "API 설계와 구현을 병렬로 분리", "subtasks": [
  {"worker_index": 1, "task": "FastAPI 기반 REST API 엔드포인트 설계: 리소스 구조, URL 패턴, 요청/응답 스키마, HTTP 상태코드 정의"},
  {"worker_index": 2, "task": "설계 스펙에 맞는 FastAPI 구현: 라우터, SQLAlchemy 모델, CRUD 로직, 예외 처리 포함"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 파이썬으로 웹 크롤러 만들어줘",
        """<ORCHESTRATE>
{"plan": "크롤러 설계와 구현을 병렬 처리", "subtasks": [
  {"worker_index": 1, "task": "웹 크롤러 아키텍처 설계: 대상 사이트 분석, requests/BeautifulSoup 구조 설계, 데이터 저장 스키마 정의"},
  {"worker_index": 2, "task": "크롤러 코드 구현: 요청 처리, HTML 파싱, 데이터 추출, CSV/JSON 저장, 재시도 로직 포함"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 3명\n\n사용자 요청: 할 일 관리 앱을 만들어줘. 백엔드, 프론트엔드, DB 설계를 나눠서",
        """<ORCHESTRATE>
{"plan": "백엔드·프론트엔드·DB를 3명이 병렬 담당", "subtasks": [
  {"worker_index": 1, "task": "PostgreSQL DB 스키마 설계: todos 테이블, 사용자 테이블, 인덱스, 마이그레이션 SQL 작성"},
  {"worker_index": 2, "task": "FastAPI 백엔드 구현: CRUD 엔드포인트(/todos GET·POST·PUT·DELETE), JWT 인증, SQLAlchemy ORM"},
  {"worker_index": 3, "task": "React 프론트엔드 구현: 할 일 목록 컴포넌트, 추가/수정/삭제 UI, axios로 백엔드 API 연동"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 이미지 분류 모델 학습 파이프라인 구축해줘",
        """<ORCHESTRATE>
{"plan": "데이터 전처리와 모델 학습 코드를 병렬 작성", "subtasks": [
  {"worker_index": 1, "task": "이미지 데이터 전처리 파이프라인: 데이터 로더(torchvision), augmentation(flip·rotate·normalize), train/val/test 분할 코드"},
  {"worker_index": 2, "task": "ResNet 기반 분류 모델 학습 코드: 모델 정의, 손실함수(CrossEntropy), Adam 옵티마이저, 에폭 루프, 검증 정확도 출력"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 챗봇 API 서버 만들어줘. OpenAI API 써서",
        """<ORCHESTRATE>
{"plan": "챗봇 로직과 API 서버 구현을 병렬 분리", "subtasks": [
  {"worker_index": 1, "task": "OpenAI API 연동 챗봇 로직: 대화 히스토리 관리, system prompt 설계, 스트리밍 응답 처리, 토큰 한도 초과 시 이전 메시지 잘라내기"},
  {"worker_index": 2, "task": "FastAPI 채팅 서버: POST /chat 엔드포인트, WebSocket /ws 스트리밍, CORS 설정, 요청 유효성 검사"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 데이터베이스 마이그레이션 스크립트 짜줘. MySQL에서 PostgreSQL로",
        """<ORCHESTRATE>
{"plan": "스키마 변환과 데이터 이전을 병렬 작성", "subtasks": [
  {"worker_index": 1, "task": "MySQL → PostgreSQL 스키마 변환 스크립트: 데이터 타입 매핑(TINYINT→BOOLEAN 등), 인덱스·외래키 변환, CREATE TABLE DDL 생성"},
  {"worker_index": 2, "task": "데이터 이전 스크립트: MySQL 읽기 → 변환 → PostgreSQL 삽입, 배치 처리, 트랜잭션 롤백, 진행률 출력"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 3명\n\n사용자 요청: 마이크로서비스 아키텍처로 전자상거래 백엔드 설계해줘",
        """<ORCHESTRATE>
{"plan": "서비스 분리 설계·구현·인프라를 3명이 병렬 담당", "subtasks": [
  {"worker_index": 1, "task": "마이크로서비스 아키텍처 설계: 사용자·상품·주문·결제 서비스 경계 정의, API Gateway 패턴, 서비스 간 통신(gRPC/REST) 방식 문서화"},
  {"worker_index": 2, "task": "사용자·상품 서비스 구현: FastAPI, JWT 인증, 상품 CRUD, PostgreSQL 스키마"},
  {"worker_index": 3, "task": "주문·결제 서비스 + Docker Compose: 서비스 컨테이너화, RabbitMQ 이벤트 버스, 결제 상태 관리"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 실시간 주식 가격 모니터링 대시보드 만들어줘",
        """<ORCHESTRATE>
{"plan": "데이터 수집 백엔드와 시각화 프론트엔드를 병렬 구현", "subtasks": [
  {"worker_index": 1, "task": "주식 데이터 수집 백엔드: yfinance로 실시간 가격 폴링, WebSocket으로 클라이언트에 푸시, FastAPI 서버 구성"},
  {"worker_index": 2, "task": "React 대시보드: WebSocket 연결, recharts로 실시간 캔들차트, 종목 추가/삭제, 가격 변동 색상 표시"}
]}
</ORCHESTRATE>"""
    ),

    # ── 투자·알파 ──────────────────────────────────────────────────────────────
    (
        "팀원: 3명\n\n사용자 요청: 삼성전자 투자 분석해줘",
        """<ORCHESTRATE>
{"plan": "재무·시장·리스크 3축 병렬 분석", "subtasks": [
  {"worker_index": 1, "task": "삼성전자 최근 3개년 재무제표 분석: 매출 성장률, 영업이익률, ROE, 부채비율 수치 중심 작성"},
  {"worker_index": 2, "task": "반도체 시장 동향 및 경쟁사 비교: SK하이닉스·TSMC·인텔과 점유율·기술력·가격 경쟁력 비교"},
  {"worker_index": 3, "task": "투자 리스크 및 포인트 정리: 지정학적 리스크, 업황 사이클, PER·PBR 기반 밸류에이션 투자 의견"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 코스피 200 퀀트 전략 분석해줘",
        """<ORCHESTRATE>
{"plan": "전략 설계와 백테스트 코드를 병렬 작성", "subtasks": [
  {"worker_index": 1, "task": "코스피 200 기반 퀀트 전략 설계: 팩터 선정(PBR·ROE·모멘텀), 리밸런싱 주기, 포트폴리오 비중 규칙, 벤치마크 비교 방법론"},
  {"worker_index": 2, "task": "백테스트 코드 구현: FinanceDataReader로 데이터 수집, pandas로 팩터 계산, 월별 리밸런싱 시뮬레이션, 샤프지수·MDD 출력"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 비트코인 단기 트레이딩 전략 분석해줘",
        """<ORCHESTRATE>
{"plan": "기술적 분석과 자동매매 로직을 병렬 작성", "subtasks": [
  {"worker_index": 1, "task": "비트코인 기술적 분석: RSI·MACD·볼린저밴드 지표 기반 매수/매도 시그널 정의, 과거 데이터로 신호 정확도 검증"},
  {"worker_index": 2, "task": "자동매매 봇 코드: ccxt로 거래소 API 연동, 시그널 감지 시 주문 실행, 손절·익절 로직, 포지션 관리"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 3명\n\n사용자 요청: 국내 2차전지 섹터 투자 리포트 작성해줘",
        """<ORCHESTRATE>
{"plan": "기업 분석·산업 동향·투자 의견을 3명이 병렬 담당", "subtasks": [
  {"worker_index": 1, "task": "LG에너지솔루션·삼성SDI·SK온 재무 분석: 매출·영업이익·수주잔고·설비투자(CAPEX) 비교"},
  {"worker_index": 2, "task": "2차전지 산업 동향: 글로벌 전기차 보급률, CATL·파나소닉 경쟁 현황, 원자재(리튬·니켈) 가격 추이"},
  {"worker_index": 3, "task": "투자 의견 및 리스크: 섹터 밸류에이션, 보조금 정책 리스크, 목표주가 산출 근거 작성"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 미국 나스닥 IT 섹터 ETF 비교 분석해줘",
        """<ORCHESTRATE>
{"plan": "ETF 성과 비교와 구성 종목 분석을 병렬 처리", "subtasks": [
  {"worker_index": 1, "task": "QQQ·XLK·VGT ETF 성과 비교: 1년·3년·5년 수익률, 변동성, 샤프지수, 운용보수(TER) 비교표 작성"},
  {"worker_index": 2, "task": "ETF 구성 종목 분석: 상위 10개 종목 비교, 섹터 편중도, 애플·마이크로소프트·엔비디아 비중 차이 및 시사점"}
]}
</ORCHESTRATE>"""
    ),

    # ── 리서치·보고서 ──────────────────────────────────────────────────────────
    (
        "팀원: 2명\n\n사용자 요청: 국내 AI 스타트업 시장 현황 보고서 작성해줘",
        """<ORCHESTRATE>
{"plan": "시장 현황 조사와 분석·인사이트를 병렬 처리", "subtasks": [
  {"worker_index": 1, "task": "국내 AI 스타트업 현황 조사: 주요 기업 목록, 투자 규모, 성장률, 정부 지원 정책 데이터 수집 및 정리"},
  {"worker_index": 2, "task": "AI 스타트업 시장 분석: 글로벌 대비 국내 경쟁력, 유망 섹터(헬스케어·제조·금융), 향후 전망 및 시사점 도출"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 생성형 AI 시장 트렌드 리포트 써줘",
        """<ORCHESTRATE>
{"plan": "기술 동향 조사와 시장 전망 분석을 병렬 처리", "subtasks": [
  {"worker_index": 1, "task": "생성형 AI 기술 동향: LLM·이미지·음악 생성 최신 모델 현황, OpenAI·구글·메타·앤스로픽 동향, 오픈소스 생태계"},
  {"worker_index": 2, "task": "생성형 AI 시장 전망: 글로벌 시장 규모 추이, B2B 활용 사례, 주요 리스크(저작권·규제), 국내 기업 대응 전략"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 3명\n\n사용자 요청: 전기차 시장 글로벌 경쟁 분석 보고서 작성해줘",
        """<ORCHESTRATE>
{"plan": "기업 분석·시장 데이터·전망을 3명이 병렬 담당", "subtasks": [
  {"worker_index": 1, "task": "테슬라·BYD·현대차 전기차 판매량·수익성·기술력 비교: 2022-2024 데이터 기반 비교표 작성"},
  {"worker_index": 2, "task": "글로벌 전기차 시장 데이터: 국가별 보급률, 충전 인프라 현황, 배터리 가격 하락 추이, IEA 전망"},
  {"worker_index": 3, "task": "전기차 산업 전망 및 투자 시사점: 주요 리스크(원자재·정책), 2030년 예측, 국내 부품사 수혜 분석"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 클라우드 서비스 AWS vs Azure vs GCP 비교 분석해줘",
        """<ORCHESTRATE>
{"plan": "기능 비교와 가격·사례 분석을 병렬 처리", "subtasks": [
  {"worker_index": 1, "task": "AWS·Azure·GCP 핵심 서비스 비교: 컴퓨팅·스토리지·DB·AI/ML·네트워크 주요 서비스 대응표 및 기능 차이 정리"},
  {"worker_index": 2, "task": "가격 비교 및 실제 사용 사례: 동일 워크로드 기준 비용 시뮬레이션, 기업 규모별 선택 기준, 국내 레퍼런스 사례"}
]}
</ORCHESTRATE>"""
    ),
    (
        "팀원: 2명\n\n사용자 요청: 국내 핀테크 규제 환경 분석해줘",
        """<ORCHESTRATE>
{"plan": "규제 현황 조사와 업계 영향 분석을 병렬 처리", "subtasks": [
  {"worker_index": 1, "task": "국내 핀테크 규제 현황: 전자금융거래법·오픈뱅킹·마이데이터 법령 정리, 금융위원회 샌드박스 사례, 최근 개정 사항"},
  {"worker_index": 2, "task": "규제 환경이 핀테크 기업에 미치는 영향: 진입 장벽 분석, 규제 완화 수혜 기업, 해외(영국·싱가포르) 규제 비교 및 시사점"}
]}
</ORCHESTRATE>"""
    ),
]

DIRECT_ANSWER_EXAMPLES = [
    (
        "팀원: 2명\n\n사용자 요청: 파이썬이란 무엇인가요?",
        "파이썬(Python)은 1991년 귀도 반 로섬이 만든 고수준 프로그래밍 언어입니다. 문법이 간결하고 읽기 쉬우며, 웹 개발·데이터 과학·AI·자동화 등 다양한 분야에서 널리 사용됩니다. 인터프리터 언어로 별도 컴파일 없이 바로 실행할 수 있습니다."
    ),
    (
        "팀원: 2명\n\n사용자 요청: REST API와 GraphQL의 차이가 뭐야?",
        "REST API는 URL 기반으로 리소스를 정의하고 HTTP 메서드(GET·POST·PUT·DELETE)로 조작합니다. GraphQL은 단일 엔드포인트에서 클라이언트가 필요한 필드만 쿼리로 요청합니다. REST는 캐싱이 쉽고 표준이 명확하며, GraphQL은 오버패칭 없이 데이터를 정밀하게 가져올 수 있습니다."
    ),
    (
        "팀원: 3명\n\n사용자 요청: 안녕하세요!",
        "안녕하세요! AI 팀 관리자입니다. 개발·투자·리서치 분야의 작업을 요청해 주시면 팀원들과 협력하여 최고의 결과를 드리겠습니다."
    ),
    (
        "팀원: 2명\n\n사용자 요청: 머신러닝과 딥러닝의 차이는?",
        "머신러닝은 데이터로부터 패턴을 학습하는 알고리즘의 총칭입니다(SVM·랜덤포레스트 등). 딥러닝은 머신러닝의 하위 분야로, 여러 층의 신경망을 사용해 더 복잡한 패턴을 학습합니다. 딥러닝은 이미지·자연어 처리에서 특히 강력하지만 많은 데이터와 컴퓨팅 자원이 필요합니다."
    ),
    (
        "팀원: 2명\n\n사용자 요청: P/E ratio가 뭐야?",
        "P/E ratio(주가수익비율)는 주가를 주당순이익(EPS)으로 나눈 값입니다. 예를 들어 주가 10만원, EPS 5천원이면 P/E = 20입니다. 이 수치가 높으면 성장 기대가 크거나 고평가, 낮으면 저평가 또는 저성장 기업으로 볼 수 있습니다."
    ),
    (
        "팀원: 2명\n\n사용자 요청: 작업 현황이 어떻게 돼?",
        "현재 팀원 2명이 대기 중입니다. 개발·투자·리서치 등 원하시는 작업을 말씀해 주시면 바로 분배하겠습니다."
    ),
    (
        "팀원: 1명\n\n사용자 요청: 파이썬으로 피보나치 수열 짜줘",
        "파이썬 피보나치 수열 구현입니다:\n\n```python\ndef fibonacci(n):\n    a, b = 0, 1\n    for _ in range(n):\n        print(a, end=' ')\n        a, b = b, a + b\n\nfibonacci(10)  # 0 1 1 2 3 5 8 13 21 34\n```\n\n재귀 버전보다 반복문을 쓰는 것이 메모리 효율적입니다."
    ),
    (
        "팀원: 2명\n\n사용자 요청: 오늘 날씨 어때?",
        "저는 실시간 날씨 정보에 접근할 수 없습니다. 날씨 앱이나 검색을 이용해 주세요. 개발·투자·리서치 관련 작업이 있으시면 말씀해 주세요."
    ),
]


def build_record(user_content: str, assistant_content: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]
    }


def load_from_db() -> list[dict]:
    """DB에 저장된 오케스트레이션 로그를 훈련 데이터로 변환."""
    try:
        from app.db import SessionLocal
        from app.models import OrchestrationLog
        import json as _json

        db = SessionLocal()
        logs = db.query(OrchestrationLog).all()
        db.close()

        records = []
        for log in logs:
            if not log.synthesis_result:
                continue
            subtasks = _json.loads(log.subtasks_json or "[]")
            worker_names = _json.loads(log.worker_names or "[]")
            n_workers = len(worker_names)

            # assistant 쪽은 ORCHESTRATE 블록으로 재구성
            subtask_list = ", ".join(
                f'{{"worker_index": {i+1}, "task": "{s["task"]}"}}'
                for i, s in enumerate(subtasks)
            )
            assistant = (
                f'<ORCHESTRATE>\n'
                f'{{"plan": "{log.plan_summary}", "subtasks": [{subtask_list}]}}\n'
                f'</ORCHESTRATE>'
            )
            user_content = f"팀원: {n_workers}명\n\n사용자 요청: {log.user_prompt}"
            records.append(build_record(user_content, assistant))

        print(f"[DB] 로그 {len(records)}건 추가")
        return records
    except Exception as e:
        print(f"[DB] 로드 실패: {e}")
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-db", action="store_true", help="DB 로그도 포함")
    parser.add_argument("--out", default="finetune/finetune_data.jsonl")
    args = parser.parse_args()

    records = []

    # 합성 오케스트레이션 예시
    for user_content, assistant_content in ORCHESTRATE_EXAMPLES:
        records.append(build_record(user_content, assistant_content))

    # 직접 답변 예시
    for user_content, assistant_content in DIRECT_ANSWER_EXAMPLES:
        records.append(build_record(user_content, assistant_content))

    # DB 로그 추가 (선택)
    if args.from_db:
        records.extend(load_from_db())

    out_path = args.out
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"데이터셋 생성 완료: {out_path}  ({len(records)}건)")
    print(f"  - 오케스트레이션 예시: {len(ORCHESTRATE_EXAMPLES)}건")
    print(f"  - 직접 답변 예시:      {len(DIRECT_ANSWER_EXAMPLES)}건")


if __name__ == "__main__":
    main()
