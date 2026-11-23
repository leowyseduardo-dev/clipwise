@echo off
setlocal
set "cfOllama=%LOCALAPPDATA%\Clipwise\ollama-portable\ollama.exe"
if exist "%cfOllama%" powershell.exe -NoProfile -Command "try { $null = Invoke-RestMethod -Uri http://127.0.0.1:11434/api/version -TimeoutSec 2 -ErrorAction Stop } catch { Start-Process -FilePath $env:cfOllama -ArgumentList serve -WindowStyle Hidden }"
set "cfApp=%~dp0desktop\dist\Studio-1.3.0\Clipwise\Clipwise.exe"
if not exist "%cfApp%" set "cfApp=%~dp0desktop\dist\Clipwise\Clipwise.exe"
start "" "%cfApp%"
