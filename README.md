# Word AI 写作助手

Windows Word 2019 桌面版 AI 写作插件，集成 DeepSeek API 实现润色扩写、流式续写和结构化概要生成。

## 功能

- **润色/扩写** (Ctrl+E): 选中文本，一键扩写润色，直接替换原文
- **流式续写** (Ctrl+Enter): 从光标处续写，逐句实时写入，再按停止
- **概要系统**: 自动提取人物、情节、伏笔、风格标签，注入每次请求
- **增量更新**: 新章节增量更新概要，无需重读全文

## 系统要求

- Windows 10/11
- Microsoft Word 2019 桌面版
- .NET Framework 4.8
- Python 3.11+

## 安装

### 1. Python 后端

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. VSTO 加载项

1. 用 Visual Studio 2022 打开 `WordAddIn\WordAddIn.csproj`
2. 构建 → 生成 WordAddIn
3. 运行项目启动 Word 调试，或发布为 ClickOnce 安装包

### 3. 配置

1. 启动 Word，点击 "AI 写作" → "设置"
2. 填入 DeepSeek API Key（从 https://platform.deepseek.com 获取）
3. 调整上下文长度和润色参数

## 开发

```bash
# 启动后端
cd backend && venv\Scripts\python main.py

# 构建 VSTO
msbuild WordAddIn\WordAddIn.csproj /t:Build
```

## 项目结构

```
WordAI/
├── backend/          # Python FastAPI 后台
│   ├── main.py       # API 入口
│   ├── config.py     # 配置加密
│   ├── deepseek_client.py  # DeepSeek 客户端
│   ├── prompt_builder.py   # Prompt 构建
│   ├── summary_manager.py  # 概要管理
│   └── database.py   # SQLite
├── WordAddIn/        # VSTO C# 加载项
│   ├── ThisAddIn.cs  # 入口与生命周期
│   ├── HotkeyManager.cs    # 快捷键
│   ├── ContextExtractor.cs # 文本提取
│   ├── TextWriter.cs       # 文本写入
│   ├── BackendClient.cs    # HTTP 客户端
│   └── SettingsForm.cs     # 设置窗口
└── docs/             # 设计文档
```

Commit: `docs: add README with installation and usage guide`
