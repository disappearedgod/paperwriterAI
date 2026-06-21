---
type: always
description: "LLM 集成规范，修改任何 LLM 相关代码前必须阅读"
---

# LLM 集成规范

## 当前 LLM 配置
- **主用模型**: MiniMax-M2.7-highspeed（推理模型）
- **API 地址**: `https://minnimax.chat/v1`（OpenAI 兼容接口）
- **备用模型**: DeepSeek
- **可选模型**: OpenAI GPT-4o, Gemini 2.0 Flash

## MiniMax 特殊处理（关键！）

### 1. 推理模型 `<think>` 标签
MiniMax-M2.7-highspeed 是推理模型，返回内容包含 `<think>...</think>` 标签。
**必须**在所有 LLM 返回处用正则清理：
```python
content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
```

### 2. 参数名称
- MiniMax 使用 `max_tokens`（**不是** `max_completion_tokens`）
- 所有 provider 统一使用 `max_tokens` 参数名

### 3. 超时与重试
```python
timeout = 180  # 秒，不可超过
max_retries = 2
```
- 每次 LLM 调用**必须**显式设置 timeout
- 失败后重试最多 2 次
- 超时后触发优雅降级（不阻塞主流程）

## LLMCaller 使用规范
- 所有 LLM 调用通过 `src/tools/fetchers.py` 中的 `LLMCaller` 类
- 不要在 `server.py` 中直接构造 HTTP 请求调用 LLM
- `LLMCaller` 已封装 provider 适配、超时、重试、think 标签清理

## API Key 安全
- **绝不**在代码中硬编码 API key
- API key 来源优先级: `config.local.json` > 环境变量 > `config.json`
- `config.local.json` 和 `config.json` 都在 `.gitignore` 中
- 提交代码前检查是否有 key 泄露

## Token 配额管理
- MiniMax 默认 max_tokens: 32000
- 各阶段配额分配建议:
  - 论文分析: 4096
  - 视角分析: 4096
  - 大纲生成: 8192
  - 论文章节: 8192
  - 文献综述: 8192
- 推理模型会消耗大量 token 在内部推理上，实际输出远少于配额

## 错误处理
- LLM 返回空内容: 检查是否被 think 标签截断，尝试增大 max_tokens
- 超时: 自动重试 → 重试失败 → 优雅降级
- 401/403: 检查 API key 是否有效
- 429: 限流，等待后重试
