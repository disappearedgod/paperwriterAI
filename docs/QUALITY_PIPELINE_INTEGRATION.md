# 论文质量流水线集成方案

> 版本: 1.2 | 日期: 2026-06-21 | 状态: **✅ Step 4+5+6 已集成 (前端+后端)**

---

## 1. 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FARS 论文全流程                                   │
├───────────┬───────────┬───────────┬───────────┬───────────┬───────────────┤
│  Step 1   │  Step 2   │  Step 3   │  Step 4   │  Step 5   │    Step 6     │
│  AI写作   │ 人工增强   │ 查重查袭  │ AI痕迹检测│ 论文评审  │  综合报告     │
│           │           │           │           │           │               │
│ FARS系统  │ 专家介入   │ 13工具可选│ ✅已实现  │ ✅已实现  │ ✅已实现     │
│ 自动生成  │ 本地编辑   │ Turnitin  │ Fast-DetectGPT| Claude  │ 7维度评分    │
│           │           │ iThenticate│ gpt-neo-2.7B| DeepSeek  │ 雷达图展示  │
└───────────┴───────────┴───────────┴───────────┴───────────┴───────────────┘
```

**现有系统**: FARS (Step 1 AI写作) ✅ 已完成
**本次实现**: Step 4 AI检测 + Step 5 论文评审 + Step 6 综合报告 ✅ **已完成(含前端)**

### 新增/修改文件

| 文件 | 说明 |
|------|------|
| `src/tools/quality_pipeline.py` | ✅ 完整实现 (FastDetectGPTDetector + PaperReviewer + QualityReporter) |
| `docs/fars_dashboard.html` | ✅ 新增4个按钮: AI痕迹检测/论文评审/完整流水线 + JS函数 |
| `server.py` | ✅ 已集成5个API端点 (quality/pipeline, quality/detect-ai, quality/review-paper 等) |
| `vendor/fast-detect-gpt/` | ✅ 克隆自 GitHub (gpt-neo-2.7B 评分模型) |
| `setup-fast-detectgpt.sh` | ✅ 安装脚本 |
| `src/services/paper_reviewer.py` | 论文评审服务（Claude/DeepSeek/本地） |
| `src/services/__init__.py` | Services 包入口 |
| `vendor/fast-detect-gpt/` | Git Submodule: ICLR 2024 Fast-DetectGPT |
| `setup-fast-detectgpt.sh` | Fast-DetectGPT 安装脚本 |

---

## 2. 各步骤工具矩阵

### 2.1 查重查袭 (Step 3)

| 工具 | 类型 | API支持 | 费用 | 说明 |
|------|------|---------|------|------|
| **Turnitin** | 商业 | REST API | 付费 | 全球最广泛使用 |
| **iThenticate** | 商业 | REST API | 付费 | 期刊出版标准 |
| **Copyscape** | 商业 | API | 按次 | 网页查重为主 |
| **Paperpass** | 商业 | 无API | 按次 | 中文论文友好 |
| **知网查重** | 商业 | 无API | 按次 | 中国高校标准 |
| **Grammarly** | Freemium | API | 免费+ | 语法+查重 |
| **QuillBot** | Freemium | 无API | 免费+ | 改写+查重 |
| **Copyleaks** | 商业 | REST API | 付费 | AI+抄袭联合 |
| **Crossref** | 免费 | API | 免费 | DOI元数据比对 |
| **SmallSEOTools** | 免费 | 无API | 免费 | 在线工具 |

### 2.2 AI痕迹检测 (Step 4)

| 工具 | 类型 | API支持 | 费用 | 说明 |
|------|------|---------|------|------|
| **GPTZero** | 免费+ | REST API | 免费+ | 最流行 |
| **Originality.ai** | 商业 | REST API | 按字数 | 团队版可用 |
| **Copyleaks** | 商业 | REST API | 付费 | AI+抄袭联合检测 |
| **ZeroGPT** | 免费 | 无API | 免费 | 快速轻量 |
| **Turnitin AI** | 商业 | 内嵌 | 随查重 | 集成在查重中 |
| **Hive** | 商业 | REST API | 付费 | 企业级 |
| **Content at Scale** | 商业 | API | 付费 | AI内容检测 |
| **Sapling** | 商业 | API | 付费 | 语法+AI检测 |
| **GLTR** | 开源 | 本地运行 | 免费 | 文本统计特征 |
| **Plag AI** | 免费 | 无API | 免费 | 开源检测 |
| **Writeful** | 免费 | 无API | 免费 | 学术辅助 |

### 2.3 论文评审评分 (Step 5)

| 工具 | 类型 | API支持 | 费用 | 说明 |
|------|------|---------|------|------|
| **paperreview.ai** | Web | 无API | 免费 | 斯坦福团队 |
| **Paperpal** | Freemium | 无API | 免费+ | 编辑+评审 |
| **SciSpace** | Freemium | API | 免费+ | 论文理解 |
| **Elicit** | 免费 | API | 免费 | 文献分析 |
| **Scholarcy** | 商业 | API | 付费 | 摘要生成 |
| **Claude** | 商业 | API | 按token | 深度学术分析 |
| **ChatGPT** | 商业 | API | 按token | 多用途 |
| **Wordvice AI** | 商业 | 无API | 付费 | 专业编辑 |
| **Writefull** | 免费 | 无API | 免费 | 学术写作 |
| **Paper Digest** | 免费 | 无API | 免费 | 论文总结 |
| **Semantic Scholar** | 免费 | API | 免费 | AI论文分析 |
| **OpenReview** | 免费 | 无API | 免费 | 开放同行评审 |

---

## 3. 已实现的 API 端点 (v3.2)

### Step 4: AI痕迹检测

```bash
# 检测论文 AI 痕迹（Fast-DetectGPT）
POST /api/quality/detect-ai
Body: {"paper_id": 123}
Response: {
    "success": true,
    "overall_ai_probability": 0.23,     # 0.0 ~ 1.0
    "is_likely_ai_generated": false,
    "high_ai_risk_segments": [...],     # 高风险段落
    "summary": "共检测12个段落，整体AI概率23%",
    "detector": "fast-detectgpt",
    "model": "gpt-neo-2.7B"
}

