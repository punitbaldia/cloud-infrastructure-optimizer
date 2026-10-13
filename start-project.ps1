$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$runtimeRoot = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies"
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$nodeExe = if ($nodeCommand) { $nodeCommand.Source } else { Join-Path $runtimeRoot "node\bin\node.exe" }
$pnpmScript = Join-Path $runtimeRoot "node\node_modules\pnpm\bin\pnpm.cjs"
if (!(Test-Path $nodeExe)) { throw "Install Node.js 24 first." }
if (!(Test-Path "backend\.venv\Scripts\python.exe")) {
    py -3.12 -m venv backend\.venv
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 environment creation failed." }
}
$pythonExe = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
& $pythonExe -m pip install -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Backend dependencies failed." }
& $pythonExe backend\setup_demo.py
$env:PATH = (Split-Path $nodeExe) + ";" + $env:PATH
$env:CI = "true"
if (Test-Path $pnpmScript) {
    & $nodeExe $pnpmScript --dir frontend install --frozen-lockfile
} else {
    corepack pnpm --dir frontend install --frozen-lockfile
}
if ($LASTEXITCODE -ne 0) { throw "Frontend dependencies failed." }
& $nodeExe frontend\node_modules\typescript\bin\tsc -b frontend
if ($LASTEXITCODE -ne 0) { throw "Frontend type check failed." }
Push-Location frontend
& $nodeExe node_modules\vite\bin\vite.js build --configLoader native
Pop-Location
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
Push-Location backend
& $pythonExe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }
Write-Host "Open http://127.0.0.1:8001. Username: admin. Password is ADMIN_PASSWORD in backend/.env."
& $pythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
Pop-Location
