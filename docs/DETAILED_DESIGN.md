# FARS 详细设计文档

> 版本: 1.0 | 日期: 2026-06-20 | 状态: 详细设计

---

## 1. 系统概述

### 1.1 设计目标

FARS (Fully Automated Research System) 是一个用于**量化交易领域的全自动研究系统**，目标是让LLM扮演量化研究员角色，自主完成：

1. 因子挖掘与假设生成
2. 策略回测与性能评估
3. 代码生成与错误自愈
4. 研究报告自动撰写

最终输出**可发表的学术论文**。

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| 模块化 | 每个组件职责单一，可独立测试 |
| 可扩展 | 支持添加新的Agent、数据源、评估指标 |
| 可复现 | 实验结果可重复，版本可控 |
| 沙箱安全 | LLM生成的代码在隔离环境中执行 |
| 迭代优化 | 支持假设→实验→评估→改进的循环 |

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FARS Orchestrator                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         Message Bus (Agent 通信)                       │  │
│  │   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐        │  │
│  │   │ Ideation │───│ Planning │───│Experiment│───│ Writing  │        │  │
│  │   │  Agent   │   │  Agent   │   │  Agent   │   │  Agent   │        │  │
│  │   └──────────┘   └──────────┘   └──────────┘   └──────────┘        │  │
│  │        │             │             │             │                  │  │
│  │        └─────────────┴─────────────┴─────────────┘                  │  │
│  │                         ↕ Critique & Refinement                         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│                              Shared Workspace                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   papers/   │  │experiments/ │  │   reports/  │  │  logs/      │       │
│  │  (论文库)   │  │  (实验记录)  │  │  (输出报告)  │  │  (运行日志)  │       │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │
├─────────────────────────────────────────────────────────────────────────────┤
│                              Tools Layer                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │  Paper      │  │  Market     │  │  Backtest   │  │   LLM      │       │
│  │  Fetcher    │  │  Data       │  │  Engine     │  │  Caller    │       │
│  │  (arXiv)    │  │  (yfinance/ │  │  (Backtrader│  │  (OpenAI/  │       │
│  │             │  │   AkShare)   │  │   /Qlib)    │  │   DeepSeek)│       │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │
├─────────────────────────────────────────────────────────────────────────────┤
│                              Data Layer                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     SQLite (papers, alpha_factors,                  │   │
│  │                              experiments, reports)                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Agent详细设计

#### 2.2.1 Ideation Agent（灵感与假设生成器）

**职责**：
- 搜索和获取相关论文
- 分析论文的方法论和创新点
- 从论文提取可量化的交易逻辑
- 生成结构化的Alpha因子假设

**输入**：
- 搜索关键词 (query)
- 最大论文数 (max_papers)
- 论文ID列表 (paper_ids) — 可选，用于指定论文

**输出**：
```json
{
  "hypothesis_id": "hyp_20260620_001",
  "source_paper": {
    "paper_id": "arXiv:2409.06289",
    "title": "Automate Strategy Finding with LLM",
    "authors": ["Author1", "Author2"],
    "year": 2024
  },
  "alpha_name": "LLM_Sentiment_Momentum",
  "description": "基于论文提出的LLM情绪分析结合动量效应",
  "trading_logic": "当LLM对短期新闻情绪评分为正且股价处于20日均线上方时，买入",
  "parameters": {
    "sentiment_threshold": 0.6,
    "lookback_period": 20
  },
  "expected_direction": "long_only",
  "risk_factors": ["市场系统性风险", "流动性风险"]
}
```

**Prompt模板**（详见第4节）

#### 2.2.2 Planning Agent（实验计划制定）

**职责**：
- 将假设转化为详细的实验计划
- 设计对照组和实验组
- 设定评估指标和成功标准
- 规划数据需求和回测参数

**输入**：
- Hypothesis JSON
- 可用数据源列表
- 回测时间范围

**输出**：
```json
{
  "experiment_id": "exp_20260620_001",
  "hypothesis_id": "hyp_20260620_001",
  "plan": {
    "objective": "验证LLM情绪+动量策略的有效性",
    "hypothesis": "该策略在A股市场能获得显著正收益",
    "success_criteria": {
      "sharpe_ratio": { "min": 1.5 },
      "max_drawdown": { "max": -0.25 },
      "ic": { "min": 0.02 }
    },
    "experiments": [
      {
        "name": "baseline",
        "description": "传统动量策略（无LLM信号）",
        "parameters": {}
      },
      {
        "name": "llm_sentiment_momentum",
        "description": "LLM情绪+动量组合策略",
        "parameters": {
          "sentiment_threshold": 0.6,
          "lookback_period": 20
        }
      },
      {
        "name": "sensitivity_analysis",
        "description": "参数敏感性分析",
        "parameters": {
          "sentiment_threshold": [0.4, 0.5, 0.6, 0.7, 0.8],
          "lookback_period": [10, 20, 30, 60]
        }
      }
    ],
    "data_requirements": {
      "market_data": "A股日线数据，2018-01-01至2025-12-31",
      "alternative_data": "新闻数据（用于LLM情绪分析）",
      "frequency": "日频"
    },
    "backtest_config": {
      "initial_cash": 1000000,
      "commission": 0.001,
      "slippage": 0.0005
    }
  }
}
```

