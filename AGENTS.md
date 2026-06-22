# FARS — Fully Automated Research System

## 项目定位

FARS 是面向量化交易与金融科技领域的**全自动学术论文生成系统**。从种子论文出发，实现文献分析→假设生成→实验设计→回测验证→论文撰写→评分迭代的闭环。

## 技术栈

- **语言**: Python 3.12+
- **Web 框架**: Flask（`server.py`，端口 8080）
- **LLM 后端**: MiniMax-M2.7-highspeed（主用）/ DeepSeek（备用）/ OpenAI / Gemini（可选）
- **数据库**: MongoDB（可选语义检索）
- **回测**: backtrader, backtesting
- **AI 检测**: Fast-DetectGPT（ICLR 2024，vendor/fast-detect-gpt/）
- **前端**: 纯 HTML/CSS/JS（v1 单文件 + v2 组件化），无框架依赖
- **量化数据**: yfinance, akshare

## 核心架构

```
server.py (Flask API, ~5984行, 系统核心入口)
    │
    ├── src/core/             # 核心引擎层
    │   ├── research_engine.py    # 断点续分析引擎（Checkpoint状态机+优雅降级）
    │   ├── research_runner.py    # 研究流水线（后台推进：文献→假设→实验→论文）
    │   ├── research_archive.py   # 研究存档管理（分配ID、创建workspace）
    │   ├── research_graphs.py    # 作者/引用关系网络
    │   ├── seed_library.py       # 种子论文库管理
    │   ├── paper_extractor.py    # 论文正文提取（PDF→文本）
    │   ├── pdf_compiler.py       # LaTeX→PDF编译
    │   ├── config.py             # 配置管理（研究方向、LLM Provider、Workspace）
    │   ├── database.py           # 数据库操作
    │   ├── data_registry.py      # 数据注册表
    │   ├── mongo_index.py        # MongoDB语义索引
    │   └── research_reset.py     # 研究重置
    │
    ├── src/agents/           # Agent层（4大Agent合并在agents.py）
    │   └── agents.py             # Ideation/Planning/Experiment/Writing Agent
    │
    ├── src/tools/            # 工具层
    │   ├── fetchers.py           # PaperFetcher/MarketDataFetcher/LLMCaller/CodeExecutor
    │   ├── backtest.py           # 回测引擎（BacktestEngine + MomentumStrategy）
    │   ├── quality_pipeline.py   # 论文质量流水线（AI检测+评审+雷达图）
    │   ├── literature_review_engine.py  # STORM风格文献综述引擎
    │   └── paperreview_submitter.py     # 论文投稿提交
    │
    ├── src/services/         # 服务层
    │   ├── ai_detector.py        # Fast-DetectGPT AI痕迹检测封装
    │   └── paper_reviewer.py     # 论文评审服务（Claude/DeepSeek/本地）
    │
    ├── src/prompts/          # Prompt模板
    │   └── templates.py          # 7+个模板（idea/analysis/code/writing/review等）
    │
    ├── src/main.py           # CLI主入口（FARS类，支持--direction/--topic）
    ├── src/fars_research.py  # 研究数据模型（Hypothesis/Experiment/Paper/ResearchBranch）
    └── src/workflow.py       # 完整工作流（编译→AI检测→投稿）
```

## 前端

两套前端均由 `server.py` 托管，共享所有后端 API：
- **v1**: `docs/fars_dashboard.html`（单文件，含质量流水线按钮）→ 访问 `/docs/fars_dashboard.html`
- **v2**: `docs/v2/`（组件化：pipeline-view/research-sidebar/topology-graph/quality-panel 等）→ 访问 `/v2/`

## 关键机制

### 1. Checkpoint 断点续分析
- 每个 research_id 有独立 workspace: `data/research/RS-{id}_checkpoint/`
- `checkpoint.json` 记录每步状态（pending/in_progress/completed/failed）
- MD5 防重：写入前校验，防止状态冲突
- 每步完成后立即持久化

### 2. 优雅降级
- 写作失败时自动切换至已有分析结果续写
- 并发生成 Bug 报告（不阻塞主流程）

