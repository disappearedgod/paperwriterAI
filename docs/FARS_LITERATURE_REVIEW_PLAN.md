# FARS 论文生成系统改进计划 v3.0
## 集成 STORM 与 GPT Researcher 的文献综述能力

> 版本: 3.0 | 日期: 2026-06-20 | 状态: 规划中

---

## 1. 背景与目标

### 1.1 当前系统局限

现有 `generate_paper_content` 函数存在以下问题：

1. **缺乏文献综述能力**: 直接生成论文，无深度调研过程
2. **无多角度视角**: 无法从不同学术角度分析主题
3. **无迭代优化**: 生成一次完成，无 Review-Revision 循环
4. **输出格式简单**: 仅生成 Markdown，无完整 LaTeX/PDF

### 1.2 参考系统分析

#### STORM (Stanford)

**核心机制**: Perspective-guided Question Asking

```
Phase 1: Pre-writing (调研阶段)
├── 1.1 Topic Unpacking (主题拆解)
│   └── 将主题分解为多个学术视角
├── 1.2 Perspective-guided Question Asking (视角引导提问)
│   ├── 对每个视角生成 N 个深度问题
│   └── 模拟 M 轮对话探索问题
├── 1.3 Information Gathering (信息收集)
│   └── 从可信来源收集证据
└── 1.4 Outline Generation (大纲生成)
    └── 基于调研生成结构化大纲

Phase 2: Writing (写作阶段)
├── 2.1 Section-by-section Generation
│   └── 基于大纲逐节生成
└── 2.2 Citation Integration (引用整合)
    └── 自动生成 in-text citations

效果: 84.83% citation recall (传统方法仅 20-30%)
```

#### GPT Researcher (Tavily)

**核心机制**: Parallel Chapter Research + Review-Revision Loop

```
Stage 1: Planning (规划)
├── 分析用户查询
└── 生成详细的研究大纲

Stage 2: Initial Research (初步调研)
├── 并行执行初步搜索
└── 汇总关键发现

Stage 3: Deep Research (深度调研)
├── 并行章节研究 (ChiefEditor 协调)
│   ├── Researcher: 负责信息收集
│   ├── Editor: 负责内容编辑
│   └── Reviewer: 负责质量审查
├── Review-Revision 循环
│   ├── Reviewer 提出修改意见
│   └── Reviser 修订内容
└── 重复直到达标

Stage 4: Writing (写作)
└── 基于深度调研撰写报告

Stage 5: Publishing (发布)
└── 格式化为最终文档

8 个专业 Agent: ChiefEditor, Researcher, Editor, Reviewer, Reviser, Writer, Publisher, Human
```

### 1.3 改进目标

1. **引入文献综述引擎**: 模拟 STORM 的多视角调研机制
2. **多轮 Review-Revision**: 借鉴 GPT Researcher 的质量控制循环
3. **增强 Introduction 质量**: 生成真正有深度的文献综述
4. **支持完整 LaTeX**: 输出可编译的学术论文格式

---

## 2. 系统架构改进

### 2.1 新增模块

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Literature Review Engine (新增)                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │
│  │ PerspectiveGen  │───▶│ QuestionAsker  │───▶│ EvidenceCollector│  │
│  │ (STORM视角生成)  │    │ (STORM提问)     │    │ (证据收集)        │  │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘  │
│                                                                      │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │
│  │ ReviewReviser   │◀───▶│ Reviewer        │    │ OutlineGenerator │  │
│  │ (GPT-Reviser)   │    │ (GPT-Reviewer)  │    │ (大纲生成)        │  │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 论文生成流程改进

**Before (当前流程)**:
```
User Topic → Generate (一次性) → Markdown Paper
```

**After (新流程)**:
```
User Topic
    ↓
┌─────────────────────────────────────┐
│  Phase 1: Literature Review          │
│  ├── Perspective Generation (STORM)  │
│  ├── Question Asking (STORM)         │
│  ├── Evidence Collection (并行)       │
│  └── Outline Generation              │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Phase 2: Section Generation         │
│  ├── Abstract (生成)                 │
│  ├── Introduction + Literature Review │
│  ├── Methodology                     │
│  ├── Experiments                     │
│  ├── Results                         │
│  ├── Discussion                      │
│  └── Conclusion                      │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Phase 3: Review-Revision Loop       │
│  ├── Review (评分)                   │
│  ├── Revision (修订)                 │
│  └── Repeat (最多4轮)                │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Phase 4: Final Output               │
│  └── LaTeX + PDF Compilation         │
└─────────────────────────────────────┘
```

---

## 3. 详细实现方案

### 3.1 Perspective Generation (视角生成)

**Prompt 模板** (参考 STORM):

