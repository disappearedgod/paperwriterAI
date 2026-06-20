"""
FARS - Prompt模板
为四个Agent设计的Prompt模板
"""

# ============== 通用系统提示 ==============

SCIENTIFIC_AGENT_SYSTEM_PROMPT = """你是一个专业的量化研究助手，专注于金融量化交易和因子挖掘领域。你的任务是：
1. 从学术论文中提取可编程的交易逻辑和因子表达式
2. 生成结构化的数学公式和Python代码
3. 评估和优化量化策略

重要约束：
- 所有生成的代码必须是安全且可执行的
- 因子表达式必须有明确的金融逻辑支撑
- 数学公式必须使用标准的数学符号或LaTeX格式

数据库Schema参考：
- papers: {paper_id, title, authors, year, arxiv_id, abstract, methodology, status}
- alpha_factors: {factor_id, name, category, formula_latex, code_expression, status}
- experiments: {exp_id, hypothesis, code_path, result_metrics, status}

请始终输出结构化的JSON格式结果。"""


# ============== Ideation Agent提示 ==============

IDEA_GENERATION_PROMPT = """## 任务：从论文中生成交易假设

你是一个量化研究助手，需要从以下论文中提取和生成交易假设。

### 论文信息
标题：{title}
作者：{authors}
年份：{year}
摘要：{abstract}

### 方法论（如果有）
{methodology}

### 核心贡献（如果有）
{key_contributions}

### 任务要求

1. **仔细阅读论文**，理解其核心发现和方法论
2. **提取可量化的交易逻辑**，将其转化为数学公式
3. **生成多个候选假设**，每个假设包含：
   - 假设ID（如 idea_001）
   - 假设描述（中文）
   - 数学公式（LaTeX格式）
   - Python代码片段
   - 预期效果（收益/风险/IC等）

4. **确保假设的创新性**，不是简单的已知因子组合

### 输出格式

请输出以下JSON格式的结果：

```json
{{
  "paper_id": "{paper_id}",
  "ideas": [
    {{
      "idea_id": "idea_001",
      "title": "假设标题",
      "description": "详细的假设描述，解释金融逻辑",
      "formula_latex": "数学公式，用LaTeX格式",
      "python_code": "Python代码片段（示意性，不需要完整可运行）",
      "expected_metrics": {{
        "target_ic": 0.03,
        "target_sharpe": 1.5,
        "category": "Momentum"
      }},
      "novelty": "解释这个假设相对于现有方法的创新点",
      "risk_notes": "潜在风险和限制"
    }}
  ],
  "literature_review": "与现有文献的关系和对比",
  "research_gaps": "论文未解决但值得探索的问题"
}}
```

请确保输出的JSON是有效的，可以被json.loads()解析。"""


PAPER_ANALYSIS_PROMPT = """## 任务：深度分析量化论文

你是一个专业的量化研究助手，需要对以下论文进行深度分析：

### 论文标题
{title}

### 论文摘要
{abstract}

### 任务要求

请完成以下分析任务：

1. **方法论提取**
   - 识别论文使用的核心方法（机器学习/统计/深度学习等）
   - 提取关键的算法步骤
   - 理解数据处理流程

2. **关键发现**
   - 列出3-5个核心发现
   - 每个发现必须有数据支撑

3. **因子分析**（如果是因子相关论文）
   - 提取所有可编程的因子表达式
   - 用LaTeX格式表示每个因子
   - 评估每个因子的可复现性

4. **研究局限**
   - 识别论文的假设和限制条件
   - 分析可能失败的市场环境

5. **创新点**
   - 与传统方法相比的核心创新
   - 可能的改进方向

### 输出格式

```json
{{
  "paper_id": "{paper_id}",
  "analysis": {{
    "methodology": {{
      "type": "方法类型",
      "steps": ["步骤1", "步骤2"],
      "data_requirements": ["数据需求1"],
      "model_architecture": "模型架构描述（如果适用）"
    }},
    "key_findings": [
      {{
        "finding": "发现描述",
        "evidence": "支撑证据",
        "significance": "重要性"
      }}
    ],
    "extractable_factors": [
      {{
        "name": "因子名称",
        "formula_latex": "LaTeX公式",
        "implementation_hint": "实现提示",
        "estimated_ic": "估计IC值"
      }}
    ],
    "limitations": ["限制1", "限制2"],
    "improvement_opportunities": ["改进机会1", "改进机会2"]
  }}
}}
```"""


