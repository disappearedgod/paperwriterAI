[OPEN] writing=0.78 stuck

## Symptom
- Dashboard 显示 writing 阶段进度长期停在 0.78
- `is_generating=true`，但 `research_activity.updated_at` / `current_run.updated_at` 不再变化
- `llm_inflight` 为空（非“正在等待 LLM”态）
- 论文正文文件仍为占位内容：`article/RS-20260621-101_paper.md`

## Environment
- Host: macOS
- Service: `http://127.0.0.1:8080`
- Research dir: `data/research/RS-20260621-101_2311_10723_LLM_in_Finance_Survey_11`
- Run ID: `RUN-20260621223517-b104644d`

## Hypotheses (falsifiable)
1. Writing 线程在 LLM 返回后卡在“落盘/汇总产物”步骤（I/O 阻塞或死锁），导致进度与 updated_at 不再推进。
2. Writing 线程已异常退出，但 `is_generating`/`current_run.status` 未被正确回写（状态机缺少 finally 回收/错误回写）。
3. Writing 线程仍在运行，但“progress/updated_at 的更新”路径未被调用（例如：progress 只在特定节点更新；或异常路径跳过更新）。
4. Writing 线程卡在某个外部调用（非 LLM）：例如实验聚合、引用注入、文件打包/压缩、下载中心索引写入等。
5. `llm_inflight` 维护逻辑存在缺口：真实仍在等待请求，但 inflight 未正确设置/未正确清理，造成误判。

## Evidence Collected (pre-fix)
- `/api/research/state`（同一进程 3 秒内两次读取）：
  - `research_activity.phase=writing`
  - `progress=0.78`
  - `research_activity.updated_at` 不变：`2026-06-21T22:35:17.625072`
  - `is_generating=true`
  - `current_run.status=in_progress` 且 `current_run.updated_at` 不变：`2026-06-21T22:35:17.638612`
  - `llm_inflight=null`
- `logs/RS-20260621-101_writing_checkpoint.json`：
  - `status=in_progress`
  - `updated_at=2026-06-21T22:35:20.949520`
- `article/RS-20260621-101_paper.md` 仅包含占位文本（无正文）。

## Evidence Collected (instrumented repro)
- Debug Server: `http://127.0.0.1:7777`（session: `writing-078-stuck`）
- 新运行（复现）：
  - `research_id=RS-20260621-103`，run_id=`RUN-20260621232304-5477e1cf`
  - 可稳定收到 `llm_call_heartbeat`（每 10s）与 `llm_call_error(HTTP 504)` → `llm_call_start` 重试链路
  - 同时 `/api/research/state` 中 `research_activity.updated_at` 不会随心跳更新，但 `llm_inflight.updated_at` 会变化
  - 说明 “UI 进度/更新时间不动” 本身不足以判断卡死，需要引入 heartbeat/last_active 判定

## Next
- 增加“写作阶段关键步骤”与“卡点心跳”打点（不改业务逻辑），并复现一次 stuck 时抓到最后一个事件点。
- 根据证据决定最小修复：保证任何异常/阻塞都能回写 `failed` + `reason`，并提供 resume/retry 的操作路径。