```python
PERSPECTIVE_GENERATION_PROMPT = """## 任务: 生成研究视角

针对主题: {topic}

请从以下多个学术视角分析该主题，每个视角需包含:
1. 视角名称 (如: 机器学习、量化金融、行为金融学)
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

```json
{{
  "perspectives": [
    {{
      "name": "视角名称",
      "research_questions": ["问题1", "问题2"],
      "methodology": "相关方法论",
      "potential_contribution": "潜在贡献"
    }}
  ]
}}
```"
```

### 3.2 Question Asking (问题生成)

**Prompt 模板** (参考 STORM 的 Perspective-guided Question Asking):

```python
QUESTION_ASKING_PROMPT = """## 任务: 生成深度研究问题

主题: {topic}
视角: {perspective}

请为上述视角生成 5-8 个深度研究问题，这些问题应该:
1. 探索该视角下的关键争议
2. 寻求具体的证据和数据
3. 引导发现主题的深层联系

### 问题类型

- **背景问题**: 关于主题基本事实的问题
- **比较问题**: 与其他方法/观点的异同
- **因果问题**: 原因和结果的关系
- **评估问题**: 优缺点和适用性

### 输出格式

```json
{{
  "perspective": "{perspective}",
  "questions": [
    {{
      "type": "问题类型",
      "question": "问题内容",
      "expected_answer_type": "期望的答案类型"
    }}
  ]
}}
```"
```

### 3.3 Evidence Collection (证据收集)

**并行收集机制**:

```python
async def collect_evidence_parallel(questions: list, max_concurrent: int = 5) -> dict:
    """并行收集证据"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_for_question(q):
        async with semaphore:
            return await fetch_evidence(q)

    tasks = [fetch_for_question(q) for q in questions]
    results = await asyncio.gather(*tasks)
    return {q["question"]: r for q, r in zip(questions, results)}
```

### 3.4 Literature Review Section Generation (文献综述生成)

**Prompt 模板** (参考 STORM 的 Introduction + Related Work):

```python
LITERATURE_REVIEW_PROMPT = """## 任务: 撰写文献综述章节

主题: {topic}

### 收集到的证据

```json
{evidence}
```

### 研究大纲

```json
{outline}
```

### 任务要求

1. **结构化综述**: 按照主题流派/方法论分类组织
2. **批判性分析**: 总结各流派的优势和局限
3. **研究空白**: 明确当前研究的不足
4. **引用标注**: 使用 [1], [2], [3] 格式标注参考来源

### 章节结构

1. 概述该领域的发展历程
2. 分类讨论主要流派/方法
3. 分析各方法的优缺点
4. 指出研究空白和争议点
5. 引出本文的创新点

### 输出格式

LaTeX 格式，包含:
- \\section{Literature Review}
- 分类小节
- 引用标注
- 总结段落

请直接输出 LaTeX 源码，不需要其他说明。"""
```

### 3.5 Review-Revision Loop (评审修订循环)

**Reviewer Prompt**:

```python
PAPER_REVIEW_PROMPT = """## 任务: 评审论文质量

请评审以下论文章节:

### 论文标题
{title}

### 待评审内容
{content}

### 评审维度

1. **学术严谨性** (1-10)
   - 方法论是否合理
   - 论证是否有逻辑

2. **创新性** (1-10)
   - 是否有新贡献
   - 与现有工作如何区分

3. **完整性** (1-10)
   - 章节是否完整
   - 是否有遗漏重要方面

4. **可读性** (1-10)
   - 表达是否清晰
   - 结构是否合理

5. **引用质量** (1-10)
   - 引用是否相关
   - 是否有必要的背景引用

### 输出格式

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
```

**Reviser Prompt**:

```python
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
```

---

## 4. LaTeX 模板系统

### 4.1 支持的模板

```python
LATEX_TEMPLATES = {
    "icml": {
        "name": "ICML (International Conference on Machine Learning)",
        "class": "\\documentclass[preprint,authoryear,12pt]{elsarticle}",
        "format": "双栏"
    },
    "iclr": {
        "name": "ICLR (International Conference on Learning Representations)",
        "class": "\\documentclass{article}",
        "format": "单栏"
    },
    "neurips": {
        "name": "NeurIPS (Neural Information Processing Systems)",
        "class": "\\documentclass{article}",
        "format": "双栏"
    },
    "jff": {
        "name": "Journal of Financial Frontiers",
        "class": "\\documentclass[preprint,authoryear,12pt]{elsarticle}",
        "format": "单栏"
    }
}
```

### 4.2 完整 LaTeX 结构

```latex
\documentclass[preprint,authoryear,12pt]{elsarticle}

\begin{document}

\begin{frontmatter}

\title{论文标题}

\author[1]{作者1}
\author[1]{作者2}
\affil[1]{机构}

\begin{abstract}
摘要内容 (150-200词)
\end{abstract}

\begin{keyword}
关键词1, 关键词2, 关键词3
\end{keyword}

\end{frontmatter}

\section{Introduction}
\label{sec:intro}
引言内容...

\section{Literature Review}
\label{sec:lit_review}
文献综述...

\section{Methodology}
\label{sec:method}
方法论...

\section{Experiments}
\label{sec:exp}
实验...

\section{Results}
\label{sec:results}
结果...

\section{Discussion}
\label{sec:disc}
讨论...

\section{Conclusion}
\label{sec:conc}
结论...

\section*{References}
\bibliographystyle{elsarticle-harv}
\bibliography{references}

\end{document}
```

