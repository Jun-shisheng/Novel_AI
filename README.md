# Novel AI — Word 写作助手

在 Microsoft Word 中直接调用 AI 润色、续写、改写、生成大纲和角色卡，并维护整部作品的概要。快捷键全局生效，无需切换窗口。

## 功能

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Shift+E` | 润色选中文本（扩写、优化表达，比例可在配置中调整） |
| `Ctrl+Shift+Enter` | 续写 / 停止（从光标处流式生成） |
| `Ctrl+Shift+G` | 分析全文生成概要（角色、情节线、伏笔、世界观、风格标签） |
| `Ctrl+Alt+R` | 按指定风格改写选中文本（简洁、文艺、悬疑、古风等） |
| `Ctrl+Alt+L` | 按目标字数续写（100–5000 字） |
| `Ctrl+Alt+O` | 生成章节大纲（长文自动分段汇总） |
| `Ctrl+Alt+P` | 角色卡：梗概、当前状态、目标、冲突、人物关系、后续发展 |
| `Ctrl+Alt+Z` | 撤销上一次 AI 修改（一键恢复原文） |
| `Ctrl+Alt+M` | 作品库：查看、编辑、导出、导入、删除各文档概要 |
| `Ctrl+Alt+U` | 开启/关闭自动概要更新 |
| `Ctrl+Alt+K` | 设置 DeepSeek API Key |
| `Ctrl+Alt+H` | 查看全部快捷键 |
| `Ctrl+Alt+Q` | 退出 WordAI |

### 角色卡

`Ctrl+Alt+P` 打开结构化的角色卡，包含：

- **主角**：姓名、梗概、当前状态、目标、冲突、后续发展
- **人物**：角色定位、人物梗概、关系、后续发展
- **角色关系**：角色 A ↔ 角色 B 的关系及变化（如「师徒 → 决裂 → 和解」）

概要中已有角色信息时直接展示；点击「AI 完善角色卡」会结合概要与正文补齐梗概、关系和后续发展，确认后点「保存到概要」写回。

### 概要系统

- AI 分块分析全文，提取主角、人物关系、伏笔、世界观、风格标签，存入本地 SQLite。
- 后续润色、续写、改写、大纲、角色卡都会自动注入概要，让 AI 理解整体剧情。
- 多个文档按文件路径自动区分，切换小说不会混淆概要。
- **自动更新**：保存文档后，如果新增内容超过阈值（默认 1200 字），且距上次更新超过最小间隔（默认 60 秒），会在后台增量更新概要，不必整本重算。
- **作品库**（`Ctrl+Alt+M`）：按文档查看/编辑概要 JSON，支持导出、导入和删除。导出文件包含覆盖位置，导入后可继续自动更新。

> 自动更新只处理文档末尾的新增内容；如果大幅修改了前文，建议按 `Ctrl+Shift+G` 重新生成。

### 每次结果都不一样

对同一段落重复润色、改写，或在同一起点重复续写时：

- 每次会随机切换创作侧重点（环境、心理、动作、对话、句式节奏等）
- 上一次生成的内容会作为「避免重复」参考传给模型
- 润色/改写温度提高到 0.9，降低输出趋同

因此撤销后重新执行，通常会得到另一种写法，而不是原样重放。

### 撤销

- `Ctrl+Alt+Z`：精确恢复最近一次 AI 修改（润色、改写、续写、插入大纲）。
- `Ctrl+Z`：AI 写入被包在 Word 自定义撤销记录中，一次即可整段撤销。
- 如果该段文字之后又被手动修改，一键撤销会拒绝执行并提示，避免覆盖新内容。

### 静默运行

启动后不弹窗打扰写作。API Key 未配置、快捷键被占用、AI 请求失败等情况只写入 Word 状态栏和日志；需要操作时再通过快捷键打开对应窗口。

## 安装

### 一键安装（推荐）

双击 `安装.bat`。脚本会自动：

1. 查找兼容的 Python（3.11 / 3.12）
2. 创建 `backend\venv`
3. 安装依赖
4. 创建 `config`、`logs` 目录

> 项目锁定 `pywin32==308` 等依赖，暂不支持 Python 3.14。若默认 `python` 是 3.14，请安装 Python 3.11/3.12；`安装.bat` 会自动优先使用 `py -3.12` / `py -3.11`。

### 手动安装

```bash
git clone https://github.com/Jun-shisheng/Novel_AI.git
cd Novel_AI

