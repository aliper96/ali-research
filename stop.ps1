# ============================================================
#  ali_researcher — stop everything
#  Usage: .\stop.ps1
# ============================================================

function Write-Header($msg) { Write-Host "`n  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)     { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Step($msg)   { Write-Host "  --> $msg" -ForegroundColor DarkCyan }

Clear-Host
Write-Host ""
Write-Host "  Stopping ali_researcher services..." -ForegroundColor Yellow
Write-Host ""

# Kill uvicorn
Write-Header "Backend"
$uvicorn = Get-Process -Name "python" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*uvicorn*" }
if ($uvicorn) {
    $uvicorn | Stop-Process -Force
    Write-Ok "uvicorn stopped"
} else {
    Write-Step "uvicorn was not running"
}

# Kill node (Next.js)
Write-Header "Frontend"
$node = Get-Process -Name "node" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*next*" }
if ($node) {
    $node | Stop-Process -Force
    Write-Ok "Next.js stopped"
} else {
    Write-Step "Next.js was not running"
}

# Stop SearXNG
Write-Header "SearXNG"
$searxRunning = docker ps --filter "name=searxng-core" --filter "status=running" -q 2>$null
if ($searxRunning) {
    Push-Location "C:\searxng"
    docker compose stop | Out-Null
    Pop-Location
    Write-Ok "SearXNG stopped"
} else {
    Write-Step "SearXNG was not running"
}

# Stop LaTeX Compiler
Write-Header "LaTeX Compiler"
$latexRunning = docker ps --filter "name=latex-compiler" --filter "status=running" -q 2>$null
if ($latexRunning) {
    Push-Location $PSScriptRoot
    docker compose stop latex-compiler | Out-Null
    Pop-Location
    Write-Ok "LaTeX compiler stopped"
} else {
    Write-Step "LaTeX compiler was not running"
}

# Stop Memgraph
Write-Header "Memgraph"
$mgRunning = docker ps --filter "name=memgraph" --filter "status=running" -q 2>$null
if ($mgRunning) {
    docker stop memgraph | Out-Null
    Write-Ok "Memgraph stopped"
} else {
    Write-Step "Memgraph was not running"
}

Write-Host ""
Write-Host "  All services stopped." -ForegroundColor Green
Write-Host ""
