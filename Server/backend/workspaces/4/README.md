# 프로젝트 개요

이 프로젝트는 FastAPI를 사용하여 RESTful API 서버를 구축하는 예제입니다. 사용자는 이 서버를 활용하여 다양한 엔드포인트를 통해 데이터를 생성, 읽기, 업데이트 및 삭제하는 작업을 수행할 수 있습니다.

## 주요 기능
- 데이터 생성(Create)
- 데이터 읽기(Read)
- 데이터 업데이트(Update)
- 데이터 삭제(Delete)


## 실행 방법

### 1. 필수 요구사항 설치

- Python 3.8 이상
- 패키지 의존성은 `requirements.txt` 파일 포함

```bash
pip install -r requirements.txt
```

### 2. 서버 실행

FastAPI 서버는 다음 명령어를 통해 실행할 수 있습니다:

```bash
python -m uvicorn src.main:app --reload
```

서버는 기본적으로 `http://127.0.0.1:8000`에서 실행됩니다.

### 3. API 문서 확인

서비스가 실행되면, 아래 경로에서 API 문서를 확인할 수 있습니다.

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Redoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)


## 사용법

1. API 문서를 통해 사용 가능한 엔드포인트와 요청 형식을 확인합니다.
2. Swagger UI를 활용하여 API 테스트를 쉽게 진행할 수 있습니다.
3. 필요에 따라 요청을 커스터마이징하여 데이터 처리를 수행합니다.