py -3.11 -m venv backend\venv
backend\venv\Scripts\pip install -r backend\requirements.txt
```

## 使用

- `启动.bat`：无控制台窗口启动（日常使用）。
- `start.bat`：带控制台启动（调试用，关闭窗口即退出）。

启动后切换到 Word 即可。首次使用先按 `Ctrl+Shift+G` 生成概要，之后润色、续写、角色卡就能关联完整上下文。

## API Key

项目不包含任何 API 密钥。

1. 获取 DeepSeek API Key：[platform.deepseek.com](https://platform.deepseek.com) → API Keys → 创建。
2. 在 Word 中按 `Ctrl+Alt+K` 填入。
3. 密钥加密存储在本地 `config/settings.json`，不会上传 GitHub。

也可以直接编辑 `config/settings.json` 的 `api_key` 字段（首次启动后会生成该文件）。

## 配置

配置文件：`config/settings.json`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `api_key` | `""` | DeepSeek API Key（加密存储） |
| `api_base_url` | `https://api.deepseek.com/v1` | OpenAI 兼容接口地址 |
| `model` | `deepseek-chat` | 模型名 |
| `continue_before_chars` | `3000` | 续写时读取的光标前文长度 |
| `continue_after_chars` | `500` | 续写时读取的光标后文长度 |
| `polish_before_chars` | `500` | 润色/改写时读取的前文长度 |
| `polish_after_chars` | `200` | 润色/改写时读取的后文长度 |
| `polish_expand_ratio` | `1.3` | 润色扩写比例（1.3 = 增加约 30%） |
| `auto_summary_update` | `true` | 是否自动增量更新概要 |
| `auto_summary_threshold` | `1200` | 触发自动更新的新增字数阈值 |
| `auto_summary_min_interval` | `60` | 两次自动更新的最小间隔（秒） |

## 数据与日志

| 路径 | 内容 |
|------|------|
| `.ai-writing/summaries.db` | 各文档概要、风格标签、自动更新位置 |
| `config/settings.json` | 配置与加密后的 API Key |
| `logs/word_ai.log` | 启动器日志 |
| `logs/backend.log` | 后台服务日志 |

以上路径均已加入 `.gitignore`。

## 架构

```
启动.bat / start.bat
      │
      └── word_ai.py（启动器，Python 主线程）
            ├── 启动 / 复用 backend/main.py（FastAPI :19800）
            ├── Word COM 自动化（所有 COM 调用固定在主线程）
            ├── 系统全局热键（RegisterHotKey + 独立消息窗口）
            ├── 网络请求在后台线程执行，结果回主线程队列
            └── tkinter 对话框（作品库、角色卡、大纲）

backend/
  main.py             FastAPI 入口与 API 路由
  deepseek_client.py  DeepSeek 封装（流式、超时、429/5xx 重试）
  prompt_builder.py   润色/改写/续写/大纲/角色卡/概要提示词
  summary_manager.py  分块提取、增量合并、作品库 CRUD
  text_chunker.py     按段落/句子分块（兼容 Word 的 \r 段落标记）
  database.py         SQLite（summaries / style_tags / doc_state）
  config.py           API Key 加密存储与配置
  utils.py            JSON 容错解析、换行规范化
  version.py          版本号（启动器据此判断是否复用后台）
  tests/              离线单元测试
```

## 测试

```bash
cd backend
venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试不会访问真实 AI 服务，覆盖分块、JSON 解析、提示词、概要 CRUD、增量更新、角色卡和启动器纯函数。

## 常见问题

**启动后没有反应**

查看 `logs/word_ai.log` 与 `logs/backend.log`。若提示旧版后台仍在运行，请在任务管理器中结束残留的 `python.exe` 后重试。

**快捷键无效**

可能被其他软件占用。`Ctrl+Alt+H` 的帮助窗口会列出注册失败的快捷键；日志中也有记录。

**自动更新没有触发**

需要先按 `Ctrl+Shift+G` 生成过一次概要（旧版概要缺少覆盖位置信息），并且文档已保存、新增字数达到阈值。

**润色/续写提示 API Key 无效**

按 `Ctrl+Alt+K` 重新设置；状态栏和日志会给出提示，不会弹窗。

## 依赖

- Python 3.11 / 3.12
- Microsoft Word（Windows）
- DeepSeek API Key（或兼容 OpenAI 格式的服务）

## License

MIT
