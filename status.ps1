# ============================================================
#  ali_researcher — check status of all services
#  Usage: .\status.ps1
# ============================================================

function Write-Ok($label, $detail)   { Write-Host "  [UP]  $label" -ForegroundColor Green -NoNewline; Write-Host "  $detail" -ForegroundColor DarkGray }
function Write-Down($label, $detail) { Write-Host "  [--]  $label" -ForegroundColor DarkGray -NoNewline; Write-Host "  $detail" -ForegroundColor DarkGray }
function Write-Err($label, $detail)  { Write-Host "  [XX]  $label" -ForegroundColor Red -NoNewline; Write-Host "  $detail" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "  ali_researcher — service status" -ForegroundColor Cyan
Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray

# Backend
try {
    $h = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -TimeoutSec 3 -UseBasicParsing
    $body = $h.Content | ConvertFrom-Json
    $mg = if ($body.memgraph) { "Memgraph connected" } else { "Memgraph offline" }
    Write-Ok "Backend  " "http://localhost:8000  [$mg]"
} catch {
    Write-Err "Backend  " "http://localhost:8000  (not responding)"
}

# Frontend
try {
    $null = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 3 -UseBasicParsing
    Write-Ok "Frontend " "http://localhost:3000"
} catch {
    Write-Down "Frontend " "http://localhost:3000  (not responding)"
}

# SearXNG
try {
    $s = Invoke-WebRequest -Uri "http://localhost:8080/search?q=test&format=json" -TimeoutSec 4 -UseBasicParsing
    $data = $s.Content | ConvertFrom-Json
    Write-Ok "SearXNG  " "http://localhost:8080  ($($data.results.Count) results on test query)"
} catch {
    Write-Down "SearXNG  " "http://localhost:8080  (not responding — using public fallback)"
}

# Memgraph
$mgRunning = docker ps --filter "name=memgraph" --filter "status=running" -q 2>$null
if ($mgRunning) {
    Write-Ok "Memgraph " "bolt://localhost:7687"
} else {
    Write-Down "Memgraph " "bolt://localhost:7687  (container not running)"
}

# LaTeX Compiler
try {
    $null = Invoke-WebRequest -Uri "http://localhost:8001/health" -TimeoutSec 3 -UseBasicParsing
    Write-Ok "LaTeX    " "http://localhost:8001  (compilador activo)"
} catch {
    Write-Down "LaTeX    " "http://localhost:8001  (not responding — run: docker compose up -d latex-compiler)"
}

Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""