# ============== Planning Agent提示 ==============

EXPERIMENT_PLANNING_PROMPT = """## 任务：制定实验计划

基于以下研究假设，制定详细的实验计划：

### 研究假设
{idea_summary}

### 假设详情
```json
{idea_details}
```

### 可用数据源
- yfinance: 美股数据
- akshare: A股数据
- MongoDB: 本地历史数据（collection: daily_bars）
- 股票池: CSI300, SSE50, SP500

### 任务要求

1. **定义实验目标**
   - 明确要验证的假设
   - 设定成功标准（IC、Sharpe、Max Drawdown阈值）

2. **设计实验方案**
   - 数据选择（标的、时间范围、频率）
   - 对比基准
   - 实验组设置

3. **规划实验步骤**
   - 步骤1: 数据准备
   - 步骤2: 因子计算
   - 步骤3: 回测验证
   - 步骤4: 结果评估

4. **风险控制**
   - 识别可能的失败模式
   - 制定备选方案

### 输出格式

```json
{{
  "experiment_id": "exp_001",
  "hypothesis": "假设描述",
  "objectives": ["目标1", "目标2"],
  "data_config": {{
    "symbols": ["股票列表"],
    "start_date": "开始日期",
    "end_date": "结束日期",
    "frequency": "数据频率"
  }},
  "backtest_config": {{
    "framework": "backtrader",
    "initial_cash": 1000000,
    "commission": 0.001,
    "rebalance_frequency": "月"
  }},
  "evaluation_metrics": {{
    "min_sharpe_ratio": 1.5,
    "max_drawdown_threshold": -0.25,
    "min_ic": 0.02
  }},
  "steps": [
    {{
      "step_id": 1,
      "description": "步骤描述",
      "code_template": "代码模板",
      "expected_output": "预期输出"
    }}
  ],
  "alternative_strategies": ["备选策略1"],
  "risk_mitigation": "风险缓解措施"
}}
```"""


# ============== Experiment Agent提示 ==============

CODE_GENERATION_PROMPT = """## 任务：生成回测代码

根据以下实验计划，生成完整的可执行Python回测代码：

### 实验计划
{experiment_plan}

### 可用的工具和库
- backtrader: 回测框架
- pandas, numpy: 数据处理
- yfinance: 获取美股数据
- akshare: 获取A股数据
- pymongo: 连接MongoDB

### 重要约束

1. **代码安全性**
   - 不要包含任何会删除文件或破坏系统的操作
   - 数据读取必须在沙箱环境中进行
   - 所有外部API调用必须有超时和错误处理

2. **代码完整性**
   - 包含完整的import语句
   - 包含数据获取、因子计算、回测执行、结果输出的全流程
   - 包含必要的注释

3. **输出规范**
   - 将回测结果保存为JSON格式
   - 生成权益曲线图表（matplotlib）
   - 所有图表保存到charts/目录

4. **错误处理**
   - 包含try-except错误处理
   - 打印详细的执行日志
   - 错误时输出有意义的错误信息

### 输出格式

请输出完整的Python代码，确保：
1. 代码可以直接在Python 3.8+环境中运行
2. 包含所有必要的依赖
3. 输出结果包含所有评估指标

```python
# 你的代码
import ...
# ... 完整代码 ...
```

### 预期输出结构

```json
{{
  "experiment_id": "实验ID",
  "execution_time": "执行时间",
  "result_metrics": {{
    "total_return": 0.15,
    "sharpe_ratio": 1.8,
    "max_drawdown": -0.12,
    "annual_return": 0.18,
    "total_trades": 50
  }},
  "charts": ["charts/equity_curve.png", "charts/drawdown.png"],
  "status": "completed",
  "logs": "执行日志"
}}
```"""


