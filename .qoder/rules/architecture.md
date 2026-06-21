---
type: always
description: "FARS 系统架构规则，所有修改必须遵守"
---

# FARS 架构规则

## 分层架构（严格遵守依赖方向）

```
server.py (API 层) → src/core/ (核心引擎层) → src/tools/ (工具层)
                   → src/agents/ (Agent层)   → src/tools/
                   → src/services/ (服务层)  → src/tools/
```

- **上层可以依赖下层，下层不能依赖上层**
- `src/tools/` 不能 import `src/core/` 或 `server.py`
- `src/agents/` 不能 import `server.py`

## 核心文件职责

| 文件 | 唯一职责 | 不能做 |
|------|----------|--------|
| `server.py` | API 端点 + 请求处理 + LLM 调用编排 | 不能包含业务逻辑实现 |
| `research_engine.py` | Checkpoint 状态机 + 断点续分析 | 不能直接调用 API |
| `research_runner.py` | 后台研究流水线推进 | 不能处理 HTTP 请求 |
| `agents.py` | 4 大 Agent 的决策逻辑 | 不能直接操作文件 |
| `fetchers.py` | LLM 调用 + 数据获取 + 代码执行 | 不能包含业务决策 |
| `literature_review_engine.py` | STORM 风格文献综述 | 不能修改 checkpoint |

## 数据流

```
种子论文(PDF) → paper_extractor → research_engine(分析) → agents(决策) → writing → 论文输出
                    ↓                    ↓                    ↓
              paper_analysis/      checkpoint.json       draft/
```

## Checkpoint 机制（不可破坏）
- 每个 research_id 对应独立目录: `data/research/RS-{id}_checkpoint/`
- `checkpoint.json` 是核心状态文件，每步完成后立即持久化
- MD5 防重：写入前必须校验
- 不能跳过 checkpoint 直接执行步骤

## 配置文件加载
- `config.local.json` 优先于 `config.json`
- 使用 `src/core/config.py` 中的 `load_effective_config()` 和 `get_effective_llm_config()`
- 不要在代码中硬编码 API key 或 base_url

## 前端
- v1 (`docs/fars_dashboard.html`) 和 v2 (`docs/v2/`) 共享所有后端 API
- 前端修改不需要重启服务器（静态文件自动 reload）
- v2 组件在 `docs/v2/components/` 下，每个组件一个 `.js` 文件
