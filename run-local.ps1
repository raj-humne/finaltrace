# SentinelTrace Local Runner
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Starting SentinelTrace Local Environment..." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Start Backend API in a new PowerShell window
Write-Host "[1/2] Launching Backend API on http://localhost:8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$scriptDir'; python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload"

# Start Frontend UI in a new PowerShell window
Write-Host "[2/2] Launching Frontend UI on http://localhost:5173..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$scriptDir\web'; npx vite --host 127.0.0.1 --port 5173"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "SentinelTrace running in local terminal windows!" -ForegroundColor Green
Write-Host " - Frontend: http://localhost:5173"
Write-Host " - API Docs: http://localhost:8000/docs"
Write-Host " - Demo Credentials:"
Write-Host "     Username: riya"
Write-Host "     Password: 123456"
Write-Host "==========================================================" -ForegroundColor Cyan