#### 2.2.3 Experiment Agent（实验执行与错误自愈）

**职责**：
- 根据实验计划生成Python回测代码
- 在沙箱环境中执行代码
- 捕获错误并进行自我修复
- 计算评估指标并判断是否达标

**错误自愈机制**：

```python
class ExperimentAgent:
    MAX_RETRIES = 3

    def execute_with_self_healing(self, code: str, context: dict) -> dict:
        """带自我修复的代码执行"""
        for attempt in range(self.MAX_RETRIES):
            try:
                result = self.execute_code(code, context)
                return {"success": True, "result": result}

            except SyntaxError as e:
                code = self.fix_syntax_error(code, e)

            except DataError as e:
                code = self.fix_data_error(code, e)

            except CalculationError as e:
                code = self.fix_calculation_error(code, e)

            except Exception as e:
                # 未知错误，尝试Debug Agent
                debug_prompt = DEBUG_ASSISTANCE_PROMPT.format(
                    code=code,
                    error=str(e),
                    context=context
                )
                fixed_code = self.llm.call(debug_prompt)
                code = fixed_code

        return {"success": False, "attempts": self.MAX_RETRIES}
```

**输出**：
```json
{
  "experiment_id": "exp_20260620_001",
  "run_id": "run_001",
  "status": "success",
  "results": {
    "sharpe_ratio": 1.82,
    "max_drawdown": -0.18,
    "annual_return": 0.24,
    "ic": 0.035,
    "win_rate": 0.58
  },
  "generated_code": "...",
  "execution_log": "...",
  "healing_attempts":  ,
  "judgment": {
    "passed": true,
    "details": "Sharpe Ratio (1.82) > 1.5 ✓, Max Drawdown (-0.18) > -0.25 ✓"
  }
}
```

#### 2.2.4 Writing Agent（论文撰写）

**职责**：
- 根据实验结果撰写完整学术论文
- 生成LaTeX格式的可提交论文
- 自动生成图表（收益曲线、回撤图、IC分析等）
- 输出参考文献BibTeX

**输出**：
```json
{
  "paper_id": "paper_20260620_001",
  "title": "LLM-Driven Sentiment and Momentum Strategy in A-Share Market",
  "abstract": "...",
  "sections": {
    "introduction": "...",
    "related_work": "...",
    "methodology": "...",
    "experiment": "...",
    "conclusion": "..."
  },
  "figures": [
    {"id": "fig:returns", "path": "reports/figures/returns.png"},
    {"id": "fig:drawdown", "path": "reports/figures/drawdown.png"}
  ],
  "tables": [
    {"id": "tab:performance", "path": "reports/tables/performance.tex"},
    {"id": "tab:parameters", "path": "reports/tables/parameters.tex"}
  ],
  "tex_content": "完整LaTeX源码",
  "references": "BibTeX格式参考文献"
}
```

---

## 3. 数据流设计

### 3.1 主数据流

```
[论文搜索] → [论文分析] → [假设生成] → [实验计划] → [代码生成]
                                                      ↓
[数据获取] ← ← ← ← ← ← ← ← ← ← ← ← ← ← [代码执行]
    ↓                                           ↓
[市场数据]                                   [回测结果]
    ↓                                           ↓
[数据预处理] → [因子计算] → [策略回测] → [结果评估]
                                            ↓
                                    [评估通过?]──否→ [错误自愈] → [重新执行]
                                            ↓是
                                    [论文撰写] → [报告输出]
```

### 3.2 消息传递协议

Agent间通过Message Bus进行通信：

```python
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
import uuid

class MessageType(Enum):
    HYPOTHESIS_READY = "hypothesis_ready"
    PLAN_READY = "plan_ready"
    CODE_READY = "code_ready"
    RESULT_READY = "result_ready"
    PAPER_READY = "paper_ready"
    ERROR = "error"
    HEAL_REQUEST = "heal_request"

@dataclass
class Message:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = None
    sender: str = ""
    receiver: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: time.time())

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "type": self.type.value,
            "sender": self.sender,
            "receiver": self.receiver,
            "payload": self.payload,
            "timestamp": self.timestamp
        })

    @staticmethod
    def from_json(json_str: str) -> "Message":
        data = json.loads(json_str)
        return Message(
            id=data["id"],
            type=MessageType(data["type"]),
            sender=data["sender"],
            receiver=data["receiver"],
            payload=data["payload"],
            timestamp=data["timestamp"]
        )
```

### 3.3 工作空间结构

```
workspace/
├── projects/
│   └── {project_id}/
│       ├── config.yaml           # 项目配置
│       ├── papers/               # 论文PDF和摘要
│       ├── hypotheses/           # 假设JSON
│       │   └── {hypothesis_id}.json
│       ├── experiments/          # 实验记录
│       │   ├── {experiment_id}/
│       │   │   ├── plan.json
│       │   │   ├── code.py
│       │   │   ├── result.json
│       │   │   └── logs/
│       │   └── experiment_registry.json
│       ├── reports/              # 输出报告
│       │   ├── {paper_id}/
│       │   │   ├── paper.tex
│       │   │   ├── figures/
│       │   │   └── references.bib
│       │   └── final/
│       └── cache/                # 临时缓存
│           ├── market_data/
│           └── llm_responses/
```

