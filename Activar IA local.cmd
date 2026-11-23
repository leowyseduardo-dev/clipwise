@echo off
setlocal
set "cfpython=%Clipwise_BUILD_PYTHON%"
if not defined cfpython set "cfpython=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%cfpython%" goto missing
"%cfpython%" "%~dp0tools\activar_ollama.py" --solo-ia
set "cfresult=%errorlevel%"
pause
exit /b %cfresult%
:missing
echo Define Clipwise_BUILD_PYTHON con el Python de compilacion de Clipwise.
pause
exit /b 1
