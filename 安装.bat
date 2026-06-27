@echo off
chcp 65001 >nul
echo ===================================
echo   Word AI 写作助手 — 安装
echo ===================================
echo.

cd /d "G:\WordAI"

echo [1/3] 创建 Python 虚拟环境...
if not exist "backend\venv" (
    python -m venv backend\venv
    echo   完成
) else (
    echo   已存在，跳过
)

echo [2/3] 安装依赖包（可能需要几分钟）...
backend\venv\Scripts\python.exe -m pip install --quiet --upgrade pip
backend\venv\Scripts\python.exe -m pip install --quiet -r backend\requirements.txt
backend\venv\Scripts\python.exe -m pip install --quiet pywin32
echo   完成

echo [3/3] 初始化配置文件...
if not exist "config" mkdir config
echo   完成

echo.
echo ===================================
echo   安装完成！
echo.
echo   以后每次写作只需双击「启动.bat」
echo   或在桌面创建「启动.bat」的快捷方式
echo ===================================
echo.
pause
