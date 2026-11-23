@echo off
setlocal
set "CLIPFORGE_CLOUD_DIR=%LOCALAPPDATA%\Temp\opencode\cloudtest"
set "CLIPFORGE_PUBLIC_ORIGIN=http://127.0.0.1:8000"
set "ADMIN_EMAILS=Leowysgarcia@gmail.com"
cd /d "%~dp0"
start "" "C:\Users\leoca\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn engine.cloud.main:app --host 127.0.0.1 --port 8000
timeout /t 3 >nul
start "" "http://127.0.0.1:8000"
