@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "backend\venv\Scripts\pythonw.exe" (
    echo 未找到 Python 虚拟环境，请先双击运行「安装.bat」。
    pause
    exit /b 1
)
if not exist "word_ai.py" (
    echo 未找到 word_ai.py，请确认文件完整。
    pause
    exit /b 1
)

echo WordAI 启动中...
start "" "%~dp0backend\venv\Scripts\pythonw.exe" "%~dp0word_ai.py"

echo.
echo 已启动！切换到 Word 即可使用：
echo   Ctrl+Shift+E      润色选中文本
echo   Ctrl+Shift+Enter  续写 / 停止
echo   Ctrl+Shift+G      生成全文概要
echo   Ctrl+Alt+N        故事记忆（状态/章节/检索索引）
echo   Ctrl+Alt+V        查看连贯性检查结果
echo   Ctrl+Alt+H        查看全部快捷键
echo   Ctrl+Alt+Q        退出 WordAI
echo.
echo 启动失败时会弹出提示，详细日志见 logs\word_ai.log
timeout /t 3 >nul
