#!/usr/bin/env python3
"""
FARS 论文评分与迭代重生成服务器
"""

from flask import Flask, request, jsonify, send_from_directory, make_response
import os
import sys
import json
import re
import requests
import threading
import time
import subprocess
import mimetypes
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from tools.quality_pipeline import (
    FastDetectGPTDetector,
    PaperReviewer,
    QualityReporter,
    run_quality_pipeline,
    AIDetectionResult,
    PaperReviewResult,
    QualityReport,
)
from core.research_archive import (
    RESEARCH_DIR,
    allocate_research_id,
    bump_research_seq,
    create_research_workspace,
    artifact_filenames,
    save_article_markdown,
    scaffold_experiment_code,
    write_meta,
    paper_record_paths,
    artifacts_for_api,
    research_root,
    build_artifacts_record,
)
from core.data_registry import (
    get_registry,
    get_paper_generation_context,
    PAPERS_STATE_FILE,
    WORKFLOW_STATE_FILE,
)
from core.mongo_index import index_paper_record, query_papers, check_market_data
from core.research_reset import reset_research
from core.research_graphs import (
    build_author_network_from_seed_papers,
    build_citation_network,
)
from core.seed_library import list_seed_papers, get_pdf_path, fetch_new_papers
from core.research_runner import ResearchRunner
from core.research_engine import (
    load_checkpoint as load_research_checkpoint,
    resume_research as resume_research_checkpoint,
    build_author_network,
)
from prompts.templates import (
    fill_perspective_prompt,
    fill_question_prompt,
    fill_literature_review_prompt,
    fill_introduction_prompt,
    fill_review_prompt,
    fill_revision_prompt,
    fill_full_paper_prompt,
)

app = Flask(__name__, static_folder='docs', static_url_path='')
app.logger.setLevel(logging.INFO)

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
_CONFIG_LOCAL_PATH = Path(__file__).resolve().parent / "config.local.json"

_app_config: Dict[str, Any] = {}
_llm_config: Dict[str, Any] = {}
_llm_providers: Dict[str, Any] = {}
_config_mtime_ns: Tuple[Optional[int], Optional[int]] = (None, None)

#region debug-point writing-stuck-078-reporter
_DBG_CACHE: Dict[str, str] = {}
_DBG_CTX = threading.local()

def _dbg_load() -> None:
    if _DBG_CACHE.get("loaded") == "1":
        return
    _DBG_CACHE["loaded"] = "1"
    if os.environ.get("DEBUG_SERVER_URL"):
        _DBG_CACHE["url"] = os.environ["DEBUG_SERVER_URL"]
        _DBG_CACHE["session"] = os.environ.get("DEBUG_SESSION_ID", "")
        return
    try:
        env_dir = Path(__file__).resolve().parent / ".dbg"
        for name in ("writing-078-stuck.env", "writing-stuck-078.env"):
            env_path = env_dir / name
            if not env_path.exists():
                continue
            for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "DEBUG_SERVER_URL":
                    _DBG_CACHE["url"] = v
                elif k == "DEBUG_SESSION_ID":
                    _DBG_CACHE["session"] = v
            break
    except Exception:
        return

def _dbg_set_context(*, research_id: str, research_dir: str) -> None:
    try:
        _DBG_CTX.research_id = str(research_id or "")
        _DBG_CTX.research_dir = str(research_dir or "")
        _DBG_CACHE["research_id"] = str(research_id or "")
        _DBG_CACHE["research_dir"] = str(research_dir or "")
    except Exception:
        return

def _dbg_clear_context() -> None:
    try:
        _DBG_CTX.research_id = ""
        _DBG_CTX.research_dir = ""
        _DBG_CACHE.pop("research_id", None)
        _DBG_CACHE.pop("research_dir", None)
    except Exception:
        return

def _dbg_log_path() -> Optional[Path]:
    research_dir = getattr(_DBG_CTX, "research_dir", "") or (_DBG_CACHE.get("research_dir") or "")
    if not research_dir:
        return None
    root = Path(research_dir)
    session_id = _DBG_CACHE.get("session", "writing-stuck-078") or "writing-stuck-078"
    safe = re.sub(r"[^a-z0-9._-]+", "_", str(session_id).lower())
    return root / "logs" / f"trae-debug-log-{safe}.ndjson"

def _dbg_console_line(body: Dict[str, Any]) -> str:
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    keys = [
        ("run_id", payload.get("run_id")),
        ("research_id", payload.get("research_id")),
        ("phase", payload.get("phase")),
        ("step", payload.get("step")),
        ("attempt", payload.get("attempt")),
        ("elapsed_s", payload.get("elapsed_s")),
        ("status", payload.get("status")),
        ("error", payload.get("error")),
    ]
    tail = " ".join([f"{k}={v}" for k, v in keys if v not in (None, "", 0, 0.0)])
    return f"[dbg:{body.get('session','')}] {body.get('ts','')} {body.get('event','')} {tail}".rstrip()

def _dbg_event(name: str, payload: Dict[str, Any]) -> None:
    _dbg_load()
    session_id = _DBG_CACHE.get("session", "writing-stuck-078")
    run_id = payload.get("run_id") if isinstance(payload, dict) else None
    body = {
        "ts": datetime.now().isoformat(),
        "event": name,
        "session": session_id,
        "sessionId": session_id,
        "runId": (str(run_id) if run_id else ""),
        "payload": payload,
    }
    try:
        line = _dbg_console_line(body)
        if line:
            app.logger.info(line)
    except Exception:
        pass
    try:
        log_path = _dbg_log_path()
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8", errors="replace") as f:
                f.write(json.dumps(body, ensure_ascii=False) + "\n")
    except Exception:
        pass
    url = _DBG_CACHE.get("url")
    if not url:
        return
    try:
        requests.post(url, json=body, timeout=0.8)
    except Exception:
        return
#endregion debug-point writing-stuck-078-reporter


def _file_mtime_ns(path: Path) -> Optional[int]:
    try:
        return path.stat().st_mtime_ns
    except Exception:
        return None


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for k, v in override.items():
            if k in merged:
                merged[k] = _deep_merge(merged[k], v)
            else:
                merged[k] = v
        return merged
    return override


