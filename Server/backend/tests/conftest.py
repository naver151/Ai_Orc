"""
pytest 공통 픽스처

사용 방법:
  cd Server/backend
  pip install pytest pytest-asyncio httpx
  pytest tests/ -v
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app

# ── 인메모리 SQLite DB (테스트 전용) ────────────────────────────
TEST_DB_URL = "sqlite:///./test.db"

engine_test = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """테스트 시작 전 테이블 생성, 종료 후 삭제."""
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture()
def client():
    """FastAPI TestClient — 매 테스트마다 DB 오버라이드."""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def db():
    """직접 DB 세션 (모델 직접 조작 시 사용)."""
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
