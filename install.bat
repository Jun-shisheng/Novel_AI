@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================
echo   WordAI Setup
echo ===================================
echo.

echo [1/4] Checking Python version...
set "PY=python"
py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
if /i "%PY%"=="python" (
    py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
)
%PY% -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Compatible Python not found.
    echo This project requires Python 3.11 / 3.12. Install it from https://www.python.org
    pause
    exit /b 1
)
echo   Done

echo [2/4] Creating Python virtual env...
if exist "backend\venv\Scripts\python.exe" (
    "backend\venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo   Existing venv is incompatible, recreating...
        rmdir /s /q "backend\venv"
    )
)
if not exist "backend\venv\Scripts\python.exe" (
    %PY% -m venv "backend\venv"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)
echo   Done

echo [3/4] Installing dependencies...
"backend\venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
"backend\venv\Scripts\python.exe" -m pip install --quiet -r "backend\requirements.txt"
if errorlevel 1 (
    echo ERROR: Dependency installation failed. Check your network connection.
    pause
    exit /b 1
)
echo   Done

echo [4/4] Creating folders...
if not exist "config" mkdir "config"
if not exist "logs" mkdir "logs"
echo   Done

echo.
echo ===================================
echo   Setup complete!
echo.
echo   To start: double-click start.bat (console) or 启动.bat (windowless).
echo   On first launch you will be asked for a DeepSeek API key.
echo   Press Ctrl+Alt+H in Word for all hotkeys.
echo ===================================
pause