DEBUG_ASSISTANCE_PROMPT = """## 任务：Debug和修复代码错误

以下代码执行时出错，请分析错误并提供修复方案：

### 错误信息
```
{error_traceback}
```

### 原始代码
```python
{original_code}
```

### 上下文
- 实验ID: {experiment_id}
- 假设描述: {hypothesis}

### 任务要求

1. **分析错误**
   - 识别错误类型和根本原因
   - 判断是语法错误、运行时错误还是逻辑错误

2. **提供修复**
   - 给出修复后的完整代码
   - 解释修复方案

3. **预防建议**
   - 提供避免类似错误的建议

### 输出格式

```json
{{
  "error_analysis": {{
    "type": "错误类型",
    "root_cause": "根本原因",
    "line_number": "出错行号（如果能定位）"
  }},
  "fixed_code": "修复后的完整代码",
  "fix_explanation": "修复解释",
  "prevention_tips": ["预防建议1", "预防建议2"]
}}
```"""


# ============== Writing Agent提示 ==============

PAPER_WRITING_PROMPT = """## 任务：撰写研究论文

基于以下实验结果，撰写一篇可发表的学术论文。

### 实验信息
- 实验ID: {experiment_id}
- 研究假设: {hypothesis}

### 实验结果
{experiment_results}

### 原始论文（参考）: {original_title} by {original_authors} ({original_year})

### 输出要求

请生成完整的LaTeX论文源码，包含以下部分：
1. Title（标题）
2. Abstract（摘要，150-200词）
3. Introduction（引言，1-2页）
4. Methodology（方法论，含数学公式）
5. Empirical Results（实证结果）
6. Conclusion（结论）
7. References（参考文献，5-10篇）

**重要**：即使实验数据不完美（如收益偏低、Sharpe不高），也必须保留并照实报告，这是学术诚信要求。

输出格式（必须是有效JSON）:
{{
  "paper_title": "论文标题",
  "tex_content": "完整LaTeX源码（标准ICML格式，使用\\documentclass[preprint,authoryear,12pt]{{elsarticle}}）",
  "references": ["参考文献列表"],
  "charts_needed": ["图表列表"]
}}"""


# ============== 评估提示 ==============

STRATEGY_EVALUATION_PROMPT = """## 任务：评估策略性能

基于以下回测结果，评估策略的质量和可发表性：

### 回测结果
```json
{backtest_results}
```

### 实验配置
- 数据范围: {data_range}
- 再平衡频率: {rebalance_frequency}
- 基准对比: {benchmark}

### 评估维度

1. **收益能力**
   - 总收益率
   - 年化收益率
   - 相对基准的超额收益

2. **风险控制**
   - 最大回撤
   - 波动率
   - 卡玛比率

3. **风险调整收益**
   - 夏普比率
   - 索提诺比率
   - 信息比率

4. **策略稳定性**
   - 胜率
   - 盈利因子
   - 交易次数

5. **可发表性判断**
   - 是否达到发表标准
   - 需要改进的地方

### 输出格式

```json
{{
  "evaluation_summary": {{
    "overall_score": 7.5,
    "recommendation": "值得发表/需要改进/不推荐发表",
    "strengths": ["优势1", "优势2"],
    "weaknesses": ["劣势1", "劣势2"]
  }},
  "detailed_metrics": {{
    "profitability": {{
      "score": 8,
      "details": "..."
    }},
    "risk_control": {{
      "score": 7,
      "details": "..."
    }},
    "risk_adjusted_return": {{
      "score": 7.5,
      "details": "..."
    }},
    "stability": {{
      "score": 7,
      "details": "..."
    }}
  }},
  "publication_readiness": {{
    "ready": false,
    "improvements_needed": ["需要的改进1"],
    "target_venues": ["目标期刊/会议"]
  }}
}}
```"""