# 检查安装状态
GET /api/quality/detect-ai/status
Response: {
    "available": true,
    "detector": "fast-detectgpt",
    "models": ["gpt-neo-2.7B", "gpt-j-6B", "Llama3-8B", "Llama3-8B-Instruct"],
    "setup_script": "/setup-fast-detectgpt.sh"
}
```

### Step 5: 论文评审

```bash
# 评审论文（Claude/DeepSeek/本地）
POST /api/quality/review-paper
Body: {"paper_id": 123, "sections": true}
Response: {
    "success": true,
    "title": "论文标题",
    "review": {
        "overall_score": 7.5,
        "dimension_scores": {
            "novelty": 7.5, "rigor": 7.0, "completeness": 7.5,
            "readability": 7.0, "citation_quality": 6.5
        },
        "strengths": ["创新点明确", "实验设计合理"],
        "weaknesses": ["文献综述不够全面"],
        "recommendation": "weak_accept"
    },
    "radar_chart": {...}
}

# 检查评审服务状态
GET /api/quality/review-paper/status
Response: {
    "available": true,
    "reviewers": {
        "claude": {"available": true, "model": "claude-sonnet-4"},
        "deepseek": {"available": false},
        "paperreview_ai": {"available": true}
    }
}
```

### Step 6: 一键综合报告

```bash
# 一键执行 Step 4 + Step 5 + 综合报告
POST /api/quality/full-report
Body: {"paper_id": 123, "checks": ["ai_detection", "review"]}
Response: {
    "success": true,
    "paper_id": 123,
    "ai_detection": {
        "overall_ai_probability": 0.23,
        "is_likely_ai_generated": false
    },
    "review": {
        "overall_score": 7.5,
        "recommendation": "weak_accept"
    },
    "final_report": {
        "overall_quality_score": 8.15,
        "grade": "A",
        "verdict": "优秀",
        "recommendation": "✓ 论文质量合格，可考虑提交"
    }
}
```

### 流水线状态

```bash
# 查询流水线状态
GET /api/quality/pipeline/<paper_id>
Response: {
    "paper_id": 123,
    "steps": {
        "ai_generation": {"status": "completed"},
        "human_edit": {"status": "pending"},
        "plagiarism_check": {"status": "unknown"},
        "ai_detection": {"status": "completed", "result": {...}},
        "review": {"status": "completed", "result": {...}},
        "report": {"status": "completed", "result": {...}}
    }
}

