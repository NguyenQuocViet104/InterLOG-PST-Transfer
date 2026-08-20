$ErrorActionPreference = "Stop"

$dashboardRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $dashboardRoot "backend"
$frontendRoot = Join-Path $dashboardRoot "frontend"
$venvRoot = Join-Path $backendRoot ".venv"
$python = Join-Path $venvRoot "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    $workspacePython = [IO.Path]::GetFullPath((Join-Path $dashboardRoot "..\..\..\.venv\Scripts\python.exe"))

    if ($pythonCommand) {
        & $pythonCommand.Source -m venv $venvRoot
    }
    elseif ($pyLauncher) {
        & $pyLauncher.Source -3 -m venv $venvRoot
    }
    elseif (Test-Path -LiteralPath $workspacePython) {
        # Development workspace fallback. A portable deployment should install Python 3.
        $python = $workspacePython
    }
    else {
        throw "Khong tim thay Python 3. Hay cai Python hoac Python Launcher (py.exe), sau do chay lai."
    }

    if ($python -eq (Join-Path $venvRoot "Scripts\python.exe")) {
        & $python -m pip install -r (Join-Path $backendRoot "requirements.txt")
    }
}

& $python -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Python da tim thay nhung thieu FastAPI/Uvicorn. Hay cai dashboard\backend\requirements.txt."
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
