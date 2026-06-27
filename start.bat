@echo off
chcp 936 >nul
cd /d "G:\WordAI"

echo Starting WordAI...
start "" "G:\WordAI\backend\venv\Scripts\pythonw.exe" "G:\WordAI\word_ai.py"
echo Started! Switch to Word to use:
echo   Ctrl+E      = Polish selected text
echo   Ctrl+Enter  = Continue / Stop
timeout /t 2 >nul
