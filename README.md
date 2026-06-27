# Novel AI — Word 写作助手

在 Microsoft Word 中直接调用 AI 润色、续写、分析小说全文。快捷键全局生效，无需切换窗口。

## 功能

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Shift+E` | 润色选中文本（扩写、优化表达） |
| `Ctrl+Shift+Enter` | 续写（从光标处流式生成，按段落输出） |
| `Ctrl+Shift+G` | 生成全文概要（提取角色、情节线、风格标签） |

**概要系统**：AI 分块分析全文，提取主角、人物关系、伏笔、世界观、风格标签，存入本地 SQLite。后续润色和续写自动注入概要，使 AI 理解整体剧情而非仅依赖上下文窗口。

多个文档按文件路径自动区分，切换小说不会混淆概要。

## 安装

```bash
# 1. 克隆项目
git clone https://github.com/Jun-shisheng/Novel_AI.git
cd Novel_AI

# 2. 创建虚拟环境
python -m venv backend\venv

# 3. 安装依赖
backend\venv\Scripts\pip install -r backend\requirements.txt
backend\venv\Scripts\pip install pywin32
```

## 使用

双击 `start.bat`，打开 Word，开始写作。

**首次使用**先按 `Ctrl+Shift+G` 让 AI 分析全文生成概要，之后润色和续写就会关联完整上下文。

## 配置

首次运行在 Word 状态栏提示输入 API Key，加密存储在 `config/settings.json`。也可直接编辑该文件（首次启动后自动生成）。

## 架构

```
start.bat → word_ai.py (启动器)
              ├── 启动 backend/main.py (FastAPI :19800)
              ├── Word COM 自动化（读写文档）
              ├── 系统全局热键（RegisterHotKey + 消息窗口）
              └── tkinter 主线程调度

backend/
  main.py            FastAPI 入口
  deepseek_client.py DeepSeek API 封装（支持流式）
  prompt_builder.py  润色/续写/概要提示词构建
  summary_manager.py 全文分块提取 + 增量合并
  database.py        SQLite 存储（按文档路径隔离）
  config.py          API Key 加密存储
```

## 依赖

- Python 3.11+
- Microsoft Word (Windows)
- DeepSeek API Key

## License

MIT
