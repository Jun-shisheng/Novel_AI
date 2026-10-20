@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================
echo   Word AI 写作助手 — 安装
echo ===================================
echo.

echo [1/4] 检查 Python 版本...
set "PY=python"
py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
if /i "%PY%"=="python" (
    py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
)
%PY% -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo 错误：未找到兼容的 Python。
    echo 本项目需要 Python 3.11 / 3.12，请从 https://www.python.org 安装后重试。
    echo.
    pause
    exit /b 1
)
echo   完成

echo [2/4] 创建 Python 虚拟环境...
if exist "backend\venv\Scripts\python.exe" (
    "backend\venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo   现有虚拟环境版本不兼容，正在重新创建...
        rmdir /s /q "backend\venv"
    )
)
if not exist "backend\venv\Scripts\python.exe" (
    %PY% -m venv "backend\venv"
    if errorlevel 1 (
        echo.
        echo 错误：创建虚拟环境失败。
        pause
        exit /b 1
    )
)
echo   完成

echo [3/4] 安装依赖包（可能需要几分钟）...
"backend\venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
"backend\venv\Scripts\python.exe" -m pip install --quiet -r "backend\requirements.txt"
if errorlevel 1 (
    echo.
    echo 错误：依赖安装失败，请检查网络连接。
    pause
    exit /b 1
)
echo   完成

echo [4/4] 初始化目录...
if not exist "config" mkdir "config"
if not exist "logs" mkdir "logs"
echo   完成

echo.
echo ===================================
echo   安装完成！
echo.
echo   以后每次写作只需双击「启动.bat」
echo   首次启动会提示输入 DeepSeek API Key
echo   按 Ctrl+Alt+H 查看全部快捷键
echo ===================================
echo.
pause
