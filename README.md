# Word AI 写作助手

Windows Word 2019 桌面版 AI 写作插件，集成 DeepSeek API 实现润色扩写和流式续写。

## 使用

```
双击「启动.bat」→ 切换到 Word → 开始写
```

| 快捷键 | 功能 |
|--------|------|
| **Ctrl+E** | 选中段落后润色扩写，直接替换原文 |
| **Ctrl+Enter** | 光标处开始续写 / 再次按停止 |

## 一键安装

1. 确保已安装 **Python 3.11+**（python.org 下载）
2. 双击 `安装.bat`，等待完成
3. 把 `启动.bat` 创建桌面快捷方式，方便每天使用

## 配置

API Key 已预置。如需修改，编辑 `config/settings.json`（首次运行后生成）。

## 目录结构

```
G:\WordAI\
├── word_ai.py          # 主启动器（快捷键 + Word 集成）
├── 安装.bat            # 一次性安装脚本
├── 启动.bat            # 日常使用入口
├── backend/            # Python 后台服务
├── config/             # 配置文件（G 盘）
└── .ai-writing/        # 概要数据库（G 盘）
```
