# PaperWriterAI - 基于LLM的循环论文生成系统

循环生成量化交易领域高质量学术论文的全自动系统。

## 系统概述

PaperWriterAI 是一个基于大语言模型(LLM)的自动化学术论文生成系统，专注于量化交易和金融科技领域。系统从一篇高引用的综述论文出发，自主进行文献分析、假设生成、实验设计、论文撰写，循环迭代产出高质量学术论文。

## 核心流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     PaperWriterAI 核心流程                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. 综述输入 → 2. 文献分析 → 3. 假设生成 → 4. 实验设计           │
│         ↑                                    ↓                   │
│         └──── 6. 论文输出 ← 5. 实验验证 ←───                     │
│                                                                   │
│  循环迭代：评分 → 反馈 → 改进 → 直至产出高质量论文               │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## 项目结构

```
paperwriterAI/
├── src/
│   ├── core/
│   │   ├── config.py         # 核心配置
│   │   └── database.py       # SQLite数据库
│   ├── agents/
│   │   ├── ideation.py       # 灵感生成Agent
│   │   ├── planning.py       # 实验计划Agent
│   │   ├── experiment.py     # 实验执行Agent
│   │   └── writing.py        # 论文撰写Agent
│   ├── tools/
│   │   ├── fetchers.py       # 论文/数据获取
│   │   └── backtest.py       # 回测引擎
│   └── prompts/
│       └── templates.py      # Prompt模板
├── scripts/
│   ├── chunked_generation.py # 分块生成器
│   └── fars_paper_generator.py
├── docs/
│   ├── fars_dashboard.html   # Dashboard界面
│   └── reviews/
│       └── seed_review.md     # 起始综述
├── server.py                 # Flask API服务器
└── requirements.txt
```

## 起始综述

本系统以以下论文作为起点进行循环研究：

**"Automate Strategy Finding with LLM in Quant Investment"** (arXiv:2409.06289)

- **作者**: 提出了基于LLM和多智能体架构的量化投资框架
- **核心贡献**:
  1. 多模态Alpha因子挖掘（从学术论文、财务报告、K线图等多源提取预测信号）
  2. 多智能体市场评估（具有不同风险偏好的多样化交易智能体池）
  3. 动态权重优化（基于实时市场条件动态选择和分配权重）
- **实验结果**: 2023年中国A股SSE 50指数回测，策略收益+53.17%，显著优于指数基准(-11.73%)

## 快速开始

### 1. 安装依赖

```bash
cd paperwriterAI
pip install -r requirements.txt
```

### 2. 配置API Key

```bash
export MINIMAX_API_KEY="your-api-key"
# 或使用 DeepSeek
export DEEPSEEK_API_KEY="your-api-key"
```

### 3. 启动服务器

```bash
python server.py
```

### 4. 打开Dashboard

在浏览器中访问 `http://localhost:8080/docs/fars_dashboard.html`

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/research/state` | GET | 获取研究状态 |
| `/api/generate/start` | POST | 开始/继续生成 |
| `/api/generate/pause` | POST | 暂停生成 |
| `/api/generate/next` | POST | 生成下一篇论文 |
| `/api/score` | POST | 论文评分 |
| `/api/iterate` | POST | 迭代改进 |

## 评分标准

论文评分从5个维度进行（满分10分，7分通过）：

- **创新性**: 0-3分
- **方法论**: 0-2分
- **实验验证**: 0-2分
- **写作质量**: 0-2分
- **避免过拟合**: 0-1分

## License

MIT License