---

## 4. Prompt模板集合（详细版）

### 4.1 Idea Generation Prompt

```python
IDEA_GENERATION_PROMPT = """
你是一位专业的量化交易研究员。你的任务是从以下论文中提取可量化的交易策略假设。

## 论文信息
- 标题: {paper_title}
- 作者: {paper_authors}
- 年份: {paper_year}
- 摘要: {paper_abstract}

## 论文全文
{paper_full_text}

## 你的任务

1. **阅读并理解论文的方法论**
   - 论文提出了什么新的交易方法或因子？
   - 这些方法的核心逻辑是什么？
   - 作者如何验证其有效性？

2. **提取可量化的交易逻辑**
   - 将论文的定性描述转化为具体的交易规则
   - 明确买入/卖出条件
   - 定义所需的技术指标或数据源

3. **生成结构化的假设**
   请以以下JSON格式输出你的假设：

```json
{{
  "alpha_name": "简洁的策略名称",
  "description": "1-2句话描述策略核心思想",
  "trading_logic": "详细的交易逻辑描述，包含具体的指标和阈值",
  "parameters": {{
    "param1": "默认值和范围",
    "param2": "默认值和范围"
  }},
  "expected_direction": "long_only | short_only | long_short",
  "risk_factors": ["风险因素1", "风险因素2"],
  "market_universe": "A股 | 美股 | 数字货币 | 通用",
  "time_horizon": "日内 | 日频 | 周频"
}}
```

## 输出要求

- 假设必须基于论文提供的方法，不能凭空捏造
- 参数要有合理的默认值
- 风险因素要考虑市场风险、流动性风险、执行风险等
- 如果论文方法难以量化，说明原因并提出可能的近似方案
"""

PAPER_ANALYSIS_PROMPT = """
你是一位量化金融领域的学术审稿人。你的任务是对以下论文进行深度分析，提取其核心贡献和研究方法。

## 论文标题
{paper_title}

## 论文摘要
{paper_abstract}

## 论文内容
{paper_content}

## 分析框架

请从以下维度进行分析：

### 1. 研究问题
- 论文试图解决什么问题？
- 这个问题在量化交易领域的重要性？

### 2. 方法论
- 采用了什么技术方法？
- 数据来源和特征工程？
- 模型架构和训练策略？

### 3. 创新点
- 与现有方法相比有何改进？
- 关键的技术突破是什么？

### 4. 实验设计
- 如何验证方法的有效性？
- 评估指标有哪些？
- 对照实验如何设计？

### 5. 可复现性
- 论文是否提供了足够的细节来复现？
- 哪些部分可能难以复现？

### 6. 局限性
- 方法的适用条件是什么？
- 可能失效的场景有哪些？

## 输出格式

请输出一份结构化的分析报告，包含以上六个维度的详细分析。
"""
```

### 4.2 Experiment Planning Prompt

```python
EXPERIMENT_PLANNING_PROMPT = """
你是一位量化研究实验设计专家。你的任务是将假设转化为可执行的实验计划。

## 假设信息
{hypothesis_json}

## 可用数据源
{data_sources}

## 回测时间范围
{backtest_period}

## 你的任务

设计一个完整的实验计划，包括：

### 1. 实验目标
- 明确要验证的核心假设
- 设定可量化的成功标准

### 2. 实验设计

请设计以下实验：

**实验A - 基准对比**
- 使用传统方法（如简单动量）作为基准
- 参数设置要经典且广泛接受

**实验B - 假设策略**
- 实现假设中的交易逻辑
- 使用假设中建议的参数

**实验C - 参数敏感性分析**
- 探索关键参数的不同取值
- 找出最优参数组合

### 3. 评估指标

必须包含以下指标：
- 年化收益率 (Annual Return)
- 夏普比率 (Sharpe Ratio) - 目标: ≥ 1.5
- 最大回撤 (Max Drawdown) - 目标: ≤ -25%
- 信息系数 (IC) - 目标: ≥ 0.02
- 胜率 (Win Rate)

### 4. 数据需求
- 明确所需的市场数据
- 是否有特殊数据需求（如情绪数据）
- 数据频率和时间范围

### 5. 回测配置
- 初始资金
- 交易费用
- 滑点设置
- 仓位管理规则

## 输出格式

请输出JSON格式的实验计划，结构如下：

```json
{{
  "experiment_id": "exp_xxx",
  "hypothesis_id": "hyp_xxx",
  "plan": {{
    "objective": "...",
    "hypothesis": "...",
    "success_criteria": {{...}},
    "experiments": [...],
    "data_requirements": {{...}},
    "backtest_config": {{...}}
  }}
}}
```
"""

CODE_GENERATION_PROMPT = """
你是一位量化交易工程师。你的任务是根据实验计划生成可执行的Python回测代码。

## 实验计划
{experiment_plan}

## 假设信息
{hypothesis}

## 数据源信息
{data_sources}

## 技术要求

### 代码结构
代码必须包含以下部分：

```python
import pandas as pd
import numpy as np
import yfinance as yf
import backtrader as bt
from datetime import datetime, timedelta

