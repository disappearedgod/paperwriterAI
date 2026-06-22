from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.data_registry import (
    DATA_DIR,
    PAPERS_STATE_FILE,
    RESEARCH_DIR,
    SEED_MANIFEST,
    SEED_SUMMARIES,
    WORKFLOW_STATE_FILE,
    get_mongodb_config,
)


LITERATURE_COLLECTION = "literature_records"
BENCHMARK_COLLECTION = "benchmark_records"
FAILURE_COLLECTION = "failure_cases"
INNOVATION_COLLECTION = "innovation_tasks"
ALIGNMENT_COLLECTION = "benchmark_alignment"
REPLICATION_COLLECTION = "replication_runs"
ACTION_COLLECTION = "action_tasks"


def _safe_load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _get_client() -> Tuple[Optional[Any], Optional[str]]:
    try:
        from pymongo import MongoClient
    except Exception:
        return None, "pymongo_unavailable"

    cfg = get_mongodb_config()
    try:
        client = MongoClient(cfg["uri"], serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return client, None
    except Exception as e:
        return None, str(e)


def _ensure_indexes(db: Any) -> None:
    db[LITERATURE_COLLECTION].create_index([("arxiv_id", 1)], unique=True, sparse=True)
    db[LITERATURE_COLLECTION].create_index([("title", 1)])
    db[BENCHMARK_COLLECTION].create_index([("research_id", 1)], unique=True, sparse=True)
    db[BENCHMARK_COLLECTION].create_index([("paper_id", 1)], sparse=True)
    db[FAILURE_COLLECTION].create_index([("case_id", 1)], unique=True)
    db[FAILURE_COLLECTION].create_index([("research_id", 1), ("ts", -1)])
    db[INNOVATION_COLLECTION].create_index([("task_id", 1)], unique=True)
    db[INNOVATION_COLLECTION].create_index([("status", 1), ("source_type", 1)])
    db[ALIGNMENT_COLLECTION].create_index([("alignment_id", 1)], unique=True)
    db[ALIGNMENT_COLLECTION].create_index([("topic", 1), ("paper_kind", 1)])
    db[REPLICATION_COLLECTION].create_index([("run_id", 1)], unique=True)
    db[REPLICATION_COLLECTION].create_index([("research_id", 1)], unique=True, sparse=True)
    db[ACTION_COLLECTION].create_index([("task_id", 1)], unique=True)
    db[ACTION_COLLECTION].create_index([("status", 1), ("priority", -1), ("updated_at", -1)])
    db[ACTION_COLLECTION].create_index([("research_id", 1), ("action_type", 1)])


def _digest(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", errors="replace")).hexdigest()


def _paper_kind_of(title: str, topic: str) -> Tuple[str, str]:
    mix = (str(title or "") + "\n" + str(topic or "")).lower()
    seeds = (
        "survey",
        "seed",
        "arxiv:",
        "文献",
        "综述",
        "论文解读",
        "paper reading",
    )
    if any(s in mix for s in seeds):
        return "reference_analysis", "文献解读"
    return "generated", "AI撰写"


def _load_seed_summary_map() -> Dict[str, Dict[str, Any]]:
    raw = _safe_load_json(SEED_SUMMARIES)
    items: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        items = [x for x in raw if isinstance(x, dict)]
    elif isinstance(raw, dict):
        bucket = raw.get("papers") or raw.get("summaries") or []
        if isinstance(bucket, list):
            items = [x for x in bucket if isinstance(x, dict)]
    out: Dict[str, Dict[str, Any]] = {}
    for item in items:
        key = str(item.get("arxiv_id") or item.get("id") or "").strip()
        if key:
            out[key] = item
    return out


def _sync_literature_records(db: Any) -> int:
    manifest = _safe_load_json(SEED_MANIFEST) or {}
    seed_papers = manifest.get("seed_papers") or []
    summary_map = _load_seed_summary_map()
    count = 0
    for sp in seed_papers:
        if not isinstance(sp, dict):
            continue
        arxiv_id = str(sp.get("arxiv_id") or "").strip()
        summary = summary_map.get(arxiv_id) or {}
        record = {
            "arxiv_id": arxiv_id,
            "title": sp.get("title"),
            "authors": sp.get("authors") or [],
            "year": sp.get("year"),
            "categories": sp.get("categories") or [],
            "key_topics": sp.get("key_topics") or [],
            "pdf_path": sp.get("pdf_path"),
            "pdf_url": sp.get("pdf_url"),
            "arxiv_url": sp.get("arxiv_url"),
            "downloaded_at": sp.get("downloaded_at"),
            "summary": summary.get("summary") or summary.get("abstract") or "",
            "summary_preview": str(summary.get("text") or summary.get("summary") or summary.get("abstract") or "")[:1500],
            "extracted_at": summary.get("extracted_at") or summary.get("updated_at"),
            "has_pdf": bool(sp.get("pdf_path")),
            "source": "seed_library",
            "updated_at": datetime.now().isoformat(),
        }
        key = {"arxiv_id": arxiv_id} if arxiv_id else {"title": str(sp.get("title") or "")}
        db[LITERATURE_COLLECTION].update_one(key, {"$set": record}, upsert=True)
        count += 1
    return count


def _sync_benchmark_records(db: Any) -> int:
    papers_state = _safe_load_json(PAPERS_STATE_FILE) or {}
    papers = papers_state.get("papers") or []
    count = 0
    for p in papers:
        if not isinstance(p, dict):
            continue
        title = str(p.get("title") or "")
        topic = str(p.get("topic") or "")
        kind, kind_label = _paper_kind_of(title, topic)
        record = {
            "paper_id": p.get("id"),
            "research_id": p.get("research_id"),
            "branch_id": p.get("branch_id"),
            "title": title,
            "topic": topic,
            "status": p.get("status"),
            "quality_score": p.get("quality_score"),
            "paper_kind": kind,
            "paper_kind_label": kind_label,
            "artifacts": p.get("artifacts") or {},
            "file_path": p.get("file_path"),
            "research_dir": p.get("research_dir"),
            "created_at": p.get("created_at"),
            "updated_at": datetime.now().isoformat(),
        }
        rid = str(p.get("research_id") or "").strip()
        key = {"research_id": rid} if rid else {"paper_id": p.get("id")}
        db[BENCHMARK_COLLECTION].update_one(key, {"$set": record}, upsert=True)
        count += 1
    return count


def _pick_strategy_metrics(bt: Dict[str, Any], qa: Dict[str, Any]) -> Dict[str, Any]:
    baseline = {}
    benchmark = {}
    quantagent = {}
    ablations = {}
    universe = {}
    cost_model = {}
    template_version = ""

    if isinstance(bt, dict):
        template_version = str(bt.get("template_version") or "")
        universe = bt.get("universe") if isinstance(bt.get("universe"), dict) else {}
        cost_model = bt.get("cost_model") if isinstance(bt.get("cost_model"), dict) else {}
        results = bt.get("results") if isinstance(bt.get("results"), dict) else {}
        best_portfolio = {}
        for _, bucket in results.items():
            if not isinstance(bucket, dict):
                continue
            portfolio = bucket.get("portfolio") if isinstance(bucket.get("portfolio"), dict) else {}
            if portfolio:
                best_portfolio = portfolio
                break
        if best_portfolio:
            benchmark = (best_portfolio.get("benchmark") or {}).get("metrics") if isinstance(best_portfolio.get("benchmark"), dict) else {}
            strategies = best_portfolio.get("strategies") if isinstance(best_portfolio.get("strategies"), dict) else {}
            best_name = str(best_portfolio.get("best_strategy") or "")
            if best_name and isinstance(strategies.get(best_name), dict):
                baseline = (strategies.get(best_name) or {}).get("metrics") or {}
            elif strategies:
                first = next(iter(strategies.values()))
                if isinstance(first, dict):
                    baseline = first.get("metrics") or {}
            quantagent = (best_portfolio.get("quantagent") or {}).get("metrics") if isinstance(best_portfolio.get("quantagent"), dict) else {}

    if isinstance(qa, dict):
        template_version = str(qa.get("template_version") or template_version or "")
        if not universe:
            universe = {
                "symbols": [qa.get("stock")] if qa.get("stock") else [],
                "frequencies": [qa.get("frequency")] if qa.get("frequency") else [],
                "data_range": qa.get("data_range"),
            }
        if not cost_model:
            cost_model = qa.get("cost_model") if isinstance(qa.get("cost_model"), dict) else {}
        q = qa.get("quantagent") if isinstance(qa.get("quantagent"), dict) else {}
        if not quantagent:
            quantagent = q.get("metrics") if isinstance(q.get("metrics"), dict) else {}
        ablations = q.get("ablations") if isinstance(q.get("ablations"), dict) else {}
        if not baseline:
            baseline = qa.get("baseline_best_strategy_metrics") if isinstance(qa.get("baseline_best_strategy_metrics"), dict) else {}
        if not benchmark:
            benchmark = qa.get("benchmark") if isinstance(qa.get("benchmark"), dict) else {}

    return {
        "baseline_metrics": baseline or {},
        "benchmark_metrics": benchmark or {},
        "quantagent_metrics": quantagent or {},
        "ablations": ablations or {},
        "universe": universe or {},
        "cost_model": cost_model or {},
        "template_version": template_version,
    }


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if not s:
            return None
        s = s.replace("%", "")
        return float(s)
    except Exception:
        return None


def _metric(metrics: Dict[str, Any], key: str) -> Optional[float]:
    if not isinstance(metrics, dict):
        return None
    return _to_float(metrics.get(key))


def _cmp_primary(metrics: Dict[str, Any]) -> Tuple[str, Optional[float]]:
    sharpe = _metric(metrics, "sharpe_ratio")
    if sharpe is not None:
        return "sharpe_ratio", sharpe
    annual = _metric(metrics, "annual_return")
    if annual is not None:
        return "annual_return", annual
    total = _metric(metrics, "total_return")
    if total is not None:
        return "total_return", total
    return "none", None


def _is_valid_ablation(ablations: Dict[str, Any]) -> bool:
    if not isinstance(ablations, dict) or not ablations:
        return False
    non_empty = [k for k, v in ablations.items() if k and isinstance(v, dict) and bool(v.get("metrics") or v)]
    return len(non_empty) >= 3


def _compare_alignment(alignment: Dict[str, Any]) -> Dict[str, Any]:
    baseline = alignment.get("baseline_metrics") if isinstance(alignment.get("baseline_metrics"), dict) else {}
    benchmark = alignment.get("benchmark_metrics") if isinstance(alignment.get("benchmark_metrics"), dict) else {}
    qa = alignment.get("quantagent_metrics") if isinstance(alignment.get("quantagent_metrics"), dict) else {}
    ablations = alignment.get("ablations") if isinstance(alignment.get("ablations"), dict) else {}

    warnings: List[str] = []
    if not alignment.get("has_backtest_results"):
        warnings.append("missing_backtest_results")
    if not alignment.get("has_quantagent_results"):
        warnings.append("missing_quantagent_results")

    universe = alignment.get("universe") if isinstance(alignment.get("universe"), dict) else {}
    cost_model = alignment.get("cost_model") if isinstance(alignment.get("cost_model"), dict) else {}
    if not universe:
        warnings.append("missing_universe")
    if not cost_model:
        warnings.append("missing_cost_model")

    base_key, base_val = _cmp_primary(baseline)
    qa_key, qa_val = _cmp_primary(qa)
    bench_key, bench_val = _cmp_primary(benchmark)

    eps = 0.05
    winner = "unknown"
    if qa_val is None and base_val is None:
        winner = "unknown"
    elif qa_val is None:
        winner = "baseline"
    elif base_val is None:
        winner = "quantagent"
    else:
        if qa_val > base_val + eps:
            winner = "quantagent"
        elif base_val > qa_val + eps:
            winner = "baseline"
        else:
            winner = "tie"

    improvement_vs_baseline = None
    if qa_val is not None and base_val is not None:
        improvement_vs_baseline = qa_val - base_val

    improvement_vs_benchmark = None
    if qa_val is not None and bench_val is not None:
        improvement_vs_benchmark = qa_val - bench_val

    compare_lines: List[str] = []
    if qa_val is not None or base_val is not None:
        compare_lines.append(
            f"QuantAgent vs Baseline ({qa_key if qa_val is not None else '-'}): "
            f"{qa_val if qa_val is not None else '-'} vs {base_val if base_val is not None else '-'} -> {winner}"
        )
    if qa_val is not None and bench_val is not None:
        qa_vs_bench = "quantagent" if qa_val > bench_val + eps else ("benchmark" if bench_val > qa_val + eps else "tie")
        compare_lines.append(
            f"QuantAgent vs Benchmark ({qa_key}): {qa_val} vs {bench_val} -> {qa_vs_bench}"
        )

    has_valid_ablation = _is_valid_ablation(ablations)
    if not has_valid_ablation:
        warnings.append("insufficient_ablations")

    confidence = 100
    for w in warnings:
        if w in ("missing_backtest_results", "missing_quantagent_results"):
            confidence -= 35
        elif w in ("missing_universe", "missing_cost_model"):
            confidence -= 15
        elif w == "insufficient_ablations":
            confidence -= 20
        else:
            confidence -= 10
    if confidence < 0:
        confidence = 0

    return {
        "winner": winner,
        "primary_metric": qa_key if qa_key != "none" else base_key,
        "improvement_vs_baseline": improvement_vs_baseline,
        "improvement_vs_benchmark": improvement_vs_benchmark,
        "comparison_summary": " | ".join(compare_lines)[:800],
        "has_valid_ablation": has_valid_ablation,
        "alignment_warnings": warnings,
        "confidence_score": confidence,
    }


def _calc_replication_status(status: str, has_bt: bool, has_qa: bool, quality_score: Any) -> str:
    st = str(status or "").lower()
    if st == "generated" and has_bt and has_qa:
        return "reproduced"
    if st in ("paused", "failed", "error") and (has_bt or has_qa):
        return "partial"
    if st in ("paused", "failed", "error"):
        return "blocked"
    if quality_score is not None and has_bt:
        return "evaluated"
    return "pending"


def _sync_alignment_and_replication(db: Any) -> Dict[str, int]:
    papers_state = _safe_load_json(PAPERS_STATE_FILE) or {}
    papers = papers_state.get("papers") or []
    align_count = 0
    repl_count = 0

    for p in papers:
        if not isinstance(p, dict):
            continue
        title = str(p.get("title") or "")
        topic = str(p.get("topic") or "")
        research_id = str(p.get("research_id") or "").strip()
        paper_id = p.get("id")
        paper_kind, paper_kind_label = _paper_kind_of(title, topic)
        research_dir = Path(str(p.get("research_dir") or "")).expanduser()
        meta = _safe_load_json(research_dir / "meta.json") if research_dir else None

        bt = None
        qa = None
        if isinstance(meta, dict):
            arts = meta.get("artifacts") if isinstance(meta.get("artifacts"), dict) else {}
            bt_path = Path(str(arts.get("backtest_results") or ""))
            qa_path = Path(str(arts.get("quantagent_results") or ""))
            bt = _safe_load_json(bt_path) if str(bt_path) else None
            qa = _safe_load_json(qa_path) if str(qa_path) else None

        parsed = _pick_strategy_metrics(bt if isinstance(bt, dict) else {}, qa if isinstance(qa, dict) else {})
        has_bt = bool(bt)
        has_qa = bool(qa)
        alignment_id = _digest(f"{research_id}|{paper_id}|{topic}")
        alignment = {
            "alignment_id": alignment_id,
            "paper_id": paper_id,
            "research_id": research_id,
            "branch_id": p.get("branch_id"),
            "title": title,
            "topic": topic,
            "paper_kind": paper_kind,
            "paper_kind_label": paper_kind_label,
            "status": p.get("status"),
            "quality_score": p.get("quality_score"),
            "baseline_metrics": parsed.get("baseline_metrics") or {},
            "benchmark_metrics": parsed.get("benchmark_metrics") or {},
            "quantagent_metrics": parsed.get("quantagent_metrics") or {},
            "ablations": parsed.get("ablations") or {},
            "universe": parsed.get("universe") or {},
            "cost_model": parsed.get("cost_model") or {},
            "template_version": parsed.get("template_version") or "",
            "has_backtest_results": has_bt,
            "has_quantagent_results": has_qa,
            "updated_at": datetime.now().isoformat(),
        }
        alignment.update(_compare_alignment(alignment))
        db[ALIGNMENT_COLLECTION].update_one({"alignment_id": alignment_id}, {"$set": alignment}, upsert=True)
        align_count += 1

        run_id = _digest(f"replication|{research_id}|{paper_id}")
        replication = {
            "run_id": run_id,
            "paper_id": paper_id,
            "research_id": research_id,
            "title": title,
            "topic": topic,
            "paper_kind": paper_kind,
            "status": p.get("status"),
            "replication_status": _calc_replication_status(str(p.get("status") or ""), has_bt, has_qa, p.get("quality_score")),
            "quality_score": p.get("quality_score"),
            "research_dir": str(research_dir) if research_dir else "",
            "file_path": p.get("file_path"),
            "environment": {
                "template_version": parsed.get("template_version") or "",
                "cost_model": parsed.get("cost_model") or {},
            },
            "dataset": parsed.get("universe") or {},
            "artifacts_present": {
                "backtest_results": has_bt,
                "quantagent_results": has_qa,
                "markdown": bool((meta or {}).get("artifacts", {}).get("markdown")) if isinstance(meta, dict) else False,
                "code": bool((meta or {}).get("artifacts", {}).get("code")) if isinstance(meta, dict) else False,
            },
            "baseline_metrics": parsed.get("baseline_metrics") or {},
            "benchmark_metrics": parsed.get("benchmark_metrics") or {},
            "quantagent_metrics": parsed.get("quantagent_metrics") or {},
            "updated_at": datetime.now().isoformat(),
        }
        db[REPLICATION_COLLECTION].update_one({"run_id": run_id}, {"$set": replication}, upsert=True)
        repl_count += 1

    return {"benchmark_alignment": align_count, "replication_runs": repl_count}


def _action_from_warning(w: str) -> Tuple[str, str, str, str]:
    w = str(w or "").strip()
    if w == "missing_backtest_results":
        return ("run_backtest", "缺少 baseline 回测结果", "补跑 baseline 回测生成 backtest_results.json", "high")
    if w == "missing_quantagent_results":
        return ("run_quantagent", "缺少 QuantAgent 结果", "补跑 QuantAgent 实验生成 quantagent_results.json", "high")
    if w == "insufficient_ablations":
        return ("run_ablations", "消融实验不足", "补齐至少 3 组消融实验（quantagent_results.ablations）", "medium")
    if w == "missing_universe":
        return ("fill_metadata", "缺少数据范围", "补齐 universe（symbols/frequencies/start_date/end_date）", "medium")
    if w == "missing_cost_model":
        return ("fill_metadata", "缺少成本模型", "补齐 cost_model（commission_bps/slippage_bps/total_bps）", "medium")
    return ("investigate", f"需要排查: {w}", "排查该告警并补齐对应产物/元数据", "low")


def _sync_action_tasks(db: Any) -> int:
    rows = list(db[ALIGNMENT_COLLECTION].find({}, {"_id": 0}).sort("updated_at", -1).limit(500))
    count = 0
    now = datetime.now().isoformat()
    for a in rows:
        warnings = a.get("alignment_warnings") if isinstance(a.get("alignment_warnings"), list) else []
        if not warnings:
            continue
        for w in warnings:
            action_type, title, desc, priority = _action_from_warning(str(w))
            task_id = _digest(f"{a.get('alignment_id')}|{action_type}|{w}")
            record = {
                "task_id": task_id,
                "action_type": action_type,
                "title": title,
                "description": desc,
                "priority": priority,
                "status": "open",
                "research_id": a.get("research_id"),
                "paper_id": a.get("paper_id"),
                "topic": a.get("topic"),
                "evidence": {
                    "alignment_id": a.get("alignment_id"),
                    "warnings": warnings,
                    "winner": a.get("winner"),
                    "confidence_score": a.get("confidence_score"),
                },
                "updated_at": now,
            }
            db[ACTION_COLLECTION].update_one(
                {"task_id": task_id},
                {"$set": record, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            count += 1
    return count


def _load_failure_rows(limit: int = 500) -> List[Dict[str, Any]]:
    path = DATA_DIR / "failure_ledger.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    for line in lines[-max(1, int(limit)):]:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _sync_failure_cases(db: Any) -> int:
    rows = _load_failure_rows()
    count = 0
    for row in rows:
        research_id = str(row.get("research_id") or "").strip()
        phase = str(row.get("phase") or "").strip()
        error = str(row.get("error") or "").strip()
        ts = str(row.get("ts") or "")
        case_id = _digest(f"{research_id}|{phase}|{error}|{ts}")
        record = {
            "case_id": case_id,
            "research_id": research_id,
            "phase": phase,
            "error": error,
            "context": row.get("context") or {},
            "ts": ts,
            "updated_at": datetime.now().isoformat(),
        }
        db[FAILURE_COLLECTION].update_one({"case_id": case_id}, {"$set": record}, upsert=True)
        count += 1
    return count


def _sync_innovation_tasks(db: Any) -> int:
    workflow = _safe_load_json(WORKFLOW_STATE_FILE) or {}
    papers_state = _safe_load_json(PAPERS_STATE_FILE) or {}
    lit = workflow.get("literature_review") or {}
    current_run = papers_state.get("current_run") if isinstance(papers_state.get("current_run"), dict) else {}
    run_id = str(current_run.get("run_id") or "")
    topic = str(current_run.get("topic") or workflow.get("project_name") or "")

    tasks: List[Dict[str, Any]] = []
    for idx, text in enumerate(lit.get("research_gaps") or [], start=1):
        val = str(text or "").strip()
        if not val:
            continue
        tasks.append({
            "source_type": "research_gap",
            "title": f"研究空白 {idx}",
            "description": val,
            "tags": lit.get("key_themes") or [],
        })
    for idx, text in enumerate(lit.get("potential_innovations") or [], start=1):
        val = str(text or "").strip()
        if not val:
            continue
        tasks.append({
            "source_type": "potential_innovation",
            "title": f"潜在创新 {idx}",
            "description": val,
            "tags": lit.get("key_themes") or [],
        })
    for item in papers_state.get("hypotheses") or []:
        if not isinstance(item, dict):
            continue
        tasks.append({
            "source_type": "hypothesis",
            "title": str(item.get("title") or item.get("id") or "未命名假设"),
            "description": str(item.get("description") or ""),
            "tags": item.get("tags") or [],
        })

    count = 0
    for idx, task in enumerate(tasks, start=1):
        source_type = str(task.get("source_type") or "unknown")
        title = str(task.get("title") or "").strip()
        desc = str(task.get("description") or "").strip()
        if not title and not desc:
            continue
        task_id = _digest(f"{source_type}|{title}|{desc}")
        record = {
            "task_id": task_id,
            "source_type": source_type,
            "title": title or f"{source_type}_{idx}",
            "description": desc,
            "tags": task.get("tags") or [],
            "topic": topic,
            "run_id": run_id,
            "status": "proposed",
            "updated_at": datetime.now().isoformat(),
        }
        db[INNOVATION_COLLECTION].update_one({"task_id": task_id}, {"$set": record}, upsert=True)
        count += 1
    return count


def sync_research_intelligence() -> Dict[str, Any]:
    client, err = _get_client()
    if err:
        return {"success": False, "error": err}
    cfg = get_mongodb_config()
    db = client[cfg["db"]]
    try:
        _ensure_indexes(db)
        result = {
            "literature_records": _sync_literature_records(db),
            "benchmark_records": _sync_benchmark_records(db),
            "failure_cases": _sync_failure_cases(db),
            "innovation_tasks": _sync_innovation_tasks(db),
        }
        result.update(_sync_alignment_and_replication(db))
        result["action_tasks"] = _sync_action_tasks(db)
        client.close()
        return {"success": True, "synced": result}
    except Exception as e:
        client.close()
        return {"success": False, "error": str(e)[:200]}


def get_research_intelligence_summary() -> Dict[str, Any]:
    client, err = _get_client()
    if err:
        return {"success": False, "error": err}
    cfg = get_mongodb_config()
    db = client[cfg["db"]]
    try:
        payload = {
            "literature_records": db[LITERATURE_COLLECTION].estimated_document_count(),
            "benchmark_records": db[BENCHMARK_COLLECTION].estimated_document_count(),
            "failure_cases": db[FAILURE_COLLECTION].estimated_document_count(),
            "innovation_tasks": db[INNOVATION_COLLECTION].estimated_document_count(),
            "benchmark_alignment": db[ALIGNMENT_COLLECTION].estimated_document_count(),
            "replication_runs": db[REPLICATION_COLLECTION].estimated_document_count(),
            "action_tasks": db[ACTION_COLLECTION].estimated_document_count(),
        }
        latest_failures = list(db[FAILURE_COLLECTION].find({}, {"_id": 0}).sort("ts", -1).limit(5))
        latest_tasks = list(db[INNOVATION_COLLECTION].find({}, {"_id": 0}).sort("updated_at", -1).limit(5))
        latest_alignment = list(db[ALIGNMENT_COLLECTION].find({}, {"_id": 0}).sort("updated_at", -1).limit(5))
        latest_actions = list(db[ACTION_COLLECTION].find({}, {"_id": 0}).sort("updated_at", -1).limit(5))
        client.close()
        return {
            "success": True,
            "summary": payload,
            "latest_failures": latest_failures,
            "latest_tasks": latest_tasks,
            "latest_alignment": latest_alignment,
            "latest_actions": latest_actions,
        }
    except Exception as e:
        client.close()
        return {"success": False, "error": str(e)[:200]}


def get_benchmark_alignment(limit: int = 50, topic: str = "") -> Dict[str, Any]:
    client, err = _get_client()
    if err:
        return {"success": False, "error": err}
    cfg = get_mongodb_config()
    db = client[cfg["db"]]
    try:
        query: Dict[str, Any] = {}
        if str(topic or "").strip():
            query["topic"] = {"$regex": str(topic).strip()}
        rows = list(db[ALIGNMENT_COLLECTION].find(query, {"_id": 0}).sort("updated_at", -1).limit(max(1, int(limit or 50))))
        client.close()
        return {"success": True, "count": len(rows), "rows": rows}
    except Exception as e:
        client.close()
        return {"success": False, "error": str(e)[:200]}


def get_benchmark_comparison(limit: int = 50, topic: str = "", winner: str = "") -> Dict[str, Any]:
    client, err = _get_client()
    if err:
        return {"success": False, "error": err}
    cfg = get_mongodb_config()
    db = client[cfg["db"]]
    try:
        query: Dict[str, Any] = {}
        if str(topic or "").strip():
            query["topic"] = {"$regex": str(topic).strip()}
        if str(winner or "").strip():
            query["winner"] = str(winner).strip()
        rows = list(
            db[ALIGNMENT_COLLECTION]
            .find(query, {"_id": 0})
            .sort([("confidence_score", -1), ("improvement_vs_baseline", -1), ("updated_at", -1)])
            .limit(max(1, int(limit or 50)))
        )
        for r in rows:
            if "winner" not in r or "comparison_summary" not in r:
                r.update(_compare_alignment(r))
        client.close()
        return {"success": True, "count": len(rows), "rows": rows}
    except Exception as e:
        client.close()
        return {"success": False, "error": str(e)[:200]}


def get_replication_runs(limit: int = 50, status: str = "") -> Dict[str, Any]:
    client, err = _get_client()
    if err:
        return {"success": False, "error": err}
    cfg = get_mongodb_config()
    db = client[cfg["db"]]
    try:
        query: Dict[str, Any] = {}
        if str(status or "").strip():
            query["replication_status"] = str(status).strip()
        rows = list(db[REPLICATION_COLLECTION].find(query, {"_id": 0}).sort("updated_at", -1).limit(max(1, int(limit or 50))))
        client.close()
        return {"success": True, "count": len(rows), "rows": rows}
    except Exception as e:
        client.close()
        return {"success": False, "error": str(e)[:200]}


def get_action_tasks(limit: int = 50, status: str = "", action_type: str = "") -> Dict[str, Any]:
    client, err = _get_client()
    if err:
        return {"success": False, "error": err}
    cfg = get_mongodb_config()
    db = client[cfg["db"]]
    try:
        query: Dict[str, Any] = {}
        if str(status or "").strip():
            query["status"] = str(status).strip()
        if str(action_type or "").strip():
            query["action_type"] = str(action_type).strip()
        rows = list(
            db[ACTION_COLLECTION]
            .find(query, {"_id": 0})
            .sort([("priority", -1), ("updated_at", -1)])
            .limit(max(1, int(limit or 50)))
        )
        client.close()
        return {"success": True, "count": len(rows), "rows": rows}
    except Exception as e:
        client.close()
        return {"success": False, "error": str(e)[:200]}
