@echo off
chcp 936 >nul
cd /d "G:\WordAI"

echo ===================================
echo   WordAI Setup
echo ===================================
echo.

echo [1/3] Creating Python virtual env...
if not exist "backend\venv" (
    python -m venv backend\venv
    if errorlevel 1 (
        echo ERROR: Python not found. Please install Python 3.11+ from python.org
        pause
        exit /b 1
    )
    echo   Done
) else (
    echo   Already exists, skip
)

echo [2/3] Installing dependencies...
backend\venv\Scripts\python.exe -m pip install --quiet --upgrade pip
backend\venv\Scripts\python.exe -m pip install --quiet -r backend\requirements.txt
echo   Done

echo [3/3] Creating config folder...
if not exist "config" mkdir config
echo   Done

echo.
echo ===================================
echo   Setup complete!
echo.
echo   To start: double-click start.bat
echo ===================================
pause