# ============ 策略实现 ============

class YourStrategy(bt.Strategy):
    """你的策略实现"""

    def __init__(self):
        # 指标计算
        pass

    def next(self):
        # 交易逻辑
        pass

# ============ 主程序 ============

def run_backtest():
    # 1. 数据获取
    data = fetch_data(...)

    # 2. 回测引擎设置
    cerebro = bt.Cerebro()
    cerebro.addstrategy(YourStrategy)

    # 3. 添加数据
    datafeed = bt.feeds.PandasData(dataname=data)
    cerebro.adddata(datafeed)

    # 4. 经纪商设置
    cerebro.broker.set_cash(1000000)
    cerebro.broker.setcommission(commission=0.001)

    # 5. 运行回测
    results = cerebro.run()

    # 6. 输出结果
    print_results(results)

if __name__ == "__main__":
    run_backtest()
```

### 错误处理
- 添加try-except包裹数据获取和计算
- 对NaN值进行合理处理
- 提供有意义的错误信息

### 性能要求
- 使用向量化操作而非循环
- 避免重复计算
- 合理使用缓存

## 输出要求

1. 生成完整的、可运行的Python代码
2. 代码必须包含中文注释
3. 包含详细的参数说明
4. 输出结果必须包含所有评估指标

请生成代码：
"""

DEBUG_ASSISTANCE_PROMPT = """
你是一位Python调试专家。用户的代码遇到了错误，请帮忙修复。

## 错误信息
```
{error}
```

## 上下文信息
```python
# 相关代码片段
{code_snippet}
```

## 错误发生时的变量值
{context}

## 你的任务

1. **分析错误原因**
   - 找出错误的根本原因
   - 确定是语法错误、逻辑错误还是数据问题

2. **修复代码**
   - 提供修复后的完整代码
   - 在修复处添加注释说明

3. **建议改进**
   - 提出避免类似问题的建议
   - 如有更优雅的实现方式，指出

## 输出格式

请按以下格式输出：

### 错误分析
[简短说明错误原因]

### 修复后的代码
```python
[完整修复后的代码]
```

### 改进建议
[2-3条改进建议]
"""
```

### 4.3 Strategy Evaluation Prompt

```python
STRATEGY_EVALUATION_PROMPT = """
你是一位量化策略评估专家。你的任务是评估回测结果的性能。

## 回测结果
```json
{backtest_result}
```

## 成功标准
```json
{success_criteria}
```

## 你的任务

### 1. 逐项评估

对每个成功标准进行评估：

| 指标 | 实际值 | 标准 | 是否达标 |
|------|--------|------|----------|
| Sharpe Ratio | x.xx | ≥ 1.5 | ✓/✗ |
| Max Drawdown | -x.xx% | ≤ -25% | ✓/✗ |
| IC | x.xx | ≥ 0.02 | ✓/✗ |
| ... | ... | ... | ... |

### 2. 综合判断

基于所有指标，给出综合评估：
- **通过 (Passed)**：所有核心指标达标
- **有条件通过 (Conditional)**：大部分指标达标，但有改进空间
- **未通过 (Failed)**：核心指标未达标

### 3. 详细分析

- 哪些指标表现良好？
- 哪些指标未达标，原因是什么？
- 有哪些潜在风险？

### 4. 改进建议

如果策略未完全达标，提出具体的改进建议：
- 参数调优方向
- 可能的策略改进
- 风险控制增强

## 输出格式

```json
{{
  "evaluation_id": "eval_xxx",
  "experiment_id": "exp_xxx",
  "overall_judgment": "passed | conditional | failed",
  "metrics_evaluation": [
    {{
      "metric": "sharpe_ratio",
      "actual_value": 1.82,
      "threshold": 1.5,
      "passed": true,
      "notes": "..."
    }}
  ],
  "analysis": "...",
  "improvement_suggestions": ["...", "..."]
}}
```
```

### 4.4 Paper Writing Prompt

