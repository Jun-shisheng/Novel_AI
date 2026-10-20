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
| `Ctrl+Alt+N` | 故事记忆：当前状态、章节记忆、重建本地检索索引 |
| `Ctrl+Alt+V` | 查看最近一次连贯性检查结果，可让 AI 修正并替换 |
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

### 故事记忆（章节级 + 当前状态）

生成或自动更新概要时，AI 会为每段正文额外提取：

- **本段概要**：这一段发生了什么
- **本段结束状态**：时间、地点、在场人物、关键物品、未解决线索、关系变化
- 全局概要中的主角、情节线、伏笔、世界观也会并入当前状态

这些内容存入本地 SQLite，并在润色、改写、续写时作为「事实约束」注入提示词。`Ctrl+Alt+N` 可以查看当前状态和全部章节记忆；「重建检索索引」只重建本地检索，不调用 AI。

### 本地检索（BM25，零依赖）

- 正文按约 1200 字分块，使用中文二元组 + 英文单词建立本地索引
- 优先使用 SQLite FTS5，不可用时退回纯 Python BM25
- 根据当前上下文里的角色名、地点、关键词召回最相关的过往段落，作为「相关前文」注入
- 自动排除当前正在处理的段落，避免把原文再喂回给模型
- 不需要向量库、嵌入模型或额外 Python 依赖

### 连贯性自检

润色、改写、续写完成后，会额外做一次低温检查（默认开启）：

- 对照当前状态、章节记忆和相关前文，只报告**明确矛盾**：人物状态、时间、地点、物品、关系、设定、情节因果
- 有问题时只在 Word 状态栏提示，不弹窗；按 `Ctrl+Alt+V` 查看详情
- 可以在查看窗口里让 AI 只修正矛盾并替换原文；原文已变化时会拒绝覆盖
- 每次检查会增加一次 API 调用，可在 `config/settings.json` 设置 `consistency_check: false` 关闭

### 能做到什么、做不到什么

这些机制能明显减少「人物瞬移、死人复生、伏笔丢失、长文后段忘设定」等问题，但**不能彻底消除幻觉**：

- 检索可能召回过期或无关段落；摘要会压缩丢失细节
- 状态是 AI 提取的，可能有错；大段修改前文后建议重新生成概要
- 自检也可能漏掉矛盾，或把合理创作误判为问题
- 冲突时以当前正文为准；重要设定建议在作品库里手动修正概要

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
| `memory_enabled` | `true` | 是否注入章节记忆/状态/本地检索结果 |
| `memory_retrieve_top_k` | `4` | 每次检索注入的相关段落数 |
| `memory_recent_chapters` | `3` | 注入的最近章节记忆条数 |
| `consistency_check` | `true` | 生成后是否做连贯性自检 |

## 数据与日志

| 路径 | 内容 |
|------|------|
| `.ai-writing/summaries.db` | 各文档概要、风格标签、自动更新位置、章节记忆、当前状态、检索索引 |
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
  prompt_builder.py   润色/改写/续写/大纲/角色卡/概要/连贯性提示词
  summary_manager.py  分块提取、增量合并、作品库 CRUD、连贯性检查
  memory_manager.py   章节记忆、当前状态、本地 BM25 检索（FTS5/纯 Python）
  text_chunker.py     按段落/句子分块（兼容 Word 的 \r 段落标记）
  database.py         SQLite（summaries / style_tags / doc_state / chapter_memory / story_state / memory_chunks）
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

共 37 个测试，不会访问真实 AI 服务，覆盖分块、JSON 解析、提示词、概要 CRUD、增量更新、角色卡、章节记忆、状态、本地检索、连贯性提示词和启动器纯函数。

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

## 设计参考

故事记忆层参考了以下开源项目的思路（仅借鉴设计，未复制代码）：

| 项目 | 借鉴点 |
|------|--------|
| [mem0ai/mem0](https://github.com/mem0ai/mem0) | 事实抽取、检索、可编辑记忆 |
| [letta-ai/letta](https://github.com/letta-ai/letta) | 核心状态 / 归档记忆 / 按需召回的分层结构 |
| [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | 实体关系 + 多级摘要 + 混合检索 |
| [microsoft/graphrag](https://github.com/microsoft/graphrag) | 人物关系图与结构化知识 |
| [SillyTavern/SillyTavern](https://github.com/SillyTavern/SillyTavern) | Character Card、World Info 按需注入 |
| [YILING0013/AI_NovelGenerator](https://github.com/YILING0013/AI_NovelGenerator) | 长篇上下文衔接与伏笔管理 |
| [PenglongHuang/chinese-novelist-skill](https://github.com/PenglongHuang/chinese-novelist-skill) | 自动校验与不合格重写 |
| [EthanYoQ/AI-Novel-Writer](https://github.com/EthanYoQ/AI-Novel-Writer) | 章节蓝图、角色/世界资料、本地全文检索 |
| [ExplosiveCoderflome/AI-Novel-Writing-Assistant](https://github.com/ExplosiveCoderflome/AI-Novel-Writing-Assistant) | 角色库、世界手册、章节状态、RAG |
| [THUDM/LongWriter](https://github.com/THUDM/LongWriter) | 长文先规划后写作 |

## License

MIT