def _load_config_file(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _reload_config() -> None:
    global _app_config, _llm_config, _llm_providers, _config_mtime_ns
    base = _load_config_file(_CONFIG_PATH)
    local = _load_config_file(_CONFIG_LOCAL_PATH)
    _app_config = _deep_merge(base, local) if base or local else {}
    _llm_config = dict((_app_config.get("llm") or {}))
    _llm_providers = dict((_app_config.get("llm_providers") or {}))
    _config_mtime_ns = (_file_mtime_ns(_CONFIG_PATH), _file_mtime_ns(_CONFIG_LOCAL_PATH))


def _maybe_reload_config() -> None:
    global _config_mtime_ns
    current = (_file_mtime_ns(_CONFIG_PATH), _file_mtime_ns(_CONFIG_LOCAL_PATH))
    if current != _config_mtime_ns:
        _reload_config()


def _is_reasonable_api_key(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    key = value.strip()
    if not key:
        return False
    if len(key) < 8 or len(key) > 256:
        return False
    if any(ch.isspace() for ch in key):
        return False
    if any(ord(ch) > 127 for ch in key):
        return False
    return True


def _save_local_llm_config(llm: Dict[str, Any], llm_providers: Dict[str, Any]) -> None:
    local = _load_config_file(_CONFIG_LOCAL_PATH)
    existing_llm = dict(local.get("llm") or {})
    existing_providers = dict(local.get("llm_providers") or {})

    def merge_preserve_key(new_cfg: Dict[str, Any], old_cfg: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(old_cfg)
        merged.update(new_cfg)
        if (not new_cfg.get("api_key")) and old_cfg.get("api_key"):
            merged["api_key"] = old_cfg.get("api_key")
        if merged.get("api_key") and (not _is_reasonable_api_key(merged.get("api_key"))):
            merged["api_key"] = ""
        return merged

    local["llm"] = merge_preserve_key(llm, existing_llm)

    merged_providers: Dict[str, Any] = dict(existing_providers)
    for name, cfg in (llm_providers or {}).items():
        if isinstance(cfg, dict):
            merged_providers[name] = merge_preserve_key(cfg, dict(existing_providers.get(name) or {}))
    local["llm_providers"] = merged_providers
    _CONFIG_LOCAL_PATH.write_text(json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_provider_api_key(provider: str, provider_cfg: Dict[str, Any]) -> str:
    env_map = {
        "minimax": "MINIMAX_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "custom": "CUSTOM_API_KEY",
    }
    env_key = env_map.get(provider)
    if env_key and os.environ.get(env_key):
        key = os.environ.get(env_key) or ""
        return key if _is_reasonable_api_key(key) else ""
    key = str(provider_cfg.get("api_key") or "")
    return key if _is_reasonable_api_key(key) else ""


def get_effective_llm_config() -> Dict[str, Any]:
    _maybe_reload_config()
    provider = str(_llm_config.get("provider") or "minimax")
    provider_cfg = dict((_llm_providers.get(provider) or {}))
    merged = dict(provider_cfg)
    merged.update(_llm_config)
    merged["provider"] = provider
    merged["api_key"] = _get_provider_api_key(provider, merged)
    if os.environ.get("LLM_BASE_URL"):
        merged["base_url"] = str(os.environ.get("LLM_BASE_URL") or "").strip()
    return merged


def _llm_endpoint(provider: str, base_url: str) -> str:
    base = (base_url or "").strip()
    if not base:
        if provider == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta"
        if provider == "openai":
            return "https://api.openai.com/v1"
        return "https://api.minimax.chat/v1"
    return base


def _llm_chat_url(provider: str, base_url: str) -> str:
    base = _llm_endpoint(provider, base_url).rstrip("/")
    if provider == "gemini":
        return base
    if provider == "minimax":
        if (
            base.endswith("/chat/completions")
            or base.endswith("/text/chatcompletion_pro")
            or base.endswith("/text/chatcompletion_v2")
        ):
            return base
        return f"{base}/chat/completions"
    if base.endswith("/chat/completions") or base.endswith("/text/chatcompletion_pro"):
        return base
    return f"{base}/chat/completions"


def _llm_available(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    provider = cfg.get("provider")
    if provider in ("openai", "minimax", "gemini") and not cfg.get("api_key"):
        return False, f"{provider} api_key 未配置"
    if provider == "custom" and cfg.get("base_url") and cfg.get("model") and not cfg.get("api_key"):
        return True, ""
    if provider == "custom" and (not cfg.get("base_url") or not cfg.get("model")):
        return False, "custom base_url/model 未配置"
    return True, ""


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "", encoding="utf-8", errors="replace")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")


def _build_author_network_from_seed_papers(papers: List[dict]) -> Dict[str, Any]:
    return build_author_network_from_seed_papers(papers)


def _tokenize_for_overlap(text: str) -> List[str]:
    return []


def _build_citation_network(*, papers_data: dict, seed_papers: List[dict]) -> Dict[str, Any]:
    return build_citation_network(papers_data=papers_data, seed_papers=seed_papers)


_LLM_USAGE_LOCK = threading.Lock()
_LLM_USAGE_BUFFER: Dict[str, Dict[str, Dict[str, int]]] = {}
_LLM_USAGE_META: Dict[str, Dict[str, str]] = {}
_LLM_USAGE_LAST_FLUSH_TS = 0.0

_LLM_INFLIGHT_LOCK = threading.Lock()
_LLM_INFLIGHT: Dict[str, Dict[str, Any]] = {}


def _llm_inflight_start(
    *,
    run_id: str,
    phase: str,
    provider: str,
    model: str,
    attempt: int,
    req_id: str,
    prompt_len: int,
    max_tokens: int,
    timeout_s: int,
) -> None:
    if not run_id:
        return
    with _LLM_INFLIGHT_LOCK:
        _LLM_INFLIGHT[run_id] = {
            "run_id": run_id,
            "phase": str(phase or "unknown"),
            "provider": str(provider or ""),
            "model": str(model or ""),
            "attempt": int(attempt or 0),
            "req_id": str(req_id or ""),
            "prompt_len": int(prompt_len or 0),
            "max_tokens": int(max_tokens or 0),
            "timeout_s": int(timeout_s or 0),
            "started_at": datetime.now().isoformat(),
            "elapsed_s": 0.0,
            "updated_at": datetime.now().isoformat(),
        }


def _llm_inflight_heartbeat(*, run_id: str, req_id: str, elapsed_s: float) -> None:
    if not run_id:
        return
    with _LLM_INFLIGHT_LOCK:
        row = _LLM_INFLIGHT.get(run_id)
        if not isinstance(row, dict):
            return
        if str(row.get("req_id") or "") != str(req_id or ""):
            return
        row["elapsed_s"] = float(elapsed_s or 0.0)
        row["updated_at"] = datetime.now().isoformat()
        _LLM_INFLIGHT[run_id] = row


def _llm_inflight_end(*, run_id: str, req_id: str) -> None:
    if not run_id:
        return
    with _LLM_INFLIGHT_LOCK:
        row = _LLM_INFLIGHT.get(run_id)
        if not isinstance(row, dict):
            return
        if str(row.get("req_id") or "") != str(req_id or ""):
            return
        _LLM_INFLIGHT.pop(run_id, None)


def _llm_inflight_snapshot(papers_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    papers_data = papers_data or load_papers()
    current_run = papers_data.get("current_run") if isinstance(papers_data.get("current_run"), dict) else {}
    run_id = str(current_run.get("run_id") or "")
    if not run_id:
        return None
    with _LLM_INFLIGHT_LOCK:
        row = _LLM_INFLIGHT.get(run_id)
        if not isinstance(row, dict):
            return None
        return dict(row)


def _bump_llm_usage(
    *,
    run_id: str,
    phase: str,
    provider: str,
    model: str,
    usage: Optional[Dict[str, Any]] = None,
    ok: bool = True,
    prompt_len: Optional[int] = None,
    content_len: Optional[int] = None,
) -> None:
    if not run_id:
        return
    p = str(phase or "unknown")
    with _LLM_USAGE_LOCK:
        by_phase = _LLM_USAGE_BUFFER.setdefault(run_id, {})
        row = by_phase.setdefault(
            p,
            {
                "calls": 0,
                "errors": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "est_prompt_tokens": 0,
                "est_completion_tokens": 0,
                "est_total_tokens": 0,
            },
        )
        row["calls"] += 1
        if not ok:
            row["errors"] += 1
        if isinstance(usage, dict):
            pt = int(usage.get("prompt_tokens") or 0)
            ct = int(usage.get("completion_tokens") or 0)
            tt = int(usage.get("total_tokens") or (pt + ct))
            row["prompt_tokens"] += pt
            row["completion_tokens"] += ct
            row["total_tokens"] += tt
        else:
            try:
                pl = int(prompt_len or 0)
                cl = int(content_len or 0)
                if pl > 0:
                    row["est_prompt_tokens"] += max(1, (pl + 3) // 4)
                if cl > 0:
                    row["est_completion_tokens"] += max(1, (cl + 3) // 4)
                row["est_total_tokens"] = int(row.get("est_prompt_tokens") or 0) + int(row.get("est_completion_tokens") or 0)
            except Exception:
                pass
        _LLM_USAGE_META[run_id] = {"provider": str(provider or ""), "model": str(model or "")}


def _flush_llm_usage(papers_data: Dict[str, Any]) -> bool:
    global _LLM_USAGE_LAST_FLUSH_TS
    current_run = papers_data.get("current_run") if isinstance(papers_data.get("current_run"), dict) else {}
    run_id = current_run.get("run_id") or ""
    if not run_id:
        return False

    with _LLM_USAGE_LOCK:
        buffered = _LLM_USAGE_BUFFER.get(run_id)
        meta = _LLM_USAGE_META.get(run_id) or {}
        if not buffered:
            return False

        existing = papers_data.get("run_metrics") if isinstance(papers_data.get("run_metrics"), dict) else {}
        if existing.get("run_id") != run_id:
            existing = {"run_id": run_id, "phases": {}}
        phases = existing.get("phases") if isinstance(existing.get("phases"), dict) else {}

        for phase, row in buffered.items():
            dst = phases.get(phase) if isinstance(phases.get(phase), dict) else {
                "calls": 0,
                "errors": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "est_prompt_tokens": 0,
                "est_completion_tokens": 0,
                "est_total_tokens": 0,
            }
            for k in ("calls", "errors", "prompt_tokens", "completion_tokens", "total_tokens", "est_prompt_tokens", "est_completion_tokens", "est_total_tokens"):
                dst[k] = int(dst.get(k) or 0) + int(row.get(k) or 0)
            phases[phase] = dst

        existing["phases"] = phases
        existing["provider"] = meta.get("provider") or existing.get("provider")
        existing["model"] = meta.get("model") or existing.get("model")
        existing["updated_at"] = datetime.now().isoformat()
        papers_data["run_metrics"] = existing

        _LLM_USAGE_BUFFER.pop(run_id, None)
        if not _LLM_USAGE_BUFFER:
            _LLM_USAGE_META.pop(run_id, None)

        _LLM_USAGE_LAST_FLUSH_TS = time.time()
        return True


def _decorate_stage_experiments(papers_data: Dict[str, Any]) -> List[dict]:
    experiments = papers_data.get("experiments") or []
    if not experiments:
        return []

    activity = papers_data.get("research_activity") if isinstance(papers_data.get("research_activity"), dict) else {}
    phase = str(activity.get("phase") or "idle")
    overall_progress = float(activity.get("progress") or 0.0)
    inflight = _llm_inflight_snapshot(papers_data)

    registry = get_registry() or {}
    seed_count = int((registry.get("seed_papers") or {}).get("count") or 0)
    hypotheses_count = len(papers_data.get("hypotheses") or [])
    papers_count = len(papers_data.get("papers") or [])

    run_metrics = papers_data.get("run_metrics") if isinstance(papers_data.get("run_metrics"), dict) else {}
    phase_metrics = run_metrics.get("phases") if isinstance(run_metrics.get("phases"), dict) else {}

    def _elapsed_seconds(row: Dict[str, Any]) -> float:
        if not isinstance(row, dict):
            return 0.0
        try:
            started_at = row.get("started_at")
            completed_at = row.get("completed_at")
            if not started_at:
                return 0.0
            started = datetime.fromisoformat(str(started_at))
            finished = datetime.fromisoformat(str(completed_at)) if completed_at else datetime.now()
            return max(0.0, (finished - started).total_seconds())
        except Exception:
            return 0.0

    def _sum_usage(phases: List[str]) -> Dict[str, int]:
        total = {
            "calls": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "est_prompt_tokens": 0,
            "est_completion_tokens": 0,
            "est_total_tokens": 0,
        }
        for p in phases:
            row = phase_metrics.get(p)
            if not isinstance(row, dict):
                continue
            for k in total.keys():
                total[k] += int(row.get(k) or 0)
        return total

    decorated = []
    for exp in experiments:
        exp_dict = dict(exp)
        stage_phases = exp_dict.get("stage_phases") if isinstance(exp_dict.get("stage_phases"), list) else []
        usage = _sum_usage([str(p) for p in stage_phases])

        progress_pct = 0.0
        if exp_dict.get("status") == "success":
            progress_pct = 100.0
        elif exp_dict.get("status") == "experimenting":
            if exp_dict.get("id") == "exp_1":
                progress_pct = {"starting": 10.0, "literature_review": 45.0, "hypothesis": 80.0}.get(phase, overall_progress * 100.0)
            elif exp_dict.get("id") == "exp_2":
                progress_pct = 50.0
            else:
                progress_pct = max(0.0, min(100.0, overall_progress * 100.0))

        metrics: Dict[str, Any] = {
            "进度%": progress_pct,
            "LLM调用": usage["calls"],
            "Token": usage["total_tokens"],
            "Token估算": usage["est_total_tokens"],
            "失败": usage["errors"],
        }
        if exp_dict.get("id") == "exp_1":
            metrics["种子论文"] = seed_count
            metrics["假设数"] = hypotheses_count
            lit_row = phase_metrics.get("literature_review") if isinstance(phase_metrics.get("literature_review"), dict) else {}
            hyp_row = phase_metrics.get("hypothesis") if isinstance(phase_metrics.get("hypothesis"), dict) else {}
            metrics["阅读耗时(s)"] = lit_row.get("read_seconds") or 0.0
            metrics["分析耗时(s)"] = lit_row.get("analysis_seconds") or 0.0
            metrics["单篇阅读(s)"] = lit_row.get("avg_read_seconds_per_paper") or 0.0
            metrics["单篇分析(s)"] = lit_row.get("avg_analysis_seconds_per_paper") or 0.0
            metrics["假设耗时(s)"] = _elapsed_seconds(hyp_row)
        if exp_dict.get("id") == "exp_3":
            metrics["产物论文"] = papers_count
            write_row = phase_metrics.get("writing") if isinstance(phase_metrics.get("writing"), dict) else {}
            metrics["写作用时(s)"] = write_row.get("writing_seconds") or _elapsed_seconds(write_row)
            if inflight and str(inflight.get("phase") or "") == "writing":
                metrics["LLM进行中"] = 1.0
                metrics["本次LLM等待(s)"] = float(inflight.get("elapsed_s") or 0.0)
        if exp_dict.get("id") == "exp_2":
            graph_row = phase_metrics.get("experimenting") if isinstance(phase_metrics.get("experimenting"), dict) else {}
            metrics["图谱耗时(s)"] = graph_row.get("graph_build_seconds") or _elapsed_seconds(graph_row)
            metrics["作者数"] = graph_row.get("author_count") or 0
            metrics["机构数"] = graph_row.get("institution_count") or 0
            metrics["引用边"] = graph_row.get("citation_edge_count") or 0

        exp_dict["metrics"] = metrics
        decorated.append(exp_dict)

    return decorated


def call_llm(prompt: str, *, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
    cfg = get_effective_llm_config()
    ok, reason = _llm_available(cfg)
    if not ok:
        return f"LLM 未就绪: {reason}"

    session = requests.Session()
    session.trust_env = False

    provider = cfg["provider"]
    model = str(cfg.get("model") or ("abab6.5s-chat" if provider == "minimax" else "gpt-4o"))
    temp = float(temperature if temperature is not None else cfg.get("temperature", 0.7))
    mt = int(max_tokens if max_tokens is not None else cfg.get("max_tokens", 4096))
    timeout_s = 600  # 统一600s超时，论文生成需要更长时间
    papers_ctx = load_papers()
    run_id = ((papers_ctx.get("current_run") or {}).get("run_id") if isinstance(papers_ctx.get("current_run"), dict) else "") or ""
    phase = str((papers_ctx.get("research_activity") or {}).get("phase") if isinstance(papers_ctx.get("research_activity"), dict) else "unknown")
    cfg_timeout = cfg.get("request_timeout_s")
    try:
        cfg_timeout_s = int(cfg_timeout) if cfg_timeout is not None else 0
    except Exception:
        cfg_timeout_s = 0
    try:
        env_timeout_s = int(os.environ.get("LLM_REQUEST_TIMEOUT_S") or 0)
    except Exception:
        env_timeout_s = 0
    if env_timeout_s > 0:
        timeout_s = env_timeout_s
    if cfg_timeout_s > 0:
        timeout_s = cfg_timeout_s
    elif provider == "minimax" and phase == "writing":
        timeout_s = min(timeout_s, 600)  # writing阶段最多600秒
    prompt_len = len(prompt or "")
    prompt_sample = (prompt or "")[:200]
    _dbg_event("llm_call_prepare", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "timeout_s": timeout_s, "max_tokens": mt, "temperature": temp, "prompt_len": prompt_len, "prompt_sample": prompt_sample})

    if provider == "gemini":
        req_id = str(uuid4())
        _llm_inflight_start(run_id=run_id, phase=phase, provider=provider, model=model, attempt=1, req_id=req_id, prompt_len=prompt_len, max_tokens=mt, timeout_s=timeout_s)
        base = _llm_endpoint(provider, str(cfg.get("base_url") or "")).rstrip("/")
        key = cfg.get("api_key") or ""
        url = f"{base}/models/{model}:generateContent?key={key}"
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temp, "maxOutputTokens": mt},
        }
        t0 = time.time()
        resp_box: Dict[str, Any] = {}
        exc_box: Dict[str, Any] = {}

        def _do_post_gemini():
            try:
                resp_box["resp"] = session.post(url, json=body, timeout=timeout_s)
            except Exception as e:
                exc_box["exc"] = e

        th = threading.Thread(target=_do_post_gemini, daemon=True)
        th.start()
        th.join(timeout_s)
        if th.is_alive():
            _llm_inflight_end(run_id=run_id, req_id=req_id)
            _dbg_event("llm_call_timeout", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": 1, "error": f"total timeout {timeout_s}s"})
            _bump_llm_usage(run_id=run_id, phase=phase, provider=provider, model=model, ok=False)
            raise requests.exceptions.Timeout(f"llm total timeout ({timeout_s}s)")
        if exc_box.get("exc"):
            _llm_inflight_end(run_id=run_id, req_id=req_id)
            raise exc_box["exc"]
        resp = resp_box.get("resp")
        if resp is None:
            _llm_inflight_end(run_id=run_id, req_id=req_id)
            raise RuntimeError("llm request failed")
        _llm_inflight_heartbeat(run_id=run_id, req_id=req_id, elapsed_s=time.time() - t0)
        data = resp.json()
        if "error" in data:
            _llm_inflight_end(run_id=run_id, req_id=req_id)
            _bump_llm_usage(run_id=run_id, phase=phase, provider=provider, model=model, ok=False)
            raise RuntimeError(data["error"].get("message") or str(data["error"]))
        candidates = data.get("candidates") or []
        if not candidates:
            _llm_inflight_end(run_id=run_id, req_id=req_id)
            _bump_llm_usage(run_id=run_id, phase=phase, provider=provider, model=model, ok=True, prompt_len=prompt_len, content_len=0)
            return ""
        content = (candidates[0].get("content") or {}).get("parts") or []
        _llm_inflight_end(run_id=run_id, req_id=req_id)
        text_out = (content[0].get("text") if content else "") or ""
        _bump_llm_usage(run_id=run_id, phase=phase, provider=provider, model=model, ok=True, prompt_len=prompt_len, content_len=len(text_out))
        return text_out

    url = _llm_chat_url(provider, str(cfg.get("base_url") or ""))
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temp,
        "max_tokens": mt,  # MiniMax也使用max_tokens (不是max_completion_tokens)
    }

    last_exc: Optional[Exception] = None
    for attempt in range(3):
        try:
            req_id = str(uuid4())
            stop_evt = threading.Event()

            def _hb():
                t0 = time.time()
                while not stop_evt.wait(10.0):
                    elapsed_s = time.time() - t0
                    _llm_inflight_heartbeat(run_id=run_id, req_id=req_id, elapsed_s=elapsed_s)
                    _dbg_event("llm_call_heartbeat", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": attempt + 1, "req_id": req_id, "elapsed_s": round(elapsed_s, 2), "timeout_s": timeout_s, "prompt_len": prompt_len})

            threading.Thread(target=_hb, daemon=True).start()
            _llm_inflight_start(run_id=run_id, phase=phase, provider=provider, model=model, attempt=attempt + 1, req_id=req_id, prompt_len=prompt_len, max_tokens=mt, timeout_s=timeout_s)
            _dbg_event("llm_call_start", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": attempt + 1, "req_id": req_id, "url": url, "timeout_s": timeout_s, "max_tokens": mt})
            resp_box: Dict[str, Any] = {}
            exc_box: Dict[str, Any] = {}

            def _do_post():
                try:
                    resp_box["resp"] = session.post(url, headers=headers, json=payload, timeout=timeout_s)
                except Exception as e:
                    exc_box["exc"] = e

            th = threading.Thread(target=_do_post, daemon=True)
            th.start()
            th.join(timeout_s)
            if th.is_alive():
                stop_evt.set()
                _llm_inflight_end(run_id=run_id, req_id=req_id)
                _dbg_event("llm_call_timeout", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": attempt + 1, "req_id": req_id, "error": f"total timeout {timeout_s}s"})
                raise requests.exceptions.Timeout(f"llm total timeout ({timeout_s}s)")
            if exc_box.get("exc"):
                stop_evt.set()
                _llm_inflight_end(run_id=run_id, req_id=req_id)
                raise exc_box["exc"]
            resp = resp_box.get("resp")
            stop_evt.set()
            if resp is None:
                _llm_inflight_end(run_id=run_id, req_id=req_id)
                raise RuntimeError("llm request failed")
            try:
                data = resp.json()
            except ValueError:
                snippet = (resp.text or "")[:200]
                _llm_inflight_end(run_id=run_id, req_id=req_id)
                _dbg_event("llm_call_non_json", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": attempt + 1, "req_id": req_id, "status": resp.status_code, "snippet": snippet})
                raise RuntimeError(f"非JSON响应: HTTP {resp.status_code} {snippet}")
            if "error" in data:
                err = data["error"].get("message") if isinstance(data["error"], dict) else str(data["error"])
                _llm_inflight_end(run_id=run_id, req_id=req_id)
                _dbg_event("llm_call_error", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": attempt + 1, "req_id": req_id, "status": resp.status_code, "error": err})
                raise RuntimeError(err or "llm error")
            content = (
                (data.get("choices") or [{}])[0].get("message", {}).get("content")
                or (data.get("choices") or [{}])[0].get("message", {}).get("reasoning")  # MiniMax reasoning fallback
                or (data.get("choices") or [{}])[0].get("text", "")
                or ""
            )
            # 去除 MiniMax-M2.7 推理模型的 <think>...</think> 标签
            if content and "<think>" in content:
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            if not content:
                finish_reason = (data.get("choices") or [{}])[0].get("finish_reason", "unknown")
                _llm_inflight_end(run_id=run_id, req_id=req_id)
                _dbg_event("llm_call_empty", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": attempt + 1, "req_id": req_id, "finish_reason": finish_reason})
                raise RuntimeError(f"LLM返回空内容, finish_reason={finish_reason}")
            _dbg_event("llm_call_ok", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": attempt + 1, "req_id": req_id, "status": resp.status_code, "usage": (data.get("usage") if isinstance(data.get("usage"), dict) else None), "content_len": len(content), "content_sample": content[:200]})
            _llm_inflight_end(run_id=run_id, req_id=req_id)
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
            _bump_llm_usage(run_id=run_id, phase=phase, provider=provider, model=model, usage=usage, ok=True, prompt_len=prompt_len, content_len=len(content))
            return content
        except requests.exceptions.Timeout as exc:
            last_exc = exc
            try:
                _llm_inflight_end(run_id=run_id, req_id=req_id)
            except Exception:
                pass
            _dbg_event("llm_call_timeout", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": attempt + 1, "error": str(exc)})
            if "total timeout" in str(exc) and phase == "writing":
                break
        except requests.exceptions.ConnectionError as exc:
            last_exc = exc
            try:
                _llm_inflight_end(run_id=run_id, req_id=req_id)
            except Exception:
                pass
            _dbg_event("llm_call_conn_error", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": attempt + 1, "error": str(exc)})
        except RuntimeError as exc:
            last_exc = exc
            try:
                _llm_inflight_end(run_id=run_id, req_id=req_id)
            except Exception:
                pass
            _dbg_event("llm_call_runtime_error", {"run_id": run_id, "phase": phase, "provider": provider, "model": model, "attempt": attempt + 1, "error": str(exc)})
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    if last_exc:
        _bump_llm_usage(run_id=run_id, phase=phase, provider=provider, model=model, ok=False)
        raise last_exc
    _bump_llm_usage(run_id=run_id, phase=phase, provider=provider, model=model, ok=False)
    raise RuntimeError("llm request failed")


_reload_config()


def _llm_preflight_response():
    cfg = get_effective_llm_config()
    ok, reason = _llm_available(cfg)
    if ok:
        return None
    return jsonify({
        "success": False,
        "code": "llm_not_configured",
        "error": f"LLM 未配置: {reason}",
        "provider": cfg.get("provider"),
        "model": cfg.get("model"),
        "base_url": cfg.get("base_url"),
    }), 400

# 历史记录存储
HISTORY_FILE = os.path.join(os.path.dirname(__file__), 'data', 'grading_history.json')

# 分支研究系统存储
BRANCHES_FILE = os.path.join(os.path.dirname(__file__), 'data', 'research_branches.json')
RESEARCH_STATE_FILE = os.path.join(os.path.dirname(__file__), 'data', 'research_state.json')
RESEARCH_LOGS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'research_logs.json')
PAPERS_STATE_FILE_PATH = str(PAPERS_STATE_FILE)
WORKFLOW_STATE_FILE_PATH = str(WORKFLOW_STATE_FILE)
PAPERS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'papers')
SEED_REVIEW_PATH = os.path.join(os.path.dirname(__file__), 'docs', 'reviews', 'seed_review.md')
DEFAULT_TOPIC = "量化交易策略研究"

def ensure_dir(path):
    """确保目录存在"""
    if not os.path.exists(path):
        os.makedirs(path)

def load_json_file(filepath):
    """加载JSON文件"""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def save_json_file(filepath, data):
    """保存JSON文件"""
    ensure_dir(os.path.dirname(filepath))
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ============ 分支管理函数 ============

def load_branches() -> dict:
    """加载分支数据"""
    data = load_json_file(BRANCHES_FILE)
    return data if data else {"branches": [], "current_branch_id": None, "global_settings": {"auto_continue": True, "pause_after_next": False}}

def save_branches(data: dict):
    """保存分支数据"""
    save_json_file(BRANCHES_FILE, data)

def create_branch(name: str, review_content: str = None, parent_branch_id: int = None) -> dict:
    """创建新分支"""
    branches_data = load_branches()
    branch_id = len(branches_data['branches']) + 1

    branch = {
        "id": branch_id,
        "name": name,
        "created_at": datetime.now().isoformat(),
        "review_content": review_content,
        "parent_branch_id": parent_branch_id,
        "paper_ids": [],
        "status": "active",
        "iterations_count": 0
    }

    branches_data['branches'].append(branch)
    branches_data['current_branch_id'] = branch_id
    branches_data['current_branch'] = branch_id
    save_branches(branches_data)

    # 创建分支专属的papers目录
    branch_papers_dir = os.path.join(PAPERS_DIR, f"branch_{branch_id}")
    ensure_dir(branch_papers_dir)

    return branch

def get_current_branch() -> dict:
    """获取当前分支"""
    branches_data = load_branches()
    current_id = branches_data.get('current_branch_id') or branches_data.get('current_branch')
    if current_id:
        for branch in branches_data.get('branches', []):
            if branch['id'] == current_id:
                return branch
    return None


def load_seed_review() -> str:
    """加载默认种子综述"""
    if os.path.exists(SEED_REVIEW_PATH):
        with open(SEED_REVIEW_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    return DEFAULT_TOPIC


def ensure_default_branch() -> dict:
    """确保存在可用分支，无分支时基于种子综述或文献分析创建默认分支"""
    current = get_current_branch()
    if current:
        return current

    review = load_seed_review()
    workflow = load_workflow_state()
    if workflow.get("project_name"):
        name = workflow["project_name"]
    else:
        name = "默认研究分支"

    lit_path = os.path.join(os.path.dirname(__file__), 'data', 'research', 'seed_paper_analysis.md')
    if os.path.exists(lit_path):
        with open(lit_path, 'r', encoding='utf-8') as f:
            review = f.read()

    return create_branch(name, review)


def resolve_branch(branch_id=None) -> dict:
    """解析并切换到目标分支，必要时创建默认分支"""
    if branch_id is not None:
        try:
            branch_id = int(branch_id)
        except (TypeError, ValueError):
            branch_id = None

    if branch_id:
        branches_data = load_branches()
        for branch in branches_data.get('branches', []):
            if branch['id'] == branch_id:
                branches_data['current_branch_id'] = branch_id
                save_branches(branches_data)
                return branch

    return ensure_default_branch()


def derive_topic(topic: str, branch: dict) -> str:
    """从请求或分支综述中推导研究主题"""
    if topic and topic.strip():
        return topic.strip()

    review = (branch or {}).get('review_content') or ''
    if review:
        candidates = []
        for line in review.split('\n'):
            line = line.strip()
            m = re.match(r"^###\s*论文\d+\s*:\s*(.+)$", line)
            if m:
                candidates.append(m.group(1).strip())
        if candidates:
            try:
                papers = load_papers()
                idx = len(papers.get("runs") or []) % len(candidates)
                pick = candidates[idx] or candidates[0]
                return pick[:160]
            except Exception:
                return candidates[0][:160]

        for line in review.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                title = line.lstrip('#').strip()
                if title:
                    return title
        summary = review.strip().replace('\n', ' ')
        return summary[:120]

    return DEFAULT_TOPIC

# ============ 论文存储函数 ============

def load_papers() -> dict:
    """加载论文数据（独立于 workflow 状态文件）。"""
    default = {
        "papers": [], "current_paper_id": None, "next_research_seq": 1,
        "generation_queue": [], "is_generating": False, "is_paused": False,
        "hypotheses": [], "experiments": [],
        "live_graphs": {},
        "run_metrics": {},
        "current_run": None, "runs": [],
        "research_activity": {"phase": "idle", "message": "等待开始", "progress": 0},
        "settings": {"auto_continue": True, "pause_after_next": False},
        "stop_requested": False,
    }
    data = load_json_file(PAPERS_STATE_FILE_PATH)
    if data and isinstance(data.get("papers"), list):
        merged = dict(default)
        merged.update(data)
        merged_settings = dict(default.get("settings") or {})
        merged_settings.update((data.get("settings") or {}))
        merged["settings"] = merged_settings
        if merged.get("runs") is None:
            merged["runs"] = []
        return merged

    # 兼容：旧版 papers 存在 research_state.json 中
    legacy = load_json_file(RESEARCH_STATE_FILE)
    if legacy and isinstance(legacy.get("papers"), list):
        merged = dict(default)
        merged.update(legacy)
        merged_settings = dict(default.get("settings") or {})
        merged_settings.update((legacy.get("settings") or {}))
        merged["settings"] = merged_settings
        if merged.get("runs") is None:
            merged["runs"] = []
        save_json_file(PAPERS_STATE_FILE_PATH, merged)
        return merged

    return default


def save_papers(data: dict):
    """保存论文数据"""
    save_json_file(PAPERS_STATE_FILE_PATH, data)


def _default_workflow_state() -> dict:
    now = datetime.now().isoformat()
    return {
        "version": "2.0",
        "project_name": "",
        "created_at": now,
        "updated_at": now,
        "status": "idle",
        "current_phase": "initialization",
        "phase_history": [],
        "literature_review": {
            "papers_read": [],
            "papers_to_read": [],
            "key_themes": [],
            "research_questions": [],
        },
        "research_progress": {
            "current_iteration": 0,
            "total_iterations_planned": 3,
            "iterations": [],
        },
    }


def load_workflow_state() -> dict:
    """加载研究工作流状态（文献调研阶段等）。"""
    data = load_json_file(WORKFLOW_STATE_FILE_PATH)
    if data and data.get("version") == "2.0":
        return data
    default = _default_workflow_state()
    save_json_file(WORKFLOW_STATE_FILE_PATH, default)
    return default


def save_workflow_state(data: dict):
    save_json_file(WORKFLOW_STATE_FILE_PATH, data)


def index_paper_to_mongo(paper: dict) -> dict:
    """论文保存后写入 MongoDB 索引（失败不阻断主流程）。"""
    try:
        return index_paper_record(paper)
    except Exception as e:
        return {"success": False, "indexed": False, "error": str(e)}


_research_runner: Optional[ResearchRunner] = None


def get_research_runner() -> ResearchRunner:
    global _research_runner
    if _research_runner is None:
        _research_runner = ResearchRunner(
            load_papers=load_papers,
            save_papers=save_papers,
            load_workflow=load_workflow_state,
            save_workflow=save_workflow_state,
            create_paper=create_paper_record,
            add_log=add_research_log,
        )
    return _research_runner

def get_papers_for_branch(branch_id: int) -> list:
    """获取指定分支的所有论文"""
    papers_data = load_papers()
    return [p for p in papers_data.get('papers', []) if p.get('branch_id') == branch_id]

def save_paper_to_file(paper_id: int, branch_id: int, content: str, title: str = None,
                       research_id: str = None, papers_data: dict = None) -> str:
    """保存论文到研究档案目录（兼容旧调用签名）。"""
    papers_data = papers_data or load_papers()
    title = title or f"paper_{paper_id}"
    research_id = research_id or allocate_research_id(papers_data)
    workspace = create_research_workspace(
        research_id=research_id,
        paper_id=paper_id,
        branch_id=branch_id,
        title=title,
        topic=title,
        content=content,
    )
    return workspace["file_path"]

def ensure_history_dir():
    """确保历史记录目录存在"""
    history_dir = os.path.dirname(HISTORY_FILE)
    if not os.path.exists(history_dir):
        os.makedirs(history_dir)

def load_history() -> list:
    """加载历史记录"""
    ensure_history_dir()
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(history: list):
    """保存历史记录"""
    ensure_history_dir()
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def add_history_record(record: dict):
    """添加历史记录"""
    history = load_history()
    record['id'] = len(history) + 1
    record['timestamp'] = datetime.now().isoformat()
    history.insert(0, record)  # 最新记录在前
    # 只保留最近100条
    history = history[:100]
    save_history(history)

# ============ 研究日志函数 ============

def load_research_logs() -> list:
    """加载研究日志"""
    if os.path.exists(RESEARCH_LOGS_FILE):
        try:
            with open(RESEARCH_LOGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_research_logs(logs: list):
    """保存研究日志"""
    with open(RESEARCH_LOGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def add_research_log(paper_id: int, research_id: str, status: str, message: str = "", details: dict = None) -> dict:
    """添加研究日志记录"""
    logs = load_research_logs()
    log_record = {
        "id": len(logs) + 1,
        "paper_id": paper_id,
        "research_id": research_id,
        "status": status,
        "message": message,
        "details": details or {},
        "timestamp": datetime.now().isoformat()
    }
    logs.insert(0, log_record)
    # 只保留最近200条
    logs = logs[:200]
    save_research_logs(logs)
    return log_record

# 评分标准
SCORING_CRITERIA = """
## 论文评分标准 (0-10分)

### 1. 创新性 (0-3分)
- 0分: 完全重复已有工作，无任何创新
- 1分: 略有改动但核心思想相同
- 2分: 有一定的创新点但不够突出
- 3分: 显著的创新贡献

### 2. 方法论 (0-2分)
- 0分: 方法不明确或不可行
- 1分: 方法基本可行但有缺陷
- 2分: 方法严谨且可复现

### 3. 实验验证 (0-2分)
- 0分: 无实验或实验不充分
- 1分: 有实验但不够全面
- 2分: 实验全面且结果可靠

### 4. 写作质量 (0-2分)
- 0分: 结构混乱，语言不通顺
- 1分: 基本可读但有改进空间
- 2分: 写作专业流畅

### 5. 避免过拟合 (0-1分)
- 0分: 明显过拟合迹象（如仅在特定数据集上有效）
- 1分: 无过拟合迹象，泛化能力良好
"""


def score_paper(paper_content: str) -> dict:
    """使用LLM对论文进行评分"""
    ok, _ = _llm_available(get_effective_llm_config())
    if not ok:
        # 返回模拟评分
        return {
            "total_score": 6.5,
            "pass": True,
            "criteria": {
                "innovation": {"score": 2, "max": 3, "comment": "有一定的创新点"},
                "methodology": {"score": 1, "max": 2, "comment": "方法基本可行"},
                "experiment": {"score": 1, "max": 2, "comment": "实验基本充分"},
                "writing": {"score": 1.5, "max": 2, "comment": "写作较为流畅"},
                "overfitting": {"score": 1, "max": 1, "comment": "无明显过拟合"}
            },
            "feedback": "论文整体质量良好，建议继续优化实验部分。"
        }

    # 限制论文内容长度，避免超出token限制
    max_content_len = 30000  # 约10000 tokens
    truncated_content = paper_content[:max_content_len]
    if len(paper_content) > max_content_len:
        truncated_content += f"\n\n[论文内容已截断，原始长度: {len(paper_content)} 字符]"

    prompt = f"""
你是一个专业的学术论文评审专家。请对以下论文进行评分和评审。

{SCORING_CRITERIA}

## 待评审论文

{truncated_content}

## 输出格式

请严格按以下JSON格式输出评分结果（不要输出任何其他内容）：

{{
    "total_score": 0-10的浮点数,
    "pass": true或false（7分以上通过）,
    "criteria": {{
        "innovation": {{"score": 0-3, "comment": "评审意见"}},
        "methodology": {{"score": 0-2, "comment": "评审意见"}},
        "experiment": {{"score": 0-2, "comment": "评审意见"}},
        "writing": {{"score": 0-2, "comment": "评审意见"}},
        "overfitting": {{"score": 0-1, "comment": "评审意见"}}
    }},
    "feedback": "总体评审意见和改进建议（50字以内）"
}}
"""
    try:
        content = call_llm(prompt, temperature=0.3, max_tokens=2048)
        # 提取JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        return {"error": "无法解析评分结果", "raw": content}
    except Exception as e:
        return {"error": str(e)}


def regenerate_paper(paper_content: str, feedback: str, criteria: dict) -> str:
    """根据评审反馈重新生成论文"""
    ok, _ = _llm_available(get_effective_llm_config())
    if not ok:
        return f"[模拟重生成] 基于反馈优化论文: {feedback[:50]}..."

    # 找出主要问题
    issues = []
    if criteria.get("innovation", {}).get("score", 0) < 2:
        issues.append("创新性不足")
    if criteria.get("methodology", {}).get("score", 0) < 1:
        issues.append("方法论存在缺陷")
    if criteria.get("experiment", {}).get("score", 0) < 1:
        issues.append("实验验证不充分")
    if criteria.get("overfitting", {}).get("score", 0) < 1:
        issues.append("存在过拟合风险")

    issues_text = "；".join(issues) if issues else "整体质量需要提升"

    # 限制论文内容长度，避免超出token限制
    max_content_len = 25000  # 约8000 tokens
    truncated_content = paper_content[:max_content_len]
    if len(paper_content) > max_content_len:
        truncated_content += f"\n\n[论文内容已截断，原始长度: {len(paper_content)} 字符]"

    prompt = f"""
你是一个量化交易领域的学术论文写作专家。请根据评审反馈重新撰写论文。

## 原始论文

{truncated_content}

## 评审反馈

总体评分: {criteria.get('total_score', 'N/A')}/10
通过状态: {"通过" if criteria.get('pass') else "不通过"}
主要问题: {issues_text}

各项评分:
- 创新性: {criteria.get('innovation', {}).get('score', 'N/A')}/3 - {criteria.get('innovation', {}).get('comment', '')}
- 方法论: {criteria.get('methodology', {}).get('score', 'N/A')}/2 - {criteria.get('methodology', {}).get('comment', '')}
- 实验验证: {criteria.get('experiment', {}).get('score', 'N/A')}/2 - {criteria.get('experiment', {}).get('comment', '')}
- 写作质量: {criteria.get('writing', {}).get('score', 'N/A')}/2 - {criteria.get('writing', {}).get('comment', '')}
- 避免过拟合: {criteria.get('overfitting', {}).get('score', 'N/A')}/1 - {criteria.get('overfitting', {}).get('comment', '')}

评审建议: {feedback}

## 重写要求

1. **提升创新性**: 确保有明确的研究动机和独特贡献
2. **强化方法论**: 方法必须严谨、可复现、有理论支撑
3. **完善实验验证**: 包含充分的消融实验和对比实验，确保结果可靠性
4. **避免过拟合**: 使用交叉验证、多种市场环境测试、理论分析泛化能力
5. **保证写作质量**: 结构清晰、逻辑连贯、语言专业

请输出一篇完整的新论文（Markdown格式），确保解决上述问题。
"""

    # 估算token并计算安全的max_tokens
    estimated_input_tokens = len(prompt) // 3
    max_output_tokens = min(4096, 150000 - estimated_input_tokens)

    try:
        return call_llm(prompt, temperature=0.5, max_tokens=max_output_tokens)
    except Exception as e:
        return f"重生成失败: {str(e)}"


def find_related_papers(topic: str, failed_aspects: list) -> list:
    """查找相关论文以改进论文质量"""
    ok, _ = _llm_available(get_effective_llm_config())
    if not ok:
        return [
            {"title": "相关论文A", "reason": "提供方法论支持"},
            {"title": "相关论文B", "reason": "提供实验验证思路"}
        ]

    prompt = f"""
你是一个量化交易领域的文献专家。请根据以下主题和论文不足之处，推荐可能有所帮助的参考论文。

## 论文主题
{topic}

## 论文不足之处
{', '.join(failed_aspects)}

## 输出格式

请列出3-5篇可能有所帮助的参考论文，每篇包含：
- 论文标题
- 作者/来源
- 为什么有帮助（如何解决论文的不足）
- arXiv ID（如果可获得）

使用中文输出。
"""
    try:
        return call_llm(prompt, temperature=0.3, max_tokens=2048)
    except Exception as e:
        return f"查找失败: {str(e)}"


@app.route('/api/score', methods=['POST'])
def api_score():
    """论文评分API"""
    data = request.json
    paper_content = data.get('paper', '')

    if not paper_content:
        return jsonify({"error": "论文内容不能为空"}), 400

    result = score_paper(paper_content)
    
    # 保存到历史记录
    add_history_record({
        "type": "score",
        "paper_preview": paper_content[:500],
        "paper_full": paper_content,
        "result": result
    })
    
    return jsonify(result)


@app.route('/api/regenerate', methods=['POST'])
def api_regenerate():
    """论文重生成API"""
    data = request.json
    paper_content = data.get('paper', '')
    feedback = data.get('feedback', '')
    criteria = data.get('criteria', {})

    if not paper_content:
        return jsonify({"error": "论文内容不能为空"}), 400

    new_paper = regenerate_paper(paper_content, feedback, criteria)
    
    # 保存到历史记录
    add_history_record({
        "type": "regenerate",
        "original_preview": paper_content[:500],
        "feedback": feedback,
        "criteria": criteria,
        "new_paper_preview": new_paper[:500],
        "new_paper_full": new_paper
    })
    
    return jsonify({"new_paper": new_paper})


@app.route('/api/find_papers', methods=['POST'])
def api_find_papers():
    """查找相关论文API"""
    data = request.json
    topic = data.get('topic', '')
    failed_aspects = data.get('failed_aspects', [])

    if not topic:
        return jsonify({"error": "主题不能为空"}), 400

    papers = find_related_papers(topic, failed_aspects)
    
    # 保存到历史记录
    add_history_record({
        "type": "find_papers",
        "topic": topic,
        "failed_aspects": failed_aspects,
        "related_papers": papers
    })
    
    return jsonify({"related_papers": papers})


@app.route('/api/iterate', methods=['POST'])
def api_iterate():
    """完整迭代流程: 评分 -> 找论文 -> 重生成 -> 再评分"""
    data = request.json
    paper_content = data.get('paper', '')
    topic = data.get('topic', '量化交易策略')
    max_iterations = data.get('max_iterations', 3)

    if not paper_content:
        return jsonify({"error": "论文内容不能为空"}), 400

    results = {
        "iterations": [],
        "final_status": None
    }

    current_paper = paper_content

    for i in range(max_iterations):
        # 评分
        score_result = score_paper(current_paper)

        iteration_result = {
            "iteration": i + 1,
            "score": score_result,
            "paper": current_paper[:200] + "..." if len(current_paper) > 200 else current_paper
        }

        # 检查是否通过
        if score_result.get("pass", False):
            results["final_status"] = "passed"
            results["final_paper"] = current_paper
            results["final_score"] = score_result
            iteration_result["action"] = "通过，无需继续"
            results["iterations"].append(iteration_result)
            break

        # 获取失败原因
        failed_aspects = []
        criteria = score_result.get("criteria", {})
        if criteria.get("innovation", {}).get("score", 0) < 2:
            failed_aspects.append("创新性不足")
        if criteria.get("methodology", {}).get("score", 0) < 1:
            failed_aspects.append("方法论存在缺陷")
        if criteria.get("experiment", {}).get("score", 0) < 1:
            failed_aspects.append("实验验证不充分")
        if criteria.get("overfitting", {}).get("score", 0) < 1:
            failed_aspects.append("存在过拟合风险")

        # 查找相关论文
        related_papers = find_related_papers(topic, failed_aspects)
        iteration_result["related_papers"] = related_papers
        iteration_result["failed_aspects"] = failed_aspects

        # 重生成
        new_paper = regenerate_paper(
            current_paper,
            score_result.get("feedback", ""),
            criteria
        )
        iteration_result["new_paper_preview"] = new_paper[:200] + "..."

        current_paper = new_paper
        iteration_result["action"] = "已重生成，进入下一轮"

        results["iterations"].append(iteration_result)

    if results["final_status"] is None:
        results["final_status"] = "max_iterations_reached"
        results["final_paper"] = current_paper
        results["final_score"] = score_paper(current_paper)
    
    # 保存完整迭代到历史记录
    add_history_record({
        "type": "iterate",
        "initial_paper_preview": paper_content[:500],
        "initial_paper_full": paper_content,
        "topic": topic,
        "max_iterations": max_iterations,
        "results": results
    })
    
    return jsonify(results)


@app.route('/api/history', methods=['GET'])
def api_history():
    """获取历史记录列表"""
    history = load_history()
    # 返回列表形式（不含完整论文内容，节省带宽）
    preview_list = []
    for record in history:
        preview_list.append({
            "id": record.get('id'),
            "timestamp": record.get('timestamp'),
            "type": record.get('type'),
            "paper_preview": record.get('paper_preview', '')[:200] + '...' if record.get('paper_preview') and len(record.get('paper_preview', '')) > 200 else record.get('paper_preview', ''),
            "result_summary": f"评分: {record.get('result', {}).get('total_score', 'N/A')}/10" if record.get('result') else None,
            "topic": record.get('topic', ''),
            "iterations_count": len(record.get('results', {}).get('iterations', [])) if record.get('results') else 0
        })
    return jsonify({"history": preview_list})


@app.route('/api/history/<int:record_id>', methods=['GET'])
def api_history_detail(record_id: int):
    """获取单条历史记录的完整内容"""
    history = load_history()
    for record in history:
        if record.get('id') == record_id:
            return jsonify(record)
    return jsonify({"error": "记录不存在"}), 404


# ============ 分支研究系统 API ============

def _parse_iso_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _compute_last_active(papers_data: Dict[str, Any], inflight: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    candidates: List[Tuple[str, Optional[str]]] = []
    activity = papers_data.get("research_activity") if isinstance(papers_data.get("research_activity"), dict) else {}
    current_run = papers_data.get("current_run") if isinstance(papers_data.get("current_run"), dict) else {}
    run_metrics = papers_data.get("run_metrics") if isinstance(papers_data.get("run_metrics"), dict) else {}
    candidates.append(("research_activity", activity.get("updated_at")))
    candidates.append(("current_run", current_run.get("updated_at")))
    candidates.append(("run_metrics", run_metrics.get("updated_at")))
    if isinstance(inflight, dict):
        candidates.append(("llm_inflight", inflight.get("updated_at")))

    best_src: Optional[str] = None
    best_ts: Optional[str] = None
    best_dt: Optional[datetime] = None
    for src, ts in candidates:
        dt = _parse_iso_dt(ts)
        if dt is None:
            continue
        if best_dt is None or dt > best_dt:
            best_dt = dt
            best_src = src
            best_ts = str(ts)

    stall_seconds: Optional[int] = None
    if best_dt is not None:
        stall_seconds = int(max(0.0, (datetime.now() - best_dt).total_seconds()))

    return {
        "last_active_at": best_ts,
        "last_active_source": best_src,
        "stall_seconds": stall_seconds,
    }


def _maybe_self_heal_startup(papers_data: Dict[str, Any], inflight: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not papers_data.get("is_generating"):
        return None
    if inflight:
        return None
    runner = get_research_runner()
    runner_running = False
    try:
        runner_running = bool(runner.is_running())
    except Exception:
        runner_running = False
    if runner_running:
        return None

    now = datetime.now().isoformat()
    activity = papers_data.get("research_activity") if isinstance(papers_data.get("research_activity"), dict) else {}
    current_run = papers_data.get("current_run") if isinstance(papers_data.get("current_run"), dict) else {}

    progress = activity.get("progress")
    try:
        progress_val = float(progress) if progress is not None else 0.0
    except Exception:
        progress_val = 0.0

    papers_data["is_generating"] = False
    papers_data["is_paused"] = True
    papers_data["stop_requested"] = False

    if isinstance(current_run, dict):
        current_run["status"] = "paused"
        current_run["updated_at"] = now
        papers_data["current_run"] = current_run

    papers_data["research_activity"] = {
        "phase": "paused",
        "message": "检测到服务重启或后台线程丢失，已自动暂停（可点击“继续”断点续传）",
        "progress": progress_val,
        "updated_at": now,
    }

    payload = {"type": "startup_self_heal", "reason": "runner_not_running", "at": now}
    papers_data["last_self_heal"] = payload
    return payload


def _maybe_auto_pause_stall(
    papers_data: Dict[str, Any],
    inflight: Optional[Dict[str, Any]],
    last_active: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not papers_data.get("is_generating"):
        return None
    if papers_data.get("is_paused"):
        return None
    if inflight:
        return None

    stall_s = last_active.get("stall_seconds")
    if stall_s is None:
        return None
    try:
        threshold_s = int(os.environ.get("STALL_AUTO_PAUSE_S") or "120")
    except Exception:
        threshold_s = 120
    if threshold_s <= 0:
        threshold_s = 120
    if int(stall_s) < threshold_s:
        return None

    now = datetime.now().isoformat()
    activity = papers_data.get("research_activity") if isinstance(papers_data.get("research_activity"), dict) else {}
    current_run = papers_data.get("current_run") if isinstance(papers_data.get("current_run"), dict) else {}
    phase = str(activity.get("phase") or "")
    if phase in ("idle", "completed", "error"):
        return None

    progress = activity.get("progress")
    try:
        progress_val = float(progress) if progress is not None else 0.0
    except Exception:
        progress_val = 0.0

    last_src = last_active.get("last_active_source") or "unknown"
    papers_data["is_generating"] = False
    papers_data["is_paused"] = True
    papers_data["stop_requested"] = True

    if isinstance(current_run, dict):
        current_run["status"] = "paused"
        current_run["updated_at"] = now
        papers_data["current_run"] = current_run

    papers_data["research_activity"] = {
        "phase": "paused",
        "message": f"检测到超过 {threshold_s}s 无活动（source={last_src}），已自动暂停（可点击“继续”断点续传）",
        "progress": progress_val,
        "updated_at": now,
    }

    payload = {
        "type": "stall_auto_pause",
        "reason": "no_activity_no_inflight",
        "threshold_s": threshold_s,
        "stall_seconds": int(stall_s),
        "last_active_at": last_active.get("last_active_at"),
        "last_active_source": last_src,
        "at": now,
    }
    papers_data["last_self_heal"] = payload
    return payload


@app.route('/api/research/state', methods=['GET'])
def api_research_state():
    """获取研究状态"""
    papers_data = load_papers()
    dirty = _flush_llm_usage(papers_data)
    inflight = _llm_inflight_snapshot(papers_data)
    last_active = _compute_last_active(papers_data, inflight)
    self_heal = _maybe_self_heal_startup(papers_data, inflight)
    if self_heal:
        dirty = True
    stall_action = _maybe_auto_pause_stall(papers_data, inflight, last_active)
    if stall_action:
        self_heal = stall_action
        dirty = True
    branches_data = load_branches()
    workflow = load_workflow_state()
    current_branch = get_current_branch()
    current_branch_id = branches_data.get('current_branch_id') or branches_data.get('current_branch')

    experiments = _decorate_stage_experiments(papers_data)
    if experiments:
        papers_data["experiments"] = experiments
    if dirty:
        save_papers(papers_data)

    last_active = _compute_last_active(papers_data, inflight)
    return jsonify({
        "success": True,
        "is_generating": papers_data.get('is_generating', False),
        "is_paused": papers_data.get('is_paused', False),
        "settings": papers_data.get('settings', {}),
        "current_branch": current_branch,
        "current_branch_id": current_branch_id,
        "papers": papers_data.get('papers', []),
        "papers_count": len(papers_data.get('papers', [])),
        "hypotheses": papers_data.get('hypotheses', []),
        "experiments": papers_data.get('experiments', []),
        "run_metrics": papers_data.get("run_metrics", {}),
        "llm_inflight": inflight,
        "live_graphs": papers_data.get("live_graphs", {}),
        "current_run": papers_data.get('current_run'),
        "runs": papers_data.get('runs', []),
        "research_activity": papers_data.get('research_activity', {}),
        "last_active_at": last_active.get("last_active_at"),
        "last_active_source": last_active.get("last_active_source"),
        "stall_seconds": last_active.get("stall_seconds"),
        "self_heal": self_heal,
        "queue_length": len(papers_data.get('generation_queue', [])),
        "all_branches": branches_data.get('branches', []),
        "workflow": workflow,
        "data_registry_summary": {
            "seed_papers_count": get_registry().get("seed_papers", {}).get("count", 0),
            "research_archives_count": len(get_registry().get("research_archives", [])),
        },
    })


def _live_graphs_payload(papers_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    papers_data = papers_data or load_papers()
    live = papers_data.get("live_graphs") if isinstance(papers_data.get("live_graphs"), dict) else None
    if not live:
        return None
    current_run = papers_data.get("current_run") if isinstance(papers_data.get("current_run"), dict) else {}
    run_id = current_run.get("run_id") or ""
    status = current_run.get("status") or ""
    phase = (papers_data.get("research_activity") or {}).get("phase") or ""
    if live.get("run_id") != run_id:
        return None
    if status not in ("in_progress", "paused"):
        return None
    if phase not in ("experimenting", "writing", "paused"):
        return None
    return live


@app.route('/api/research/run', methods=['GET'])
def api_research_run():
    papers = load_papers()
    current_run = papers.get("current_run")
    activity = papers.get("research_activity") or {}
    phase = activity.get("phase") or "idle"
    status = None
    if isinstance(current_run, dict):
        status = current_run.get("status")

    resumable = False
    if current_run and isinstance(current_run, dict):
        resumable = (status in (None, "in_progress", "paused")) and (phase not in ("completed", "error"))

    return jsonify({
        "success": True,
        "resumable": resumable,
        "current_run": current_run,
        "research_activity": activity,
    })


@app.route('/api/research/checkpoints', methods=['GET'])
def api_research_checkpoints():
    papers = load_papers()
    checkpoints = []

    seen = set()
    for run in reversed(papers.get("runs") or []):
        rid = run.get("research_id")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        meta = {
            "topic": run.get("topic"),
            "started_at": run.get("started_at"),
            "status": run.get("status"),
            "papers_count": 1,
        }
        checkpoints.append({"research_id": rid, "has_checkpoint": True, "meta": meta})

    base = Path(__file__).resolve().parent / "data" / "research"
    if base.exists():
        for ws in base.glob("*_checkpoint"):
            if not ws.is_dir():
                continue
            rid = ws.name
            if rid.endswith("_checkpoint"):
                rid = rid[: -len("_checkpoint")]
            if rid in seen:
                continue
            cp_path = ws / "checkpoint.json"
            meta = {}
            has_checkpoint = False
            if cp_path.exists():
                has_checkpoint = True
                try:
                    meta = json.loads(cp_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            checkpoints.append({"research_id": rid, "has_checkpoint": has_checkpoint, "meta": meta})

    def _sort_key(item: Dict[str, Any]) -> str:
        meta = item.get("meta") or {}
        return str(meta.get("updated_at") or meta.get("created_at") or "")

    checkpoints.sort(key=_sort_key, reverse=True)
    return jsonify({"success": True, "checkpoints": checkpoints})


@app.route('/api/research/resume/<research_id>', methods=['POST'])
def api_research_resume_checkpoint(research_id: str):
    preflight = _llm_preflight_response()
    if preflight:
        return preflight
    papers_data = load_papers()
    if papers_data.get("is_generating"):
        return jsonify({"success": False, "error": "已有任务进行中，请先停止或等待完成"}), 409

    for run in reversed(papers_data.get("runs") or []):
        if run.get("research_id") == research_id:
            branch_id = int(run.get("branch_id") or (get_current_branch() or {}).get("id") or 1)
            topic = str(run.get("topic") or derive_topic("", get_current_branch()))
            now = datetime.now().isoformat()
            papers_data["current_run"] = {
                "run_id": f"RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
                "branch_id": branch_id,
                "topic": topic,
                "status": "paused",
                "started_at": now,
                "updated_at": now,
                "last_checkpoint_phase": "paused",
            }
            papers_data["hypotheses"] = []
            papers_data["experiments"] = []
            papers_data["generation_queue"] = []
            papers_data["is_paused"] = True
            papers_data["is_generating"] = False
            papers_data["research_activity"] = {
                "phase": "paused",
                "message": f"已选择断点 {research_id}，准备继续…",
                "progress": 0.0,
                "updated_at": now,
            }
            save_papers(papers_data)
            result = get_research_runner().kickoff(topic=topic, branch_id=branch_id, resume=True)
            return jsonify({**result, "success": True, "message": "已从所选断点继续（研究流水线）"})

    papers_data["is_generating"] = True
    papers_data["is_paused"] = False
    papers_data["research_activity"] = {
        "phase": "resuming",
        "message": f"从断点 {research_id} 继续…",
        "progress": 0.08,
        "updated_at": datetime.now().isoformat(),
    }
    save_papers(papers_data)

    def _run():
        try:
            result = resume_research_checkpoint(research_id)
            status = result.get("status") if isinstance(result, dict) else "done"
            msg = "断点恢复完成" if status not in ("error",) else (result.get("message") if isinstance(result, dict) else "断点恢复失败")
            add_research_log(0, research_id, "checkpoint_resume", msg, {"result": result})
            papers = load_papers()
            papers["is_generating"] = False
            papers["research_activity"] = {
                "phase": "completed" if status not in ("error",) else "error",
                "message": msg,
                "progress": 1.0 if status not in ("error",) else 0.0,
                "updated_at": datetime.now().isoformat(),
            }
            save_papers(papers)
        except Exception as e:
            add_research_log(0, research_id, "checkpoint_resume", "断点恢复异常", {"error": str(e)})
            papers = load_papers()
            papers["is_generating"] = False
            papers["research_activity"] = {
                "phase": "error",
                "message": f"断点恢复异常: {str(e)}",
                "progress": 0.0,
                "updated_at": datetime.now().isoformat(),
            }
            save_papers(papers)

    threading.Thread(target=_run, daemon=True, name=f"resume-{research_id}").start()
    return jsonify({"success": True, "message": "已启动断点恢复"})


@app.route('/api/research/author-network/latest', methods=['GET'])
def api_author_network_latest():
    papers_data = load_papers()
    live = _live_graphs_payload(papers_data)
    if live and isinstance(live.get("author_network"), dict):
        return jsonify({"success": True, "author_network": live.get("author_network"), "source": "live"})
    papers = list_seed_papers()
    return jsonify({"success": True, "author_network": _build_author_network_from_seed_papers(papers), "source": "seed"})


@app.route('/api/research/citation-network/latest', methods=['GET'])
def api_citation_network_latest():
    papers_data = load_papers()
    live = _live_graphs_payload(papers_data)
    if live and isinstance(live.get("citation_network"), dict):
        return jsonify({"success": True, "citation_network": live.get("citation_network"), "source": "live"})
    seed_papers = list_seed_papers()
    return jsonify({"success": True, "citation_network": _build_citation_network(papers_data=papers_data, seed_papers=seed_papers), "source": "computed"})


@app.route('/api/branches', methods=['GET'])
def api_branches_list():
    """获取所有分支列表"""
    branches_data = load_branches()
    branches = branches_data.get('branches', [])

    # 为每个分支添加论文统计
    papers_data = load_papers()
    for branch in branches:
        branch_papers = [p for p in papers_data.get('papers', []) if p.get('branch_id') == branch['id']]
        branch['papers_count'] = len(branch_papers)
        branch['latest_paper_date'] = branch_papers[-1].get('created_at') if branch_papers else None

    return jsonify({
        "success": True,
        "branches": branches,
        "current_branch_id": branches_data.get('current_branch_id') or branches_data.get('current_branch')
    })


# ============ LLM调用记录 API ============

@app.route('/api/llm-calls', methods=['GET'])
def api_llm_calls_list():
    """获取LLM调用记录列表"""
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        agent_name = request.args.get('agent')
        status = request.args.get('status')
        research_id = request.args.get('research_id')

        # 读取JSON文件作为数据源
        history_file = Path(__file__).resolve().parent / "data" / "llm_call_logs.json"
        calls = []
        if history_file.exists():
            try:
                calls = json.loads(history_file.read_text(encoding='utf-8'))
            except Exception:
                calls = []

        # 应用过滤器
        if agent_name:
            calls = [c for c in calls if c.get('agent_name') == agent_name]
        if status:
            calls = [c for c in calls if c.get('status') == status]
        if research_id:
            calls = [c for c in calls if c.get('research_id') == research_id]

        # 按时间倒序
        calls.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # 分页
        total = len(calls)
        calls = calls[offset:offset + limit]

        return jsonify({
            "calls": calls,
            "total": total,
            "limit": limit,
            "offset": offset
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/llm-calls/<call_id>', methods=['GET'])
def api_llm_call_detail(call_id: str):
    """获取单条LLM调用详情"""
    try:
        history_file = Path(__file__).resolve().parent / "data" / "llm_call_logs.json"
        if not history_file.exists():
            return jsonify({"error": "调用记录不存在"}), 404

        calls = json.loads(history_file.read_text(encoding='utf-8'))
        call = next((c for c in calls if c.get('call_id') == call_id), None)

        if not call:
            return jsonify({"error": "调用记录不存在"}), 404

        return jsonify(call)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/llm-calls/stats', methods=['GET'])
def api_llm_calls_stats():
    """获取LLM调用统计信息"""
    try:
        history_file = Path(__file__).resolve().parent / "data" / "llm_call_logs.json"
        calls = []
        if history_file.exists():
            try:
                calls = json.loads(history_file.read_text(encoding='utf-8'))
            except Exception:
                calls = []

        total_calls = len(calls)
        success_calls = len([c for c in calls if c.get('status') == 'success'])
        failed_calls = len([c for c in calls if c.get('status') == 'failed'])

        total_tokens = sum(c.get('total_tokens', 0) for c in calls)
        avg_latency = sum(c.get('latency_ms', 0) for c in calls) / total_calls if total_calls > 0 else 0

        # 按Agent统计
        agent_stats = {}
        for c in calls:
            agent = c.get('agent_name', 'unknown')
            if agent not in agent_stats:
                agent_stats[agent] = {'call_count': 0, 'tokens': 0, 'latency_sum': 0}
            agent_stats[agent]['call_count'] += 1
            agent_stats[agent]['tokens'] += c.get('total_tokens', 0)
            agent_stats[agent]['latency_sum'] += c.get('latency_ms', 0)

        agent_stats_list = [
            {
                'agent_name': agent,
                'call_count': stats['call_count'],
                'tokens': stats['tokens'],
                'avg_latency': stats['latency_sum'] / stats['call_count'] if stats['call_count'] > 0 else 0
            }
            for agent, stats in agent_stats.items()
        ]

        return jsonify({
            "total_calls": total_calls,
            "success_calls": success_calls,
            "failed_calls": failed_calls,
            "success_rate": round(success_calls / total_calls * 100, 2) if total_calls > 0 else 0,
            "total_tokens": total_tokens,
            "avg_latency_ms": round(avg_latency, 2),
            "agent_stats": agent_stats_list
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/branches', methods=['POST'])
def api_create_branch():
    """创建新分支"""
    data = request.json
    name = data.get('name', f"分支 {datetime.now().strftime('%Y%m%d_%H%M%S')}")
    review_content = data.get('review_content', '')
    parent_branch_id = data.get('parent_branch_id')

    branch = create_branch(name, review_content, parent_branch_id)
    return jsonify({"success": True, "branch": branch, "message": f"分支 '{name}' 创建成功"})


@app.route('/api/branches/<int:branch_id>', methods=['GET'])
def api_branch_detail(branch_id: int):
    """获取分支详情"""
    branches_data = load_branches()
    branch = None
    for b in branches_data.get('branches', []):
        if b['id'] == branch_id:
            branch = b.copy()
            break

    if not branch:
        return jsonify({"error": "分支不存在"}), 404

    # 获取该分支的论文
    papers_data = load_papers()
    branch_papers = [p for p in papers_data.get('papers', []) if p.get('branch_id') == branch_id]

    branch['papers'] = branch_papers
    return jsonify({"branch": branch})


@app.route('/api/branches/switch/<int:branch_id>', methods=['POST'])
def api_switch_branch(branch_id: int):
    """切换当前分支"""
    branches_data = load_branches()
    for b in branches_data.get('branches', []):
        if b['id'] == branch_id:
            branches_data['current_branch_id'] = branch_id
            save_branches(branches_data)
            return jsonify({"success": True, "branch": b, "message": f"已切换到分支 '{b['name']}'"})

    return jsonify({"error": "分支不存在"}), 404


@app.route('/api/generate/start', methods=['POST'])
def api_start_generation():
    """开始研究：后台推进文献→假设→实验→论文"""
    preflight = _llm_preflight_response()
    if preflight:
        return preflight
    data = request.json or {}

    current_branch = resolve_branch(data.get('branch_id'))
    topic = derive_topic(data.get('topic', ''), current_branch)

    resume = bool(data.get("resume"))
    result = get_research_runner().kickoff(topic=topic, branch_id=current_branch['id'], resume=resume)
    result["current_branch"] = current_branch
    return jsonify(result)


@app.route('/api/generate/pause', methods=['POST'])
def api_pause_generation():
    """暂停生成 - 生成完下一篇后停止"""
    papers_data = load_papers()
    papers_data['settings']['pause_after_next'] = True
    save_papers(papers_data)

    return jsonify({"success": True, "message": "已设置暂停，将在生成下一篇论文后停止"})


@app.route('/api/generate/resume', methods=['POST'])
def api_resume_generation():
    """继续生成"""
    preflight = _llm_preflight_response()
    if preflight:
        return preflight
    papers_data = load_papers()
    papers_data['is_paused'] = False
    papers_data['settings']['pause_after_next'] = False
    save_papers(papers_data)

    current_run = papers_data.get("current_run") if isinstance(papers_data.get("current_run"), dict) else {}
    branch_id = int(current_run.get("branch_id") or (get_current_branch() or {}).get("id") or 1)
    topic = str(current_run.get("topic") or derive_topic("", get_current_branch()))
    result = get_research_runner().kickoff(topic=topic, branch_id=branch_id, resume=True)
    return jsonify({**result, "message": "已继续生成"})


@app.route('/api/generate/stop', methods=['POST'])
def api_stop_generation():
    """完全停止生成"""
    papers_data = load_papers()
    papers_data['is_generating'] = False
    papers_data['is_paused'] = False
    papers_data['generation_queue'] = []
    papers_data["stop_requested"] = True
    if isinstance(papers_data.get("current_run"), dict):
        papers_data["current_run"]["status"] = "stopped"
        papers_data["current_run"]["updated_at"] = datetime.now().isoformat()
    papers_data["research_activity"] = {
        "phase": "completed",
        "message": "已停止生成",
        "progress": 1.0,
        "updated_at": datetime.now().isoformat(),
    }
    save_papers(papers_data)

    return jsonify({"success": True, "message": "已停止生成，清空队列"})


@app.route('/api/generate/next', methods=['POST'])
def api_generate_next():
    """生成下一篇论文（手动触发）"""
    preflight = _llm_preflight_response()
    if preflight:
        return preflight
    data = request.json or {}

    current_branch = resolve_branch(data.get('branch_id'))
    topic = derive_topic(data.get('topic', ''), current_branch)
    paper_record = create_paper_record(topic, current_branch['id'])

    papers_data = load_papers()
    papers_data['is_generating'] = False
    papers_data['is_paused'] = False
    save_papers(papers_data)

    return jsonify({
        "success": True,
        "paper": paper_record,
        "message": "论文生成成功"
    })


def _load_json_maybe(path: Path) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _run_experiment_and_collect(*, root: Path, research_id: str) -> Dict[str, Any]:
    names = {
        "experiment": root / "code" / f"{research_id}_experiment.py",
        "backtest_results": root / "metrics" / f"{research_id}_backtest_results.json",
        "quantagent_results": root / "metrics" / f"{research_id}_quantagent_results.json",
        "indicator_sample": root / "data" / f"{research_id}_indicator_sample.json",
        "experiment_data": root / "data" / f"{research_id}_experiment_data.json",
        "quantagent_trace": root / "data" / f"{research_id}_quantagent_trace.json",
        "log": root / "logs" / f"{research_id}_experiment.log",
    }
    result: Dict[str, Any] = {
        "ran": False,
        "ok": False,
        "error": None,
        "paths": {k: str(v) for k, v in names.items() if k != "log"},
        "data": {},
    }

    try:
        if str(os.environ.get("AUTO_UPDATE_EXPERIMENT_CODE") or "1") != "0":
            if names["experiment"].exists():
                exp_text = names["experiment"].read_text(encoding="utf-8", errors="replace")
            else:
                exp_text = ""
            needs_update = ("EXPERIMENT_TEMPLATE_VERSION" not in exp_text) or ("v3_multi_asset_cost_freq" not in exp_text)
            if (not exp_text) or needs_update:
                meta = {}
                meta_path = root / "meta.json"
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        meta = {}
                title = str(meta.get("title") or meta.get("topic") or research_id)
                topic = str(meta.get("topic") or title)
                scaffold_experiment_code(root, research_id, title, topic)
    except Exception:
        pass

    if not names["quantagent_results"].exists():
        _write_json(
            names["quantagent_results"],
            {"research_id": research_id, "status": "pending", "metrics": {}, "benchmark": {}, "created_at": datetime.now().isoformat()},
        )
    if not names["quantagent_trace"].exists():
        _write_json(
            names["quantagent_trace"],
            {"research_id": research_id, "status": "pending", "trace": [], "created_at": datetime.now().isoformat()},
        )

    if not names["experiment"].exists():
        result["error"] = "experiment_code_missing"
        return result

    env = dict(os.environ)
    env["RESEARCH_ID"] = research_id
    env["RESEARCH_ROOT"] = str(root)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    env["NO_PROXY"] = "*"
    try:
        proc = subprocess.run(
            [sys.executable, str(names["experiment"])],
            cwd=str(root),
            env=env,
            timeout=900,
            capture_output=True,
            text=True,
        )
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        names["log"].parent.mkdir(parents=True, exist_ok=True)
        names["log"].write_text(out, encoding="utf-8", errors="replace")
        result["ran"] = True
        result["ok"] = proc.returncode == 0
        if proc.returncode != 0:
            result["error"] = f"experiment_failed_rc_{proc.returncode}"
    except Exception as exc:
        result["ran"] = True
        result["ok"] = False
        result["error"] = str(exc)

    result["data"] = {
        "backtest_results": _load_json_maybe(names["backtest_results"]),
        "quantagent_results": _load_json_maybe(names["quantagent_results"]),
        "indicator_sample": _load_json_maybe(names["indicator_sample"]),
        "experiment_data": _load_json_maybe(names["experiment_data"]),
        "quantagent_trace": _load_json_maybe(names["quantagent_trace"]),
    }
    return result


def _persist_experiment_documents(
    *,
    root: Path,
    research_id: str,
    topic: str,
    papers_data: dict,
    experiment_bundle: Optional[Dict[str, Any]] = None,
) -> None:
    hypotheses = papers_data.get("hypotheses") or []
    experiments = papers_data.get("experiments") or []

    spec_path = root / "experiments" / f"{research_id}_experiment_data_spec.md"
    _write_text(
        spec_path,
        "\n".join([
            f"# 实验数据说明（{research_id}）",
            "",
            "本研究档案目录包含以下实验相关文件：",
            "",
            f"- data/{research_id}_experiment_data.json：实验配置与中间数据（可复现输入/输出字段）",
            f"- data/{research_id}_indicator_sample.json：指标样本（特征列、时间索引、示例记录）",
            f"- metrics/{research_id}_backtest_results.json：回测结果（收益、风险、基准对比、统计检验）",
            f"- data/{research_id}_quantagent_trace.json：QuantAgent 多智能体决策 trace（每步信号、投票结果、持仓与收益）",
            f"- metrics/{research_id}_quantagent_results.json：QuantAgent 结果汇总（与 baseline/基准对比的指标）",
            f"- code/{research_id}_experiment.py：实验代码（可直接运行）",
            "",
            "约定：所有表格与结论必须以以上 JSON 的真实字段为依据，不得编造。",
            "",
        ])
    )

    hyp_lines = [f"# 研究假设（{research_id}）", "", f"主题：{topic}", ""]
    if not hypotheses:
        hyp_lines.append("暂无假设记录。")
    else:
        for idx, h in enumerate(hypotheses, start=1):
            hyp_lines.extend([
                f"## H{idx:02d}. {h.get('title') or h.get('id')}",
                "",
                f"- id: {h.get('id')}",
                f"- status: {h.get('status')}",
                f"- tags: {', '.join(h.get('tags') or [])}",
                f"- expected_outcome: {h.get('expected_outcome')}",
                "",
                (h.get("description") or "").strip(),
                "",
            ])
            if h.get("actual_outcome"):
                hyp_lines.extend([f"- actual_outcome: {h.get('actual_outcome')}", ""])
    _write_text(root / "experiments" / f"{research_id}_hypotheses.md", "\n".join(hyp_lines))

    seed_papers = list_seed_papers()
    try:
        author_network = _build_author_network_from_seed_papers(seed_papers)
    except Exception:
        author_network = {"authors": [], "institutions": [], "papers": [], "collaborations": []}

    citation_network = _build_citation_network(papers_data=papers_data, seed_papers=seed_papers)

    _write_json(root / "graphs" / f"{research_id}_author_network.json", author_network)
    _write_json(root / "graphs" / f"{research_id}_citation_network.json", citation_network)

    author_md = "\n".join([
        f"# 作者-机构合作网络（{research_id}）",
        "",
        f"- authors: {len(author_network.get('authors') or [])}",
        f"- institutions: {len(author_network.get('institutions') or [])}",
        f"- collaborations: {len(author_network.get('collaborations') or [])}",
        "",
        "JSON 文件：",
        f"- graphs/{research_id}_author_network.json",
        "",
    ])
    _write_text(root / "graphs" / f"{research_id}_author_network.md", author_md)

    citation_md = "\n".join([
        f"# 引用关系网络（{research_id}）",
        "",
        f"- aiPapers: {len(citation_network.get('aiPapers') or [])}",
        f"- references: {len(citation_network.get('references') or [])}",
        f"- edges: {len(citation_network.get('edges') or [])}",
        "",
        "JSON 文件：",
        f"- graphs/{research_id}_citation_network.json",
        "",
    ])
    _write_text(root / "graphs" / f"{research_id}_citation_network.md", citation_md)

    res_lines = [f"# 实验结果与记录（{research_id}）", "", f"主题：{topic}", ""]
    if experiments:
        res_lines.append("## 实验记录（编号）")
        res_lines.append("")
        for idx, exp in enumerate(experiments, start=1):
            res_lines.extend([
                f"- EXP{idx:03d} {exp.get('id')}: {exp.get('title')}",
                f"  - status: {exp.get('status')}",
                f"  - method: {exp.get('method')}",
            ])
        res_lines.append("")

    if experiment_bundle:
        res_lines.extend([
            "## 实验执行",
            "",
            f"- ran: {experiment_bundle.get('ran')}",
            f"- ok: {experiment_bundle.get('ok')}",
            f"- error: {experiment_bundle.get('error')}",
            "",
            "## 产物路径",
            "",
        ])
        paths = experiment_bundle.get("paths") if isinstance(experiment_bundle.get("paths"), dict) else {}
        for k, v in paths.items():
            res_lines.append(f"- {k}: {v}")
        res_lines.append("")

    res_lines.extend([
        "## 图谱文件",
        "",
        f"- graphs/{research_id}_author_network.json",
        f"- graphs/{research_id}_citation_network.json",
        "",
    ])
    _write_text(root / "experiments" / f"{research_id}_experiment_results.md", "\n".join(res_lines))


def create_paper_record(topic: str, branch_id: int, parent_paper_id: int = None) -> dict:
    """创建并持久化一篇论文记录"""
    papers_data = load_papers()
    current_run = papers_data.get("current_run") if isinstance(papers_data.get("current_run"), dict) else {}
    pending_rid = str(current_run.get("pending_research_id") or "")
    pending_dir = str(current_run.get("pending_research_dir") or "")
    pending_pid = int(current_run.get("pending_paper_id") or 0)
    resume_workspace = bool(pending_rid and pending_dir and pending_pid)
    paper_id = pending_pid if resume_workspace else (len(papers_data.get('papers', [])) + 1)
    branch_papers = [
        p for p in papers_data.get('papers', [])
        if p.get('branch_id') == branch_id and p.get("status") == "generated"
    ]
    research_id = pending_rid if resume_workspace else allocate_research_id(papers_data)
    branches_data = load_branches()
    branch_review = None
    for b in branches_data.get('branches', []):
        if b.get('id') == branch_id:
            branch_review = b.get('review_content')
            break
    provisional_title = topic.strip()[:80] if topic else "未命名论文"

    parent_research_id = None
    if parent_paper_id:
        for p in papers_data.get('papers', []):
            if p.get('id') == parent_paper_id:
                parent_research_id = p.get('research_id')
                break

    def _read_json(path: Path) -> Optional[Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return None

    def _load_experiment_bundle_from_workspace(*, root: Path, research_id: str) -> Dict[str, Any]:
        names = artifact_filenames(research_id)
        exp_path = root / "code" / names["experiment_code"]
        ind_path = root / "data" / names["indicator_sample"]
        data_path = root / "data" / names["experiment_data"]
        bt_path = root / "metrics" / names["backtest_results"]
        qa_trace_path = root / "data" / names["quantagent_trace"]
        qa_res_path = root / "metrics" / names["quantagent_results"]
        return {
            "ran": True,
            "ok": True,
            "error": None,
            "paths": {
                "experiment": str(exp_path),
                "indicator_sample": str(ind_path),
                "experiment_data": str(data_path),
                "backtest_results": str(bt_path),
                "quantagent_trace": str(qa_trace_path),
                "quantagent_results": str(qa_res_path),
            },
            "data": {
                "indicator_sample": _read_json(ind_path) if ind_path.exists() else None,
                "experiment_data": _read_json(data_path) if data_path.exists() else None,
                "backtest_results": _read_json(bt_path) if bt_path.exists() else None,
                "quantagent_trace": _read_json(qa_trace_path) if qa_trace_path.exists() else None,
                "quantagent_results": _read_json(qa_res_path) if qa_res_path.exists() else None,
            },
        }

    if resume_workspace:
        root = Path(pending_dir)
        workspace = {
            "research_id": research_id,
            "research_dir": str(root),
            "file_path": str(root / "article" / f"{research_id}_paper.md"),
            "artifacts": artifacts_for_api(root, research_id),
        }
        experiment_bundle = _load_experiment_bundle_from_workspace(root=root, research_id=research_id)
        qa = experiment_bundle.get("data", {}).get("quantagent_results") if isinstance(experiment_bundle, dict) else None
        if (not qa) or (isinstance(qa, dict) and qa.get("status") == "pending"):
            experiment_bundle = None
    else:
        workspace = create_research_workspace(
            research_id=research_id,
            paper_id=paper_id,
            branch_id=branch_id,
            title=provisional_title,
            topic=topic,
            content=f"# {provisional_title}\n\n> 实验运行中，将在完成后生成完整论文正文。\n",
            status="paused",
            parent_research_id=parent_research_id,
        )
        root = Path(workspace["research_dir"])
        current_run = papers_data.get("current_run") if isinstance(papers_data.get("current_run"), dict) else {}
        current_run["pending_paper_id"] = paper_id
        current_run["pending_research_id"] = research_id
        current_run["pending_research_dir"] = str(root)
        current_run["updated_at"] = datetime.now().isoformat()
        papers_data["current_run"] = current_run
        save_papers(papers_data)
        experiment_bundle = None

    _dbg_set_context(research_id=research_id, research_dir=str(root))
    _dbg_event("paper_create_start", {"research_id": research_id, "paper_id": paper_id, "branch_id": branch_id, "topic": topic})
    try:
        if experiment_bundle is None:
            exp_started = time.perf_counter()
            _dbg_event("paper_experiment_start", {"research_id": research_id, "paper_id": paper_id})
            experiment_bundle = _run_experiment_and_collect(root=root, research_id=research_id)
            _dbg_event("paper_experiment_done", {
                "research_id": research_id,
                "paper_id": paper_id,
                "elapsed_s": round(max(0.0, time.perf_counter() - exp_started), 3),
                "ran": (experiment_bundle.get("ran") if isinstance(experiment_bundle, dict) else None),
                "ok": (experiment_bundle.get("ok") if isinstance(experiment_bundle, dict) else None),
                "error": (str(experiment_bundle.get("error"))[:300] if isinstance(experiment_bundle, dict) and experiment_bundle.get("error") else None),
            })

        persist_started = time.perf_counter()
        _dbg_event("paper_persist_docs_start", {"research_id": research_id, "paper_id": paper_id})
        _persist_experiment_documents(root=root, research_id=research_id, topic=topic, papers_data=papers_data, experiment_bundle=experiment_bundle)
        _dbg_event("paper_persist_docs_done", {"research_id": research_id, "paper_id": paper_id, "elapsed_s": round(max(0.0, time.perf_counter() - persist_started), 3)})

        writing_started = time.perf_counter()
        _dbg_event("paper_writing_start", {"research_id": research_id, "paper_id": paper_id})
        gen = generate_paper_content(
            topic,
            branch_papers,
            branch_review=branch_review,
            research_id=research_id,
            experiment_bundle=experiment_bundle,
            root=root,
        )
        paper_content = str(gen.get("content") or "")
        status = str(gen.get("status") or "failed")
        _dbg_event("paper_writing_done", {"research_id": research_id, "paper_id": paper_id, "elapsed_s": round(max(0.0, time.perf_counter() - writing_started), 3), "content_len": len(paper_content or ""), "content_sample": (paper_content or "")[:200], "status": status, "reason": str(gen.get("reason") or "")[:300]})

        title = extract_title(paper_content) or provisional_title

        save_started = time.perf_counter()
        _dbg_event("paper_save_markdown_start", {"research_id": research_id, "paper_id": paper_id})
        save_article_markdown(root, research_id, paper_content)
        _dbg_event("paper_save_markdown_done", {"research_id": research_id, "paper_id": paper_id, "elapsed_s": round(max(0.0, time.perf_counter() - save_started), 3)})

        meta_started = time.perf_counter()
        _dbg_event("paper_write_meta_start", {"research_id": research_id, "paper_id": paper_id, "status": status})
        write_meta(
            root,
            research_id=research_id,
            paper_id=paper_id,
            branch_id=branch_id,
            title=title,
            topic=topic,
            status=status,
            parent_research_id=parent_research_id,
        )
        _dbg_event("paper_write_meta_done", {"research_id": research_id, "paper_id": paper_id, "elapsed_s": round(max(0.0, time.perf_counter() - meta_started), 3)})

        workspace["file_path"] = str(root / "article" / f"{research_id}_paper.md")
        workspace["artifacts"] = artifacts_for_api(root, research_id)
        if not resume_workspace:
            bump_research_seq(papers_data, research_id)
    except Exception as e:
        _dbg_event("paper_create_exception", {"research_id": research_id, "paper_id": paper_id, "error": str(e)[:600]})
        raise
    finally:
        _dbg_event("paper_create_finish", {"research_id": research_id, "paper_id": paper_id})
        _dbg_clear_context()

    paper_record = {
        "id": paper_id,
        "research_id": research_id,
        "branch_id": branch_id,
        "topic": topic,
        "content": paper_content,
        "title": title,
        "status": status,
        "quality_score": None,
        "iteration_count": 0,
        "created_at": datetime.now().isoformat(),
        "parent_paper_id": parent_paper_id,
        **paper_record_paths(workspace),
    }

    if resume_workspace:
        updated = False
        for idx, existing in enumerate(papers_data.get("papers", []) or []):
            if existing.get("id") == paper_id:
                merged = dict(existing)
                merged.update(paper_record)
                papers_data["papers"][idx] = merged
                updated = True
                break
        if not updated:
            papers_data.setdefault('papers', []).append(paper_record)
    else:
        papers_data.setdefault('papers', []).append(paper_record)
    papers_data['current_paper_id'] = paper_id
    current_run = papers_data.get("current_run") if isinstance(papers_data.get("current_run"), dict) else {}
    if status == "generated":
        current_run.pop("pending_paper_id", None)
        current_run.pop("pending_research_id", None)
        current_run.pop("pending_research_dir", None)
        current_run["updated_at"] = datetime.now().isoformat()
        papers_data["current_run"] = current_run
    save_papers(papers_data)

    for branch in branches_data.get('branches', []):
        if branch['id'] == branch_id:
            branch.setdefault('paper_ids', []).append(paper_id)
            branch['iterations_count'] = branch.get('iterations_count', 0) + 1
            break
    save_branches(branches_data)

    add_history_record({
        "type": "generate",
        "paper_id": paper_id,
        "research_id": research_id,
        "branch_id": branch_id,
        "topic": topic,
        "title": paper_record['title'],
        "status": status
    })

    if status == "generated":
        mongo_result = index_paper_to_mongo(paper_record)
        paper_record["mongo_index"] = mongo_result
    else:
        paper_record["mongo_index"] = {"success": False, "indexed": False, "error": f"skip_mongo_when_{status}"}

    return paper_record


def _seed_papers_for_references(*, limit: int = 12) -> List[Dict[str, Any]]:
    seeds = list_seed_papers() or []
    def _score(p: Dict[str, Any]) -> int:
        try:
            return int(p.get("citation_count") or 0)
        except Exception:
            return 0
    seeds = sorted(seeds, key=_score, reverse=True)
    return seeds[: max(1, int(limit))]


def _build_seed_references_block(*, limit: int = 12) -> str:
    items = _seed_papers_for_references(limit=limit)
    lines = ["## 参考文献", ""]
    for idx, p in enumerate(items, start=1):
        title = (p.get("title") or "").strip()
        authors = (p.get("authors") or "").strip()
        year = p.get("year")
        arxiv_id = (p.get("arxiv_id") or "").strip()
        url = (p.get("arxiv_url") or p.get("pdf_url") or "").strip()
        parts = []
        if authors:
            parts.append(authors)
        if year:
            parts.append(f"({year})")
        if title:
            parts.append(title)
        if arxiv_id:
            parts.append(f"arXiv:{arxiv_id}")
        if url:
            parts.append(url)
        text = " ".join([x for x in parts if x])
        if not text:
            continue
        lines.append(f"[{idx}] {text}")
    return "\n".join(lines).strip() + "\n"


def _apply_reference_block(content: str, ref_block: str) -> str:
    if not content:
        return ref_block
    markers = ["\n## 参考文献", "\n# 参考文献"]
    cut = -1
    for m in markers:
        pos = content.find(m)
        if pos >= 0:
            cut = pos + 1
            break
    if cut >= 0:
        return content[:cut].rstrip() + "\n\n" + ref_block.strip() + "\n"
    return content.rstrip() + "\n\n" + ref_block.strip() + "\n"


def _apply_truthfulness_guard(content: str, *, experiment_bundle: Optional[Dict[str, Any]] = None) -> str:
    if not content or not experiment_bundle or not isinstance(experiment_bundle.get("data"), dict):
        return content
    qa = experiment_bundle["data"].get("quantagent_results")
    if not isinstance(qa, dict):
        return content
    q = qa.get("quantagent") if isinstance(qa.get("quantagent"), dict) else {}
    agents = q.get("agents") if isinstance(q.get("agents"), list) else []
    rule_based = False
    for a in agents:
        if not isinstance(a, dict):
            continue
        sig = str(a.get("signal") or "").lower()
        if ("ma" in sig) or ("rsi" in sig) or ("bb_" in sig) or ("boll" in sig) or ("close" in sig):
            rule_based = True
            break
    if not rule_based:
        return content
    note = "说明：本文 QuantAgent 实验为规则代理投票模拟（信号由 MA/RSI/布林带等规则产生），作为多智能体框架的可复现实验基线；真实逐 tick 的 LLM agent 交易与在线实盘验证留作未来工作。"
    if note in content:
        return content
    marker = "\n## 摘要\n"
    pos = content.find(marker)
    if pos >= 0:
        insert_at = pos + len(marker)
        return content[:insert_at] + "\n" + note + "\n\n" + content[insert_at:].lstrip()
    return note + "\n\n" + content


def _build_experiment_facts_block(experiment_bundle: Optional[Dict[str, Any]]) -> str:
    if not experiment_bundle or not isinstance(experiment_bundle.get("data"), dict):
        return ""
    data = experiment_bundle["data"]
    bt = data.get("backtest_results") if isinstance(data.get("backtest_results"), dict) else {}
    qa = data.get("quantagent_results") if isinstance(data.get("quantagent_results"), dict) else {}
    if not bt and not qa:
        return ""

    facts: List[str] = []
    if isinstance(bt, dict):
        strategies: Dict[str, Any] = {}
        best = str(bt.get("best_strategy") or "")
        primary_symbol = ""
        try:
            universe = bt.get("universe") if isinstance(bt.get("universe"), dict) else {}
            syms = universe.get("symbols") if isinstance(universe.get("symbols"), list) else []
            if syms:
                primary_symbol = str(syms[0] or "")
        except Exception:
            primary_symbol = ""

        if isinstance(bt.get("results"), dict):
            results = bt.get("results") if isinstance(bt.get("results"), dict) else {}
            freq = "1d" if "1d" in results else (next(iter(results.keys()), "") if results else "")
            scope = results.get(freq) if isinstance(results.get(freq), dict) else {}
            portfolio = scope.get("portfolio") if isinstance(scope.get("portfolio"), dict) else {}
            best = str(portfolio.get("best_strategy") or best)
            by_symbol = scope.get("by_symbol") if isinstance(scope.get("by_symbol"), dict) else {}
            if primary_symbol and isinstance(by_symbol.get(primary_symbol), dict):
                strategies = (by_symbol.get(primary_symbol) or {}).get("strategies") if isinstance((by_symbol.get(primary_symbol) or {}).get("strategies"), dict) else {}
            else:
                any_sym = next(iter(by_symbol.keys()), "")
                if any_sym and isinstance(by_symbol.get(any_sym), dict):
                    strategies = (by_symbol.get(any_sym) or {}).get("strategies") if isinstance((by_symbol.get(any_sym) or {}).get("strategies"), dict) else {}
        else:
            strategies = bt.get("strategies") if isinstance(bt.get("strategies"), dict) else {}

        if best:
            facts.append(f"- baseline_best_strategy: {best}")

        ma = strategies.get("ma_crossover") if isinstance(strategies.get("ma_crossover"), dict) else {}
        if ma:
            fast_ma = ma.get("fast_ma")
            slow_ma = ma.get("slow_ma")
            if fast_ma and slow_ma:
                facts.append(f"- baseline_ma_crossover: MA{fast_ma}/MA{slow_ma}")
        rsi = strategies.get("rsi_mean_reversion") if isinstance(strategies.get("rsi_mean_reversion"), dict) else {}
        if rsi:
            lb = rsi.get("lookback")
            lo = rsi.get("lower_threshold")
            hi = rsi.get("upper_threshold")
            hold = rsi.get("hold_days")
            if lb and lo is not None and hi is not None:
                tail = f", hold_days={hold}" if hold is not None else ""
                facts.append(f"- baseline_rsi_mean_reversion: lookback={lb}, lower={lo}, upper={hi}{tail}")
        bb = strategies.get("bollinger_bands") if isinstance(strategies.get("bollinger_bands"), dict) else {}
        if bb:
            window = bb.get("window")
            std_mult = bb.get("std_mult")
            if window and std_mult is not None:
                facts.append(f"- baseline_bollinger_bands: window={window}, std_mult={std_mult}")

        cost_model = bt.get("cost_model") if isinstance(bt.get("cost_model"), dict) else {}
        if cost_model:
            total_bps = cost_model.get("total_bps")
            comm = cost_model.get("commission_bps")
            slip = cost_model.get("slippage_bps")
            if total_bps is not None:
                facts.append(f"- cost_total_bps: {total_bps}")
            if comm is not None or slip is not None:
                facts.append(f"- cost_breakdown_bps: commission={comm}, slippage={slip}")

    if isinstance(qa, dict):
        q = qa.get("quantagent") if isinstance(qa.get("quantagent"), dict) else {}
        agents = q.get("agents") if isinstance(q.get("agents"), list) else []
        if agents:
            for a in agents[:6]:
                if isinstance(a, dict) and a.get("id") and a.get("signal"):
                    facts.append(f"- quantagent_agent_{a.get('id')}_signal: {a.get('signal')}")
        agg = q.get("aggregator")
        if agg:
            facts.append(f"- quantagent_aggregator: {agg}")

    if not facts:
        return ""
    return "## 实验事实（必须严格一致，不得自行改写）\n" + "\n".join(facts) + "\n"


def _section_target_chars(title: str) -> int:
    targets = {
        "摘要": 700,
        "引言": 2200,
        "文献综述": 1800,
        "数据与实验设置": 2200,
        "方法论": 2600,
        "实验过程与可重复实现": 2000,
        "实验结果与分析": 2400,
        "消融实验": 1400,
        "结论与未来工作": 900,
        "参考文献": 600,
    }
    return int(targets.get(title) or 1200)


def _section_needs_more(title: str, body: str) -> bool:
    text = (body or "").strip()
    if not text:
        return True
    if len(text) < _section_target_chars(title):
        return True
    if text.count("$$") % 2 == 1:
        return True
    tail = text[-30:]
    if tail.endswith(("(", "（", "=", "\\frac", "\\sum", "max(", "min(", "在多", "在文", "在实", "其中")):
        return True
    return False


def _extract_expected_experiment_params(experiment_bundle: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not experiment_bundle or not isinstance(experiment_bundle.get("data"), dict):
        return {}
    data = experiment_bundle["data"]
    bt = data.get("backtest_results") if isinstance(data.get("backtest_results"), dict) else {}
    qa = data.get("quantagent_results") if isinstance(data.get("quantagent_results"), dict) else {}

    expected: Dict[str, Any] = {}
    cost_model = {}
    if isinstance(bt, dict):
        cost_model = bt.get("cost_model") if isinstance(bt.get("cost_model"), dict) else {}
    if isinstance(qa, dict) and not cost_model:
        cost_model = qa.get("cost_model") if isinstance(qa.get("cost_model"), dict) else {}
    if cost_model:
        expected["cost_model"] = {
            "commission_bps": cost_model.get("commission_bps"),
            "slippage_bps": cost_model.get("slippage_bps"),
            "total_bps": cost_model.get("total_bps"),
        }

    by_symbol = qa.get("by_symbol") if isinstance(qa, dict) and isinstance(qa.get("by_symbol"), dict) else {}
    sym = next(iter(by_symbol.keys()), "")
    sym_obj = by_symbol.get(sym) if sym and isinstance(by_symbol.get(sym), dict) else {}
    strategies = sym_obj.get("strategies") if isinstance(sym_obj.get("strategies"), dict) else {}
    ma = strategies.get("ma_crossover") if isinstance(strategies.get("ma_crossover"), dict) else {}
    if ma:
        expected["baseline_ma"] = {"fast": ma.get("fast_ma"), "slow": ma.get("slow_ma")}
    rsi = strategies.get("rsi_mean_reversion") if isinstance(strategies.get("rsi_mean_reversion"), dict) else {}
    if rsi:
        expected["baseline_rsi"] = {
            "lookback": rsi.get("lookback"),
            "lower": rsi.get("lower_threshold"),
            "upper": rsi.get("upper_threshold"),
            "hold_days": rsi.get("hold_days"),
        }
    bb = strategies.get("bollinger_bands") if isinstance(strategies.get("bollinger_bands"), dict) else {}
    if bb:
        expected["baseline_bb"] = {"window": bb.get("window"), "std_mult": bb.get("std_mult")}

    q = qa.get("quantagent") if isinstance(qa, dict) else {}
    agents = q.get("agents") if isinstance(q, dict) else []
    if isinstance(agents, list):
        for a in agents:
            if not isinstance(a, dict):
                continue
            if a.get("id") == "trend":
                expected["quantagent_trend_signal"] = a.get("signal")
            if a.get("id") == "meanrev":
                expected["quantagent_meanrev_signal"] = a.get("signal")
            if a.get("id") == "vol":
                expected["quantagent_vol_signal"] = a.get("signal")

    return expected


def _extract_section_text(content: str, title: str) -> str:
    header = f"## {title}"
    start = content.find(header)
    if start < 0:
        return ""
    after = start + len(header)
    nxt = content.find("\n## ", after)
    end = len(content) if nxt < 0 else nxt
    return content[start:end]


def _paper_needs_experiment_fix(content: str, *, experiment_bundle: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    expected = _extract_expected_experiment_params(experiment_bundle)
    issues: List[Dict[str, Any]] = []
    if not expected:
        return {"ok": True, "issues": issues, "expected": expected}

    def _find_ma_pair(text: str) -> Optional[Tuple[int, int]]:
        m = re.search(r"MA\\s*5\\s*/\\s*MA\\s*(\\d+)", text, flags=re.I)
        if m:
            try:
                return 5, int(m.group(1))
            except Exception:
                return None
        m = re.search(r"MA\\s*5[^\\d]{0,20}MA\\s*(\\d+)", text, flags=re.I)
        if m:
            try:
                return 5, int(m.group(1))
            except Exception:
                return None
        return None

    baseline = expected.get("baseline_ma") if isinstance(expected.get("baseline_ma"), dict) else {}
    baseline_slow = baseline.get("slow")
    baseline_fast = baseline.get("fast")
    if baseline_fast and baseline_slow:
        for sec in ("数据与实验设置", "方法论"):
            sec_text = _extract_section_text(content, sec)
            if not sec_text:
                continue
            if ("均线交叉" in sec_text) or ("ma_crossover" in sec_text.lower()):
                pair = _find_ma_pair(sec_text)
                if pair and int(pair[0]) == int(baseline_fast) and int(pair[1]) != int(baseline_slow):
                    issues.append({"type": "baseline_ma_mismatch", "section": sec, "found": f"MA{pair[0]}/MA{pair[1]}", "expected": f"MA{baseline_fast}/MA{baseline_slow}"})

    for sec in ("数据与实验设置", "方法论"):
        sec_text = _extract_section_text(content, sec)
        if not sec_text:
            continue
        if "趋势" in sec_text or "Trend" in sec_text:
            pair = _find_ma_pair(sec_text)
            if pair and int(pair[1]) == int(baseline_slow or 60) and "ma5 > ma20" in str(expected.get("quantagent_trend_signal") or ""):
                issues.append({"type": "trend_ma_confused_with_baseline", "section": sec, "found": f"MA{pair[0]}/MA{pair[1]}", "expected": "MA5/MA20 (trend agent) 与 MA5/MA60 (baseline) 区分"})

    return {"ok": (len(issues) == 0), "issues": issues, "expected": expected}



def generate_paper_content(
    topic: str,
    existing_papers: list,
    research_id: Optional[str] = None,
    experiment_bundle: Optional[Dict[str, Any]] = None,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """生成论文内容"""
    cfg = get_effective_llm_config()
    ok, reason = _llm_available(cfg)
    if not ok:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rid = research_id or stamp
        return {"status": "generated", "reason": reason, "content": f"""# {topic}

> LLM 未配置（{reason}），当前为离线占位输出。生成时间: {stamp}，Run: {rid}

## 摘要

本文提出了一种创新的量化交易策略，旨在解决{topic}领域的关键问题。

## 1. 引言

量化交易在金融领域发挥着越来越重要的作用...

## 2. 方法论

我们提出了一种基于机器学习的交易策略...

## 3. 实验验证

在多个数据集上的实验表明...

## 4. 结论

本文提出的策略在回测中表现优异...
"""}

    topic_list = ""
    if existing_papers:
        recent_papers = existing_papers[-3:]
        topics = [p.get('topic', '未命名') for p in recent_papers]
        topic_list = "\n".join([f"- {t}" for t in topics])

    exp_block = ""
    if experiment_bundle and isinstance(experiment_bundle.get("data"), dict):
        run_info = ""
        if experiment_bundle.get("ran") and not experiment_bundle.get("ok"):
            run_info = f"\n- 实验运行失败: {experiment_bundle.get('error')}\n"
        backtest = (experiment_bundle["data"].get("backtest_results") or {})
        quantagent_results = (experiment_bundle["data"].get("quantagent_results") or {})
        quantagent_trace = experiment_bundle["data"].get("quantagent_trace")
        exp_data = (experiment_bundle["data"].get("experiment_data") or {})
        indicator = experiment_bundle["data"].get("indicator_sample")
        bt_str = json.dumps(backtest, ensure_ascii=False)[:6000] if backtest else ""
        qa_res_str = json.dumps(quantagent_results, ensure_ascii=False)[:4000] if quantagent_results else ""
        qa_trace_dump = quantagent_trace
        if isinstance(quantagent_trace, list):
            qa_trace_dump = quantagent_trace[:20]
        qa_trace_str = json.dumps(qa_trace_dump, ensure_ascii=False)[:2000] if quantagent_trace else ""
        exp_str = json.dumps(exp_data, ensure_ascii=False)[:2000] if exp_data else ""
        ind_str = json.dumps(indicator, ensure_ascii=False)[:2000] if isinstance(indicator, (list, dict)) else ""
        exp_block = f"""

## 实验产物（请基于真实数据撰写，不得编造）
- research_id: {research_id or ""}
- 实验脚本: {experiment_bundle.get("paths", {}).get("experiment") if experiment_bundle else ""}
- 指标样本: {experiment_bundle.get("paths", {}).get("indicator_sample") if experiment_bundle else ""}
- 实验数据: {experiment_bundle.get("paths", {}).get("experiment_data") if experiment_bundle else ""}
- 回测结果: {experiment_bundle.get("paths", {}).get("backtest_results") if experiment_bundle else ""}
- QuantAgent trace: {experiment_bundle.get("paths", {}).get("quantagent_trace") if experiment_bundle else ""}
- QuantAgent 结果汇总: {experiment_bundle.get("paths", {}).get("quantagent_results") if experiment_bundle else ""}
{run_info}

### experiment_data.json（节选）
{exp_str}

### backtest_results.json（节选）
{bt_str}

### quantagent_results.json（节选）
{qa_res_str}

### quantagent_trace.json（节选）
{qa_trace_str}

### indicator_sample.json（节选）
{ind_str}
"""
    facts_block = _build_experiment_facts_block(experiment_bundle)

    min_chars = 14000
    prompt = f"""作为量化交易领域的学术论文写作专家，请根据以下主题生成一篇**详细完整、可复现、重视实验**的学术论文。

研究主题：{topic}

研究编号：{research_id or ""}

论文结构要求（必须包含且写满，不能省略）：
1. **摘要**：300-500字（问题、方法、结果、贡献）
2. **引言**：至少1200字（背景、动机、现有方法不足、贡献点列表、结构安排）
3. **文献综述**：至少1000字（分小节对比 6-10 篇相关方向，指出空白）
4. **数据与实验设置**：至少1200字（数据源、时间范围、预处理、特征/指标、基准定义、评价指标、训练/验证划分）
5. **方法论**：至少1600字（完整公式、算法伪代码、参数设置、复杂度与风险控制）
6. **实验过程与可重复实现**：至少1200字（如何运行脚本、依赖、随机性控制、输出文件解释）
7. **实验结果与分析**：至少1600字（与基准对比表格、风险收益指标表格、收益曲线文字解读、统计检验）
8. **消融实验**：至少800字（移除/替换关键模块的结果表格）
9. **结论与未来工作**：400-600字
10. **参考文献**：至少 8 条

重要约束：
- 必须使用 Markdown 输出，包含 ## 章节标题
- 全文字数不少于 {min_chars} 中文字符（约 4-5 页 A4 正文）
- 不要写占位符（如"此处省略..."），每个章节都必须有实质内容
- 实验部分必须以提供的实验产物为依据，不得编造具体数值
- 实验对齐：metrics/*_backtest_results.json 表示 baseline（技术指标策略回测）；metrics/*_quantagent_results.json 表示 QuantAgent（多智能体投票模拟）结果；两者均存在时必须同时报告并明确区分
- 如果 QuantAgent 实验仅为“投票模拟/规则代理”，必须如实描述，不得声称已完成逐 tick LLM 交易/线上实盘验证
- 参考文献只允许来自“允许引用列表”，不得杜撰论文/作者/年份/arXiv

{exp_block}
{facts_block}

请直接输出完整论文，不包含任何其他说明。
"""

    seed_refs = _seed_papers_for_references(limit=12)
    if seed_refs:
        lines = []
        for p in seed_refs:
            arxiv_id = (p.get("arxiv_id") or "").strip()
            title = (p.get("title") or "").strip()
            year = p.get("year")
            url = (p.get("arxiv_url") or p.get("pdf_url") or "").strip()
            prefix = f"arXiv:{arxiv_id}" if arxiv_id else "seed"
            tail = f" ({year})" if year else ""
            if url:
                lines.append(f"- {prefix}{tail} {title} {url}".strip())
            else:
                lines.append(f"- {prefix}{tail} {title}".strip())
        prompt += "\n\n## 允许引用列表（只能从这里挑选写入参考文献）\n" + "\n".join(lines) + "\n"

    if topic_list:
        prompt += f"已有关键主题：\n{topic_list}\n\n请确保新论文与上述主题有显著区别。\n"

    if branch_review:
        excerpt = branch_review.strip()
        if len(excerpt) > 3000:
            excerpt = excerpt[:3000]
        if excerpt:
            prompt += f"\n\n## 分支综述（用户上传摘录）\n{excerpt}\n"

    # 注入数据注册表中的文献与市场数据上下文
    data_context = get_paper_generation_context(topic)
    if data_context.strip():
        prompt += f"\n\n## 可用研究数据与文献背景\n{data_context}\n"

    provider = str(cfg.get("provider") or "").lower()
    model = str(cfg.get("model") or "")
    context_window_tokens = 0
    try:
        context_window_tokens = int(os.environ.get("CONTEXT_WINDOW_TOKENS") or 0)
    except Exception:
        context_window_tokens = 0
    if context_window_tokens <= 0:
        context_window_tokens = 204800 if provider == "minimax" else 128000

    max_prompt_len = 0
    try:
        max_prompt_len = int(os.environ.get("WRITING_MAX_PROMPT_CHARS") or 0)
    except Exception:
        max_prompt_len = 0
    if max_prompt_len <= 0:
        max_prompt_len = 60000 if provider == "minimax" else 30000
    if len(prompt) > max_prompt_len:
        if data_context:
            try:
                ctx_cap = int(os.environ.get("WRITING_DATA_CONTEXT_CHARS") or 0)
            except Exception:
                ctx_cap = 0
            if ctx_cap <= 0:
                ctx_cap = 12000
            data_context = data_context[:ctx_cap]
            prompt = prompt[:max_prompt_len - len(data_context) - 50] + f"\n\n## 可用研究数据与文献背景\n{data_context}\n"
        else:
            prompt = prompt[:max_prompt_len]

    estimated_input_tokens = len(prompt) // 3
    reserve_tokens = 0
    try:
        reserve_tokens = int(os.environ.get("WRITING_CONTEXT_RESERVE_TOKENS") or 0)
    except Exception:
        reserve_tokens = 0
    if reserve_tokens <= 0:
        reserve_tokens = 20000
    max_output_tokens_cap = 0
    try:
        max_output_tokens_cap = int(os.environ.get("WRITING_MAX_OUTPUT_TOKENS") or 0)
    except Exception:
        max_output_tokens_cap = 0
    if max_output_tokens_cap <= 0:
        max_output_tokens_cap = 32000

    max_output_tokens = min(
        int(max_output_tokens_cap),
        max(2048, int(context_window_tokens) - int(estimated_input_tokens) - int(reserve_tokens)),
    )
    cfg_max = int(cfg.get("max_tokens") or 0)
    if cfg_max > 0:
        max_output_tokens = min(max_output_tokens, cfg_max)

    total_timeout_s = 0
    try:
        total_timeout_s = int(cfg.get("writing_total_timeout_s") or 0)
    except Exception:
        total_timeout_s = 0
    try:
        env_total_s = int(os.environ.get("WRITING_TOTAL_TIMEOUT_S") or 0)
    except Exception:
        env_total_s = 0
    if env_total_s > 0:
        total_timeout_s = env_total_s
    if total_timeout_s <= 0:
        total_timeout_s = 1800  # 论文生成需要更长时间(30分钟)
    writing_t0 = time.perf_counter()

    def _remaining_s() -> float:
        return max(0.0, float(total_timeout_s) - max(0.0, time.perf_counter() - writing_t0))

    checkpoint_path: Optional[Path] = None
    article_path: Optional[Path] = None
    if root and research_id:
        checkpoint_path = root / "logs" / f"{research_id}_writing_checkpoint.json"
        article_path = root / "article" / f"{research_id}_paper.md"

    def _load_checkpoint() -> Dict[str, Any]:
        if not checkpoint_path or (not checkpoint_path.exists()):
            return {}
        try:
            return json.loads(checkpoint_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return {}

    def _save_checkpoint(patch: Dict[str, Any]) -> None:
        if not checkpoint_path:
            return
        started = time.perf_counter()
        existing = _load_checkpoint()
        merged = dict(existing)
        merged.update(patch)
        merged["updated_at"] = datetime.now().isoformat()
        _dbg_event("writing_checkpoint_save_start", {"research_id": research_id or "", "path": str(checkpoint_path), "patch_keys": list(patch.keys())})
        _write_json(checkpoint_path, merged)
        wrote_bytes: Optional[int] = None
        try:
            wrote_bytes = int(checkpoint_path.stat().st_size)
        except Exception:
            wrote_bytes = None
        _dbg_event("writing_checkpoint_save_done", {"research_id": research_id or "", "path": str(checkpoint_path), "elapsed_s": round(max(0.0, time.perf_counter() - started), 3), "bytes": wrote_bytes})

    def _save_draft(text: str) -> None:
        if root and research_id:
            started = time.perf_counter()
            _dbg_event("writing_draft_save_start", {"research_id": research_id or "", "path": str(root / "article" / f"{research_id}_paper.md"), "content_len": len(text or "")})
            save_article_markdown(root, research_id, text or "")
            wrote_bytes: Optional[int] = None
            try:
                wrote_bytes = int((root / "article" / f"{research_id}_paper.md").stat().st_size)
            except Exception:
                wrote_bytes = None
            _dbg_event("writing_draft_save_done", {"research_id": research_id or "", "elapsed_s": round(max(0.0, time.perf_counter() - started), 3), "bytes": wrote_bytes})

    content = ""
    try:
        last_tick = time.perf_counter()
        checkpoint = _load_checkpoint()

        try:
            min_chunk_tokens = int(os.environ.get("WRITING_CHUNK_MIN_TOKENS") or 0)
        except Exception:
            min_chunk_tokens = 0
        if min_chunk_tokens <= 0:
            min_chunk_tokens = 800

        try:
            max_chunk_tokens = int(os.environ.get("WRITING_CHUNK_MAX_TOKENS") or 0)
        except Exception:
            max_chunk_tokens = 0
        if max_chunk_tokens <= 0:
            max_chunk_tokens = 8000 if provider == "minimax" else 6000
        if cfg_max > 0:
            max_chunk_tokens = min(int(max_chunk_tokens), int(cfg_max))

        try:
            forced_chunk = int(os.environ.get("WRITING_CHUNK_TOKENS") or 0)
        except Exception:
            forced_chunk = 0

        if forced_chunk > 0:
            chunk_tokens = int(forced_chunk)
        else:
            base_chunk = int(max_output_tokens)
            if cfg_max > 0:
                base_chunk = max(int(min_chunk_tokens), min(int(max_output_tokens), int(cfg_max // 2 if cfg_max >= 4096 else cfg_max)))
            else:
                base_chunk = max(int(min_chunk_tokens), min(int(max_output_tokens), 6000))

            chk_chunk = checkpoint.get("chunk_tokens")
            if isinstance(chk_chunk, int):
                chunk_tokens = chk_chunk
            else:
                try:
                    chunk_tokens = int(chk_chunk)
                except Exception:
                    chunk_tokens = base_chunk
            if int(chunk_tokens) <= 0:
                chunk_tokens = base_chunk

        chunk_tokens = max(int(min_chunk_tokens), min(int(max_chunk_tokens), int(chunk_tokens)))

        def _call_with_backoff(p: str, *, temperature: float, max_tokens: int) -> Tuple[str, Dict[str, Any]]:
            tokens = int(max_tokens)
            last_err: Optional[Exception] = None
            for attempt in range(5):
                if _remaining_s() <= 1.0:
                    raise TimeoutError(f"writing total timeout ({total_timeout_s}s)")
                try:
                    started = time.perf_counter()
                    _dbg_event("writing_llm_attempt", {"topic": topic, "stage": "call_with_backoff", "attempt": attempt + 1, "max_tokens": tokens, "prompt_len": len(p or ""), "prompt_sample": (p or "")[:200]})
                    text = call_llm(p, temperature=temperature, max_tokens=tokens)
                    elapsed_s = max(0.0, time.perf_counter() - started)
                    _dbg_event("writing_llm_ok", {"topic": topic, "stage": "call_with_backoff", "attempt": attempt + 1, "max_tokens": tokens, "elapsed_s": round(elapsed_s, 3), "content_len": len(text or "")})
                    return text, {"attempt": attempt + 1, "elapsed_s": elapsed_s, "used_tokens": tokens}
                except Exception as exc:
                    last_err = exc
                    msg = str(exc)
                    _dbg_event("writing_llm_error", {"topic": topic, "stage": "call_with_backoff", "attempt": attempt + 1, "max_tokens": tokens, "error": msg[:400]})
                    lower = msg.lower()
                    retryable = (
                        ("http 504" in lower)
                        or ("gateway time-out" in lower)
                        or ("gateway timeout" in lower)
                        or ("upstream request failed" in lower)
                        or ("temporarily unavailable" in lower)
                    )
                    if retryable:
                        tokens = max(int(min_chunk_tokens), int(tokens * 0.6))
                        continue
                    raise
            if last_err:
                raise last_err
            raise RuntimeError("llm request failed")

        def _adapt_chunk_tokens(current: int, meta: Dict[str, Any]) -> int:
            used = int(meta.get("used_tokens") or current)
            attempt = int(meta.get("attempt") or 1)
            try:
                elapsed_s = float(meta.get("elapsed_s") or 0.0)
            except Exception:
                elapsed_s = 0.0
            nxt = used
            if attempt == 1 and elapsed_s > 0 and elapsed_s <= 12.0:
                nxt = min(int(max_chunk_tokens), max(int(min_chunk_tokens), int(current * 1.25) + 200))
            elif attempt >= 2 or elapsed_s >= 25.0:
                nxt = max(int(min_chunk_tokens), int(min(current, used) * 0.85))
            if _remaining_s() <= 300.0:
                nxt = min(int(nxt), max(int(min_chunk_tokens), 1200))
            if int(nxt) != int(current):
                _save_checkpoint({"chunk_tokens": int(nxt)})
            return int(nxt)

        def _fmt_metric_row(name: str, m: Dict[str, Any]) -> str:
            keys = ("total_return", "annual_return", "sharpe_ratio", "max_drawdown", "win_rate", "total_trades", "annual_vol")
            vals = []
            for k in keys:
                v = m.get(k) if isinstance(m, dict) else None
                vals.append("-" if v is None else str(v))
            return f"| {name} | " + " | ".join(vals) + " |"

        def _build_metrics_tables() -> Dict[str, str]:
            if not experiment_bundle or not isinstance(experiment_bundle.get("data"), dict):
                return {}
            data = experiment_bundle["data"]
            qa = data.get("quantagent_results")
            bt = data.get("backtest_results")
            if not isinstance(qa, dict) and not isinstance(bt, dict):
                return {}

            baseline_name = "baseline_best"
            baseline_metrics: Dict[str, Any] = {}
            benchmark_metrics: Dict[str, Any] = {}
            quantagent_metrics: Dict[str, Any] = {}
            ablations: Dict[str, Any] = {}

            if isinstance(qa, dict):
                baseline_name = str(qa.get("baseline_best_strategy") or "baseline_best")
                baseline_metrics = qa.get("baseline_best_strategy_metrics") if isinstance(qa.get("baseline_best_strategy_metrics"), dict) else {}
                benchmark_metrics = qa.get("benchmark") if isinstance(qa.get("benchmark"), dict) else {}
                q = qa.get("quantagent") if isinstance(qa.get("quantagent"), dict) else {}
                quantagent_metrics = q.get("metrics") if isinstance(q.get("metrics"), dict) else {}
                ablations = q.get("ablations") if isinstance(q.get("ablations"), dict) else {}
            elif isinstance(bt, dict):
                strategies = bt.get("strategies") if isinstance(bt.get("strategies"), dict) else {}
                best_key = str(bt.get("best_strategy") or "")
                best = strategies.get(best_key) if isinstance(strategies.get(best_key), dict) else {}
                baseline_name = best_key or "baseline_best"
                baseline_metrics = best.get("metrics") if isinstance(best.get("metrics"), dict) else {}
                benchmark_metrics = bt.get("benchmark") if isinstance(bt.get("benchmark"), dict) else {}

            compare_lines = [
                "### 指标对比表（程序注入）",
                "",
                "| 策略 | total_return(%) | annual_return(%) | sharpe | max_drawdown(%) | win_rate(%) | trades | annual_vol(%) |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
            if quantagent_metrics:
                compare_lines.append(_fmt_metric_row("QuantAgent", quantagent_metrics))
            if baseline_metrics:
                compare_lines.append(_fmt_metric_row(f"Baseline:{baseline_name}", baseline_metrics))
            if benchmark_metrics:
                br = dict(benchmark_metrics)
                if "sharpe_ratio" not in br:
                    br["sharpe_ratio"] = "-"
                if "max_drawdown" not in br:
                    br["max_drawdown"] = "-"
                if "win_rate" not in br:
                    br["win_rate"] = "-"
                if "total_trades" not in br:
                    br["total_trades"] = "-"
                if "annual_vol" not in br:
                    br["annual_vol"] = "-"
                compare_lines.append(_fmt_metric_row(f"Benchmark:{str(benchmark_metrics.get('name') or 'buy&hold')}", br))
            compare_md = "\n".join(compare_lines).strip()

            ab_lines = [
                "### 消融对比表（程序注入）",
                "",
                "| 变体 | total_return(%) | annual_return(%) | sharpe | max_drawdown(%) | win_rate(%) | trades | annual_vol(%) |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
            if isinstance(ablations, dict) and ablations:
                order = list(ablations.keys())
                for key in order[:12]:
                    m = ablations.get(key)
                    if isinstance(m, dict):
                        ab_lines.append(_fmt_metric_row(str(key), m))
            ab_md = "\n".join(ab_lines).strip()

            return {
                "实验结果与分析": compare_md if compare_md else "",
                "消融实验": ab_md if ab_md else "",
            }

        tables_by_section = _build_metrics_tables()
        try:
            writing_mode = str(
                (checkpoint.get("writing_mode") if isinstance(checkpoint.get("writing_mode"), str) else "")
                or (cfg.get("writing_mode") if isinstance(cfg.get("writing_mode"), str) else "")
                or (os.environ.get("WRITING_MODE") or "")
                or "sectioned"
            )
        except Exception:
            writing_mode = "sectioned"
        writing_mode = writing_mode.strip().lower() or "sectioned"
        outline = checkpoint.get("outline") if isinstance(checkpoint.get("outline"), str) else ""
        use_sectioned = (writing_mode == "sectioned") or bool(outline)
        if use_sectioned and (not isinstance(outline, str)):
            use_sectioned = False
        _dbg_event("writing_start", {"topic": topic, "min_chars": min_chars, "chunk_tokens": chunk_tokens, "min_chunk_tokens": int(min_chunk_tokens), "max_chunk_tokens": int(max_chunk_tokens), "max_output_tokens": max_output_tokens, "prompt_len": len(prompt), "data_context_len": len(data_context or ""), "mode": writing_mode, "context_window_tokens": int(context_window_tokens), "model": model})
        resumed = False
        content = ""
        next_step = 0
        if article_path and article_path.exists() and isinstance(checkpoint.get("status"), str) and checkpoint.get("status") in ("paused", "in_progress", "failed", "completed"):
            try:
                content = article_path.read_text(encoding="utf-8", errors="replace")
                next_step = int(checkpoint.get("next_step") or 0)
                resumed = True
            except Exception:
                content = ""
                next_step = 0
                resumed = False
        if resumed and isinstance(checkpoint.get("status"), str) and checkpoint.get("status") == "completed":
            if (len(content or "") < int(min_chars)) or ("## 参考文献" not in (content or "")):
                _save_checkpoint({"status": "paused", "reason": "incomplete", "content_len": len(content or ""), "has_refs": ("## 参考文献" in (content or ""))})
        if resumed:
            _dbg_event("writing_resume_loaded", {"topic": topic, "research_id": research_id or "", "content_len": len(content), "next_step": next_step})
        if use_sectioned:
            sections: List[Tuple[str, str]] = [
                ("摘要", "300-500字（问题、方法、结果、贡献）"),
                ("引言", "至少1200字（背景、动机、现有方法不足、贡献点列表、结构安排）"),
                ("文献综述", "至少1000字（分小节对比 6-10 篇相关方向，指出空白）"),
                ("数据与实验设置", "至少1200字（数据源、时间范围、预处理、特征/指标、基准定义、评价指标、训练/验证划分）"),
                ("方法论", "至少1600字（完整公式、算法伪代码、参数设置、复杂度与风险控制）"),
                ("实验过程与可重复实现", "至少1200字（如何运行脚本、依赖、随机性控制、输出文件解释）"),
                ("实验结果与分析", "至少1600字（必须同时报告 baseline(backtest_results) 与 QuantAgent(quantagent_results) 的指标对比表，解释差异、收益曲线文字解读、统计检验；数值只能来自 JSON）"),
                ("消融实验", "至少800字（必须使用 quantagent_results.ablations 给出至少 3 组消融对比表，并解释每个智能体的贡献；数值只能来自 JSON）"),
                ("结论与未来工作", "400-600字"),
                ("参考文献", "至少 8 条"),
            ]

            if resumed and content:
                dup = False
                if content.count("\n# ") >= 1:
                    dup = True
                if not dup:
                    for sec_title, _ in sections:
                        if content.count(f"## {sec_title}") > 1:
                            dup = True
                            break
                if dup:
                    _dbg_event("writing_restart_for_structure", {"topic": topic, "research_id": research_id or "", "content_len": len(content), "next_step": next_step})
                    resumed = False
                    next_step = 0
                    outline = ""
                    content = f"# {topic}\n\n"
                    _save_draft(content)
                    _save_checkpoint({"status": "in_progress", "writing_mode": "sectioned", "next_step": 0, "reason": "restart_for_structure"})

            outline_prompt = f"""你将撰写一篇量化交易学术论文，请先生成“详细提纲”，用于后续分章节生成。

研究主题：{topic}
研究编号：{research_id or ""}

要求：
- 仅输出提纲，不要写正文
- 使用 Markdown 输出，每个章节必须以二级标题开头，格式为：## <章节名>
- 必须覆盖以下章节（顺序一致）：{", ".join([s[0] for s in sections])}
- 每章给出 4-8 条要点（用 - 列表），包括应写的内容、表格/公式/伪代码建议
- “实验结果与分析/消融实验”只能基于给定实验产物，不得编造数值

{exp_block}
{facts_block}

## 可用研究数据与文献背景
{(data_context or "")[:6000]}
"""

            if (not resumed) or (not outline):
                _save_checkpoint({"status": "in_progress", "writing_mode": "sectioned", "min_chars": min_chars, "next_step": 0})
                outline, meta = _call_with_backoff(outline_prompt, temperature=0.4, max_tokens=min(1200, chunk_tokens))
                chunk_tokens = _adapt_chunk_tokens(int(chunk_tokens), meta)
                outline = (outline or "").strip()
                if not outline:
                    _save_checkpoint({"status": "failed", "reason": "empty_outline"})
                    return {"status": "failed", "reason": "empty_outline", "content": ""}
                _save_checkpoint({"status": "in_progress", "writing_mode": "sectioned", "outline": outline, "next_step": 0})
                content = f"# {topic}\n\n"
                _save_draft(content)
            else:
                _save_checkpoint({"writing_mode": "sectioned"})
                if not content.strip():
                    content = f"# {topic}\n\n"
                    _save_draft(content)

            for idx in range(next_step, len(sections)):
                if _remaining_s() <= 1.0:
                    raise TimeoutError(f"writing total timeout ({total_timeout_s}s)")
                if time.perf_counter() - last_tick >= 10.0:
                    last_tick = time.perf_counter()
                    _dbg_event("writing_tick", {"topic": topic, "step": idx, "content_len": len(content or ""), "remaining_s": round(_remaining_s(), 1), "has_refs": ("## 参考文献" in content)})
                    try:
                        papers = load_papers()
                        run_metrics = papers.get("run_metrics") if isinstance(papers.get("run_metrics"), dict) else {}
                        run_metrics["writing_heartbeat"] = {
                            "research_id": research_id or "",
                            "step": idx,
                            "section": str(sections[idx][0]),
                            "content_len": len(content or ""),
                            "updated_at": datetime.now().isoformat(),
                        }
                        run_metrics["updated_at"] = datetime.now().isoformat()
                        papers["run_metrics"] = run_metrics
                        save_papers(papers)
                    except Exception:
                        pass
                sec_title, sec_req = sections[idx]
                tail = (content or "")[-2400:]
                injected_table = (tables_by_section.get(sec_title) or "").strip()
                injected_hint = ""
                if injected_table:
                    injected_hint = "\n\n你必须原样包含下方表格块（不要改动任何数字/字段，不要删除表格）：\n\n" + injected_table + "\n"
                sec_prompt = f"""你正在分章节撰写量化交易学术论文，请只输出当前章节内容。

研究主题：{topic}
研究编号：{research_id or ""}

提纲：
{outline[:8000]}

已写内容末尾（供你续写衔接，不要重复）：
{tail}

当前要写的章节：{sec_title}
章节要求：{sec_req}

约束：
- 只输出本章节，不要输出其他章节
- 不要输出任何以 "# " 或 "## " 开头的标题行（标题由系统自动添加）；允许使用 "###" 及更低级标题作为小节
- 如果需要表格，必须用 Markdown 表格
- 涉及实验数值时，只能引用实验产物内容，不得编造

{exp_block}
{facts_block}
{injected_hint}
"""
                _dbg_event("writing_section_prepare", {"topic": topic, "step": idx, "section": sec_title, "tail_len": len(tail), "outline_len": len(outline or "")})
                more = ""
                meta: Dict[str, Any] = {}
                for _ in range(2):
                    more, meta = _call_with_backoff(sec_prompt, temperature=0.7, max_tokens=chunk_tokens)
                    chunk_tokens = _adapt_chunk_tokens(int(chunk_tokens), meta)
                    more = (more or "").strip()
                    if more:
                        break
                _dbg_event("writing_section_done", {"topic": topic, "step": idx, "section": sec_title, "more_len": len(more), "more_sample": more[:200]})
                if not more:
                    _save_checkpoint({"status": "paused", "writing_mode": "sectioned", "outline": outline, "next_step": idx, "content_len": len(content), "has_refs": ("## 参考文献" in content), "reason": f"empty_section:{sec_title}"})
                    return {"status": "paused", "reason": f"empty_section:{sec_title}", "content": content}
                header = f"## {sec_title}"
                if (not resumed) and header in content:
                    content = content.split(header)[0].rstrip() + "\n\n"
                body_lines = (more or "").splitlines()
                while body_lines and (not body_lines[0].strip()):
                    body_lines.pop(0)
                while body_lines and (body_lines[0].startswith("# ") or body_lines[0].startswith("## ")):
                    body_lines.pop(0)
                    while body_lines and (not body_lines[0].strip()):
                        body_lines.pop(0)
                more_body = "\n".join(body_lines).strip()
                if injected_table and ("### 指标对比表（程序注入）" not in (more_body or "")) and ("### 消融对比表（程序注入）" not in (more_body or "")):
                    more_body = injected_table + "\n\n" + (more_body or "")
                tries = 0
                while _section_needs_more(sec_title, more_body) and tries < 3 and _remaining_s() > 20.0:
                    tries += 1
                    sec_tail = (more_body or "")[-1600:]
                    cont_prompt = f"""你正在完善论文的单个章节，请继续补全当前章节内容，只输出需要追加的正文，不要重复已有内容。

章节：{sec_title}
章节要求：{sec_req}

已写章节末尾（供你衔接续写，不要重复）：
{sec_tail}

约束：
- 不要输出任何以 "# " 或 "## " 开头的标题行
- 如有公式，请确保 $$ 成对闭合
- 涉及实验数值时，只能引用实验产物内容，不得编造

{exp_block}
{facts_block}
{injected_hint}
"""
                    extra, meta2 = _call_with_backoff(cont_prompt, temperature=0.65, max_tokens=max(int(min_chunk_tokens), int(chunk_tokens * 0.75)))
                    chunk_tokens = _adapt_chunk_tokens(int(chunk_tokens), meta2)
                    extra = (extra or "").strip()
                    if not extra:
                        break
                    extra_lines = extra.splitlines()
                    while extra_lines and (not extra_lines[0].strip()):
                        extra_lines.pop(0)
                    while extra_lines and (extra_lines[0].startswith("# ") or extra_lines[0].startswith("## ")):
                        extra_lines.pop(0)
                        while extra_lines and (not extra_lines[0].strip()):
                            extra_lines.pop(0)
                    extra_body = "\n".join(extra_lines).strip()
                    if extra_body:
                        more_body = (more_body.rstrip() + "\n\n" + extra_body).strip()
                content = content.rstrip() + "\n\n" + header + "\n\n" + (more_body or "")
                _save_draft(content)
                _save_checkpoint({"status": "in_progress", "writing_mode": "sectioned", "outline": outline, "next_step": idx + 1, "content_len": len(content), "has_refs": ("## 参考文献" in content)})

            def _find_section_span(text: str, title: str) -> Optional[Tuple[int, int]]:
                header = f"## {title}"
                start = text.find(header)
                if start < 0:
                    return None
                after = start + len(header)
                nxt = text.find("\n## ", after)
                end = len(text) if nxt < 0 else nxt
                return start, end

            def _expand_section_once(text: str, title: str, req: str) -> str:
                span = _find_section_span(text, title)
                if not span:
                    return text
                start, end = span
                section_block = text[start:end]
                tail = section_block[-1800:]
                expand_prompt = f"""你正在补全论文的单个章节，请在不改变已有内容的前提下，在该章节末尾追加补充内容。

章节：{title}
章节要求：{req}

该章节末尾（供你衔接续写，不要重复）：
{tail}

约束：
- 只输出需要追加的正文，不要输出任何以 "# " 或 "## " 开头的标题行
- 允许使用 "###" 作为小节标题
- 如有公式，请确保 $$ 成对闭合
- 涉及实验数值时，只能引用实验产物内容，不得编造

{exp_block}
{facts_block}
"""
                extra, meta = _call_with_backoff(expand_prompt, temperature=0.6, max_tokens=max(int(min_chunk_tokens), int(chunk_tokens * 0.75)))
                chunk_tokens = _adapt_chunk_tokens(int(chunk_tokens), meta)
                extra = (extra or "").strip()
                if not extra:
                    return text
                extra_lines = extra.splitlines()
                while extra_lines and (not extra_lines[0].strip()):
                    extra_lines.pop(0)
                while extra_lines and (extra_lines[0].startswith("# ") or extra_lines[0].startswith("## ")):
                    extra_lines.pop(0)
                    while extra_lines and (not extra_lines[0].strip()):
                        extra_lines.pop(0)
                extra_body = "\n".join(extra_lines).strip()
                if not extra_body:
                    return text
                new_section = (section_block.rstrip() + "\n\n" + extra_body).rstrip()
                return text[:start] + new_section + text[end:]

            expansions = 0
            while len(content) < int(min_chars) and _remaining_s() > 25.0 and expansions < 3:
                expansions += 1
                candidates = ["实验结果与分析", "方法论", "数据与实验设置", "文献综述", "引言"]
                picked: Optional[str] = None
                picked_req: Optional[str] = None
                for t, r in sections:
                    if t in candidates:
                        span = _find_section_span(content, t)
                        if not span:
                            continue
                        start, end = span
                        body = content[start:end]
                        if _section_needs_more(t, body):
                            picked = t
                            picked_req = r
                            break
                if not picked or not picked_req:
                    break
                before_len = len(content)
                content = _expand_section_once(content, picked, picked_req)
                if len(content) <= before_len:
                    break
                _save_draft(content)
                _save_checkpoint({"status": "in_progress", "writing_mode": "sectioned", "outline": outline, "next_step": len(sections), "content_len": len(content), "has_refs": ("## 参考文献" in content)})

            done = (len(content) >= min_chars and "## 参考文献" in content)
            if done:
                content = _apply_reference_block(content, _build_seed_references_block(limit=12))
                content = _apply_truthfulness_guard(content, experiment_bundle=experiment_bundle)
                quality = _paper_needs_experiment_fix(content, experiment_bundle=experiment_bundle)
                if (not quality.get("ok")) and isinstance(quality.get("issues"), list):
                    rewrites: List[str] = []
                    for it in quality.get("issues")[:2]:
                        sec = str((it or {}).get("section") or "")
                        if sec and sec not in rewrites:
                            rewrites.append(sec)

                    for sec_title in rewrites:
                        sec_req = ""
                        for t, r in sections:
                            if t == sec_title:
                                sec_req = r
                                break
                        span = _find_section_span(content, sec_title)
                        if not span:
                            continue
                        start, end = span
                        current = content[start:end]
                        tail = current[-1800:]
                        injected_table = (tables_by_section.get(sec_title) or "").strip()
                        injected_hint = ""
                        if injected_table:
                            injected_hint = "\n\n你必须原样包含下方表格块（不要改动任何数字/字段，不要删除表格）：\n\n" + injected_table + "\n"
                        fix_prompt = f"""你正在修复论文的单个章节，使其与实验 JSON 完全一致。请重写该章节的正文内容（不输出任何 #/## 标题行），并确保不出现与实验事实相矛盾的参数/数值。

章节：{sec_title}
章节要求：{sec_req}

该章节当前末尾（供你理解原文风格；输出时不要复刻错误）：
{tail}

硬性约束：
- 不要输出任何以 \"# \" 或 \"## \" 开头的标题行
- 只在需要时使用 \"###\" 小节标题
- 涉及任何实验参数/数值时，只能引用实验产物内容，不得编造

{exp_block}
{facts_block}
{injected_hint}
"""
                        fixed, meta = _call_with_backoff(fix_prompt, temperature=0.55, max_tokens=max(int(min_chunk_tokens), min(int(chunk_tokens), 2200)))
                        chunk_tokens = _adapt_chunk_tokens(int(chunk_tokens), meta)
                        fixed = (fixed or "").strip()
                        if fixed:
                            fixed_lines = fixed.splitlines()
                            while fixed_lines and (not fixed_lines[0].strip()):
                                fixed_lines.pop(0)
                            while fixed_lines and (fixed_lines[0].startswith("# ") or fixed_lines[0].startswith("## ")):
                                fixed_lines.pop(0)
                                while fixed_lines and (not fixed_lines[0].strip()):
                                    fixed_lines.pop(0)
                            fixed_body = "\n".join(fixed_lines).strip()
                            if injected_table and ("### 指标对比表（程序注入）" not in fixed_body) and ("### 消融对比表（程序注入）" not in fixed_body) and (sec_title in ("实验结果与分析", "消融实验")):
                                fixed_body = injected_table + "\n\n" + fixed_body
                            if fixed_body:
                                content = content[:start] + f"## {sec_title}\n\n" + fixed_body.rstrip() + content[end:]
                                _save_draft(content)
                    _save_checkpoint({"quality": quality, "quality_rewrites": rewrites})
                _save_checkpoint({"status": "completed", "writing_mode": "sectioned", "outline": outline, "next_step": len(sections), "content_len": len(content), "has_refs": True, "reason": None})
                return {"status": "generated", "reason": None, "content": content}
            _save_checkpoint({"status": "paused", "writing_mode": "sectioned", "outline": outline, "next_step": int(checkpoint.get("next_step") or next_step), "content_len": len(content), "has_refs": ("## 参考文献" in content), "reason": "incomplete"})
            return {"status": "paused", "reason": "incomplete", "content": content}

        if not resumed:
            _save_checkpoint({"status": "in_progress", "next_step": 0, "min_chars": min_chars})
            content, meta = _call_with_backoff(prompt, temperature=0.7, max_tokens=chunk_tokens)
            chunk_tokens = _adapt_chunk_tokens(int(chunk_tokens), meta)
            _dbg_event("writing_first_chunk_done", {"topic": topic, "content_len": len(content or ""), "content_sample": (content or "")[:200]})
            if not content:
                _save_checkpoint({"status": "failed", "reason": "empty_content"})
                return {"status": "failed", "reason": "empty_content", "content": ""}
            if content.startswith("LLM 未就绪"):
                _save_checkpoint({"status": "failed", "reason": "llm_not_ready"})
                return {"status": "failed", "reason": "llm_not_ready", "content": content}
            _save_draft(content)
            _save_checkpoint({"status": "in_progress", "next_step": 0, "content_len": len(content), "has_refs": ("## 参考文献" in content)})

        for idx in range(next_step, 10):
            if _remaining_s() <= 1.0:
                raise TimeoutError(f"writing total timeout ({total_timeout_s}s)")
            if time.perf_counter() - last_tick >= 10.0:
                last_tick = time.perf_counter()
                _dbg_event("writing_tick", {"topic": topic, "step": idx, "content_len": len(content or ""), "remaining_s": round(_remaining_s(), 1), "has_refs": ("## 参考文献" in content)})
            if len(content) >= min_chars and "## 参考文献" in content:
                break
            tail = content[-1800:]
            cont_prompt = f"""你正在撰写一篇量化交易学术论文，请从下面已写内容的结尾继续续写。

要求：
- 不要重复已写内容，不要重新开始
- 继续补齐缺失章节，并保证包含“## 参考文献”
- 保持与上文相同的 Markdown 结构与写作风格
- 如果上文实验结果表格不完整，补齐表格但不得编造实验数值（可使用“来自 backtest_results.json”引用已给出的数值）

已写内容末尾：
{tail}
"""
            _dbg_event("writing_continue_prepare", {"topic": topic, "step": idx + 1, "tail_len": len(tail), "tail_sample": tail[:200], "min_chars": min_chars, "has_refs": ("## 参考文献" in content), "content_len": len(content)})
            more, meta = _call_with_backoff(cont_prompt, temperature=0.7, max_tokens=chunk_tokens)
            chunk_tokens = _adapt_chunk_tokens(int(chunk_tokens), meta)
            _dbg_event("writing_continue_done", {"topic": topic, "step": idx + 1, "more_len": len(more or ""), "more_sample": (more or "")[:200]})
            if not more:
                break
            if more.strip() in content:
                break
            content = content.rstrip() + "\n\n" + more.lstrip()
            _save_draft(content)
            _save_checkpoint({"status": "in_progress", "next_step": idx + 1, "content_len": len(content), "has_refs": ("## 参考文献" in content)})
        done = (len(content) >= min_chars and "## 参考文献" in content)
        if done:
            content = _apply_reference_block(content, _build_seed_references_block(limit=12))
            content = _apply_truthfulness_guard(content, experiment_bundle=experiment_bundle)
            _save_checkpoint({"status": "completed", "next_step": 10, "content_len": len(content), "has_refs": True})
            return {"status": "generated", "reason": None, "content": content}
        _save_checkpoint({"status": "paused", "next_step": int(checkpoint.get("next_step") or next_step), "content_len": len(content), "has_refs": ("## 参考文献" in content), "reason": "incomplete"})
        return {"status": "paused", "reason": "incomplete", "content": content}
    except Exception as e:
        _dbg_event("writing_failed", {"topic": topic, "error": str(e)[:600]})
        msg = str(e)
        lower = msg.lower()
        retryable = (
            ("http 504" in lower)
            or ("gateway time-out" in lower)
            or ("gateway timeout" in lower)
            or ("upstream request failed" in lower)
            or ("temporarily unavailable" in lower)
        )
        if retryable:
            _save_draft(content or f"# {topic}\n\n")
            _save_checkpoint({"status": "paused", "reason": msg[:300], "content_len": len(content or ""), "has_refs": ("## 参考文献" in (content or ""))})
            return {"status": "paused", "reason": msg[:300], "content": content or f"# {topic}\n\n"}
        if isinstance(e, TimeoutError) or ("timeout" in lower):
            _save_draft(content or f"# {topic}\n\n")
            _save_checkpoint({"status": "paused", "reason": msg[:300], "content_len": len(content or ""), "has_refs": ("## 参考文献" in (content or ""))})
            return {"status": "paused", "reason": msg[:300], "content": content or f"# {topic}\n\n"}
        failure = (content or f"# {topic}\n\n") + f"\n\n论文生成失败: {msg}"
        _save_draft(failure)
        _save_checkpoint({"status": "failed", "reason": msg[:300], "content_len": len(failure), "has_refs": ("## 参考文献" in failure)})
        return {"status": "failed", "reason": msg[:300], "content": failure}


def extract_title(content: str) -> str:
    """从内容中提取标题"""
    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('#'):
            return line.lstrip('#').strip()
        elif line and len(line) < 100:
            return line
    return "未命名论文"


# ============ 重新开始（创建新分支）API ============

@app.route('/api/generate/restart', methods=['POST'])
def api_restart_with_new_branch():
    """重新开始 - 上传综述后创建新分支"""
    data = request.json
    review_content = data.get('review_content', '')
    branch_name = data.get('branch_name', f"分支_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    if not review_content:
        return jsonify({"error": "请提供综述内容"}), 400

    # 创建新分支（与历史数据无关）
    branch = create_branch(branch_name, review_content)

    topic = derive_topic('', branch)
    kickoff = get_research_runner().kickoff(topic=topic, branch_id=branch['id'])

    return jsonify({
        "success": True,
        "branch": branch,
        "message": f"已创建新分支 '{branch_name}' 并启动研究",
        "research": kickoff,
    })


@app.route('/api/papers', methods=['GET'])
def api_papers_list():
    """获取论文列表"""
    branch_id = request.args.get('branch_id', type=int)

    papers_data = load_papers()
    papers = papers_data.get('papers', [])

    if branch_id:
        papers = [p for p in papers if p.get('branch_id') == branch_id]

    # 不返回完整content以节省带宽
    simplified = []
    for p in papers:
        artifacts = p.get('artifacts') or {}
        if not artifacts and p.get('research_id') and p.get('title'):
            root = research_root(p['research_id'], p['title'])
            if root.exists():
                artifacts = artifacts_for_api(root, p['research_id'])
        simplified.append({
            "id": p.get('id'),
            "research_id": p.get('research_id'),
            "branch_id": p.get('branch_id'),
            "topic": p.get('topic'),
            "title": p.get('title'),
            "status": p.get('status'),
            "quality_score": p.get('quality_score'),
            "iteration_count": p.get('iteration_count'),
            "created_at": p.get('created_at'),
            "parent_paper_id": p.get('parent_paper_id'),
            "artifacts": artifacts,
            "content_preview": (p.get('content', '')[:500] + '...') if p.get('content') else ''
        })

    return jsonify({"success": True, "papers": simplified})


@app.route('/api/papers/<int:paper_id>', methods=['GET'])
def api_paper_detail(paper_id: int):
    """获取论文详情"""
    papers_data = load_papers()
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            return jsonify({"success": True, "paper": p})

    return jsonify({"success": False, "error": "论文不存在"}), 404


@app.route('/api/papers/<int:paper_id>/score', methods=['POST'])
def api_score_paper(paper_id: int):
    """对论文进行评分"""
    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    score_result = score_paper(paper.get('content', ''))
    paper['quality_score'] = score_result.get('total_score')
    paper['last_score_result'] = score_result

    save_papers(papers_data)

    # 记录到历史
    add_history_record({
        "type": "paper_score",
        "paper_id": paper_id,
        "topic": paper.get('topic'),
        "title": paper.get('title'),
        "result": score_result
    })

    return jsonify({
        "paper_id": paper_id,
        "score": score_result
    })


@app.route('/api/papers/<int:paper_id>/improve', methods=['POST'])
def api_improve_paper(paper_id: int):
    """基于评分改进论文"""
    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    score_result = paper.get('last_score_result')
    if not score_result:
        return jsonify({"error": "请先对论文进行评分"}), 400

    # 生成改进版
    improved_content = regenerate_paper(
        paper.get('content', ''),
        score_result.get('feedback', ''),
        score_result.get('criteria', {})
    )

    # 创建新版本论文
    papers_data = load_papers()
    new_paper_id = len(papers_data.get('papers', [])) + 1
    new_title = extract_title(improved_content)
    research_id = allocate_research_id(papers_data)
    workspace = create_research_workspace(
        research_id=research_id,
        paper_id=new_paper_id,
        branch_id=paper.get('branch_id'),
        title=new_title,
        topic=paper.get('topic'),
        content=improved_content,
        status="improved",
        parent_research_id=paper.get('research_id'),
    )
    bump_research_seq(papers_data)

    new_paper = {
        "id": new_paper_id,
        "research_id": research_id,
        "branch_id": paper.get('branch_id'),
        "topic": paper.get('topic'),
        "content": improved_content,
        "title": new_title,
        "status": "improved",
        "quality_score": None,
        "iteration_count": paper.get('iteration_count', 0) + 1,
        "created_at": datetime.now().isoformat(),
        "parent_paper_id": paper_id,
        "improvement_notes": score_result.get('feedback'),
        **paper_record_paths(workspace),
    }

    papers_data.setdefault('papers', []).append(new_paper)
    save_papers(papers_data)

    # 记录到历史
    add_history_record({
        "type": "improve",
        "original_paper_id": paper_id,
        "new_paper_id": new_paper_id,
        "research_id": research_id,
        "topic": paper.get('topic'),
        "improvement_notes": score_result.get('feedback')
    })

    return jsonify({
        "success": True,
        "original_paper_id": paper_id,
        "new_paper": new_paper,
        "message": "论文改进成功"
    })


# 确保必要目录存在
ensure_dir(PAPERS_DIR)
ensure_dir(str(RESEARCH_DIR))


@app.route('/research_files/<path:filepath>')
def serve_research_file(filepath):
    """提供研究档案中的可下载文件（强制下载）"""
    project_root = os.path.abspath(os.path.dirname(__file__))
    full = os.path.abspath(os.path.join(project_root, filepath))
    if not full.startswith(project_root + os.sep) and full != project_root:
        return jsonify({"error": "非法路径"}), 403
    if not os.path.isfile(full):
        return jsonify({"error": "文件不存在"}), 404
    filename = os.path.basename(full)
    return send_from_directory(
        os.path.dirname(full),
        filename,
        as_attachment=True,
        download_name=filename
    )


# ============ 论文下载 API ============

# 文件类型 -> meta.json key 映射
ARTIFACT_KEY_MAP = {
    "markdown": "markdown",
    "latex": "latex",
    "tex": "latex",
    "pdf": "pdf",
    "experiment_data": "experiment_data",
    "indicator_sample": "indicator_sample",
    "indicator": "indicator_sample",
    "backtest_results": "backtest_results",
    "backtest": "backtest_results",
    "code": "code",
    "experiment_code": "code",
}

# 文件扩展名 -> MIME type
FILE_EXTENSION_TYPE = {
    ".md": "text/markdown",
    ".tex": "application/x-latex",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".py": "text/x-python",
    ".csv": "text/csv",
}


@app.route('/api/download', methods=['GET'])
def api_download_paper():
    """
    通用论文/资源下载接口
    参数:
      paper_id: 论文ID (必填)
      file_type: 文件类型 (必填)，可选:
        - markdown / md
        - latex / tex
        - pdf
        - experiment_data / data
        - indicator_sample / indicator / indicators
        - backtest_results / backtest
        - code / experiment_code
    """
    paper_id = request.args.get('paper_id', type=int)
    file_type = request.args.get('file_type', '').lower().strip()

    if not paper_id:
        return jsonify({"error": "缺少 paper_id 参数"}), 400
    if not file_type:
        return jsonify({"error": "缺少 file_type 参数"}), 400

    # 解析文件类型
    artifact_key = ARTIFACT_KEY_MAP.get(file_type)
    if not artifact_key:
        return jsonify({
            "error": f"不支持的文件类型: {file_type}",
            "supported": list(ARTIFACT_KEY_MAP.keys())
        }), 400

    # 查找论文
    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": f"论文 {paper_id} 不存在"}), 404

    research_id = paper.get('research_id')
    title = paper.get('title', 'unknown')
    topic = paper.get('topic', '')

    if not research_id:
        return jsonify({"error": "该论文没有 research_id，无法定位文件"}), 404

    # 获取研究根目录
    slugified = research_id + '_' + re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff\-_ ]', '', title)[:30].replace(' ', '_')
    research_dir = RESEARCH_DIR / slugified

    if not research_dir.exists():
        return jsonify({"error": f"研究目录不存在: {research_dir}"}), 404

    # 读取 meta.json 获取 artifacts
    meta_path = research_dir / 'meta.json'
    if meta_path.exists():
        meta = load_json_file(str(meta_path))
        artifacts = meta.get('artifacts', {})
    else:
        # 动态构建 artifacts
        artifacts = build_artifacts_record(research_dir, research_id)

    abs_path = artifacts.get(artifact_key)
    if not abs_path or not os.path.isfile(abs_path):
        return jsonify({"error": f"文件不存在: paper_id={paper_id}, file_type={file_type}"}), 404

    # 生成有意义的下载文件名
    safe_title = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff\-_ ]', '_', title)[:40]
    ext = os.path.splitext(abs_path)[1]
    type_display_names = {
        "markdown": f"{safe_title}_论文.md",
        "latex": f"{safe_title}_latex.tex",
        "pdf": f"{safe_title}_论文.pdf",
        "experiment_data": f"{safe_title}_实验数据.json",
        "indicator_sample": f"{safe_title}_指标数据.json",
        "backtest_results": f"{safe_title}_回测结果.json",
        "code": f"{safe_title}_实验代码.py",
    }
    download_filename = type_display_names.get(artifact_key, os.path.basename(abs_path))

    # 返回文件
    project_root = os.path.abspath(os.path.dirname(__file__))
    return send_from_directory(
        os.path.dirname(abs_path),
        os.path.basename(abs_path),
        as_attachment=True,
        download_name=download_filename
    )


@app.route('/api/download/list', methods=['GET'])
def api_download_list():
    """
    获取论文可下载文件列表
    参数:
      paper_id: 论文ID (必填)
    返回:
      论文下所有可下载文件及其URL、文件名
    """
    paper_id = request.args.get('paper_id', type=int)
    if not paper_id:
        return jsonify({"error": "缺少 paper_id 参数"}), 400

    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": f"论文 {paper_id} 不存在"}), 404

    research_id = paper.get('research_id')
    title = paper.get('title', 'unknown')

    if not research_id:
        return jsonify({"error": "该论文没有 research_id"}), 404

    slugified = research_id + '_' + re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff\-_ ]', '', title)[:30].replace(' ', '_')
    research_dir = RESEARCH_DIR / slugified

    if not research_dir.exists():
        return jsonify({"error": f"研究目录不存在"}), 404

    # 获取 artifacts
    meta_path = research_dir / 'meta.json'
    if meta_path.exists():
        meta = load_json_file(str(meta_path))
        artifacts = meta.get('artifacts', {})
    else:
        artifacts = build_artifacts_record(research_dir, research_id)

    safe_title = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff\-_ ]', '_', title)[:40]
    type_info = {
        "markdown": {"label": "Markdown 论文", "ext": ".md"},
        "latex": {"label": "LaTeX 论文", "ext": ".tex"},
        "pdf": {"label": "PDF 论文", "ext": ".pdf"},
        "experiment_data": {"label": "实验数据", "ext": ".json"},
        "indicator_sample": {"label": "指标数据", "ext": ".json"},
        "backtest_results": {"label": "回测结果", "ext": ".json"},
        "code": {"label": "实验代码", "ext": ".py"},
    }

    files = []
    for key, abs_path in artifacts.items():
        if not os.path.isfile(abs_path):
            continue
        info = type_info.get(key, {"label": key, "ext": os.path.splitext(abs_path)[1]})
        download_name = f"{safe_title}_{info['label']}{info['ext']}"
        files.append({
            "file_type": key,
            "label": info["label"],
            "download_name": download_name,
            "url": f"/api/download?paper_id={paper_id}&file_type={key}",
            "exists": True
        })

    return jsonify({
        "paper_id": paper_id,
        "title": title,
        "research_id": research_id,
        "files": files
    })


# ============ 改进思路存储 ============

IMPROVEMENTS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'improvements.json')

def load_improvements() -> dict:
    """加载改进思路"""
    return load_json_file(IMPROVEMENTS_FILE) or {}

def save_improvements(data: dict):
    """保存改进思路"""
    save_json_file(IMPROVEMENTS_FILE, data)

@app.route('/api/improvements', methods=['GET'])
def api_get_improvements():
    """获取改进思路"""
    branch_id = request.args.get('branch_id', type=int)
    improvements = load_improvements()

    if branch_id:
        return jsonify({"improvements": improvements.get(str(branch_id), [])})
    return jsonify({"improvements": improvements})

@app.route('/api/improvements', methods=['POST'])
def api_save_improvement():
    """保存改进思路"""
    data = request.json
    branch_id = data.get('branch_id')
    idea = data.get('idea', '')
    source_paper_id = data.get('paper_id')

    if not branch_id or not idea:
        return jsonify({"error": "缺少必要参数"}), 400

    improvements = load_improvements()
    branch_str = str(branch_id)

    if branch_str not in improvements:
        improvements[branch_str] = []

    improvement_record = {
        "id": len(improvements[branch_str]) + 1,
        "idea": idea,
        "paper_id": source_paper_id,
        "created_at": datetime.now().isoformat(),
        "applied": False
    }

    improvements[branch_str].append(improvement_record)
    save_improvements(improvements)

    return jsonify({"improvement": improvement_record, "message": "改进思路已保存"})


# ============ 研究日志 API ============

@app.route('/api/research/logs', methods=['GET'])
def api_get_research_logs():
    """获取研究日志列表"""
    paper_id = request.args.get('paper_id', type=int)
    research_id = request.args.get('research_id')
    limit = request.args.get('limit', default=50, type=int)

    logs = load_research_logs()

    # 过滤
    if paper_id:
        logs = [log for log in logs if log.get('paper_id') == paper_id]
    if research_id:
        logs = [log for log in logs if log.get('research_id') == research_id]

    # 限制数量
    logs = logs[:limit]

    # 返回预览（不含详细内容）
    preview_list = []
    for log in logs:
        preview_list.append({
            "id": log.get('id'),
            "paper_id": log.get('paper_id'),
            "research_id": log.get('research_id'),
            "status": log.get('status'),
            "message": log.get('message'),
            "timestamp": log.get('timestamp')
        })

    return jsonify({
        "logs": preview_list,
        "total": len(load_research_logs())
    })


@app.route('/api/research/logs', methods=['POST'])
def api_add_research_log():
    """添加研究日志"""
    data = request.json
    paper_id = data.get('paper_id')
    research_id = data.get('research_id')
    status = data.get('status', 'info')
    message = data.get('message', '')
    details = data.get('details')

    if not paper_id or not research_id:
        return jsonify({"error": "缺少必要参数: paper_id 和 research_id"}), 400

    log_record = add_research_log(paper_id, research_id, status, message, details)
    return jsonify({"log": log_record, "message": "日志已添加"})


@app.route('/api/research/logs/<int:log_id>', methods=['GET'])
def api_get_research_log_detail(log_id: int):
    """获取单条日志详情"""
    logs = load_research_logs()
    for log in logs:
        if log.get('id') == log_id:
            return jsonify(log)
    return jsonify({"error": "日志不存在"}), 404


@app.route('/api/research/logs/summary', methods=['GET'])
def api_get_research_logs_summary():
    """获取研究日志摘要信息（用于仪表板显示）"""
    logs = load_research_logs()

    if not logs:
        return jsonify({
            "total_logs": 0,
            "recent_activity": None,
            "papers_under_research": 0,
            "status_breakdown": {}
        })

    # 统计各状态的日志数量
    status_breakdown = {}
    paper_ids = set()
    for log in logs:
        status = log.get('status', 'unknown')
        status_breakdown[status] = status_breakdown.get(status, 0) + 1
        paper_ids.add(log.get('paper_id'))

    return jsonify({
        "total_logs": len(logs),
        "recent_activity": logs[0] if logs else None,
        "papers_under_research": len(paper_ids),
        "status_breakdown": status_breakdown
    })


@app.route('/')
def index():
    return app.send_static_file('fars_dashboard.html')


@app.route('/v2/')
def index_v2():
    """FARS v2 前端入口"""
    return app.send_static_file('v2/index.html')


@app.route('/v2/<path:static_file>')
def index_v2_static(static_file):
    """FARS v2 静态资源（CSS/JS/组件）"""
    return send_from_directory(os.path.join(app.static_folder, 'v2'), static_file)


@app.route('/health')
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


# ============ 文献综述生成 (STORM-style) ============

def generate_with_minimax(prompt: str, max_output_tokens: int = 8192) -> str:
    """使用MiniMax API生成内容（带token限制保护，记录错误）"""
    cfg = get_effective_llm_config()
    ok, reason = _llm_available(cfg)
    if not ok:
        print(f"[generate_with_minimax] LLM未就绪: {reason}")
        return None

    try:
        estimated_input_tokens = len(prompt) // 3
        safe_max_output = min(max_output_tokens, max(256, 150000 - estimated_input_tokens))
        cfg_max = int(cfg.get("max_tokens") or 0)
        if cfg_max > 0:
            safe_max_output = min(safe_max_output, cfg_max)

        if safe_max_output < 500:
            print(f"[generate_with_minimax] token配额不足: safe_max_output={safe_max_output}")
            return None
        result = call_llm(prompt, temperature=0.7, max_tokens=safe_max_output)
        if not result:
            print(f"[generate_with_minimax] call_llm返回空结果")
        return result
    except Exception as e:
        print(f"[generate_with_minimax] 异常: {type(e).__name__}: {e}")
        return None


def generate_perspectives(topic: str) -> list:
    """生成研究视角 (STORM-style Perspective Generation)"""
    prompt = fill_perspective_prompt(topic)
    response = generate_with_minimax(prompt, max_output_tokens=8192)  # 推理模型需预留~300token思考

    if not response:
        # 回退：返回默认视角
        return [
            {"name": "方法论视角", "research_questions": ["使用什么方法？"], "methodology": "机器学习", "potential_contribution": "新算法"},
            {"name": "应用视角", "research_questions": ["有什么应用价值？"], "methodology": "量化交易", "potential_contribution": "实证验证"},
        ]

    try:
        # 尝试提取JSON
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("perspectives", [])
    except:
        pass

    return [{"name": "综合视角", "research_questions": ["核心问题"], "methodology": "综合方法", "potential_contribution": "创新贡献"}]


def generate_questions_for_perspective(topic: str, perspective: str) -> list:
    """为视角生成深度研究问题 (STORM-style Question Asking)"""
    prompt = fill_question_prompt(topic, perspective)
    response = generate_with_minimax(prompt, max_output_tokens=8192)  # 推理模型额外消耗~300token

    if not response:
        return []

    try:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("questions", [])
    except:
        pass

    return []


def generate_literature_review_section(topic: str, perspectives: list, all_questions: list) -> str:
    """生成文献综述章节 (STORM-style Literature Review)"""
    # 将视角和问题汇总为证据
    evidence = {
        "perspectives": perspectives,
        "questions": all_questions
    }

    prompt = fill_literature_review_prompt(topic, json.dumps(evidence, ensure_ascii=False, indent=2))
    response = generate_with_minimax(prompt, max_output_tokens=16384)  # 推理模型额外消耗~300token

    return response if response else ""


def review_content(title: str, content: str) -> dict:
    """评审论文内容 (GPT Researcher-style Review)"""
    prompt = fill_review_prompt(title, content)
    response = generate_with_minimax(prompt, max_output_tokens=8192)

    if not response:
        return {
            "overall_score": 5.0,
            "dimension_scores": {" rigor": 5, "novelty": 5, "completeness": 5, "readability": 5, "citation_quality": 5},
            "strengths": ["无法获取评审"],
            "weaknesses": ["API调用失败"],
            "revision_suggestions": []
        }

    try:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
    except:
        pass

    return {
        "overall_score": 5.0,
        "dimension_scores": {" rigor": 5, "novelty": 5, "completeness": 5, "readability": 5, "citation_quality": 5},
        "strengths": [],
        "weaknesses": ["解析失败"],
        "revision_suggestions": []
    }


def revise_content(original_content: str, review_result: dict) -> str:
    """根据评审意见修订内容 (GPT Researcher-style Revision)"""
    review_comments = json.dumps(review_result, ensure_ascii=False, indent=2)
    prompt = fill_revision_prompt(original_content, review_comments)
    response = generate_with_minimax(prompt, max_output_tokens=8192)

    return response if response else original_content


def generate_full_latex_paper(topic: str, template: str = "icml") -> str:
    """生成完整LaTeX论文 (集成STORM + GPT Researcher，并行化优化)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Phase 1: 文献综述生成 (STORM-style)
    print(f"[INFO] Phase 1: Generating literature review for topic: {topic}")
    perspectives = generate_perspectives(topic)

    # 并发生成所有视角的研究问题 (原来串行N次LLM调用，现在并发)
    all_questions = []
    if perspectives:
        def _gen_questions(persp):
            persp_name = persp.get("name", "")
            return generate_questions_for_perspective(topic, persp_name)

        with ThreadPoolExecutor(max_workers=min(len(perspectives), 4)) as pool:
            futures = {pool.submit(_gen_questions, p): p for p in perspectives}
            for fut in as_completed(futures):
                try:
                    qs = fut.result(timeout=200)  # 单个视角问题生成最多200s
                    all_questions.extend(qs or [])
                except Exception as e:
                    print(f"[WARN] 视角问题生成失败: {e}")

    lit_review = generate_literature_review_section(topic, perspectives, all_questions)

    # Phase 2: 生成完整论文
    print(f"[INFO] Phase 2: Generating full paper")
    novelty_points = "\n".join([
        f"- {p.get('name')}: {p.get('potential_contribution')}"
        for p in perspectives
    ])

    lit_summary = f"文献综述包含 {len(perspectives)} 个视角，共 {len(all_questions)} 个研究问题"

    # 注入种子文献与 MongoDB 数据说明
    data_context = get_paper_generation_context(topic)
    lit_summary += "\n\n" + data_context[:4000]

    prompt = fill_full_paper_prompt(
        topic=topic,
        template=template,
        literature_review_summary=lit_summary,
        novelty_points=novelty_points
    )

    full_paper = generate_with_minimax(prompt, max_output_tokens=32000)  # 完整论文需要大量 token

    if not full_paper:
        # 回退：生成简化版
        return f"""\\documentclass[preprint,authoryear,12pt]{{elsarticle}}

\\begin{{document}}

\\begin{{frontmatter}}

\\title{{{topic}}}

\\begin{{abstract}}
本文研究了{topic}领域的关键问题。我们提出了新的方法并在实验中验证了其有效性。
\\end{{abstract}}

\\end{{frontmatter}}

\\section{{Introduction}}
本研究探讨了{topic}领域的重要问题...

\\section{{Literature Review}}
{lit_review if lit_review else "相关文献综述..."}

\\section{{Methodology}}
我们提出了以下方法...

\\section{{Experiments}}
实验验证了所提出方法的有效性...

\\section{{Conclusion}}
本文总结了研究贡献并展望未来工作...

\\end{{document}}
"""

    return full_paper


# ============ 文献综述 API (STORM-style) ============

@app.route('/api/research/literature-review', methods=['POST'])
def api_generate_literature_review():
    """生成文献综述章节 (STORM-style, 并行化)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    data = request.json
    topic = data.get('topic', '')

    if not topic:
        return jsonify({"error": "请提供研究主题"}), 400

    print(f"[INFO] Generating literature review for: {topic}")

    # 生成视角
    perspectives = generate_perspectives(topic)

    # 并发生成每个视角的研究问题
    def _gen_qs_for_persp(persp):
        persp_copy = persp.copy()
        persp_copy["generated_questions"] = generate_questions_for_perspective(
            topic, persp.get("name", "")
        )
        return persp_copy

    perspectives_with_questions = []
    if perspectives:
        with ThreadPoolExecutor(max_workers=min(len(perspectives), 4)) as pool:
            futures = {pool.submit(_gen_qs_for_persp, p): i for i, p in enumerate(perspectives)}
            results_map = {}
            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    results_map[idx] = fut.result(timeout=200)
                except Exception as e:
                    print(f"[WARN] 视角问题生成失败: {e}")
                    p = perspectives[idx]
                    results_map[idx] = {**p, "generated_questions": []}
            perspectives_with_questions = [results_map[i] for i in sorted(results_map)]

    # 生成文献综述章节
    all_questions = []
    for p in perspectives_with_questions:
        all_questions.extend(p.get("generated_questions", []))

    lit_review = generate_literature_review_section(topic, perspectives, all_questions)

    return jsonify({
        "success": True,
        "topic": topic,
        "perspectives": perspectives_with_questions,
        "literature_review": lit_review,
        "total_perspectives": len(perspectives),
        "total_questions": len(all_questions)
    })


@app.route('/api/research/generate-full', methods=['POST'])
def api_generate_full_paper():
    """使用完整流程生成论文 (STORM + GPT Researcher)"""
    data = request.json
    topic = data.get('topic', '')
    template = data.get('template', 'icml')
    branch_id = data.get('branch_id')

    if not topic:
        return jsonify({"error": "请提供研究主题"}), 400

    # 解析分支
    branch = resolve_branch(branch_id)

    # 生成完整论文
    latex_content = generate_full_latex_paper(topic, template)

    # 提取标题
    title = extract_title(latex_content.replace('\\', ''))

    # 保存论文
    papers_data = load_papers()
    paper_id = len(papers_data.get('papers', [])) + 1
    research_id = allocate_research_id(papers_data)

    workspace = create_research_workspace(
        research_id=research_id,
        paper_id=paper_id,
        branch_id=branch.get('id'),
        title=title,
        topic=topic,
        content=latex_content,
        status="generated",
    )
    bump_research_seq(papers_data)

    new_paper = {
        "id": paper_id,
        "research_id": research_id,
        "branch_id": branch.get('id'),
        "topic": topic,
        "title": title,
        "content": latex_content,
        "status": "generated",
        "quality_score": None,
        "iteration_count": 0,
        "created_at": datetime.now().isoformat(),
        "generation_mode": "full",  # 标记为完整流程生成
        "template": template,
        **paper_record_paths(workspace),
    }

    papers_data.setdefault('papers', []).append(new_paper)
    save_papers(papers_data)

    mongo_result = index_paper_to_mongo(new_paper)

    # 记录日志
    add_research_log(
        paper_id=paper_id,
        research_id=research_id,
        status="generated",
        message=f"完整流程论文生成完成 (模板: {template})",
        details={"topic": topic, "template": template, "mongo_index": mongo_result}
    )

    return jsonify({
        "success": True,
        "paper_id": paper_id,
        "research_id": research_id,
        "title": title,
        "status": "generated",
        "message": "论文生成成功（完整流程）",
        "generation_mode": "full",
        "mongo_index": mongo_result,
        "data_context_used": bool(get_paper_generation_context(topic).strip()),
    })


@app.route('/api/research/review-and-revise', methods=['POST'])
def api_review_and_revise():
    """评审并修订论文 (GPT Researcher-style Review-Revision Loop)"""
    data = request.json
    paper_id = data.get('paper_id')
    rounds = data.get('rounds', 2)  # 默认2轮评审

    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    content = paper.get('content', '')
    title = paper.get('title', paper.get('topic', 'Untitled'))

    revision_history = []

    for round_i in range(rounds):
        print(f"[INFO] Review-Revision Round {round_i + 1}/{rounds}")

        # Review
        review_result = review_content(title, content)
        revision_history.append({
            "round": round_i + 1,
            "review": review_result
        })

        # 检查是否需要修订
        if review_result.get("overall_score", 5) >= 7.5:
            print(f"[INFO] Content quality sufficient (score: {review_result.get('overall_score')}), skipping revision")
            break

        # Revise
        content = revise_content(content, review_result)
        revision_history[-1]["revised_content"] = content[:500] + "..."  # 保存预览

    # 更新论文
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            p['content'] = content
            p['last_review_result'] = revision_history[-1] if revision_history else None
            break

    save_papers(papers_data)

    return jsonify({
        "success": True,
        "paper_id": paper_id,
        "rounds_completed": len(revision_history),
        "final_score": revision_history[-1].get("review", {}).get("overall_score") if revision_history else None,
        "revision_history": revision_history,
        "message": f"评审修订循环完成 ({len(revision_history)}轮)"
    })


# ============ 质量流水线 API (Step 4 + Step 5) ============

def _get_paper_content(paper_id: int) -> Tuple[Optional[Dict], Optional[str]]:
    """从 papers_data 获取论文内容和标题"""
    papers_data = load_papers()
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            content = p.get('content', '')
            if not content:
                # 尝试从文件读取
                paper_dir = p.get('paper_dir', '')
                if paper_dir:
                    content_path = Path(paper_dir) / 'paper.md'
                    if content_path.exists():
                        content = content_path.read_text(encoding='utf-8')
            title = p.get('title', '未命名论文')
            return p, content
    return None, None


@app.route('/api/quality/pipeline', methods=['POST'])
def api_quality_pipeline():
    """
    运行完整质量流水线 (Step 4 AI痕迹检测 + Step 5 论文评审)

    请求体:
    {
        "paper_id": 123,                    // 论文ID (从数据库读取)
        "content": "论文正文...",             // 或直接提供正文
        "title": "论文标题",                  // 论文标题
        "run_ai_detection": true,           // 是否运行AI检测 (默认true)
        "run_paper_review": true,           // 是否运行论文评审 (默认true)
        "anthropic_api_key": "sk-...",      // Claude API Key (可选，从环境变量读取)
    }
    """
    data = request.json or {}
    paper_id = data.get('paper_id')
    content = data.get('content', '')
    title = data.get('title', '未命名论文')

    # 如果没有提供 content，尝试从 paper_id 获取
    if not content and paper_id:
        paper_record, fetched_content = _get_paper_content(paper_id)
        if fetched_content:
            content = fetched_content
            if paper_record and not title:
                title = paper_record.get('title', title)

    if not content:
        return jsonify({"error": "请提供论文内容 (content) 或有效的 paper_id"}), 400

    run_ai = data.get('run_ai_detection', True)
    run_review = data.get('run_paper_review', True)

    # 获取 API Key
    anthropic_key = data.get('anthropic_api_key') or os.environ.get('ANTHROPIC_API_KEY')

    try:
        report = run_quality_pipeline(
            paper_id=paper_id,
            paper_title=title,
            content=content,
            anthropic_api_key=anthropic_key,
            run_ai_detection=run_ai,
            run_paper_review=run_review,
            run_internal_score=False,
        )

        reporter = QualityReporter()
        return jsonify({
            "success": True,
            "report": reporter.to_dict(report)
        })
    except Exception as e:
        print(f"[ERROR] Quality pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"质量流水线执行失败: {str(e)}"}), 500


@app.route('/api/quality/detect-ai', methods=['POST'])
def api_detect_ai():
    """
    Step 4: AI痕迹检测 (Fast-DetectGPT)

    请求体:
    {
        "content": "待检测文本...",
        "paper_id": 123,          // 可选
    }
    """
    data = request.json or {}
    content = data.get('content', '')

    if not content:
        return jsonify({"error": "请提供待检测文本"}), 400

    detector = FastDetectGPTDetector()
    result = detector.detect(content)

    return jsonify({
        "success": True,
        "ai_probability": result.ai_probability,
        "confidence": result.confidence,
        "criterion_score": result.criterion_score,
        "is_ai_generated": result.is_ai_generated,
        "risk_level": result.risk_level(),
        "suspicious_segments": result.suspicious_segments,
        "model_used": result.model_used,
        "detection_time_ms": round(result.detection_time_ms, 1),
        "local_available": detector.is_local_available,
    })


@app.route('/api/quality/review-paper', methods=['POST'])
def api_review_paper():
    """
    Step 5: 论文评审 (Claude API)

    请求体:
    {
        "title": "论文标题",
        "content": "论文正文...",
        "paper_id": 123,               // 可选
        "anthropic_api_key": "sk-..."  // 可选
    }
    """
    data = request.json or {}
    title = data.get('title', '未命名论文')
    content = data.get('content', '')

    if not content:
        return jsonify({"error": "请提供论文正文"}), 400

    anthropic_key = data.get('anthropic_api_key') or os.environ.get('ANTHROPIC_API_KEY')
    if not anthropic_key:
        return jsonify({"error": "需要提供 ANTHROPIC_API_KEY"}), 400

    reviewer = PaperReviewer(anthropic_api_key=anthropic_key)
    result = reviewer.review(title, content)

    return jsonify({
        "success": True,
        "overall_score": result.overall_score,
        "merit_score": result.merit_score,
        "clarity_score": result.clarity_score,
        "reproducibility_score": result.reproducibility_score,
        "originality_score": result.originality_score,
        "utility_score": result.utility_score,
        "strengths": result.strengths,
        "weaknesses": result.weaknesses,
        "detailed_feedback": result.detailed_feedback,
        "recommended_venue": result.recommended_venue,
        "reviewer_model": result.reviewer_model,
    })


@app.route('/api/papers/<int:paper_id>/quality-report', methods=['GET'])
def api_get_paper_quality_report(paper_id: int):
    """
    获取论文质量报告 (Step 4 + Step 5)
    GET /api/papers/{paper_id}/quality-report
    """
    paper_record, content = _get_paper_content(paper_id)

    if not paper_record:
        return jsonify({"error": "论文不存在"}), 404

    if not content:
        return jsonify({"error": "论文内容为空"}), 400

    title = paper_record.get('title', '未命名论文')

    # 获取环境变量中的 API Key
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY')

    try:
        report = run_quality_pipeline(
            paper_id=paper_id,
            paper_title=title,
            content=content,
            anthropic_api_key=anthropic_key,
            run_ai_detection=True,
            run_paper_review=bool(anthropic_key),
            run_internal_score=False,
        )

        reporter = QualityReporter()
        return jsonify({
            "success": True,
            "paper_id": paper_id,
            "title": title,
            "report": reporter.to_dict(report),
            "ai_detection_only": not bool(anthropic_key),
        })
    except Exception as e:
        print(f"[ERROR] Quality report failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"生成质量报告失败: {str(e)}"}), 500


# ============ PaperReview.ai 外部评分 API ============
# 导入外部评分工具
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'tools'))
from paperreview_submitter import (
    submit_pdf_to_paperreview,
    check_review_once,
    poll_review_result,
    PaperReviewResult,
)


@app.route('/api/papers/<int:paper_id>/submit-review', methods=['POST'])
def api_submit_paperreview(paper_id: int):
    """
    提交论文PDF到paperreview.ai进行外部评分

    请求体:
    {
        "email": "your@email.com",      // 必填
        "venue": "ICLR",                 // 可选，默认ICLR
        "pdf_path": "/path/to/paper.pdf" // 可选，如不提供则尝试使用已保存的PDF
    }
    """
    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    data = request.json or {}
    email = data.get('email')
    venue = data.get('venue', 'ICLR')
    custom_venue = data.get('custom_venue', '')
    pdf_path = data.get('pdf_path')

    if not email:
        return jsonify({"error": "缺少必填参数: email"}), 400

    # 如果没有提供pdf_path，尝试从论文artifacts获取
    if not pdf_path:
        artifacts = paper.get('artifacts', {})
        # 尝试找LaTeX PDF
        latex_pdf = artifacts.get('latex_pdf')
        if latex_pdf:
            # 转换为绝对路径
            pdf_path = latex_pdf
        else:
            # 尝试从research_dir构建路径
            research_dir = paper.get('research_dir', '')
            if research_dir:
                import glob
                pdf_files = glob.glob(os.path.join(research_dir, '**', '*.pdf'), recursive=True)
                if pdf_files:
                    pdf_path = pdf_files[0]  # 使用第一个PDF

    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify({
            "error": "未找到论文PDF文件",
            "message": "请提供pdf_path参数或先生成PDF"
        }), 400

    # 提交到paperreview.ai
    token, error = submit_pdf_to_paperreview(
        pdf_path=pdf_path,
        email=email,
        venue=venue,
        custom_venue=custom_venue
    )

    if error:
        return jsonify({
            "error": f"提交失败: {error}",
            "paper_id": paper_id
        }), 500

    # 更新论文数据
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            p['external_review_token'] = token
            p['external_review_venue'] = venue
            p['external_review_status'] = 'pending'
            p['external_review_email'] = email
            p['external_review_pdf'] = pdf_path
            break

    save_papers(papers_data)

    # 记录日志
    add_research_log(
        paper_id=paper_id,
        research_id=paper.get('research_id', ''),
        status="review_submitted",
        message=f"论文已提交到PaperReview.ai (Venue: {venue})",
        details={"token": token[:20] + "...", "venue": venue}
    )

    return jsonify({
        "success": True,
        "paper_id": paper_id,
        "token": token,
        "venue": venue,
        "message": "论文已成功提交到PaperReview.ai，请使用 /api/papers/{id}/review-status 查看评分结果"
    })


@app.route('/api/papers/<int:paper_id>/review-status', methods=['GET'])
def api_paperreview_status(paper_id: int):
    """
    查询PaperReview.ai评分状态（一次性检查）

    返回:
    - status: "pending" | "ready" | "error"
    - overall_score: 评分（如果已完成）
    - passed: 是否通过 (>5分)
    """
    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    token = paper.get('external_review_token')
    if not token:
        return jsonify({
            "status": "not_submitted",
            "message": "论文尚未提交到PaperReview.ai"
        }), 400

    # 检查评分状态
    result = check_review_once(token)

    # 更新论文数据
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            p['external_review_status'] = result.status
            if result.success:
                p['external_review_score'] = result.overall_score
                p['paper_passed'] = result.passed
                p['external_review_result'] = result.to_dict()
            break

    save_papers(papers_data)

    return jsonify({
        "paper_id": paper_id,
        "status": result.status,
        "overall_score": result.overall_score,
        "passed": result.passed if result.success else None,
        "sections": result.sections if result.success else None,
        "error": result.error,
        "message": "评分完成" if result.success else f"评分{result.status}中: {result.error or '请稍后'}"
    })


@app.route('/api/papers/<int:paper_id>/poll-review', methods=['POST'])
def api_poll_paperreview(paper_id: int):
    """
    轮询PaperReview.ai评分（持续等待结果）

    请求体:
    {
        "interval_minutes": 1.0,  // 可选，默认1分钟
        "max_hours": 24.0         // 可选，默认24小时
    }
    """
    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    token = paper.get('external_review_token')
    if not token:
        return jsonify({"error": "论文尚未提交到PaperReview.ai"}), 400

    data = request.json or {}
    interval = data.get('interval_minutes', 1.0)
    max_hours = data.get('max_hours', 24.0)
    pdf_path = paper.get('external_review_pdf')

    if not pdf_path:
        return jsonify({"error": "未找到PDF路径，无法保存评分结果"}), 400

    # 开始轮询（这可能需要较长时间）
    result = poll_review_result(
        token=token,
        pdf_path=pdf_path,
        interval_minutes=interval,
        max_hours=max_hours
    )

    # 更新论文数据
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            p['external_review_status'] = result.status
            if result.success:
                p['external_review_score'] = result.overall_score
                p['paper_passed'] = result.passed
                p['external_review_result'] = result.to_dict()
            break

    save_papers(papers_data)

    return jsonify({
        "paper_id": paper_id,
        "success": result.success,
        "status": result.status,
        "overall_score": result.overall_score,
        "passed": result.passed if result.success else None,
        "sections": result.sections if result.success else None,
        "error": result.error,
        "message": "轮询完成" if result.success else f"轮询结束: {result.error}"
    })


@app.route('/api/papers/<int:paper_id>/evaluate', methods=['POST'])
def api_evaluate_paper(paper_id: int):
    """
    完整评估论文（内部评分 + 外部评分 + 最终判断）

    请求体:
    {
        "email": "your@email.com",      // 必填（用于paperreview.ai）
        "venue": "ICLR",                 // 可选
        "internal_threshold": 7.0,       // 可选，内部评分通过阈值（默认7分）
        "external_threshold": 5.0,       // 可选，外部评分通过阈值（默认5分）
        "submit_external": true          // 可选，是否同时提交到外部评分
    }

    返回:
    {
        "paper_id": int,
        "internal_score": float,         // 内部评分
        "method_passed": bool,           // 方法是否合格 (>=7)
        "external_score": float | null,   // 外部评分（如有）
        "paper_passed": bool | null,     // 论文是否合格 (>5)
        "final_status": "success" | "failed" | "pending",
        "message": str
    }
    """
    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    data = request.json or {}
    email = data.get('email')
    venue = data.get('venue', 'ICLR')
    internal_threshold = data.get('internal_threshold', 7.0)
    external_threshold = data.get('external_threshold', 5.0)
    submit_external = data.get('submit_external', False)

    # 1. 内部评分
    content = paper.get('content', '')
    internal_result = score_paper(content)

    internal_score = internal_result.get('total_score', 0)
    method_passed = internal_score >= internal_threshold

    # 更新论文内部评分
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            p['quality_score'] = internal_score
            p['method_passed'] = method_passed
            p['last_score_result'] = internal_result
            break

    save_papers(papers_data)

    result = {
        "paper_id": paper_id,
        "internal_score": internal_score,
        "method_passed": method_passed,
        "internal_criteria": internal_result.get('criteria', {}),
        "internal_feedback": internal_result.get('feedback', ''),
        "external_score": None,
        "paper_passed": None,
        "external_status": "not_submitted" if not submit_external else "pending",
        "final_status": "pending",
        "message": ""
    }

    # 2. 外部评分（如果需要）
    if submit_external:
        if not email:
            result["message"] = "内部评分完成，但缺少email无法提交外部评分"
            result["final_status"] = "pending"
            return jsonify(result)

        # 获取PDF路径
        pdf_path = data.get('pdf_path')
        if not pdf_path:
            artifacts = paper.get('artifacts', {})
            latex_pdf = artifacts.get('latex_pdf')
            if latex_pdf:
                pdf_path = latex_pdf
            else:
                research_dir = paper.get('research_dir', '')
                if research_dir:
                    import glob
                    pdf_files = glob.glob(os.path.join(research_dir, '**', '*.pdf'), recursive=True)
                    if pdf_files:
                        pdf_path = pdf_files[0]

        if not pdf_path or not os.path.exists(pdf_path):
            result["message"] = f"内部评分完成({internal_score}分)，但未找到PDF文件无法提交外部评分"
            result["final_status"] = "pending"
            return jsonify(result)

        # 提交到paperreview.ai
        token, error = submit_pdf_to_paperreview(
            pdf_path=pdf_path,
            email=email,
            venue=venue
        )

        if error:
            result["external_status"] = "error"
            result["message"] = f"内部评分完成({internal_score}分)，但外部提交失败: {error}"
            result["final_status"] = "pending"
            return jsonify(result)

        # 更新论文数据
        for p in papers_data.get('papers', []):
            if p.get('id') == paper_id:
                p['external_review_token'] = token
                p['external_review_venue'] = venue
                p['external_review_status'] = 'pending'
                break

        save_papers(papers_data)

        result["external_status"] = "submitted"
        result["message"] = f"内部评分完成({internal_score}分)，已提交到PaperReview.ai等待评分"
        result["final_status"] = "pending"

    else:
        # 不提交外部评分，直接计算最终状态
        if method_passed:
            result["final_status"] = "success"
            result["message"] = f"论文合格！内部评分{internal_score}分 >= {internal_threshold}分"
        else:
            result["final_status"] = "failed"
            result["message"] = f"论文不合格：内部评分{internal_score}分 < {internal_threshold}分"

    return jsonify(result)


@app.route('/api/papers/<int:paper_id>/final-status', methods=['GET'])
def api_paper_final_status(paper_id: int):
    """
    获取论文最终状态（综合内部评分和外部评分）

    返回:
    {
        "paper_id": int,
        "internal_score": float,
        "method_passed": bool,           // 内部评分 >= 7
        "external_score": float | null,
        "paper_passed": bool | null,      // 外部评分 > 5
        "final_status": "success" | "failed" | "pending",
        "message": str
    }
    """
    papers_data = load_papers()
    paper = None
    for p in papers_data.get('papers', []):
        if p.get('id') == paper_id:
            paper = p
            break

    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    internal_score = paper.get('quality_score')
    method_passed = paper.get('method_passed', False) if internal_score is not None else None

    external_score = paper.get('external_review_score')
    paper_passed = paper.get('paper_passed') if external_score is not None else None

    # 计算最终状态
    if internal_score is None:
        final_status = "pending"
        message = "尚未完成内部评分"
    elif external_score is None:
        # 内部评分完成，等待外部评分
        if method_passed:
            final_status = "pending"
            message = f"内部评分通过({internal_score}分)，等待外部评分"
        else:
            final_status = "failed"
            message = f"内部评分未通过({internal_score}分 < 7分)"
    else:
        # 两者都完成
        if method_passed and paper_passed:
            final_status = "success"
            message = f"论文合格！内部评分{internal_score}分，外部评分{external_score}分"
        else:
            final_status = "failed"
            reasons = []
            if not method_passed:
                reasons.append(f"内部评分{internal_score}分 < 7分")
            if external_score is not None and not paper_passed:
                reasons.append(f"外部评分{external_score}分 <= 5分")
            message = f"论文不合格：{'；'.join(reasons)}"

    return jsonify({
        "paper_id": paper_id,
        "title": paper.get('title', 'Untitled'),
        "internal_score": internal_score,
        "method_passed": method_passed,
        "external_score": external_score,
        "paper_passed": paper_passed,
        "external_review_status": paper.get('external_review_status'),
        "final_status": final_status,
        "message": message
    })


@app.route('/api/data/registry', methods=['GET'])
def api_data_registry():
    """返回程序已知的数据位置清单"""
    registry = get_registry()
    registry["mongodb_market_data"] = check_market_data()
    return jsonify({"success": True, "registry": registry})


@app.route('/api/data/mongodb/papers', methods=['GET'])
def api_mongodb_papers():
    """查询 MongoDB 中已索引的论文"""
    limit = request.args.get('limit', 50, type=int)
    return jsonify(query_papers(limit=limit))


@app.route('/api/research/reset', methods=['POST'])
def api_research_reset():
    """从 0 开始：备份后重置论文与研究档案（默认保留 seed_papers）"""
    data = request.json or {}
    keep_seed = data.get('keep_seed_papers', True)
    keep_workflow = data.get('keep_workflow', True)
    remove_archives = data.get('remove_archives', False)
    result = reset_research(
        keep_seed_papers=keep_seed,
        keep_workflow=keep_workflow,
        remove_archives=remove_archives,
    )
    return jsonify(result)


@app.route('/api/seed-papers', methods=['GET'])
def api_seed_papers_list():
    """种子文献库列表（重置时保留，支持 PDF 下载）"""
    papers = list_seed_papers()
    return jsonify({"success": True, "count": len(papers), "papers": papers})


@app.route('/api/seed-papers/<int:paper_id>/pdf', methods=['GET'])
def api_seed_paper_pdf(paper_id):
    """下载种子文献 PDF"""
    path = get_pdf_path(paper_id)
    if not path:
        return jsonify({"success": False, "error": "PDF not found"}), 404
    return send_from_directory(
        str(path.parent),
        path.name,
        as_attachment=True,
        download_name=path.name,
    )


@app.route('/api/seed-papers/fetch', methods=['POST'])
def api_seed_papers_fetch():
    """从 arXiv 检索近五年量化/LLM/金融工程论文并下载 PDF"""
    data = request.json or {}
    target = min(max(int(data.get('count', 15)), 1), 25)
    result = fetch_new_papers(target_count=target, max_total=target)
    return jsonify(result)


def _extract_author_network_from_seed_papers() -> dict:
    """从种子论文中提取作者关系网络"""
    import json
    from pathlib import Path
    
    seed_manifest_path = Path(__file__).parent / "data" / "seed_papers" / "manifest.json"
    
    author_network = {
        "authors": [],
        "institutions": [],
        "papers": [],
        "collaborations": []
    }
    
    if not seed_manifest_path.exists():
        return author_network
    
    try:
        manifest = json.loads(seed_manifest_path.read_text(encoding="utf-8"))
        papers = manifest.get("seed_papers", [])
        
        institution_ids = {}
        author_id_counter = 1
        inst_id_counter = 1
        
        for paper in papers:
            paper_id = f"p{paper.get('id', author_id_counter)}"
            title = paper.get("title", "")
            
            # 从论文标题中提取作者信息（demo数据）
            # 实际应该从论文的authors字段提取
            authors_raw = paper.get("authors", "")
            
            # 解析作者列表
            authors_list = []
            if authors_raw:
                # 简单解析，假设格式为 "Name1, Name2, Name3"
                authors_list = [a.strip() for a in authors_raw.split(",") if a.strip()]
            
            # 如果没有作者信息，使用demo数据
            if not authors_list:
                continue
            
            # 为每个作者创建节点
            for idx, author_name in enumerate(authors_list[:5]):  # 最多5个作者
                role = "first" if idx == 0 else ("corresponding" if idx == len(authors_list) - 1 and len(authors_list) > 2 else "second")
                
                # 推断机构（demo）
                institution = _infer_institution(author_name)
                
                author_id = f"a{author_id_counter}"
                author_id_counter += 1
                
                # 添加作者节点
                author_network["authors"].append({
                    "id": author_id,
                    "name": author_name,
                    "role": role,
                    "institution": institution["name"],
                    "type": institution["type"],
                    "paper_id": paper_id
                })
                
                # 添加机构节点（如果不存在）
                inst_key = institution["name"]
                if inst_key not in institution_ids:
                    institution_ids[inst_key] = f"i{inst_id_counter}"
                    inst_id_counter += 1
                    author_network["institutions"].append({
                        "id": institution_ids[inst_key],
                        "name": institution["name"],
                        "type": institution["type"]
                    })
                
                # 添加合作关系
                if idx > 0:
                    prev_author_id = f"a{author_id_counter - 2}"
                    author_network["collaborations"].append({
                        "author1": prev_author_id,
                        "author2": author_id,
                        "paper_id": paper_id
                    })
            
            # 添加论文节点
            author_network["papers"].append({
                "id": paper_id,
                "title": title,
                "authors": authors_list
            })
    
    except Exception as e:
        print(f"Error extracting author network: {e}")
    
    return author_network


def _infer_institution(author_name: str) -> dict:
    """根据作者名推断机构（demo逻辑）"""
    # demo数据，实际应该查询论文元数据
    institutions = [
        {"name": "清华大学", "type": "university"},
        {"name": "北京大学", "type": "university"},
        {"name": "上海交通大学", "type": "university"},
        {"name": "复旦大学", "type": "university"},
        {"name": "中科院", "type": "university"},
        {"name": "微软亚洲研究院", "type": "company"},
        {"name": "阿里巴巴", "type": "company"},
        {"name": "华为诺亚", "type": "company"},
        {"name": "腾讯AI Lab", "type": "company"},
    ]
    
    # 简单hash分配
    idx = sum(ord(c) for c in author_name) % len(institutions)
    return institutions[idx]


@app.route('/api/research/author-network/<research_id>', methods=['GET'])
def api_author_network_research(research_id):
    """获取特定研究的作者关系网络"""
    # 简化实现，返回最新研究的作者网络
    return api_author_network_latest()


@app.route('/api/config/llm', methods=['GET'])
def api_llm_config_get():
    """获取当前 LLM 配置"""
    _maybe_reload_config()
    llm_config = dict(_llm_config)
    providers = {k: dict(v) for k, v in (_llm_providers or {}).items()}

    def sanitize(cfg: Dict[str, Any], provider_name: str) -> Dict[str, Any]:
        out = dict(cfg)
        out["api_key_configured"] = bool(_get_provider_api_key(provider_name, out))
        out["api_key"] = ""
        return out

    current_provider = str(llm_config.get("provider") or "minimax")
    llm_config = sanitize(llm_config, current_provider)
    providers = {k: sanitize(v, k) for k, v in providers.items()}

    return jsonify({
        "success": True,
        "llm": llm_config,
        "llm_providers": providers,
    })


@app.route('/api/config/llm', methods=['POST'])
def api_llm_config_update():
    """更新 LLM 配置"""
    data = request.json or {}
    llm = data.get("llm") or {}
    llm_providers = data.get("llm_providers") or {}
    if not isinstance(llm, dict) or not isinstance(llm_providers, dict):
        return jsonify({"success": False, "error": "invalid payload"}), 400

    incoming_keys = []
    if "api_key" in llm:
        incoming_keys.append(("llm", llm.get("api_key")))
    for name, cfg in llm_providers.items():
        if isinstance(cfg, dict) and ("api_key" in cfg):
            incoming_keys.append((f"llm_providers.{name}", cfg.get("api_key")))
    for field, key in incoming_keys:
        if key and (not _is_reasonable_api_key(key)):
            return jsonify({"success": False, "error": f"{field} api_key 非法（仅支持 ASCII 且不能包含空格）"}), 400

    _save_local_llm_config(llm, llm_providers)
    _reload_config()

    llm_config = dict(_llm_config)
    providers = {k: dict(v) for k, v in (_llm_providers or {}).items()}

    def sanitize(cfg: Dict[str, Any], provider_name: str) -> Dict[str, Any]:
        out = dict(cfg)
        out["api_key_configured"] = bool(_get_provider_api_key(provider_name, out))
        out["api_key"] = ""
        return out

    current_provider = str(llm_config.get("provider") or "minimax")
    llm_config = sanitize(llm_config, current_provider)
    providers = {k: sanitize(v, k) for k, v in providers.items()}

    return jsonify({
        "success": True,
        "message": "LLM 配置已更新",
        "llm": llm_config,
        "llm_providers": providers,
    })


@app.route('/api/config/llm/providers', methods=['GET'])
def api_llm_providers():
    """获取所有可用的 LLM providers 列表"""
    _maybe_reload_config()
    providers = _llm_providers or {}

    return jsonify({
        "success": True,
        "providers": list(providers.keys()),
        "current_provider": (_llm_config or {}).get('provider', 'minimax'),
    })


if __name__ == '__main__':
    print("=" * 60)
    print("FARS 论文评分与迭代重生成服务器 v3.1")
    print("=" * 60)
    print("API端点:")
    print("  POST /api/score                              - 论文评分")
    print("  POST /api/regenerate                         - 论文重生成")
    print("  POST /api/find_papers                        - 查找相关论文")
    print("  POST /api/iterate                            - 完整迭代流程")
    print("  POST /api/history                            - 获取历史记录列表")
    print("  GET  /api/history/<id>                       - 获取历史记录详情")
    print("  POST /api/research/literature-review         - 文献综述生成 (STORM)")
    print("  POST /api/research/generate-full             - 完整论文生成 (STORM+GPT)")
    print("  POST /api/research/review-and-revise         - 评审修订循环 (GPT Researcher)")
    print("  GET  /api/research/logs                      - 研究日志")
    print("  POST /api/papers/<id>/submit-review         - 提交到PaperReview.ai")
    print("  GET  /api/papers/<id>/review-status         - 查询PaperReview评分")
    print("  POST /api/papers/<id>/poll-review           - 轮询PaperReview评分")
    print("  POST /api/papers/<id>/evaluate              - 完整评估（内部+外部）")
    print("  GET  /api/papers/<id>/final-status          - 最终状态判断")
    print("  POST /api/research/reset                      - 从0开始（备份后重置）")
    print("  GET  /api/data/registry                       - 数据位置注册表")
    print("  GET  /api/data/mongodb/papers                 - MongoDB 论文索引")
    print("  GET  /api/seed-papers                         - 种子文献库列表")
    print("  GET  /api/seed-papers/<id>/pdf                - 下载种子文献 PDF")
    print("  POST /api/seed-papers/fetch                   - 从 arXiv 获取新文献")
    print("=" * 60)
    print("评分标准:")
    print("  内部评分 >= 7分 → 方法合格 (method_passed)")
    print("  外部评分 > 5分  → 论文合格 (paper_passed)")
    print("  两者都通过     → 最终成功 (final_status=success)")
    print("=" * 60)
    port = int(os.environ.get("PORT", "8080"))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