```python
PAPER_WRITING_PROMPT = """
你是一位量化金融领域的学术论文作者。你的任务是根据实验结果撰写一篇完整的学术论文。

## 实验信息

### 假设
{hypothesis}

### 实验计划
{experiment_plan}

### 回测结果
{backtest_results}

### 评估结论
{evaluation}

## 论文要求

### 格式要求
- 使用LaTeX格式
- 遵循标准学术论文结构
- 包含中英文摘要

### 章节结构

1. **引言 (Introduction)**
   - 研究背景和问题动机
   - 论文的主要贡献
   - 论文结构概述

2. **相关工作 (Related Work)**
   - 回顾相关研究
   - 指出现有研究的不足
   - 说明本文与现有工作的区别

3. **方法论 (Methodology)**
   - 详细的策略描述
   - 因子构建方法
   - 回测设置

4. **实验 (Experiments)**
   - 数据集描述
   - 实验设计
   - 结果展示（表格和图表）

5. **讨论 (Discussion)**
   - 结果分析
   - 策略的优势和局限
   - 可能的改进方向

6. **结论 (Conclusion)**
   - 总结主要发现
   - 未来研究方向

### 图表要求

请生成以下图表（以Python代码形式）：

1. **累计收益曲线图** - 对比策略收益与基准
2. **回撤图** - 展示策略的回撤情况
3. **IC分析图** - 展示因子的IC时间序列
4. **参数敏感性热力图** - 展示参数对性能的影响

### 参考文献

必须包含以下参考文献（格式为BibTeX）：
- 原始FARS论文
- 本文基于的论文
- 方法论相关的经典论文

## 输出格式

请输出完整的LaTeX论文源码，以及生成图表的Python代码。
"""
```

---

## 5. 技术选型

### 5.1 LLM调用

| 供应商 | 模型 | 适用场景 | 成本 | 可用性 |
|--------|------|----------|------|--------|
| OpenAI | GPT-4o | 代码生成、论文撰写 | 高 | 需API Key |
| Anthropic | Claude 3.5 | 长文本分析、推理 | 高 | 需API Key |
| DeepSeek | DeepSeek-Coder | 代码生成（推荐） | 低 | 需API Key |
| 硅基流动 | Qwen/Qwen2.5 | 国产替代 | 低 | 本地部署 |

**推荐配置**：
- Ideation Agent → GPT-4o / Claude 3.5（分析能力强）
- Planning Agent → GPT-4o（规划逻辑强）
- Experiment Agent → DeepSeek-Coder（代码质量高）
- Writing Agent → GPT-4o（写作质量高）

### 5.2 回测框架

| 框架 | 特点 | 适用场景 | 学习曲线 |
|------|------|----------|----------|
| Backtrader | 功能完整，文档丰富 | 通用回测 | 中 |
| Qlib | 微软开源，专注于量化 | A股研究 | 高 |
| Backtesting.py | 轻量级，简单易用 | 快速原型 | 低 |
| VectorBT | 向量化，速度快 | 高频分析 | 中 |

**推荐配置**：Backtrader作为主要框架，Backtesting.py作为快速原型工具。

### 5.3 数据源

| 数据源 | 覆盖范围 | 频率 | 成本 | API |
|--------|----------|------|------|------|
| yfinance | 美股、指数、加密货币 | 日/分 | 免费 | Python |
| AkShare | A股、期货、期权 | 日/分 | 免费 | Python |
| Tushare | A股（需积分） | 日/分 | 免费/付费 | Python |
| Wind | 全市场 | 日/分 | 付费 | Python |
| WRDS | 学术研究 | 日 | 付费 | SQL |

**推荐配置**：yfinance + AkShare作为免费数据源组合。

### 5.4 沙箱执行

| 方案 | 隔离性 | 资源限制 | 复杂度 | 推荐 |
|------|--------|----------|--------|------|
| Docker | 高 | 可配置 | 中 | 生产环境 |
| subprocess | 中 | 有限制 | 低 | 开发环境 |
| AWS Lambda | 高 | 有限制 | 高 | 云端部署 |
| Kubernetes | 高 | 灵活 | 高 | 企业级 |

**推荐配置**：开发环境使用subprocess，生产环境使用Docker。

---

## 6. 数据库Schema

### 6.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                           papers                                     │
│  (论文信息)                                                           │
├─────────────────────────────────────────────────────────────────────┤
│ papers ──────────< experiments                                       │
│ (论文索引)            (实验记录)                                      │
├─────────────────────────────────────────────────────────────────────┤
│ papers ──────────< alpha_factors                                     │
│                     (Alpha因子)                                      │
├─────────────────────────────────────────────────────────────────────┤
│ experiments ─────< experiment_runs                                   │
│ (实验)               (每次运行记录)                                   │
├─────────────────────────────────────────────────────────────────────┤
│ experiment_runs >──── reports                                        │
│                      (生成的论文报告)                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 表结构

#### papers（论文表）

```sql
CREATE TABLE papers (
    paper_id TEXT PRIMARY KEY,
    source VARCHAR(20) NOT NULL,           -- 'arxiv', 'semantic_scholar', 'manual'
    external_id VARCHAR(100),              -- arXiv ID, DOI, etc.
    title TEXT NOT NULL,
    authors TEXT,                          -- JSON array
    abstract TEXT,
    year INTEGER,
    categories TEXT,                      -- JSON array
    keywords TEXT,                         -- JSON array
    pdf_url TEXT,
    pdf_path TEXT,
    status VARCHAR(20) DEFAULT 'pending', -- pending, downloaded, analyzed, cited
    reading_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (status) REFERENCES paper_status(status)
);

CREATE INDEX idx_papers_source ON papers(source);
CREATE INDEX idx_papers_year ON papers(year);
CREATE INDEX idx_papers_status ON papers(status);
```

#### alpha_factors（Alpha因子表）

