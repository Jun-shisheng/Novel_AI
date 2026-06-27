@echo off
chcp 65001 >nul
cd /d "G:\WordAI"

echo WordAI 启动中...
start "" "G:\WordAI\backend\venv\Scripts\pythonw.exe" "G:\WordAI\word_ai.py"
echo 已启动！切换到 Word 即可使用
echo   Ctrl+E    → 润色选中文本
echo   Ctrl+Enter → 续写启停
timeout /t 2 >nul