### 3. STORM 风格文献综述
- 4 个学术视角（技术/应用/评估/局限）× 并行生成
- Perspective Generation → Question Asking → Evidence Collection → Outline
- `LiteratureReviewEngine` (src/tools/literature_review_engine.py)

### 4. 论文质量流水线
- Step 4: AI痕迹检测（Fast-DetectGPT，本地模型 gpt-neo-2.7B）
- Step 5: 论文评审（Claude/DeepSeek API + 本地 GPT-2 fallback，5维评分）
- Step 6: 综合报告（7维度雷达图）

### 5. LLM 调用
- `LLMCaller`（src/tools/fetchers.py）统一封装所有 LLM 调用
- MiniMax-M2.7-highspeed 是推理模型，使用 `<think>` 标签，需正则清理
- 超时 180s + 重试 2 次
- MiniMax 使用 `max_tokens` 参数（不是 `max_completion_tokens`）
- API Key 通过 `config.local.json` 或环境变量读取，**绝不提交到 git**

## 配置文件

| 文件 | 用途 | Git 跟踪 |
|------|------|----------|
| `config.json` | 默认配置模板（API key 留空） | ❌ (.gitignore) |
| `config.local.json` | 本地覆盖配置（含真实 API key） | ❌ (.gitignore) |
| `config.py` | Python 配置管理（`load_effective_config()` 合并两个 JSON） | ✅ |

**配置加载优先级**: `config.local.json` > `config.json` > 环境变量

## 数据目录

```
data/
├── seed_papers/         # 种子论文库（PDF + summary.json）
├── research/            # 研究结果（每个 research 独立 workspace）
├── research_state.json  # 研究状态
├── research_logs.json   # 研究日志
├── papers_state.json    # 论文状态
├── grading_history.json # 评分历史
└── branches.json        # 分支管理
```

## 启动方式

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key（二选一）
# 方式A: 编辑 config.local.json
# 方式B: 环境变量
export MINIMAX_API_KEY="gw-xxxxx"

# 3. 启动服务器
python server.py
# → http://localhost:8080 (v1) 或 http://localhost:8080/v2/ (v2)

# 4. CLI 模式
python src/main.py --direction quant_finance --topic "LLM in trading"
```

## API 端点概览

| 分组 | 关键端点 |
|------|----------|
| 研究流程 | `POST /api/research/full/<id>` (端到端), `POST /api/research/resume/<id>` (断点恢复) |
| 论文分析 | `POST /api/research/analyze-all`, `GET /api/research/perspective/<id>`, `GET /api/research/outline/<id>` |
| 文献综述 | `POST /api/research/literature-review`, `POST /api/research/generate-full` |
| 论文管理 | `GET /api/papers`, `POST /api/papers/<id>/score`, `POST /api/papers/<id>/improve` |
| 质量流水线 | `POST /api/quality/pipeline`, `POST /api/quality/detect-ai`, `POST /api/quality/review-paper` |
| 种子论文 | `GET /api/seed-papers`, `POST /api/seed-papers/fetch`, `POST /api/seed-papers/extract-all` |
| 分支管理 | `GET /api/branches`, `POST /api/branches`, `POST /api/branches/switch/<id>` |
| 研究运行 | `POST /api/generate/start`, `POST /api/generate/pause`, `POST /api/generate/resume` |

## 重要约定

1. **server.py 是系统核心**：5984 行，包含所有 API 端点 + LLM 调用 + 研究流程编排。修改时注意影响面。
2. **agents.py 合并了 4 个 Agent**：不是分开的 4 个文件，而是合并在 `src/agents/agents.py` 一个文件中。
3. **不要修改 config.local.json**：含真实 API key，已在 .gitignore 中。
4. **不要删除 data/ 目录内容**：包含所有研究数据和 checkpoint。
5. **LLM 调用必须设 timeout**：统一 180s，重试 2 次，防止卡死。
6. **MiniMax `<think>` 标签**：所有 LLM 返回内容必须用正则清理 `<think>...</think>` 标签。
