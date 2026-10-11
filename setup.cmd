@echo off
setlocal
cd /d "%~dp0"
where python.exe >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or later is required. Install from https://www.python.org/downloads/ with Python on PATH.
  pause
  exit /b 1
)
python.exe -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo Python 3.11 or later is required.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python.exe -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install --only-binary=:all: -r requirements.lock.txt
if errorlevel 1 exit /b 1
echo Setup complete. Open "Launch JOB-RADAR.cmd" to launch your dashboard.
echo AI environments need their own subscription login. Bun is required for LinkedIn.
