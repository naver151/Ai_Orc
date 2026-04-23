# AI Crew Commander - Backend Dev Server
# Usage: .\run_dev.ps1
# Run from: Server/backend/

$Root = $PSScriptRoot   # run_dev.ps1 이 있는 디렉토리 (Server/backend)

Write-Host ""
Write-Host "=== AI Crew Commander Backend ===" -ForegroundColor Cyan
Write-Host ""

# ── 1. .venv 활성화 ──────────────────────────────────────────────
& "$Root\.venv\Scripts\Activate.ps1"

# ── 2. Redis 상태 확인 / 시작 ────────────────────────────────────
Write-Host "[1/3] Redis 확인 중..." -ForegroundColor Yellow
$redisRunning = $false
try {
    $pong = & redis-cli ping 2>$null
    if ($pong -eq "PONG") { $redisRunning = $true }
} catch {}

if ($redisRunning) {
    Write-Host "      Redis 이미 실행 중 (PONG)" -ForegroundColor Green
} else {
    Write-Host "      Redis 시작 중..." -ForegroundColor Yellow
    Start-Process -FilePath "redis-server" `
                  -WindowStyle Minimized `
                  -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1

    # 재확인
    try {
        $pong = & redis-cli ping 2>$null
        if ($pong -eq "PONG") {
            Write-Host "      Redis 시작 완료" -ForegroundColor Green
            $redisRunning = $true
        }
    } catch {}

    if (-not $redisRunning) {
        Write-Host "      [경고] Redis를 시작하지 못했습니다." -ForegroundColor Red
        Write-Host "      Celery 없이 계속 진행합니다 (UI SSE 스트리밍은 정상 동작)." -ForegroundColor DarkYellow
    }
}

# ── 3. Celery Worker 시작 (Redis 실행 중일 때만) ──────────────────
if ($redisRunning) {
    Write-Host "[2/3] Celery Worker 시작 중..." -ForegroundColor Yellow

    $celeryArgs = @(
        "-NoExit",
        "-Command",
        "cd '$Root'; & '.\.venv\Scripts\Activate.ps1'; celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2"
    )
    Start-Process -FilePath "powershell.exe" `
                  -ArgumentList $celeryArgs `
                  -WindowStyle Normal

    Write-Host "      Celery Worker 창이 열렸습니다." -ForegroundColor Green
} else {
    Write-Host "[2/3] Celery Worker 건너뜀 (Redis 없음)" -ForegroundColor DarkYellow
}

# ── 4. FastAPI (uvicorn) 시작 ─────────────────────────────────────
Write-Host "[3/3] FastAPI (uvicorn) 시작 중..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  http://localhost:8000" -ForegroundColor Cyan
Write-Host "  Ctrl+C 로 종료" -ForegroundColor DarkGray
Write-Host ""

uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
