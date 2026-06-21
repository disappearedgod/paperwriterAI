# LLM 硬编码清理 Checklist

目标：`provider / model / base_url` 的运行时生效值只来自 `config.json` + `config.local.json`（local 覆盖）+ 环境变量（仅 API Key），并允许 dashboard 通过 `/api/config/llm` 写入 local 覆盖。

## 统一入口

- [ ] `src/core/config.py` 提供 `load_effective_config()`（config.json + config.local.json 深度合并）
- [ ] `src/core/config.py` 提供 `get_effective_llm_config()`（统一输出 provider/model/base_url/api_key/max_tokens/temperature）
- [ ] 全仓库只允许通过上述函数获取运行时 LLM 配置

## 脚本与模块（逐个验收）

- [ ] `scripts/generate_paper_with_api.py`：删除任何 `MINIMAX_CONFIG` / 写死的 base_url/model/provider
- [ ] `src/tools/fetchers.py`：移除 `base_url or "https://..."` 这类默认回退，默认 provider/model 从配置取
- [ ] `src/tools/literature_review_engine.py`：移除默认 base_url/model 回退，统一从配置取
- [ ] `src/services/paper_reviewer.py`：把写死的 API URL 与模型名改为可配置项（或复用 llm_providers / 新增 review_providers）
- [ ] `scripts/chunked_generation.py`：移除写死的 base_url/model
- [ ] `scripts/paper_submission_workflow.py`：移除默认 provider/model 写死
- [ ] `src/main.py`：移除 fallback 写死（如 ollama/gemma4/base_url），改为配置驱动

## Dashboard（页面侧）

- [ ] `docs/fars_dashboard.html`：LLM 配置弹窗不再写死 input 的默认 `value=...`
- [ ] 打开弹窗：从 `GET /api/config/llm` 填充 provider/model/base_url/temperature/max_tokens
- [ ] 保存：`POST /api/config/llm` 写入 `config.local.json`，刷新后仍保持用户配置
- [ ] 未配置 key：前端提示并引导配置，不应进入“假启动”

## 安全与仓库清洁

- [ ] `scripts/test_minimax.py`：移除任何明文 key（改为环境变量或 config.local.json）
- [ ] 仓库内禁止出现真实 key：`api_key` 只能存在于 `config.local.json` 或环境变量

## 回归验证（每改完一个文件都能做）

- [ ] 修改 `config.json` 的 provider/model/base_url 后：脚本与后端均自动生效（无需改代码）
- [ ] 删除/清空 `config.local.json` 后：系统回退到 `config.json` 的默认值
- [ ] 仅设置环境变量 API Key 时：能够覆盖 local/config 的 key（不覆盖 model/base_url）