# 雷达图数据
GET /api/quality/radar-chart/<paper_id>
Response: {
    "paper_id": 123,
    "labels": ["原创性", "严谨性", "完整性", "可读性", "引用质量", "实验设计", "写作规范"],
    "scores": [7.5, 7.0, 7.5, 7.0, 6.5, 7.0, 8.0]
}
```

---

## 4. 安装与使用

### Fast-DetectGPT 安装

```bash
# 1. 克隆 submodule（已在 vendor/fast-detect-gpt）
cd /Users/derek/Documents/Github/paperwriterAI
git submodule update --init --recursive

# 2. 运行安装脚本
bash setup-fast-detectgpt.sh

# 可选模型: gpt-neo-2.7B (默认, CPU可用) / gpt-j-6B (GPU推荐) / Llama3-8B (最佳)
bash setup-fast-detectgpt.sh gpt-j-6B
```

### 依赖安装

```bash
pip install -r requirements.txt
# 新增: transformers>=4.35.0, torch>=2.0.0, accelerate>=0.25.0
```

### API Key 配置

```bash
# Claude API (用于论文评审)
export ANTHROPIC_API_KEY="sk-ant-..."

# DeepSeek API (评审备选)
export DEEPSEEK_API_KEY="sk-..."
```

---

## 5. 实施状态

| 步骤 | 状态 | 说明 |
|------|------|------|
| Step 4 AI检测 | ✅ 已实现 | Fast-DetectGPT + 简单回退 |
| Step 5 论文评审 | ✅ 已实现 | Claude + DeepSeek + 本地fallback |
| Step 6 综合报告 | ✅ 已实现 | 一键生成综合评分和建议 |
| Step 3 查重查袭 | ⏳ 待实现 | 待集成 Copyleaks API |
| Step 2 人工增强 | ⏳ 待实现 | UI + 编辑记录 |
| Step 1 串联 | ⏳ 待实现 | FARS自动进入流水线 |

---

## 6. 与现有代码的集成点

### 数据层
- `data/quality_pipeline.json` - 流水线状态（已实现）
- 论文表 `papers` 字段: `quality_pipeline_status`（由 `update_quality_step()` 管理）

### 服务层
- `src/services/ai_detector.py` - AI检测服务 ✅
- `src/services/paper_reviewer.py` - 评审服务 ✅
- `src/services/plagiarism_checker.py` - 查重服务（待实现）

### API层
- `POST /api/quality/detect-ai` - AI痕迹检测 ✅
- `POST /api/quality/review-paper` - 论文评审 ✅
- `GET /api/quality/pipeline/<id>` - 流水线状态 ✅
- `POST /api/quality/full-report` - 一键综合报告 ✅
- `GET /api/quality/radar-chart/<id>` - 雷达图数据 ✅

### 前端层
- 待集成: Dashboard 新增「质量流水线」Tab
- 待集成: 7维度雷达图展示组件

---

*本方案将 AI_PAPER_FULL_WORKFLOW.md 中的规划转化为可执行的技术方案。*
