@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "backend\venv\Scripts\python.exe" (
    echo ERROR: Python venv not found. Run install.bat first.
    pause
    exit /b 1
)

echo Starting WordAI...
echo.
echo   Ctrl+Shift+E       = Polish selected text
echo   Ctrl+Shift+Enter   = Continue / Stop
echo   Ctrl+Shift+G       = Generate summary from full document
echo   Ctrl+Alt+R         = Rewrite in a chosen style
echo   Ctrl+Alt+L         = Continue with target length
echo   Ctrl+Alt+O         = Generate chapter outline
echo   Ctrl+Alt+P         = Character cards
echo   Ctrl+Alt+Z         = Undo last AI edit
echo   Ctrl+Alt+M         = Summary library
echo   Ctrl+Alt+U         = Toggle auto summary update
echo   Ctrl+Alt+K         = Set API key
echo   Ctrl+Alt+H         = Help
echo   Ctrl+Alt+Q         = Quit
echo.
echo Keep this console open, or use 启动.bat for a windowless launch.
echo ===================================

"backend\venv\Scripts\python.exe" word_ai.py

pause