# ============== Literature Review (STORM-style) ==============

PERSPECTIVE_GENERATION_PROMPT = """## 任务: 生成研究视角

针对主题: {topic}

请从多个学术视角分析该主题，每个视角需包含:
1. 视角名称
2. 核心研究问题 (2-3个)
3. 相关方法论
4. 潜在贡献

### 视角类型

1. **方法论视角**: 该主题涉及的方法/算法
2. **应用视角**: 实际应用场景和效果
3. **评估视角**: 如何评估/验证
4. **比较视角**: 与现有方法对比
5. **局限性视角**: 已知问题和改进空间

### 输出格式

请输出JSON格式结果，包含3-5个视角。"""


QUESTION_ASKING_PROMPT = """## 任务: 生成深度研究问题

主题: {topic}
视角: {perspective}

请为上述视角生成5-8个深度研究问题。问题应该:
1. 探索该视角下的关键争议
2. 寻求具体的证据和数据
3. 引导发现主题的深层联系

### 问题类型

- **背景问题**: 关于主题基本事实
- **比较问题**: 与其他方法/观点的异同
- **因果问题**: 原因和结果的关系
- **评估问题**: 优缺点和适用性

### 输出格式

请输出JSON格式的问题列表。"""


LITERATURE_REVIEW_PROMPT = """## 任务: 撰写文献综述章节

主题: {topic}

### 收集到的证据/调研内容

```json
{evidence}
```

### 任务要求

1. **结构化综述**: 按照主题流派/方法论分类组织
2. **批判性分析**: 总结各流派的优势和局限
3. **研究空白**: 明确当前研究的不足
4. **引用标注**: 使用 [1], [2], [3] 格式标注

### 章节结构

1. 概述该领域的发展历程
2. 分类讨论主要流派/方法
3. 分析各方法的优缺点
4. 指出研究空白和争议点
5. 引出本文的创新点

请直接输出LaTeX格式的文献综述章节源码。"""


INTRODUCTION_WITH_LIT_REVIEW_PROMPT = """## 任务: 撰写引言与文献综述

主题: {topic}

### 研究背景
{background}

### 相关工作综述
```json
{related_work}
```

### 任务要求

请撰写完整的引言章节，包含:
1. **研究背景**: 问题的提出和重要性
2. **文献综述**: 总结相关工作及其局限性
3. **研究动机**: 为什么需要这项研究
4. **本文贡献**: 列出主要创新点

### 格式要求

- LaTeX格式
- 包含适当的引用标注
- 引言长度: 500-800词
- 使用 \\section{{Introduction}} 结构

请直接输出LaTeX源码。"""


# ============== Review & Revision (GPT Researcher-style) ==============

PAPER_REVIEW_PROMPT = """## 任务: 评审论文质量

请评审以下论文章节:

### 论文标题
{title}

### 待评审内容
{content}

### 评审维度

1. **学术严谨性** (1-10): 方法论是否合理，论证是否有逻辑
2. **创新性** (1-10): 是否有新贡献，与现有工作如何区分
3. **完整性** (1-10): 章节是否完整，是否有遗漏重要方面
4. **可读性** (1-10): 表达是否清晰，结构是否合理
5. **引用质量** (1-10): 引用是否相关，是否有必要背景引用

### 输出格式

请输出JSON格式:
```json
{{
  "overall_score": 7.5,
  "dimension_scores": {{
    "rigor": 7,
    "novelty": 8,
    "completeness": 7,
    "readability": 8,
    "citation_quality": 7
  }},
  "strengths": ["优势1", "优势2"],
  "weaknesses": ["弱点1", "弱点2"],
  "revision_suggestions": [
    {{
      "location": "具体位置",
      "issue": "问题描述",
      "suggestion": "修改建议"
    }}
  ]
}}
```"""