```sql
CREATE TABLE alpha_factors (
    factor_id TEXT PRIMARY KEY,
    source_paper_id TEXT,
    factor_name TEXT NOT NULL,
    description TEXT,
    trading_logic TEXT NOT NULL,
    parameters TEXT,                       -- JSON object
    expected_direction VARCHAR(20),         -- 'long_only', 'short_only', 'long_short'
    risk_factors TEXT,                     -- JSON array
    market_universe VARCHAR(50),           -- 'A-share', 'US', 'crypto', 'general'
    time_horizon VARCHAR(20),              -- 'intraday', 'daily', 'weekly'
    related_factors TEXT,                  -- JSON array of related factor_ids
    status VARCHAR(20) DEFAULT 'generated', -- generated, validated, published
    validation_results TEXT,               -- JSON object
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (source_paper_id) REFERENCES papers(paper_id)
);

CREATE INDEX idx_factors_status ON alpha_factors(status);
CREATE INDEX idx_factors_universe ON alpha_factors(market_universe);
```

#### experiments（实验表）

```sql
CREATE TABLE experiments (
    experiment_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    experiment_name TEXT NOT NULL,
    description TEXT,
    plan TEXT NOT NULL,                    -- JSON object
    status VARCHAR(20) DEFAULT 'planned',  -- planned, running, completed, failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (hypothesis_id) REFERENCES alpha_factors(factor_id)
);

CREATE INDEX idx_experiments_status ON experiments(status);
CREATE INDEX idx_experiments_hypothesis ON experiments(hypothesis_id);
```

#### experiment_runs（实验运行记录表）

```sql
CREATE TABLE experiment_runs (
    run_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    run_number INTEGER NOT NULL,
    parameters TEXT,                        -- JSON object (actual params used)
    generated_code TEXT,
    execution_log TEXT,
    result TEXT,                           -- JSON object with metrics
    judgment TEXT,                         -- JSON object
    status VARCHAR(20) DEFAULT 'pending',   -- pending, running, success, failed, healed
    healing_attempts INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,

    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
);

CREATE INDEX idx_runs_experiment ON experiment_runs(experiment_id);
CREATE INDEX idx_runs_status ON experiment_runs(status);
```

#### reports（研究报告表）

```sql
CREATE TABLE reports (
    report_id TEXT PRIMARY KEY,
    run_id TEXT,
    report_type VARCHAR(20) DEFAULT 'paper',  -- 'paper', 'summary', 'interim'
    title TEXT,
    abstract TEXT,
    content TEXT,                          -- Full LaTeX or Markdown content
    figures TEXT,                          -- JSON array of figure paths
    tables TEXT,                           -- JSON array of table paths
    references TEXT,                       -- BibTeX format
    status VARCHAR(20) DEFAULT 'draft',    -- draft, review, final, published
    feedback TEXT,                         -- JSON array of feedback
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (run_id) REFERENCES experiment_runs(run_id)
);

CREATE INDEX idx_reports_status ON reports(status);
CREATE INDEX idx_reports_type ON reports(report_type);
```

### 6.3 辅助表

```sql
-- 论文状态枚举
CREATE TABLE paper_status (
    status VARCHAR(20) PRIMARY KEY,
    description TEXT
);

INSERT INTO paper_status VALUES
    ('pending', '待处理'),
    ('downloaded', '已下载'),
    ('analyzed', '已分析'),
    ('cited', '已引用');

-- 系统配置表
CREATE TABLE system_config (
    key TEXT PRIMARY KEY,
    value TEXT,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 运行日志表
CREATE TABLE operation_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name VARCHAR(50),
    operation VARCHAR(100),
    input_data TEXT,
    output_data TEXT,
    status VARCHAR(20),
    error_message TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_logs_agent ON operation_logs(agent_name);
CREATE INDEX idx_logs_created ON operation_logs(created_at);
```

---

## 7. API设计

### 7.1 核心类API

#### FARSOrchestrator

```python
class FARSOrchestrator:
    """FARS系统主协调器"""

    def __init__(
        self,
        project_id: str,
        llm_provider: str = "openai",
        llm_model: str = "gpt-4o",
        workspace_path: str = None
    ):
        """初始化协调器"""
        pass

    def run_full_pipeline(
        self,
        query: str,
        max_papers: int = 5,
        target_universe: str = "A-share"
    ) -> dict:
        """
        运行完整研究流程

        Args:
            query: 搜索论文的关键词
            max_papers: 最大论文数量
            target_universe: 目标市场

        Returns:
            dict: 包含所有生成内容的字典
        """
        pass

    def run_single_hypothesis(
        self,
        hypothesis_id: str
    ) -> dict:
        """
        运行单个假设的完整流程

        Args:
            hypothesis_id: 假设ID

        Returns:
            dict: 实验结果和报告
        """
        pass

    def get_experiment_status(
        self,
        experiment_id: str
    ) -> dict:
        """获取实验状态"""
        pass

    def list_experiments(
        self,
        status: str = None
    ) -> list:
        """列出所有实验"""
        pass

    def generate_report(
        self,
        experiment_id: str,
        report_type: str = "paper"
    ) -> str:
        """生成报告"""
        pass
```

