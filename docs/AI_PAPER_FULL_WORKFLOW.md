# AI 论文全流程系统设计方案

> 版本: 1.0 | 日期: 2026-06-20 | 状态: 规划中

---

## 1. 整体流程概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AI 论文质量保障全流程                          │
├─────────┬─────────────┬─────────────┬─────────────┬─────────────────┤
│ Step 1  │   Step 2    │   Step 3    │   Step 4    │     Step 5      │
│ AI写作  │ 人工增强    │  查重查袭   │ AI痕迹检测  │   论文评审评分   │
│         │             │             │             │                 │
│ FARS    │ 人工审核    │  Turnitin   │  AI检测器   │  paperreview.ai │
│ 系统    │ 补充专业    │  iThenticate│  工具集     │  + 9个替代方案  │
│ 生成    │ 见解        │  10+替代   │  10+工具    │                 │
└─────────┴─────────────┴─────────────┴─────────────┴─────────────────┘
```

---

## 2. 各步骤详解与工具推荐

### Step 1: AI 写作生成

**目标**: 使用 FARS 系统生成高质量论文草稿

#### 现有系统能力
- `seed_paper_analysis.md` → 提取具体研究主题
- `LiteratureReviewEngine` → 文献综述生成
- `BacktestEngine` → 量化因子回测
- 多 Agent 协作 (Ideation/Planning/Experiment/Writing)

#### 工具链 (多元化选择)

| 工具 | 类型 | 说明 |
|------|------|------|
| **FARS (现有)** | 本地系统 | 自主因子挖掘+回测+论文生成 |
| The AI Scientist | 开源框架 | Sakana AI，自动生成代码/实验/分析 |
| GPT Researcher | SaaS | Tavily，深度研究代理 |
| STORM | 开源 | Stanford，视角引导提问系统 |
| AutoResearcher | 开源 | 自主研究代理 |
| MiniChain | 开源 | 轻量级研究框架 |
| OpenDeepSearch | 开源 | 开放搜索引擎研究 |
| YouSearch | 开源 | 去中心化搜索研究 |
| AgentOK | 商业 | 多智能体研究平台 |
| Sciencemakers | 商业 | 科研辅助平台 |

---

### Step 2: 人工增强

**目标**: 在 AI 草稿基础上加入专业见解、数据和逻辑推演

#### 核心原则
- 加入独特数据集和实验结果
- 补充领域专业见解和批判性分析
- 强化逻辑推演和论证链条
- 修正 AI 生成的不准确内容

#### 工具推荐

| 工具 | 说明 |
|------|------|
| **人工审核 (核心)** | 领域专家深度介入 |
| Zotero / EndNote | 文献管理和引用 |
| Obsidian / Logseq | 知识图谱辅助分析 |
| Overleaf | 在线 LaTeX 协作 |
| Google Docs | 实时协作编辑 |
| Notion | 项目管理和笔记 |

---

### Step 3: 查重与查袭

**目标**: 确保学术诚信，检测抄袭和不当引用

#### 工具推荐 (10+ 替代方案)

| 工具 | 类型 | 说明 |
|------|------|------|
| **Turnitin** | 商业 | 全球最广泛使用的学术查重系统 |
| **iThenticate** | 商业 | 期刊和会议出版标准 |
| **Grammarly** |  Freemium | 查重+语法检查 |
| **Copyscape** | 商业 | 网页内容查重 |
| **QuillBot** | Freemium | 改写+查重 |
| **Crossref** | 免费 | DOI 元数据比对 |
| **Sagiarism** | 商业 | 学术查重 |
| **PlagScan** | 商业 | 欧洲学术机构常用 |
| **Duplichecker** | 免费 | 在线查重 |
| **SmallSEOTools** | 免费 | 综合查重工具 |
| **Paperpass** | 商业 | 中文论文查重 |
| **万方数据** | 商业 | 中国学术查重 |
| **知网查重** | 商业 | 中国高校标准 |

---

### Step 4: AI 痕迹检测

**目标**: 识别 AI 生成文本中的固定模式和语法结构

#### 工具推荐 (10+ 替代方案)

| 工具 | 类型 | 说明 |
|------|------|------|
| **GPTZero** | 免费+商业 | 最流行的 AI 检测器 |
| **Originality.ai** | 商业 | 团队+个人版 |
| **Turnitin AI Detection** | 商业 | 集成在查重系统中 |
| **Copyleaks** | 商业 | AI+抄袭联合检测 |
| **ZeroGPT** | 免费 | 快速 AI 文本检测 |
| **Hive** | 商业 | 企业级 AI 检测 |
| **Content at Scale** | 商业 | AI 内容检测 |
| **Passio AI Detector** | 免费 | 简洁界面 |
| **Writeful** | 免费 | 学术写作辅助 |
| **Sapling** | 商业 | 语法+AI 检测 |
| **GLTR** | 开源 | 文本统计特征分析 |
| **Detector** | 免费 | 简单在线工具 |
| **AI Checker Pro** | 免费 | 多语言支持 |
| **Plag AI** | 免费 | 开源 AI 检测 |

---

### Step 5: 论文评审与评分

**目标**: 获取结构化评审意见和目标会议评分

#### 主要工具 (paperreview.ai 及其替代)

| 工具 | 类型 | 说明 |
|------|------|------|
| **paperreview.ai** | Web | 斯坦福团队，结构化评审+评分 |
| **Paperpal** | Freemium | 编辑+评审+查重 |
| **SciSpace** | Freemium | 论文理解+评审 |
| **Elicit** | 免费 | 科研文献分析 |
| **Jenni AI** | 商业 | AI 写作+评审 |
| **Claude** | 商业 | 深度学术分析 |
| **ChatGPT** | 商业 | 多用途评审辅助 |
| **Scholarcy** | 商业 | 论文摘要+评审 |
| **Wordvice AI** | 商业 | 专业编辑+评审 |
| **Writefull** | 免费 | 学术写作辅助 |
| **Paper Digest** | 免费 | 论文总结+评审 |
| **Semantic Scholar** | 免费 | AI 论文分析 |
| **Research Rabbit** | 免费 | 文献关系图谱 |
| **Connected Papers** | 免费 | 论文引用网络 |
| **OpenReview** | 免费 | 开放同行评审平台 |

---

## 3. 与现有 FARS 系统集成方案

### 3.1 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                     paperwriterAI 主界面                        │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────────┐  │
│  │  📝 生成论文  │ │  🔍 查重查袭  │ │  🤖 AI痕迹检测         │  │
│  │  FARS 系统   │ │  第三方API   │ │  GPTZero/Originality  │  │
│  └──────────────┘ └──────────────┘ └────────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────────┐  │
│  │  ⭐ 论文评审  │ │  ✏️ 人工增强  │ │  📊 综合评分报告       │  │
│  │ paperreview │ │  编辑器介入  │ │  7步质量评分          │  │
│  └──────────────┘ └──────────────┘ └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 新增功能模块

#### 模块 1: 质量评分报告 (Quality Score Report)

```python
class QualityReport:
    """论文综合质量报告"""
    originality_score: float      # 原创性分数 (0-100)
    ai_detection_score: float    # AI痕迹分数 (越低越好)
    plagiarism_score: float      # 查重率 (越低越好)
    review_score: float          # 论文评审分数
    readability_score: float      # 可读性分数

    # 各维度评分
    dimensions = {
        "abstract": 8.5,         # 摘要质量
        "introduction": 7.5,     # 引言质量
        "methodology": 8.0,      # 方法论
        "experiments": 7.0,      # 实验设计
        "conclusion": 8.0,       # 结论
        "references": 9.0,       # 引用规范
    }
