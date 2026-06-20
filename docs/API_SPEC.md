# FARS API Specification

> 版本: 1.0 | 日期: 2026-06-20

---

## 1. 概述

本文档定义了FARS系统的RESTful API接口。

**基础URL**: `http://localhost:8000/api/v1`

**认证**: Bearer Token (待实现)

**响应格式**: JSON

---

## 2. Papers API

### 2.1 搜索论文

```
GET /papers/search
```

**参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | 是 | 搜索关键词 |
| source | string | 否 | 数据源 (arxiv, semantic_scholar, all) |
| max_results | int | 否 | 最大结果数 (默认10) |
| year_from | int | 否 | 起始年份 |
| year_to | int | 否 | 结束年份 |

**响应**:
```json
{
  "success": true,
  "data": [
    {
      "paper_id": "arxiv_2409.06289",
      "title": "Automate Strategy Finding with LLM",
      "authors": ["Zhou, Tao", "Wang, Wei"],
      "year": 2024,
      "abstract": "...",
      "url": "https://arxiv.org/abs/2409.06289"
    }
  ],
  "count": 1
}
```

### 2.2 获取论文详情

```
GET /papers/{paper_id}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "paper_id": "arxiv_2409.06289",
    "source": "arxiv",
    "external_id": "2409.06289",
    "title": "Automate Strategy Finding with LLM",
    "authors": ["Zhou, Tao", "Wang, Wei"],
    "abstract": "...",
    "year": 2024,
    "categories": ["q-fin.TR", "cs.AI"],
    "status": "analyzed",
    "reading_notes": "..."
  }
}
```

### 2.3 下载论文PDF

```
POST /papers/{paper_id}/download
```

**响应**:
```json
{
  "success": true,
  "data": {
    "paper_id": "arxiv_2409.06289",
    "pdf_path": "/workspace/papers/arxiv_2409.06289.pdf"
  }
}
```

### 2.4 分析论文

```
POST /papers/{paper_id}/analyze
```

**响应**:
```json
{
  "success": true,
  "data": {
    "paper_id": "arxiv_2409.06289",
    "analysis": {
      "research_question": "...",
      "methodology": "...",
      "innovation": "...",
      "experiments": "...",
      "reproducibility": "...",
      "limitations": "..."
    }
  }
}
```

---

## 3. Hypotheses API

### 3.1 从论文生成假设

```
POST /hypotheses/generate
```

**请求体**:
```json
{
  "paper_id": "arxiv_2409.06289",
  "market_universe": "A-share",
  "time_horizon": "daily"
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "hypothesis_id": "hyp_20260620_001",
    "alpha_name": "LLM_Sentiment_Momentum",
    "description": "...",
    "trading_logic": "...",
    "parameters": {
      "sentiment_threshold": 0.6,
      "lookback_period": 20
    }
  }
}
```

### 3.2 列出假设

```
GET /hypotheses
```

**参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 状态过滤 |
| universe | string | 否 | 市场范围 |
| page | int | 否 | 页码 (默认1) |
| page_size | int | 否 | 每页数量 (默认20) |

### 3.3 获取假设详情

```
GET /hypotheses/{hypothesis_id}
```

---

## 4. Experiments API

### 4.1 创建实验

```
POST /experiments
```

**请求体**:
```json
{
  "hypothesis_id": "hyp_20260620_001",
  "experiment_name": "Sentiment Momentum Test",
  "backtest_period": {
    "start": "2018-01-01",
    "end": "2025-12-31"
  },
  "market_universe": ["000001.SZ", "000002.SZ", "600000.SH"]
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "experiment_id": "exp_20260620_001",
    "plan": {
      "experiments": [...],
      "success_criteria": {...}
    }
  }
}
```

### 4.2 运行实验

```
POST /experiments/{experiment_id}/run
```

**响应**:
```json
{
  "success": true,
  "data": {
    "run_id": "run_001",
    "status": "running",
    "progress": 0.3
  }
}
```

### 4.3 获取实验结果

```
GET /experiments/{experiment_id}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "experiment_id": "exp_20260620_001",
    "status": "completed",
    "latest_run": {
      "run_id": "run_001",
      "result": {
        "sharpe_ratio": 1.82,
        "max_drawdown": -0.18,
        "annual_return": 0.24,
        "ic": 0.035
      },
      "judgment": {
        "passed": true
      }
    }
  }
}
```

### 4.4 获取运行日志

```
GET /experiments/{experiment_id}/runs/{run_id}/logs
```

---

## 5. Reports API

### 5.1 生成报告

```
POST /reports/generate
```

**请求体**:
```json
{
  "experiment_id": "exp_20260620_001",
  "report_type": "paper",
  "include_figures": true,
  "include_tables": true
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "report_id": "report_20260620_001",
    "status": "generating",
    "estimated_time": 60
  }
}
```

### 5.2 获取报告

```
GET /reports/{report_id}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "report_id": "report_20260620_001",
    "title": "LLM-Driven Sentiment and Momentum Strategy",
    "status": "completed",
    "content": "\\documentclass{article}...",
    "figures": [
      {"id": "fig:returns", "path": "/workspace/reports/report_20260620_001/figures/returns.png"}
    ],
    "references": "@article{...}"
  }
}
```

### 5.3 下载报告

```
GET /reports/{report_id}/download
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| format | string | 格式 (tex, pdf, zip) |

---

## 6. Pipeline API

### 6.1 运行完整流程

```
POST /pipeline/run
```

**请求体**:
```json
{
  "query": "LLM quantitative trading momentum",
  "max_papers": 5,
  "target_universe": "A-share",
  "generate_paper": true
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "pipeline_id": "pipe_20260620_001",
    "status": "running",
    "stages": {
      "ideation": {"status": "completed", "progress": 1.0},
      "planning": {"status": "running", "progress": 0.5},
      "experiment": {"status": "pending", "progress": 0},
      "writing": {"status": "pending", "progress": 0}
    }
  }
}
```

### 6.2 获取流程状态

```
GET /pipeline/{pipeline_id}
```

### 6.3 取消流程

```
POST /pipeline/{pipeline_id}/cancel
```

---

## 7. 错误响应

**格式**:
```json
{
  "success": false,
  "error": {
    "code": "PAPER_NOT_FOUND",
    "message": "论文不存在",
    "details": {}
  }
}
```

**错误代码**:
| 代码 | HTTP状态 | 说明 |
|------|----------|------|
| VALIDATION_ERROR | 400 | 请求参数错误 |
| UNAUTHORIZED | 401 | 未认证 |
| FORBIDDEN | 403 | 无权限 |
| NOT_FOUND | 404 | 资源不存在 |
| INTERNAL_ERROR | 500 | 服务器内部错误 |
| LLM_ERROR | 500 | LLM调用失败 |
| BACKTEST_ERROR | 500 | 回测执行失败 |

---

## 8. WebSocket API

用于实时获取流程进度：

```
WS /ws/pipeline/{pipeline_id}
```

**消息格式**:
```json
{
  "type": "stage_update",
  "stage": "experiment",
  "progress": 0.75,
  "message": "运行回测中..."
}
```

**消息类型**:
- `stage_update` - 阶段进度更新
- `stage_complete` - 阶段完成
- `error` - 发生错误
- `complete` - 流程完成

---

*API文档由FARS系统自动生成 | 最后更新: 2026-06-20*