#### IdeationAgent

```python
class IdeationAgent:
    """灵感生成Agent"""

    def __init__(self, llm_caller: LLMCaller):
        self.llm = llm_caller
        self.paper_fetcher = PaperFetcher()

    def search_papers(
        self,
        query: str,
        max_results: int = 10,
        sources: list = ["arxiv"]
    ) -> list:
        """
        搜索论文

        Returns:
            list: Paper对象列表
        """
        pass

    def analyze_paper(self, paper: Paper) -> dict:
        """深度分析论文"""
        pass

    def generate_ideas(self, paper: Paper) -> list:
        """
        从论文生成假设

        Returns:
            list: Hypothesis对象列表
        """
        pass

    def save_to_database(self, hypothesis: Hypothesis) -> str:
        """保存到数据库，返回hypothesis_id"""
        pass
```

#### PlanningAgent

```python
class PlanningAgent:
    """实验计划Agent"""

    def __init__(self, llm_caller: LLMCaller):
        self.llm = llm_caller

    def create_plan(
        self,
        hypothesis: Hypothesis,
        backtest_period: tuple = ("2018-01-01", "2025-12-31")
    ) -> ExperimentPlan:
        """创建实验计划"""
        pass

    def design_control_experiments(
        self,
        baseline_strategy: str
    ) -> list:
        """设计对照组实验"""
        pass

    def save_to_database(self, plan: ExperimentPlan) -> str:
        """保存到数据库"""
        pass
```

#### ExperimentAgent

```python
class ExperimentAgent:
    """实验执行Agent"""

    def __init__(
        self,
        llm_caller: LLMCaller,
        backtest_engine: BacktestEngine,
        code_executor: CodeExecutor
    ):
        pass

    def generate_code(self, plan: ExperimentPlan) -> str:
        """生成回测代码"""
        pass

    def execute_code(
        self,
        code: str,
        context: dict = None
    ) -> ExecutionResult:
        """执行代码（沙箱环境）"""
        pass

    def execute_with_self_healing(
        self,
        code: str,
        context: dict = None
    ) -> dict:
        """带自我修复的代码执行"""
        pass

    def evaluate_results(
        self,
        result: ExecutionResult,
        criteria: dict
    ) -> Evaluation:
        """评估回测结果"""
        pass

    def save_to_database(self, run: ExperimentRun) -> str:
        """保存运行记录"""
        pass
```

#### WritingAgent

```python
class WritingAgent:
    """论文撰写Agent"""

    def __init__(self, llm_caller: LLMCaller):
        self.llm = llm_caller
        self.figure_generator = FigureGenerator()

    def write_paper(
        self,
        experiment_result: dict,
        original_idea: Hypothesis,
        original_paper: Paper
    ) -> dict:
        """
        撰写完整论文

        Returns:
            dict: {
                'paper_id': str,
                'title': str,
                'tex_content': str,
                'figures': list,
                'references': str
            }
        """
        pass

    def generate_figures(self, result: dict) -> list:
        """生成图表"""
        pass

    def save_to_database(self, report: Report) -> str:
        """保存报告"""
        pass
```

### 7.2 工具类API

```python
class LLMCaller:
    """LLM调用封装"""

    def __init__(
        self,
        provider: str = "openai",  # openai, anthropic, deepseek
        model: str = "gpt-4o",
        api_key: str = None,
        base_url: str = None
    ):
        pass

    def call(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Optional[str]:
        """调用LLM"""
        pass

class PaperFetcher:
    """论文获取器"""

    def fetch_arxiv(self, paper_id: str) -> Paper:
        """获取arXiv论文"""
        pass

    def search_arxiv(self, query: str, max_results: int = 10) -> list:
        """搜索arXiv"""
        pass

    def search_semantic_scholar(self, query: str, max_results: int = 10) -> list:
        """搜索Semantic Scholar"""
        pass

class MarketDataFetcher:
    """市场数据获取器"""

    def fetch_yfinance(
        self,
        symbols: list,
        start: str,
        end: str,
        interval: str = "1d"
    ) -> pd.DataFrame:
        """获取yfinance数据（美股）"""
        pass

    def fetch_akshare(
        self,
        symbols: list,
        start: str,
        end: str,
        adjust: str = "qfq"
    ) -> pd.DataFrame:
        """获取AkShare数据（A股）"""
        pass

class BacktestEngine:
    """回测引擎"""

    def __init__(
        self,
        initial_cash: float = 1000000,
        commission: float = 0.001,
        slippage: float = 0.0005
    ):
        pass

    def setup(
        self,
        strategy_class: type,
        **strategy_params
    ) -> "BacktestEngine":
        """设置策略"""
        pass

    def add_data_from_df(
        self,
        df: pd.DataFrame,
        name: str = "data"
    ) -> "BacktestEngine":
        """添加数据"""
        pass

    def run(self) -> BacktestResult:
        """运行回测"""
        pass

class CodeExecutor:
    """代码执行器（沙箱）"""

    def __init__(
        self,
        timeout: int = 300,
        memory_limit: str = "512m"
    ):
        pass

    def execute(
        self,
        code: str,
        context: dict = None
    ) -> ExecutionResult:
        """执行代码"""
        pass

    def validate_safety(self, code: str) -> bool:
        """验证代码安全性"""
        pass
```

