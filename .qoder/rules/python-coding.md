---
type: glob
description: "Python 编码规范，适用于所有 .py 文件"
globs: "**/*.py"
---

# Python 编码规范

## 语言版本
- Python 3.12+，可使用最新语法特性（match/case, type union `X | Y` 等）

## 代码风格
- 遵循 PEP 8
- 所有公开函数/类必须有 docstring（中文或英文均可）
- 使用 type hints 标注函数参数和返回值
- import 顺序：标准库 → 第三方库 → 本地模块，各组间空一行

## 错误处理
- 不要使用裸 `except:`，必须捕获具体异常类型
- LLM 调用相关代码必须有 timeout + retry 机制
- 异常日志使用 `logging` 模块，不要用 `print`

## 命名约定
- 类名: PascalCase（如 `ResearchEngine`, `LLMCaller`）
- 函数/方法: snake_case（如 `analyze_paper`, `call_llm`）
- 常量: UPPER_SNAKE_CASE（如 `SEED_PAPERS_DIR`, `DEFAULT_TIMEOUT`）
- 私有方法: 前缀 `_`（如 `_extract_content`）

## 文件操作
- 路径操作使用 `pathlib.Path`，不用 `os.path`
- JSON 文件读写使用 `encoding="utf-8"`
- 大文件操作使用 context manager (`with open(...)`)

## server.py 特别注意
- server.py 是 5984 行的核心文件，修改时要特别谨慎
- API 端点函数使用 `@app.route` 装饰器
- 新增端点需要添加对应的错误处理和日志
- 不要在此文件中硬编码 API key 或 base_url