```

#### 模块 2: 多工具 API 集成

```python
# 查重服务
class PlagiarismChecker:
    services = {
        "turnitin": TurnitinAPI,
        "ithenticate": IThenticateAPI,
        "copyscape": CopyscapeAPI,
        "paperpass": PaperPassAPI,
        "grammarly": GrammarlyAPI,
    }

# AI 痕迹检测服务
class AIDetectionService:
    detectors = {
        "gptzero": GPTZeroAPI,
        "originality": OriginalityAPI,
        "copyleaks": CopyleaksAPI,
        "zerogpt": ZeroGPTAPI,
        "turnitin_ai": TurnitinAIAPI,
    }

# 论文评审服务
class PaperReviewService:
    reviewers = {
        "paperreview": PaperReviewAIAPI,
        "paperpal": PaperPalAPI,
        "scispace": SciSpaceAPI,
        "elicit": ElicitAPI,
        "scholarcy": ScholarcyAPI,
    }
```

---

## 4. 实施计划

### Phase 1: 核心集成 (1-2 天)
- [ ] 创建 `QualityReport` 质量评分模型
- [ ] 集成查重 API (Turnitin/iThenticate/Copyscape)
- [ ] 集成 AI 痕迹检测 API (GPTZero/Originality.ai)
- [ ] 集成论文评审 API (paperreview.ai)

### Phase 2: 自动化流水线 (2-3 天)
- [ ] 创建端到端质量检测流水线
- [ ] 实现多工具并行检测
- [ ] 生成综合评分报告

### Phase 3: 前端集成 (1-2 天)
- [ ] 添加质量检测面板
- [ ] 显示各维度评分雷达图
- [ ] 支持一键检测和导出报告

---

## 5. API 设计

```python
# 查重
POST /api/quality/check-plagiarism
Body: {"paper_text": "...", "service": "turnitin"}
Response: {"score": 5.2, "matches": [...], "service": "turnitin"}

# AI 痕迹检测
POST /api/quality/detect-ai
Body: {"paper_text": "...", "detector": "gptzero"}
Response: {"ai_probability": 0.23, "flags": [...], "detector": "gptzero"}

# 论文评审
POST /api/quality/review-paper
Body: {"paper_text": "...", "reviewer": "paperreview"}
Response: {"score": 7.5, "reviews": {...}, "recommendation": "accept"}

# 综合报告
POST /api/quality/full-report
Body: {"paper_text": "...", "checks": ["plagiarism", "ai", "review"]}
Response: {
    "plagiarism": {"score": 5.2, "service": "turnitin"},
    "ai_detection": {"score": 0.23, "detector": "gptzero"},
    "review": {"score": 7.5, "reviewer": "paperreview"},
    "overall": 85.0
}
```

---

## 6. 工具对比总结表

| 步骤 | 工具数量 | 推荐首选 | 免费选项 |
|------|----------|----------|----------|
| AI写作 | 10+ | FARS (本地) | The AI Scientist, GPT Researcher |
| 人工增强 | - | 人工审核 | Obsidian, Zotero |
| 查重查袭 | 13 | iThenticate | Copyscape, QuillBot |
| AI痕迹检测 | 14 | GPTZero | ZeroGPT, Detector |
| 论文评审 | 15 | paperreview.ai | Elicit, Semantic Scholar |

---

## 7. 优先级建议

1. **高优先级**: AI痕迹检测 + 查重 (直接影响学术诚信)
2. **中优先级**: 论文评审评分 (paperreview.ai 集成)
3. **低优先级**: 多工具并行检测 (成本考虑)

---

*本文档将作为 paperwriterAI 系统的扩展功能设计基准。*
