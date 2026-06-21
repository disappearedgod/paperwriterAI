[OPEN] Debug Session: writing-stuck-078

## Symptom
- 研究流程长期停留在 `writing` 阶段，`progress = 0.78`，状态消息反复显示“正在撰写研究论文…”
- 期望：写作阶段应在合理时间内成功落盘（generated）或失败退出（failed/error），并给出失败原因。

## Repro Steps
1. 启动服务：`python server.py`
2. `POST /api/research/reset`
3. `POST /api/generate/start`
4. 观察 `/api/research/state` 是否长期停留在 writing 0.78

## Hypotheses (Falsifiable)
1. **LLM 请求阻塞**：写作阶段已发出 LLM 请求，但 requests 没有 timeout，导致长时间挂起。
2. **重试循环卡死**：写作阶段进入多轮续写/重试，循环条件无法满足或未更新 attempt 计数，导致无穷等待。
3. **线程状态未回写**：LLM 请求已经失败或异常退出，但生成线程没有捕获/回写 `current_run.status`，UI 一直显示 writing。
4. **落盘阻塞**：LLM 返回已拿到，但在写文件/生成 artifacts（markdown/tex/meta.json）或图谱刷新阶段阻塞。
5. **上游返回非 JSON/网关 504**：LLM 返回 HTML 504/非 JSON，异常被包装但未触发失败状态，使 runner 停在 writing。

## Evidence Plan (Instrumentation)
- 在写作链路关键点埋点并上报到 Debug Server（不使用 print/console.log）：
  - writing 进入/退出（run_id、research_id、thread_id）
  - 每次 LLM 调用：attempt、prompt 长度、max_tokens、开始时间、结束时间、异常类型、HTTP status
  - LLM 返回文本：只采样前 200 字符（脱敏，不记录 api_key）
  - 写文件：目标路径、耗时、异常
  - “心跳”日志：每 10s 报告仍在等待哪一步（用于确认阻塞点）

## Fix Plan (after evidence)
- 增加 requests timeout + 针对 504/连接异常的指数退避重试
- 将“论文撰写”提示词拆分为多步：提纲 → 分节生成 → 引用/实验数据注入 → 校对合并 → 落盘
- 失败时强制回写 run 状态与错误原因，避免 UI 假完成/假进行中

## Logs
- Debug logs file: `trae-debug-log-writing-stuck-078.ndjson` (via Debug Server)
