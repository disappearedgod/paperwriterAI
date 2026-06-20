# FARS 系统架构文档 v2.0

> 版本: 2.0 | 日期: 2026-06-20 | 状态: 已更新

---

## 1. 系统概述

**FARS (Fully Automated Research System)** 是一个全自动量化交易研究系统，让 LLM 扮演量化研究员角色，自主完成因子挖掘、策略回测、代码生成到报告撰写的全流程。

### 1.1 核心特性

- **多 Agent 协作**: Ideation → Planning → Experiment → Writing 四个阶段
- **API Token 限制解决**: ChunkedPaperGenerator 将长论文分块生成
- **多数据源支持**: baostock, akshare, yfinance, tushare
- **多 LLM Provider**: MiniMax, OpenAI, Anthropic, DeepSeek, Ollama
- **研究拓扑可视化**: D3.js 交互式 Dashboard

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        FARS 主控制器                             │
│                     (src/main.py - FARS类)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ Ideation     │  │ Planning    │  │ Experiment   │            │
│  │ Agent        │→ │ Agent        │→ │ Agent        │→ ...       │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Workspace (共享工作空间)                 │  │
│  │  ├── ideas/          # 研究假设                            │  │
│  │  ├── plans/          # 实验计划                            │  │
│  │  ├── experiments/    # 实验结果                            │  │
│  │  ├── papers/         # 生成论文                            │  │
│  │  ├── data/           # 市场数据                            │  │
│  │  ├── charts/         # 可视化图表                          │  │
│  │  ├── logs/           # 运行日志                            │  │
│  │  └── backups/         # 文件备份                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ LLMCaller       │  │ MarketDataFetch │  │ BacktestEngine │  │
│  │ (多Provider)    │  │ (baostock/ak)   │  │ (backtrader)   │  │
│  └─────────────────┘  └─────────────────┘  └────────────────┘  │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ PaperFetcher    │  │ ChunkedPaper    │  │ QualityGate    │  │
│  │ (arxiv/S2)     │  │ Generator       │  │ Evaluator      │  │
│  └─────────────────┘  └─────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心模块

### 3.1 LLM 调用 (src/tools/fetchers.py)

```python
class LLMCaller:
    """支持多 Provider 自动切换的 LLM 调用器"""
    providers = ["minimax", "openai", "anthropic", "deepseek", "ollama"]

    def call(self, prompt, system_prompt=None, temperature=0.7, max_tokens=4096):
        # 自动切换到 fallback provider
```

**支持模型**:
| Provider   | Model                      | Context Window |
|------------|----------------------------|---------------|
| MiniMax    | MiniMax-M2.7-highspeed     | 196,608       |
| OpenAI     | gpt-4o, gpt-4o-mini        | 128,000       |
| Anthropic  | claude-3-5-sonnet          | 200,000       |
| DeepSeek   | deepseek-chat              | 128,000       |
| Ollama     | gemma4, qwen3.6:35b       | 32,768        |

### 3.2 分块论文生成 (scripts/chunked_paper_generator.py)

**问题**: MiniMax API 限制 196,608 tokens，输入+输出超出限制

**解决方案**: 将论文分成 8 个独立章节生成

```
章节生成顺序:
abstract → introduction → related_work → methodology
→ experimental_setup → experimental_results → discussion → conclusion

每个章节携带前3个章节的摘要作为上下文，控制 prompt 大小在 180,000 tokens 内
```

**配置参数**:
```python
@dataclass
class ChunkConfig:
    max_context_tokens: int = 180000   # 预留 buffer
    max_output_tokens: int = 16000    # 单次输出上限
    context_sections_limit: int = 3  # 携带前3章摘要
```

**效果**: Prompt 从 65,537 tokens 减少到 ~2,416 tokens (96% 减少)

### 3.3 研究方向支持 (src/core/config.py)

```python
class ResearchDirection(Enum):
    QUANT_FINANCE = "quant_finance"        # 量化金融 (主方向)
    COMPUTER_VISION = "computer_vision"     # 计算机视觉
    REINFORCEMENT_LEARNING = "rl"           # 强化学习

# 各方向对应的顶会/期刊
applicable_venues:
- QUANT_FINANCE: ["ICML", "NeurIPS", "ICLR", "JPF", "RFS"]
- COMPUTER_VISION: ["CVPR", "ICCV", "ECCV", "NeurIPS"]
- RL: ["NeurIPS", "ICML", "ICLR", "AAAI", "IJCAI"]
```

---

