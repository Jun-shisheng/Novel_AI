@echo off
chcp 936 >nul
cd /d "%~dp0"

if not exist "backend\venv\Scripts\python.exe" (
    echo ERROR: Python venv not found. Run install.bat first.
    pause
    exit /b 1
)

echo Starting WordAI...
echo.
echo   Ctrl+Shift+E        = Polish selected text
echo   Ctrl+Shift+Enter    = Continue / Stop
echo   Ctrl+Shift+G  = Generate summary from full document
echo.
echo Keep this window open. Switch to Word now.
echo ===================================

backend\venv\Scripts\python.exe word_ai.py

pause
