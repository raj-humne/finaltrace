@echo off
echo ==========================================================
echo Starting SentinelTrace Local Environment...
echo ==========================================================

cd /d "%~dp0"

echo [1/2] Launching Backend API on http://localhost:8000...
start "SentinelTrace API (Port 8000)" cmd /k "python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload"

echo [2/2] Launching Frontend UI on http://localhost:5173...
start "SentinelTrace Web (Port 5173)" cmd /k "cd web && npx vite --host 127.0.0.1 --port 5173"

echo.
echo ==========================================================
echo SentinelTrace is now launching in local terminal windows!
echo - Frontend: http://localhost:5173
echo - API Docs: http://localhost:8000/docs
echo - Demo Credentials:
echo     Username: riya (or priya.s)
echo     Password: 123456 (or analyst-demo-pw)
echo ==========================================================
