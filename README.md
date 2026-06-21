# FARS — Fully Automated Research System

> **FARS (Fully Automated Research System)** 是一款基于 LLM 的全自动学术论文生成系统，专注于量化交易与金融科技领域。从种子论文出发，自主完成文献分析、假设生成、实验设计、论文撰写全流程。

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 目录

- [系统概述](#系统概述)
- [核心架构](#核心架构)
- [完整流程逻辑](#完整流程逻辑)
- [容错与断点机制](#容错与断点机制)
- [论文质量流水线](#论文质量流水线)
- [参考系统](#参考系统)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [API 参考](#api-参考)
- [设计文档](#设计文档)
- [评分标准](#评分标准)

---

## 系统概述

FARS 从一篇高引用的种子论文（Seed Paper）出发，构建多代理协作的研究流水线，循环产出高质量学术论文：

```
种子论文 → 文献分析 → 假设生成 → 实验设计 → 回测验证 → 论文撰写 → 评分迭代
     ↑                                                                      ↓
     └──────────────────────── 评分反馈 → 迭代改进 ─────────────────────────┘
```

### 核心能力

| 能力 | 说明 |
|------|------|
| **多代理协作** | Ideation / Planning / Experiment / Writing 四大 Agent 分工明确 |
| **断点续分析** | Checkpoint 状态机，每步完成后持久化，支持从断点恢复 |
| **优雅降级** | 分析卡顿时自动降级，用已有结果继续写作，同时生成 Bug 报告 |
| **文献综述引擎** | STORM 风格多视角调研 + GPT Researcher 风格 Review-Revision 循环 |
| **多论文比对** | 跨论文作者网络、主题聚类、深度对比分析 |
| **分支迭代** | 支持多分支并行研究，独立演进 |
| **全文输出** | 支持完整 LaTeX / PDF 生成（非简略摘要） |

---

## 核心架构

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              FARS 系统架构                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐             │
│  │   Dashboard v1 (旧版)       │  │   Dashboard v2 (新版)        │             │
│  │   docs/fars_dashboard.html  │◄─┼─►│   docs/v2/index.html       │             │
│  └──────────────┬───────────────┘  │  └──────────────┬───────────────┘             │
│                 │                  │                  │                              │
│  ┌──────────────▼──────────────────▼──────────────────▼──────────────┐             │
│  │                    Flask API Server (server.py)                  │             │
│  │                    http://localhost:8080                          │             │
│  └───────────────────────────┬──────────────────────────────────────┘             │
│                                              │                                │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                         Core Modules (src/core/)                        │  │
│  ├──────────────┬──────────────┬──────────────┬───────────────────────────┤  │
│  │research_engine│research_archive│data_registry│    seed_library          │  │
│  │  断点引擎      │  研究存档     │   数据注册表   │      种子论文库           │  │
│  ├──────────────┴──────────────┴──────────────┴───────────────────────────┤  │
│  │                     Agent Modules (src/agents/)                         │  │
│  ├──────────────┬──────────────┬──────────────┬───────────────────────────┤  │
│  │  Ideation     │  Planning    │  Experiment  │  Writing                  │  │
│  │  Agent        │  Agent       │  Agent        │  Agent                    │  │
│  ├──────────────┴──────────────┴──────────────┴───────────────────────────┤  │
│  │                     Prompt Templates (src/prompts/)                      │  │
│  │  Perspective / Question / Literature Review / Introduction / Review /  │  │
│  │  Revision / Full Paper                                                  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                              │                                │
│  ┌───────────────────────────────────────────▼────────────────────────────┐  │
│  │                        MiniMax / DeepSeek LLM API                      │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
Seed Papers (PDF/JSON)
    │
    ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────────┐
│  seed_library   │────▶│  paper_extractor │────▶│  MongoDB Index (可选)   │
│  论文库管理       │     │  论文正文提取      │     │  语义检索                │
└─────────────────┘     └──────────────────┘     └─────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │    research_engine.py    │
                    │  ┌────────────────────┐  │
                    │  │ ResearchCheckpoint │  │  ← 每步写入 checkpoint.json
                    │  │  State Machine     │  │
                    │  └────────────────────┘  │
                    │                          │
                    │  Phase 1: Paper Analysis │  ← analyze_all_papers()
                    │  Phase 2: Perspective    │  ← run_perspective_analysis()
                    │  Phase 3: Outline       │  ← generate_outline()
                    │  Phase 4: Write         │  ← writing_with_degradation()
                    │  Phase 5: Full Research │  ← run_full_research()
                    └──────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │   research_archive.py    │
                    │   研究结果存档           │
                    └──────────────────────────┘
```

---

## 完整流程逻辑

### Phase 1: 论文分析 (Paper Analysis)

对种子论文库中每篇论文执行：

```python
def analyze_paper(paper_id, checkpoint, ...) -> PaperAnalysis:
    # 1. 提取论文正文
    text = get_paper_text(paper_id)
    # 2. 摘要 + 关键词提取
    summary = call_llm(SUMMARIZE_TEMPLATE, text)
    # 3. 方法论分析
    methodology = call_llm(METHODOLOGY_TEMPLATE, text)
    # 4. 实验结果分析
    experiments = call_llm(EXPERIMENTS_TEMPLATE, text)
    # 5. 保存 checkpoint（每步完成后立即持久化）
    save_checkpoint(checkpoint, step="paper_analysis", status="completed")
    return PaperAnalysis(...)
```

**断点保护**：每个子步骤完成后立即写入 `checkpoint.json`，避免中途失败导致重算。

### Phase 2: 视角分析 (Perspective Analysis) — STORM 风格

从四个学术视角对研究主题进行深度调研：

```
Perspective 1: 技术实现视角
  └─ 核心问题：该领域使用了哪些技术方案？各自优劣？

Perspective 2: 应用场景视角
  └─ 核心问题：在哪些实际场景中应用？效果如何？

Perspective 3: 评估方法视角
  └─ 核心问题：如何评估该方法？指标是什么？

Perspective 4: 局限与未来视角
  └─ 核心问题：当前方法有什么局限？未来方向？
```

每视角调用 `fill_perspective_prompt()` 生成结构化分析，并发执行以节省时间。

### Phase 3: 论文大纲生成 (Outline Generation)

基于所有分析结果，调用 `generate_outline()` 生成完整论文大纲：

```python
def generate_outline(research_id, checkpoint, ...) -> Outline:
    # 1. 汇总所有论文分析
    analyses = load_paper_analyses(research_id)
    # 2. 汇总视角分析
    perspectives = load_perspective_analysis(research_id)
    # 3. LLM 生成大纲
    outline = call_llm(OUTLINE_TEMPLATE, analyses, perspectives)
    # 4. 保存大纲到 workspace
    save_outline(research_id, outline)
    return outline
```

### Phase 4: 论文写作 (Writing) — Graceful Degradation

```python
def writing_with_degradation(research_id, checkpoint, ...) -> Paper:
    try:
        # 正常流程：逐节生成完整论文
        sections = []
        for section in outline.sections:
            content = call_llm(WRITE_SECTION_TEMPLATE, section)
            sections.append(content)
            # 每节完成后立即 checkpoint
            save_checkpoint(checkpoint, step=f"section_{section.name}", status="completed")
        return assemble_paper(sections)

    except (TokenLimitError, TimeoutError) as e:
        # 降级流程：用已有分析结果继续写作
        logger.warning(f"Graceful degradation triggered: {e}")
        bug_report = generate_bug_report(e, checkpoint)

        # 用已完成的分析继续写作
        partial_content = call_llm(
            WRITE_FROM_ANALYSIS_TEMPLATE,
            analyses=get_completed_analyses(checkpoint),
            error=str(e)
        )

        # 并发生成 Bug 报告（不阻塞主流程）
        asyncio.create_task(
            save_bug_report_async(research_id, bug_report)
        )

        return partial_content
```

### Phase 5: 断点续分析 (Resume Research)

```python
def resume_research(research_id, ...) -> ResearchResult:
    checkpoint = load_checkpoint(research_id)

    # 找出所有 pending / failed 步骤
    pending_steps = [s for s in checkpoint.steps if s.status in ("pending", "failed")]

    # 增量分析：只处理未完成的步骤
    for step in pending_steps:
        logger.info(f"Resuming step: {step.id}")
        result = execute_step(step, checkpoint)
        save_checkpoint(checkpoint, step=step.id, status="completed")

    # 生成增量报告（只更新变化部分）
    incremental = generate_incremental_report(research_id, checkpoint)
    return incremental
```

---

## 容错与断点机制

### Checkpoint 状态机

```
research_id: "RS-20260620-001"
steps:
  - id: "init"
    status: "completed"      # pending | in_progress | completed | failed
    started_at: "2026-06-20T16:00:00"
    completed_at: "2026-06-20T16:00:05"
    md5: "a1b2c3..."

  - id: "paper_analysis"
    status: "completed"
    md5: "d4e5f6..."

  - id: "perspective_analysis"
    status: "in_progress"    # 上次中断于此
    started_at: "2026-06-20T16:05:00"

  - id: "outline"
    status: "pending"

  - id: "write"
    status: "pending"

last_updated: "2026-06-20T16:07:30"
md5: "g7h8i9..."              # 写入前校验，防止重入
```

**MD5 防重机制**：每次写入前计算 `checkpoint.json` 的 MD5 值，避免重复写入或状态冲突。

### 每个 Research 的独立工作区

```
data/research/RS-{research_id}_checkpoint/
├── checkpoint.json              # 断点状态机（核心）
├── paper_analysis/              # 每篇论文分析 .md
│   ├── 2311.10723.md
│   ├── 2510.05533.md
│   └── ...
├── perspective_analysis/        # 四视角分析（技术/应用/评估/局限）
│   ├── technical.md
│   ├── application.md
│   ├── evaluation.md
│   └── limitation.md
├── author_network/              # 作者关系网络
│   ├── author_graph.json
│   └── clusters.json
├── bug_reports/               # Bug 报告（降级时生成）
│   └── {timestamp}.json
├── outline.md                 # 论文大纲
├── draft/                     # 论文草稿
│   └── incremental_report.md  # 增量报告
└── artifacts.json             # 所有产物的清单
```

---

## 论文质量流水线

FARS 集成了完整的 **AI 论文质量流水线**，覆盖从初稿到终稿的全流程质量控制：

```
AI写作 → 人工增强 → 查重查袭 → AI痕迹检测 → 论文评审 → 综合评分
   Step 1     Step 2      Step 3      Step 4        Step 5      Step 6
```

### 流水线架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    论文质量流水线 (Quality Pipeline)               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 4: AI 痕迹检测                                             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Fast-DetectGPT (ICLR 2024)                                 │ │
│  │  条件概率曲率检测 · 本地模型 · gpt-neo-2.7B / gpt-j-6B      │ │
│  │  阈值: criterion = 1.9299                                  │ │
│  │  输出: AI概率 · 置信度 · 可疑段落定位                        │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  Step 5: 论文评审                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Claude API / DeepSeek API / 本地 GPT-2 fallback          │ │
│  │  5维度评分: Reproducibility · Merit · Originality          │ │
│  │           Clarity · Utility                               │ │
│  │  输出: 结构化评审报告 + 修改建议                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  Step 6: 综合质量报告                                             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  7维度雷达图: 原创性 · 方法论 · 实验 · 写作 · 引用 ·        │ │
│  │               AI痕迹 · 整体质量                              │ │
│  │  PDF 导出 · 可分享报告                                       │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 核心模块

| 模块 | 文件 | 说明 |
|------|------|------|
| **FastDetectGPTDetector** | `src/tools/quality_pipeline.py` | 本地 AI 检测，支持 gpt-neo-2.7B / gpt-j-6B / Llama3-8B |
| **PaperReviewer** | `src/tools/quality_pipeline.py` | 论文评审，支持 Claude / DeepSeek / 本地 GPT-2 |
| **QualityReporter** | `src/tools/quality_pipeline.py` | 7维度雷达图数据生成 |
| **Fast-DetectGPT** | `vendor/fast-detect-gpt/` | Git Submodule (ICLR 2024) |

### Dashboard 按钮

在 FARS Dashboard 中新增三个质量控制按钮：

| 按钮 | 功能 | API 端点 |
|------|------|---------|
| 🔍 **AI痕迹检测** | 检测论文中 AI 生成的可疑段落 | `POST /api/quality/detect-ai` |
| 📋 **论文评审** | 结构化 5 维评审 + 修改建议 | `POST /api/quality/review-paper` |
| 🚀 **完整流水线** | 串联 Step 4+5+6，生成综合报告 | `POST /api/quality/pipeline` |

### Fast-DetectGPT 安装

```bash
# 安装脚本自动配置本地检测模型
bash setup-fast-detectgpt.sh

# 模型将下载到 ~/.cache/huggingface/hub/
# 支持模型: gpt-neo-2.7B (默认), gpt-j-6B, Llama3-8B
```

### 风险判定标准

| AI 概率 | 风险等级 | 说明 |
|---------|---------|------|
| < 30% | 🟢 Low | 正常人类写作 |
| 30-70% | 🟡 Medium | 建议人工审核 |
| > 70% | 🔴 High | 疑似 AI 生成，需大幅修改 |

---

## 参考系统

FARS 整合了以下顶级学术 AI 研究系统的核心机制：

### AI Scientist (Sakana AI)

- **树搜索 BFTS**：提出 Ideas → 做实验 → 写论文 → 评分，迭代直到收敛
- FARS 借鉴：多分支并行研究 + 评分反馈循环

### ARIS (Agentic Research System)

- **Claims-Evidence Matrix**：每个 Claim 必须映射到 Evidence，禁止无来源声明
- **三重安全门**：No Fabrication / No Overpromise / Full Coverage
- FARS 借鉴：Anti-hallucination 机制、DBLP→CrossRef 引用验证

### LightFARS (LangChain-based)

- **多智能体流水线**：规划、执行、写作分离
- FARS 借鉴：模块化 Agent 架构

### STORM (Stanford University)

- **Perspective-guided Question Asking**：N 个视角 × M 轮对话，充分探索主题
- **Phase 1 Pre-writing → Phase 2 Writing**：调研与写作分离
- 效果：84.83% citation recall（传统方法仅 20-30%）
- FARS 借鉴：多视角调研、大纲生成

### GPT Researcher (Tavily)

- **并行章节研究**：ChiefEditor 协调多 Agent 并行工作
- **Review-Revision 循环**：Reviewer 提意见 → Reviser 修订，重复直到达标
- **8 个专业 Agent**：ChiefEditor / Researcher / Editor / Reviewer / Reviser / Writer / Publisher / Human
- FARS 借鉴：Review-Revision 质量控制循环

---

## 项目结构

```
paperwriterAI/
├── server.py                          # Flask API 服务器（~4300行）
│
├── src/
│   ├── core/
│   │   ├── research_engine.py         # 容错断点分析引擎
│   │   ├── research_archive.py        # 研究存档管理
│   │   ├── data_registry.py           # 数据注册表
│   │   ├── mongo_index.py             # MongoDB 语义索引（可选）
│   │   ├── research_reset.py          # 研究重置
│   │   ├── seed_library.py            # 种子论文库
│   │   ├── paper_extractor.py         # 论文正文提取
│   │   ├── pdf_compiler.py            # PDF 编译器
│   │   └── research_runner.py         # 研究运行器
│   │
│   ├── agents/
│   │   ├── ideation.py               # 灵感生成 Agent
│   │   ├── planning.py                # 实验计划 Agent
│   │   ├── experiment.py              # 实验执行 Agent
│   │   └── writing.py                # 论文撰写 Agent
│   │
│   ├── tools/
│   │   ├── backtest.py               # 回测引擎
│   │   ├── quality_pipeline.py       # 论文质量流水线（Step 4-6）
│   │   ├── literature_review_engine.py # 文献综述引擎
│   │   └── fetchers.py               # 论文抓取器
│   │
│   └── prompts/
│       └── templates.py               # 7个 Prompt 模板
│
├── scripts/
│   ├── chunked_generation.py          # 分块生成器
│   ├── fars_paper_generator.py        # 论文生成器
│   └── real_experiment_v2.py          # 实验 v2
│
├── services/                          # 服务层（LLM 调用封装）
│
├── docs/
│   ├── fars_dashboard.html            # Dashboard 界面 v1（单文件，含质量流水线按钮）
│   ├── v2/                           # Dashboard 界面 v2（组件化）
│   │   ├── index.html                 # 主入口
│   │   ├── css/v2-dashboard.css      # 样式（含暗色主题）
│   │   ├── api/client.js             # REST API 封装（40+端点）
│   │   ├── state/store.js            # 集中状态管理（订阅/发布）
│   │   └── components/
│   │       ├── pipeline-view.js       # 5阶段流水线视图
│   │       ├── research-sidebar.js    # 研究统计+假设列表
│   │       ├── topology-graph.js      # SVG 拓扑图
│   │       ├── experiment-panel.js    # 实验日志+代码高亮
│   │       ├── quality-panel.js       # AI检测+评审+雷达图
│   │       ├── paper-compare.js       # 多论文对比
│   │       └── checkpoint-manager.js  # 检查点时间线
│   ├── FARS_LITERATURE_REVIEW_PLAN.md # 改进计划（设计文档）
│   ├── AI_PAPER_FULL_WORKFLOW.md     # 完整流程规划
│   ├── QUALITY_PIPELINE_INTEGRATION.md # 技术集成方案
│   └── reviews/
│
├── vendor/
│   └── fast-detect-gpt/              # Git Submodule - Fast-DetectGPT (ICLR 2024)
│       └── scripts/
│           ├── model.py              # 评分模型
│           ├── fast_detect_gpt.py    # 核心检测算法
│           └── local_infer.py        # 本地推理
│
├── data/
│   ├── seed_papers/                   # 种子论文库（PDF + summary.json）
│   ├── research/                      # 研究结果（每个 research 一个工作区）
│   ├── research_logs.json             # 研究日志
│   ├── grading_history.json           # 评分历史
│   ├── papers_state.json              # 论文状态
│   └── research_state.json            # 研究状态
│
├── config.json                        # API 配置（MiniMax / DeepSeek）
├── setup-fast-detectgpt.sh            # Fast-DetectGPT 安装脚本
├── requirements.txt
├── .gitmodules
└── README.md
```

---

## Dashboard v2 新版前端

FARS 提供两套前端界面，均通过 `server.py` 提供服务，共享所有后端 API：

### 访问方式

| 版本 | 路由 | 访问地址 |
|------|------|---------|
| **v1 (旧版)** | `/` | http://localhost:8080/ |
| **v2 (新版)** | `/v2/` | http://localhost:8080/v2/ |

### v2 界面功能

| Tab 面板 | 功能说明 |
|---------|---------|
| **研究总览** | 研究统计卡片、假设列表、论文列表、分支切换 |
| **流水线** | 5阶段横向流转图（Ideation→Planning→Experiment→Writing→Review），实时状态轮询 |
| **实验日志** | 回测代码高亮、日志流式输出、收益曲线 |
| **质量分析** | AI痕迹检测（Fast-DetectGPT）+ 论文评审（Claude）+ 7维度雷达图 |
| **论文对比** | 多论文横排对比、指标表格、可下载 LaTeX |

### v2 组件技术栈

```
HTML5 + CSS3 (CSS变量/暗色主题) + 原生JavaScript
    ├── 状态管理: store.js (集中式，发布/订阅)
    ├── API调用: client.js (40+ REST端点)
    ├── 可视化:  Chart.js (雷达图/折线图)
    └── 拓扑图:  SVG力导向布局
```

### 启动 v2

```bash
python3 server.py
# 访问 http://localhost:8080/v2/
```

---

## 快速开始

### 1. 安装依赖

```bash
cd paperwriterAI
pip install -r requirements.txt
```

### 2. 配置 API Key

**API Key 通过环境变量读取，不存储在配置文件中。** 请在终端设置：

```bash
# MiniMax API（主用）
export MINIMAX_API_KEY="gw-xxxxx"

# DeepSeek API（可选，备用）
export DEEPSEEK_API_KEY="sk-xxxxx"

# Claude API（用于论文质量评审 Step 5，可选）
export ANTHROPIC_API_KEY="sk-ant-xxxxx"
```

`config.json` 中各 provider 的 `api_key` 字段留空，运行时自动从环境变量读取。

### 2.1 安装 Fast-DetectGPT（可选，Step 4 AI检测）

```bash
bash setup-fast-detectgpt.sh
```

此步骤下载 ~10GB 模型文件（gpt-neo-2.7B），用于本地 AI 痕迹检测。

### 3. 启动服务器

```bash
python server.py
```

服务器运行在 `http://localhost:8080`

### 4. 打开 Dashboard

浏览器访问：`http://localhost:8080/docs/fars_dashboard.html`

---

## API 参考

### 研究流程

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/research/state` | GET | 获取研究状态 |
| `/api/research/full/<id>` | POST | 端到端完整研究流程 |
| `/api/research/reset` | POST | 重置研究 |

### 断点与恢复

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/research/checkpoint/create` | POST | 创建新断点 |
| `/api/research/checkpoint/<id>` | GET | 获取断点状态 |
| `/api/research/checkpoint/<id>/step/<step_id>` | GET | 获取单步状态 |
| `/api/research/resume/<id>` | POST | 从断点恢复（增量继续） |
| `/api/research/write-degraded` | POST | 降级写作 + Bug 报告 |

### 论文分析

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/research/analyze-paper` | POST | 分析单篇论文 |
| `/api/research/analyze-all` | POST | 批量分析（带断点保护） |
| `/api/research/perspective/<id>` | GET | STORM 风格视角分析 |
| `/api/research/compare` | POST | 多论文比对 |
| `/api/research/outline/<id>` | GET | 生成论文大纲 |

### 作者网络

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/research/author-network/<id>` | GET | 作者关系网络 |

### 文献综述（STORM/GPT Researcher 风格）

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/research/literature-review` | POST | 生成文献综述章节 |
| `/api/research/generate-full` | POST | 完整流程生成论文 |
| `/api/research/review-and-revise` | POST | Review-Revision 循环 |

### 论文管理

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/papers` | GET | 论文列表 |
| `/api/papers/<id>` | GET | 论文详情 |
| `/api/papers/<id>/score` | POST | 论文评分 |
| `/api/papers/<id>/improve` | POST | 迭代改进 |
| `/api/papers/<id>/submit-review` | POST | 提交论文评审 |
| `/api/papers/<id>/evaluate` | POST | 评估论文 |
| `/api/papers/<id>/final-status` | GET | 获取论文最终状态 |
| `/api/papers/<id>/quality-report` | GET | 获取质量报告 |
| `/api/download` | GET | 下载论文（LaTeX/PDF） |

### 质量流水线

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/quality/pipeline` | POST | 完整流水线 (Step 4+5+6) |
| `/api/quality/detect-ai` | POST | AI 痕迹检测 (Fast-DetectGPT) |
| `/api/quality/review-paper` | POST | 论文评审 (Claude/DeepSeek) |
| `/api/quality/ai-detection` | POST | AI 检测（兼容旧端点） |

### 分支管理

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/branches` | GET | 分支列表 |
| `/api/branches` | POST | 创建分支 |
| `/api/branches/<id>` | GET | 分支详情 |
| `/api/branches/switch/<id>` | POST | 切换分支 |

### 种子论文

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/seed-papers` | GET | 种子论文列表 |
| `/api/seed-papers/status` | GET | 论文库状态 |
| `/api/seed-papers/extract-all` | POST | 批量提取论文正文 |
| `/api/seed-papers/texts` | GET | 获取所有论文文本 |
| `/api/seed-papers/fetch` | POST | 抓取新论文 |

### 研究日志

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/research/logs` | GET | 获取研究日志 |
| `/api/research/logs` | POST | 添加日志 |
| `/api/research/logs/<id>` | GET | 日志详情 |
| `/api/research/logs/summary` | GET | 日志摘要（Dashboard 显示用） |

### 其他

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/generate/start` | POST | 开始/继续生成 |
| `/api/generate/pause` | POST | 暂停生成 |
| `/api/generate/resume` | POST | 恢复生成 |
| `/api/generate/next` | POST | 生成下一篇 |
| `/api/score` | POST | 论文评分 |
| `/api/iterate` | POST | 迭代改进 |
| `/api/history` | GET | 历史记录 |
| `/api/health` | GET | 健康检查 |
| `/api/data/registry` | GET | 数据注册表 |

---

## 设计文档

详细设计文档见 `docs/` 目录：

| 文档 | 说明 |
|------|------|
| [`docs/FARS_LITERATURE_REVIEW_PLAN.md`](docs/FARS_LITERATURE_REVIEW_PLAN.md) | STORM/GPT Researcher 集成方案、LaTeX 模板、Anti-hallucination |
| [`docs/AI_PAPER_FULL_WORKFLOW.md`](docs/AI_PAPER_FULL_WORKFLOW.md) | 完整流程规划（5步质量控制） |
| [`docs/QUALITY_PIPELINE_INTEGRATION.md`](docs/QUALITY_PIPELINE_INTEGRATION.md) | Fast-DetectGPT + 论文评审技术集成方案 |

---

## 评分标准

论文从 5 个维度评分（满分 10 分，7 分通过）：

| 维度 | 满分 | 说明 |
|------|------|------|
| **创新性** | 0-3 | 假设的原创性 |
| **方法论** | 0-2 | 论文方法的严谨性 |
| **实验验证** | 0-2 | 回测结果的可信度 |
| **写作质量** | 0-2 | 论文结构与表达 |
| **避免过拟合** | 0-1 | 是否存在过拟合风险 |

---

## License

MIT License
