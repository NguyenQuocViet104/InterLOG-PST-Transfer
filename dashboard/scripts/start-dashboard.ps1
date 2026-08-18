$ErrorActionPreference = "Stop"

$dashboardRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $dashboardRoot "backend"
$frontendRoot = Join-Path $dashboardRoot "frontend"
$venvRoot = Join-Path $backendRoot ".venv"
$python = Join-Path $venvRoot "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv $venvRoot
    & $python -m pip install -r (Join-Path $backendRoot "requirements.txt")
}

$frontendBuild = Join-Path $frontendRoot "dist\index.html"
if (-not (Test-Path -LiteralPath $frontendBuild)) {
    Push-Location $frontendRoot
    try {
        npm install
        npm run build
    }
    finally { Pop-Location }
}

$env:INTERLOG_TEST_MODE = "1"
Start-Process "http://127.0.0.1:8080"
Push-Location $backendRoot
try {
    & $python -m uvicorn app:app --host 127.0.0.1 --port 8080
}
finally { Pop-Location }