## 4. 数据流

```
用户输入主题
    ↓
Ideation Agent: 阅读论文 → 生成假设 → 保存到 ideas/
    ↓
Planning Agent: 制定实验计划 → 保存到 plans/
    ↓
Experiment Agent: 获取数据 → 执行回测 → 评估结果
    ↓
Writing Agent: ChunkedPaperGenerator 生成论文 → 保存到 papers/
    ↓
Dashboard 可视化: 拓扑图 + 论文列表 + 假设状态
```

---

## 5. API Token 限制解决方案

### 5.1 问题描述

```
MiniMax API: context window = 196,608 tokens
原始论文生成 prompt: 65,537 tokens (输入) + 131,072 tokens (输出) > 196,608
```

### 5.2 解决步骤

1. **分析**: 将论文结构分解为 8 个独立章节
2. **分块**: 每章节独立生成，prompt 只包含必要信息
3. **上下文传递**: 每章节携带前 3 章摘要（控制大小）
4. **组装**: 8 个章节组装成完整论文

### 5.3 效果对比

| 指标        | 原始方案   | 分块方案   | 减少比例 |
|------------|-----------|-----------|---------|
| Prompt大小  | 65,537    | ~2,416    | 96%     |
| API调用次数 | 1          | 8         | -       |
| 成功率      | 0%        | 100%      | -       |

---

## 6. Dashboard 可视化 (docs/fars_dashboard.html)

### 6.1 功能模块

- **研究拓扑图**: D3.js 力导向图，展示 Hypothesis → Experiments → Papers 关系
- **统计卡片**: 论文数、假设数、实验数、成功率
- **论文列表**: 显示所有论文（包括成功和失败的）- "所有成功建立在失败基础上"
- **假设管理**: 跟踪假设状态 HYPOTHESIS → PLANNING → EXPERIMENTING → SUCCESS/FAILED
- **实验记录**: 记录实验参数和结果

### 6.2 状态颜色编码

- `success`: 绿色 - 成功完成的论文/实验
- `failed`: 红色 - 失败的论文/实验
- `experimenting`: 黄色 - 进行中的实验
- `hypothesis`: 蓝色 - 新提出的假设

---

## 7. 目录结构

```
fars_system/
├── src/
│   ├── main.py              # FARS 主控制器
│   ├── core/
│   │   ├── config.py        # 配置、Workspace、日志、备份
│   │   └── database.py      # SQLite 数据库
│   ├── agents/
│   │   └── agents.py        # 四个 Agent 实现
│   ├── tools/
│   │   ├── backtest.py      # BacktestEngine
│   │   └── fetchers.py      # LLMCaller, PaperFetcher, MarketDataFetcher
│   └── prompts/
│       └── templates.py      # 7 个 Prompt 模板
├── scripts/
│   ├── chunked_paper_generator.py  # 分块论文生成器
│   └── generate_paper_with_api.py  # MiniMax API 集成
├── docs/
│   ├── fars_dashboard.html  # 可视化 Dashboard
│   └── API_SPEC.md          # API 规范
├── papers/                  # 论文存储
├── workspace/
│   └── projects/           # 项目工作空间
└── outputs/
    └── generated_paper.md   # 生成的论文
```

---

## 8. 研究状态流程

```
HYPOTHESIS (假设)
    ↓
PLANNING (计划中)
    ↓
EXPERIMENTING (实验中)
    ↓
    ├── SUCCESS (成功) → 论文发布
    ├── FAILED (失败) → 分析原因 → 新假设
    └── ABANDONED (放弃) → 记录原因
```

---

## 9. 下一步计划

1. **完整论文生成测试**: 使用真实 MiniMax API 生成 8 个章节
2. **LaTeX 编译**: 将 Markdown 论文编译为 PDF
3. **多 Provider 切换**: 测试 Ollama 本地模型
4. **因子挖掘扩展**: 实现更多量化因子
5. **Dashboard 增强**: 添加实时更新功能

---

## 10. 关键文件

| 文件                          | 功能                           |
|------------------------------|-------------------------------|
| `src/main.py`                | FARS 主控制器                  |
| `src/core/config.py`         | 配置、Workspace、研究方向      |
| `scripts/chunked_paper_generator.py` | 分块论文生成器 |
| `src/tools/fetchers.py`      | LLMCaller、PaperFetcher       |
| `docs/fars_dashboard.html`   | D3.js 可视化 Dashboard         |

---

*文档版本: 2.0 | 更新日期: 2026-06-20*