PAPER_REVISION_PROMPT = """## 任务: 修订论文

### 原文
{original_content}

### 评审意见
{review_comments}

### 任务要求

根据评审意见修订论文内容，确保:
1. 解决所有提出的问题
2. 保持论文整体一致性
3. 不引入新的问题

请直接输出修订后的完整内容 (LaTeX 格式)。"""


# ============== Full Paper Generation ==============

FULL_PAPER_GENERATION_PROMPT = """## 任务: 生成完整学术论文

主题: {topic}

### 模板格式
{template}

### 文献综述摘要
{literature_review_summary}

### 研究假设/创新点
{novelty_points}

### 实验结果 (如有)
```json
{experiment_results}
```

### 输出要求

请生成完整的学术论文LaTeX源码，包含以下部分:
1. Title (标题)
2. Abstract (摘要，150-200词)
3. Introduction (引言，500-800词，包含文献综述)
4. Methodology (方法论，含数学公式)
5. Empirical Results (实证结果，包含图表)
6. Discussion (讨论)
7. Conclusion (结论)
8. References (参考文献)

**重要**: 即使实验数据不完美，也必须保留并如实报告。

请直接输出完整的LaTeX源码。"""


# ============== Prompt模板辅助函数 ==============

def fill_idea_prompt(paper_info: dict) -> str:
    """填充论文分析提示模板"""
    return IDEA_GENERATION_PROMPT.format(
        paper_id=paper_info.get('paper_id', ''),
        title=paper_info.get('title', ''),
        authors=', '.join(paper_info.get('authors', [])),
        year=paper_info.get('year', ''),
        abstract=paper_info.get('abstract', ''),
        methodology=paper_info.get('methodology', 'N/A'),
        key_contributions='\n'.join([f"- {c}" for c in paper_info.get('key_contributions', [])])
    )


def fill_code_gen_prompt(experiment_plan: dict) -> str:
    """填充代码生成提示模板"""
    return CODE_GENERATION_PROMPT.format(
        experiment_plan=json.dumps(experiment_plan, ensure_ascii=False, indent=2)
    )


def fill_debug_prompt(error_traceback: str, original_code: str,
                      experiment_id: str, hypothesis: str) -> str:
    """填充Debug提示模板"""
    return DEBUG_ASSISTANCE_PROMPT.format(
        error_traceback=error_traceback,
        original_code=original_code,
        experiment_id=experiment_id,
        hypothesis=hypothesis
    )


# ============== Literature Review 辅助函数 ==============

def fill_perspective_prompt(topic: str) -> str:
    """填充视角生成提示"""
    return PERSPECTIVE_GENERATION_PROMPT.format(topic=topic)


def fill_question_prompt(topic: str, perspective: str) -> str:
    """填充问题生成提示"""
    return QUESTION_ASKING_PROMPT.format(topic=topic, perspective=perspective)


def fill_literature_review_prompt(topic: str, evidence: str) -> str:
    """填充文献综述生成提示"""
    return LITERATURE_REVIEW_PROMPT.format(topic=topic, evidence=evidence)


def fill_introduction_prompt(topic: str, background: str, related_work: str) -> str:
    """填充带文献综述的引言生成提示"""
    return INTRODUCTION_WITH_LIT_REVIEW_PROMPT.format(
        topic=topic,
        background=background,
        related_work=related_work
    )


def fill_review_prompt(title: str, content: str) -> str:
    """填充论文评审提示"""
    return PAPER_REVIEW_PROMPT.format(title=title, content=content)


def fill_revision_prompt(original_content: str, review_comments: str) -> str:
    """填充论文修订提示"""
    return PAPER_REVISION_PROMPT.format(
        original_content=original_content,
        review_comments=review_comments
    )


def fill_full_paper_prompt(topic: str, template: str, literature_review_summary: str,
                           novelty_points: str, experiment_results: str = "{}") -> str:
    """填充完整论文生成提示"""
    return FULL_PAPER_GENERATION_PROMPT.format(
        topic=topic,
        template=template,
        literature_review_summary=literature_review_summary,
        novelty_points=novelty_points,
        experiment_results=experiment_results
    )