---

## 8. 安全考虑

### 8.1 代码执行安全

```python
# 禁止的模式
FORBIDDEN_PATTERNS = [
    "import os",
    "import sys",
    "import subprocess",
    "import socket",
    "import requests",
    "open(",
    "eval(",
    "exec(",
    "__import__",
    "ctypes",
    "os.system",
    "os.popen",
]

class SecurityValidator:
    """安全验证器"""

    def validate_code(self, code: str) -> tuple[bool, str]:
        """
        验证代码安全性

        Returns:
            (is_safe, error_message)
        """
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in code:
                return False, f"禁止的模式: {pattern}"

        # 检查是否有网络访问
        if "http" in code or "url" in code.lower():
            # 允许特定的数据获取库
            allowed_data_libs = ["yfinance", "akshare", "pandas_datareader"]
            if not any(lib in code for lib in allowed_data_libs):
                return False, "不允许的网络访问"

        return True, ""

    def sanitize_imports(self, code: str) -> str:
        """清理不安全的导入"""
        pass
```

### 8.2 API Key管理

```python
# 使用环境变量存储敏感信息
import os

class APIKeyManager:
    """API密钥管理器"""

    REQUIRED_KEYS = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY"
    }

    def __init__(self):
        self._keys = {}
        for provider, env_var in self.REQUIRED_KEYS.items():
            self._keys[provider] = os.getenv(env_var)

    def get_key(self, provider: str) -> Optional[str]:
        return self._keys.get(provider)

    def validate_keys(self) -> dict:
        """验证必需的API Key"""
        missing = []
        for provider, env_var in self.REQUIRED_KEYS.items():
            if not self._keys.get(provider):
                missing.append(env_var)
        return {"valid": len(missing) == 0, "missing": missing}
```

---

## 9. 部署架构

### 9.1 开发环境

```
本地机器
├── FARS System (Python包)
├── SQLite (本地数据库)
├── Workspace (本地文件系统)
└── IDE (可选)
```

### 9.2 生产环境

```
┌─────────────────────────────────────────────────────────────────────┐
│                           用户端                                     │
│  CLI / Web UI / API Client                                         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                         API Server                                   │
│  FastAPI + Uvicorn                                                   │
│  - /api/v1/papers/*                                                 │
│  - /api/v1/experiments/*                                            │
│  - /api/v1/reports/*                                                │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        Worker Nodes                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │ Worker 1    │  │ Worker 2    │  │ Worker N    │                  │
│  │ (Ideation)  │  │ (Planning)  │  │ (Experiment)│                  │
│  │ Container   │  │ Container   │  │ Container   │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        数据存储                                      │
│  ┌─────────────┐  ┌─────────────────────────────────────────────┐   │
│  │ PostgreSQL  │  │              S3/MinIO                      │   │
│  │ (元数据)    │  │  (论文PDF、报告、图表、日志)                  │   │
│  └─────────────┘  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.3 容器化部署

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fars_system/ ./fars_system/

# 安全设置
RUN useradd -m fars
USER fars

CMD ["python", "-m", "fars_system.src.main"]
```

---

## 10. 未来扩展

### 10.1 计划中的功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 多LLM支持 | P0 | 支持Gemini、本地模型等 |
| 分布式回测 | P1 | 支持多市场并行回测 |
| 实时数据 | P1 | 支持实时行情接入 |
| 因子动物园 | P2 | 预置100+经典因子 |
| AutoML | P2 | 自动超参优化 |
| 模拟交易 | P2 | 连接券商API实盘模拟 |
| 因子相关性分析 | P2 | 多因子组合优化 |

### 10.2 可能的改进方向

1. **多Agent协作优化**：引入更智能的Agent协调机制
2. **主动学习**：根据实验结果主动搜索新论文
3. **知识图谱**：构建量化领域的知识图谱
4. **可解释性增强**：提高策略的可解释性
5. **多模态输入**：支持图表、PDF直接输入

---

## 附录

### A. 术语表

| 术语 | 英文 | 说明 |
|------|------|------|
| Alpha因子 | Alpha Factor | 用于预测资产收益的指标 |
| 信息系数 | IC (Information Coefficient) | 因子预测能力度量 |
| 夏普比率 | Sharpe Ratio | 风险调整收益指标 |
| 最大回撤 | Max Drawdown | 策略历史最大亏损 |
| 回测 | Backtest | 用历史数据验证策略 |
| 沙箱 | Sandbox | 隔离的安全执行环境 |
| 假设 | Hypothesis | 待验证的交易逻辑 |

### B. 参考资料

1. FARS原始论文 - Analemma
2. arXiv:2409.06289 - Automate Strategy Finding with LLM
3. Backtrader官方文档
4. AkShare文档
5. OpenAI API文档

---

*本文档由FARS系统自动生成 | 最后更新: 2026-06-20*