---

## 5. 实现计划

### 阶段 1: 核心引擎 (预计 2-3 天)

- [ ] 创建 `LiteratureReviewEngine` 类
- [ ] 实现 `PerspectiveGenerator`
- [ ] 实现 `QuestionAsker`
- [ ] 实现 `EvidenceCollector`
- [ ] 实现 `OutlineGenerator`

### 阶段 2: 评审循环 (预计 1-2 天)

- [ ] 创建 `Reviewer` Agent
- [ ] 创建 `Reviser` Agent
- [ ] 实现 4 轮 Review-Revision 循环
- [ ] 集成质量门控 (Quality Gate)

### 阶段 3: LaTeX 输出 (预计 1 天)

- [ ] 创建 LaTeX 模板系统
- [ ] 实现 Markdown → LaTeX 转换
- [ ] 集成 PDF 编译 (可选)

### 阶段 4: 前端集成 (预计 1 天)

- [ ] 更新 Dashboard 显示生成进度
- [ ] 添加 Review-Revision 状态显示
- [ ] 支持实时查看中间结果

---

## 6. API 变更

### 6.1 新增端点

```python
# 文献综述生成
@app.route('/api/research/literature-review', methods=['POST'])
def api_generate_literature_review():
    """生成文献综述章节"""
    data = request.json
    topic = data.get('topic')
    existing_papers = data.get('existing_papers', [])

    # 返回结构化的文献综述
    return jsonify({
        "success": True,
        "literature_review": {...},
        "perspectives": [...],
        "outline": {...}
    })

# 完整论文生成 (新流程)
@app.route('/api/research/generate-full', methods=['POST'])
def api_generate_full_paper():
    """使用完整流程生成论文"""
    data = request.json
    topic = data.get('topic')
    template = data.get('template', 'icml')

    return jsonify({
        "success": True,
        "generation_id": "GEN-xxx",
        "status": "in_progress",
        "phases": {
            "literature_review": "pending",
            "section_generation": "pending",
            "review_revision": "pending",
            "final_output": "pending"
        }
    })

# 获取生成状态
@app.route('/api/research/generate/<generation_id>/status', methods=['GET'])
def api_generation_status(generation_id):
    """获取论文生成状态"""
    return jsonify({
        "generation_id": generation_id,
        "current_phase": "literature_review",
        "progress": 0.25,
        "current_step": "Collecting evidence",
        "estimated_remaining_time": "5 minutes"
    })
```

---

## 7. 与现有代码的集成

### 7.1 保持向后兼容

```python
# 保留原有的简单生成函数
def generate_paper_content(topic: str, existing_papers: list) -> str:
    """原有的一次性生成函数 (保留兼容)"""
    ...

# 新增的完整流程生成
def generate_paper_full(topic: str, existing_papers: list,
                       template: str = 'icml',
                       review_rounds: int = 4) -> dict:
    """新的完整流程生成"""
    # Phase 1: Literature Review (STORM-style)
    literature_review = LiteratureReviewEngine.generate(topic, existing_papers)

    # Phase 2: Section Generation (Chunked)
    sections = ChunkedPaperGenerator.generate_all(
        topic=topic,
        literature_review=literature_review,
        template=template
    )

    # Phase 3: Review-Revision Loop
    final_sections = ReviewReviser.loop(
        sections=sections,
        rounds=review_rounds
    )

    # Phase 4: Compile LaTeX
    latex = LaTeXCompiler.compile(final_sections, template)

    return {
        "literature_review": literature_review,
        "sections": final_sections,
        "latex": latex,
        "status": "completed"
    }
```

### 7.2 配置选项

```python
# 在 server.py 中添加配置
PAPER_GENERATION_CONFIG = {
    "mode": "full",  # "simple" 或 "full"
    "template": "icml",
    "review_rounds": 4,
    "maxPerspectives": 5,
    "questionsPerPerspective": 6
}
```

---

## 8. 参考资料

1. **STORM**: Stanford Research Pipeline
   - 论文: "STORM: A Large-Scale Evaluation of Science Writing with LLM Agents"
   - 核心: Perspective-guided dialogue, simulated conversation

2. **GPT Researcher**: Tavily's Autonomous Research Agent
   - GitHub: https://github.com/assafelovic/gpt-researcher
   - 核心: Parallel research, Review-Revision loop

3. **AI Scientist**: Sakana AI's Automated Research System
   - 核心: Tree search (BFTS), experiment execution

4. **ARIS**: Automated Research Intelligence System
   - 核心: Claims-Evidence matrix, safety gates

---

*文档版本: 3.0 | 更新日期: 2026-06-20*
