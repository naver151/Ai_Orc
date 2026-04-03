# AI Crew Commander - Backend Dev Server
# Usage: .\run_dev.ps1
# Run from: Server/backend/

Write-Host "=== AI Crew Commander Backend ===" -ForegroundColor Cyan
Write-Host "Starting uvicorn (watching app/ only)..." -ForegroundColor Green

# .venv 활성화
& ".\.venv\Scripts\Activate.ps1"

# app 디렉토리만 감시 → .venv 패키지 변경으로 인한 무한 재시작 방지
uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
