# ali_researcher - start everything
# Usage: .\start.ps1

$Root     = $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$CondaEnv = "ali-reseach"

function Write-Header { param($msg) Write-Host "`n  $msg" -ForegroundColor Cyan }
function Write-Ok     { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn   { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Err    { param($msg) Write-Host "  [XX] $msg" -ForegroundColor Red }
function Write-Step   { param($msg) Write-Host "  --> $msg" -ForegroundColor DarkCyan }

Clear-Host
Write-Host ""
Write-Host "  ali_researcher - AI research assistant" -ForegroundColor Magenta
Write-Host ""

# 1. Docker
Write-Header "Checking Docker..."
$dockerInfo = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Err "Docker is not running. Please start Docker Desktop first."
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Ok "Docker is running"

# 2. PostgreSQL
Write-Header "PostgreSQL (session storage)"
$pgRunning = docker ps --filter "name=ali-postgres" --filter "status=running" -q
if ($pgRunning) {
    Write-Ok "PostgreSQL already running on port 5432"
} else {
    Write-Step "Starting PostgreSQL..."
    docker start ali-postgres 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Step "Container not found, creating..."
        docker run -d --name ali-postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16 | Out-Null
        Start-Sleep -Seconds 3
        docker exec ali-postgres createdb -U postgres ali_researcher 2>$null | Out-Null
    }
    Start-Sleep -Seconds 2
    $pgRunning = docker ps --filter "name=ali-postgres" --filter "status=running" -q
    if ($pgRunning) {
        Write-Ok "PostgreSQL started on port 5432"
    } else {
        Write-Warn "PostgreSQL failed to start - sessions will be in-memory only"
    }
}

# 3. SearXNG
Write-Header "SearXNG (web search)"
$searxRunning = docker ps --filter "name=searxng-core" --filter "status=running" -q
if ($searxRunning) {
    Write-Ok "SearXNG already running on http://localhost:8080"
} else {
    Write-Step "Starting SearXNG..."
    $searxDir = "C:\searxng"
    if (Test-Path "$searxDir\docker-compose.yml") {
        Push-Location $searxDir
        docker compose up -d | Out-Null
        Pop-Location
        Start-Sleep -Seconds 2
        $searxRunning = docker ps --filter "name=searxng-core" --filter "status=running" -q
        if ($searxRunning) {
            Write-Ok "SearXNG started on http://localhost:8080"
        } else {
            Write-Warn "SearXNG failed to start - using public fallback"
        }
    } else {
        Write-Warn "SearXNG not found at C:\searxng - using public fallback"
    }
}

# 4. Memgraph
Write-Header "Memgraph (knowledge graph)"
$mgRunning = docker ps --filter "name=memgraph" --filter "status=running" -q
if ($mgRunning) {
    Write-Ok "Memgraph already running on bolt://localhost:7687"
} else {
    Write-Step "Starting Memgraph..."
    docker start memgraph 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Step "Container not found, creating..."
        docker run -d -p 7687:7687 -p 7444:7444 --name memgraph memgraph/memgraph-mage | Out-Null
    }
    Start-Sleep -Seconds 3
    $mgRunning = docker ps --filter "name=memgraph" --filter "status=running" -q
    if ($mgRunning) {
        Write-Ok "Memgraph started on bolt://localhost:7687"
    } else {
        Write-Warn "Memgraph failed to start - citation graph will use basic layout"
    }
}

# 5. Backend
Write-Header "Backend (FastAPI)"
Write-Step "Starting uvicorn on http://localhost:8000 ..."
$condaInit = "$env:USERPROFILE\miniconda3\shell\condabin\conda-hook.ps1"
if (-not (Test-Path $condaInit)) {
    $condaInit = "$env:USERPROFILE\anaconda3\shell\condabin\conda-hook.ps1"
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host '  [BACKEND] ali_researcher' -ForegroundColor Cyan; & '$condaInit'; conda activate $CondaEnv; cd '$Root'; uvicorn backend.main:app --reload --port 8000"
Start-Sleep -Seconds 4

try {
    $health = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -TimeoutSec 5 -UseBasicParsing
    if ($health.StatusCode -eq 200) {
        Write-Ok "Backend healthy at http://localhost:8000"
    }
} catch {
    Write-Warn "Backend still starting... check the terminal window"
}

# 6. Frontend
Write-Header "Frontend (Next.js)"
Write-Step "Starting Next.js on http://localhost:3000 ..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Frontend'; npm run dev"
Start-Sleep -Seconds 3

# 7. Summary
Write-Host ""
Write-Host "  All services launched!" -ForegroundColor Green
Write-Host ""
Write-Host "   Frontend   ->  http://localhost:3000" -ForegroundColor White
Write-Host "   Backend    ->  http://localhost:8000" -ForegroundColor White
Write-Host "   API docs   ->  http://localhost:8000/docs" -ForegroundColor White
Write-Host "   Review     ->  http://localhost:3000/review" -ForegroundColor White
Write-Host "   Global Net ->  http://localhost:3000/global-network" -ForegroundColor White
Write-Host "   SearXNG    ->  http://localhost:8080" -ForegroundColor White
Write-Host "   Memgraph   ->  bolt://localhost:7687" -ForegroundColor White
Write-Host "   PostgreSQL ->  localhost:5432 / ali_researcher" -ForegroundColor White
Write-Host ""
Write-Host "   To stop everything: .\stop.ps1" -ForegroundColor DarkGray
Write-Host ""

Start-Sleep -Seconds 2
Start-Process "http://localhost:3000"
