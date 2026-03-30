# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI multi-agent orchestration system built with FastAPI + PostgreSQL. The goal is a system where multiple AI agents can be assigned tasks and coordinated by an orchestrator.

**Planned tech stack:** FastAPI, PostgreSQL, SQLAlchemy, Redis, ChromaDB, OpenAI API

## Development Setup

```bash
cd Server/backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Requires PostgreSQL running locally:
- Host: `localhost:5432`
- Credentials: `postgres:postgres`
- Database: `ai_orc`

## Running the Server

```bash
cd Server/backend
uvicorn app.main:app --reload
```

Server runs at `http://localhost:8000`. Tables are auto-created on startup.

## Architecture

All backend code lives in `Server/backend/app/`:

- **`main.py`** — FastAPI app init, router registration, health endpoints (`GET /`, `GET /db-test`)
- **`db.py`** — SQLAlchemy engine/session setup, `get_db()` dependency injected into all routers
- **`models.py`** — ORM models: `ProjectModel`, `AgentModel`, `TaskModel` with FK relationships
- **`schemas.py`** — Pydantic v2 schemas (separate Create/Read pairs per entity, `from_attributes=True`)
- **`routers/`** — One file per resource (`project.py`, `agent.py`, `task.py`); no service layer currently

**Request flow:** Router → `get_db()` dependency → SQLAlchemy model CRUD → Pydantic schema serialization

Agent creation validates the referenced project exists. Task creation validates both project and agent exist, and that the agent belongs to the specified project.

## Implementation Roadmap (from CLAUDE.me)

1. Task status update API
2. Orchestrator service
3. `TaskExecution` table
4. Agent Memory with RAG (ChromaDB)
5. OpenAI API integration
6. Redis queue
7. ChromaDB vector storage

When adding new features, follow the existing pattern: add ORM model to `models.py`, Pydantic schemas to `schemas.py`, and a new router in `routers/`. A service layer does not exist yet — business logic currently lives directly in routers.

## 개발 규칙

- 초보 백엔드 기준으로 설명
- 코드는 완성형으로 제공
- 구조 설계 이유 같이 설명
