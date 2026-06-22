"""
研究流水线 — 点击「开始」后在后台推进：文献 → 假设 → 实验 → 论文。
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from core.data_registry import SEED_MANIFEST
from core.research_graphs import (
    build_author_network_from_seed_papers,
    build_citation_network,
)
from core.paper_extractor import extract_all_papers, get_all_paper_texts, regenerate_analysis
from core.seed_library import list_seed_papers

_lock = threading.Lock()
_running = False

_THEME_PATTERNS = {
    "LLM": ["llm", "large language model", "大语言模型", "语言模型"],
    "量化交易": ["quant", "trading", "alpha", "因子", "量化", "交易"],
    "多智能体": ["multi-agent", "agent", "智能体", "协同"],
    "可解释性": ["explain", "interpret", "可解释", "归因"],
    "风险控制": ["risk", "drawdown", "volatility", "风险", "回撤", "波动"],
    "时序建模": ["time series", "temporal", "时序", "高频"],
    "金融预测": ["forecast", "prediction", "预测", "收益率"],
    "评估与回测": ["benchmark", "backtest", "evaluation", "评估", "回测"],
}


def _load_json_manifest() -> dict:
    if SEED_MANIFEST.exists():
        import json
        return json.loads(SEED_MANIFEST.read_text(encoding="utf-8"))
    return {}


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _detect_themes(text: str, fallback_topics: Optional[List[str]] = None) -> List[str]:
    haystack = str(text or "").lower()
    hits: List[str] = []
    for label, patterns in _THEME_PATTERNS.items():
        if any(p in haystack for p in patterns):
            hits.append(label)
    for topic in fallback_topics or []:
        normalized = str(topic or "").strip()
        if normalized:
            hits.append(normalized)
    return _dedupe_keep_order(hits)


def _build_literature_review(topic: str) -> Dict[str, Any]:
    read_started = time.perf_counter()
    extraction_stats = extract_all_papers()
    read_seconds = max(0.0, time.perf_counter() - read_started)

    analysis_started = time.perf_counter()
    analysis_markdown = regenerate_analysis()
    seed_papers = list_seed_papers()
    extracted = get_all_paper_texts(max_chars_per_paper=2400)
    extracted_map = {
        str(item.get("arxiv_id") or ""): item
        for item in extracted
        if isinstance(item, dict) and item.get("arxiv_id")
    }

    theme_counter: Counter[str] = Counter()
    papers_read: List[dict] = []
    papers_to_read: List[dict] = []

    for sp in seed_papers:
        arxiv_id = str(sp.get("arxiv_id") or "")
        extracted_item = extracted_map.get(arxiv_id)
        source_text = " ".join([
            str(sp.get("title") or ""),
            " ".join(sp.get("key_topics") or []),
            str((extracted_item or {}).get("text") or ""),
        ])
        themes = _detect_themes(source_text, fallback_topics=sp.get("key_topics") or [])
        theme_counter.update(themes)
        record = {
            "arxiv_id": arxiv_id,
            "title": sp.get("title"),
            "authors": sp.get("authors"),
            "year": sp.get("year"),
            "key_topics": themes,
            "summary_preview": str((extracted_item or {}).get("text") or "")[:800],
        }
        if extracted_item:
            papers_read.append(record)
        else:
            papers_to_read.append(record)

    key_themes = [name for name, _ in theme_counter.most_common(8)]
    if not key_themes:
        fallback = []
        for sp in seed_papers[:8]:
            fallback.extend(sp.get("key_topics") or [])
        key_themes = _dedupe_keep_order(fallback)[:8] or ["LLM", "量化交易"]

    research_questions = _dedupe_keep_order([
        f"{theme} 如何在「{topic}」场景下提升收益风险比并保持策略稳健性？"
        for theme in key_themes[:4]
    ] + [
        f"种子论文中的 {key_themes[0]} 方法，与传统量化基线相比优势和边界分别是什么？"
        if key_themes else "",
        f"如何基于真实实验产物而非主观描述，完成「{topic}」的可复现验证？",
    ])[:6]

    research_gaps = _dedupe_keep_order([
        f"现有文献已覆盖 {', '.join(key_themes[:3])}，但缺少统一的可复现实验协议与横向对比。",
        "多数工作强调收益表现，但对回撤、稳定性、失效情形和风险归因讨论不足。",
        "作者/机构/引用网络已有积累，但尚未被系统用于识别研究热点、合作关系与空白方向。",
        "从种子论文到实验代码、再到最终论文正文的闭环链路尚未形成一致的数据映射。",
    ])[:4]

    potential_innovations = _dedupe_keep_order([
        f"构建围绕「{topic}」的统一研究档案，将文献分析、实验代码、指标样本和论文写作串成闭环。",
        f"针对 {key_themes[0] if key_themes else 'LLM'} 建立与传统量化因子/基线策略的系统比较框架。",
        "将作者合作网络与引用关系图作为研究导航信号，用于解释方法来源、热点主题与空白区域。",
        "要求论文实验章节直接引用真实 backtest_results / experiment_data / indicator_sample，不再凭空生成结果。",
    ])[:4]
    analysis_seconds = max(0.0, time.perf_counter() - analysis_started)
    papers_read_count = len(papers_read)
    avg_read_seconds = read_seconds / max(1, papers_read_count)
    avg_analysis_seconds = analysis_seconds / max(1, papers_read_count)

    return {
        "extraction_stats": extraction_stats,
        "analysis_markdown": analysis_markdown,
        "papers_read": papers_read,
        "papers_to_read": papers_to_read,
        "key_themes": key_themes,
        "research_questions": research_questions,
        "research_gaps": research_gaps,
        "potential_innovations": potential_innovations,
        "timings": {
            "read_seconds": read_seconds,
            "analysis_seconds": analysis_seconds,
            "total_seconds": read_seconds + analysis_seconds,
            "avg_read_seconds_per_paper": avg_read_seconds,
            "avg_analysis_seconds_per_paper": avg_analysis_seconds,
            "papers_read_count": papers_read_count,
        },
    }


def _record_phase(workflow: dict, *, phase: str, run_id: str, details: Dict[str, Any], status: str = "completed") -> dict:
    updated = dict(workflow or {})
    history = list(updated.get("phase_history") or [])
    history.append({
        "phase": phase,
        "status": status,
        "details": details,
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
    })
    updated["phase_history"] = history[-30:]
    updated["updated_at"] = datetime.now().isoformat()
    return updated


def _merge_run_phase_metrics(papers: dict, *, run_id: str, phase: str, patch: Dict[str, Any]) -> dict:
    updated = dict(papers or {})
    metrics = updated.get("run_metrics") if isinstance(updated.get("run_metrics"), dict) else {}
    if metrics.get("run_id") != run_id:
        metrics = {"run_id": run_id, "phases": {}, "started_at": datetime.now().isoformat()}
    phases = metrics.get("phases") if isinstance(metrics.get("phases"), dict) else {}
    row = phases.get(phase) if isinstance(phases.get(phase), dict) else {}
    row.update(patch)
    phases[phase] = row
    metrics["phases"] = phases
    metrics["updated_at"] = datetime.now().isoformat()
    updated["run_metrics"] = metrics
    return updated


def _build_hypotheses(workflow: dict, topic: str, *, run_id: str = "") -> List[dict]:
    gaps: List[str] = []
    innovations: List[str] = []

    for phase in workflow.get("phase_history", []):
        if run_id and phase.get("run_id") not in ("", None, run_id):
            continue
        details = phase.get("details") or {}
        gaps.extend(details.get("research_gaps", []))
        innovations.extend(details.get("potential_innovations", []))

    lit = workflow.get("literature_review") or {}
    themes = lit.get("key_themes") or []
    questions = lit.get("research_questions") or []
    gaps.extend(lit.get("research_gaps") or [])
    innovations.extend(lit.get("potential_innovations") or [])

    seeds = list_seed_papers()[:5]
    seed_topics = []
    for sp in seeds:
        seed_topics.extend(sp.get("key_topics") or [])

    candidates = innovations or gaps or questions or [
        f"基于多智能体 LLM 的{topic}信号生成",
        f"跨时间尺度量化因子与 LLM 融合",
        f"金融幻觉检测与可解释交易决策",
    ]

    hypotheses = []
    for i, title in enumerate(candidates[:5], start=1):
        tag_pool = list(dict.fromkeys(seed_topics + themes))[:4] or ["量化", "LLM"]
        leading_question = questions[(i - 1) % len(questions)] if questions else f"如何验证「{title}」在 {topic} 中的有效性？"
        hypotheses.append({
            "id": f"hyp_{i}",
            "title": title if isinstance(title, str) else str(title),
            "description": f"围绕「{title}」提出可验证假设，结合真实种子论文分析结果与研究主题「{topic}」。核心问题：{leading_question}",
            "tags": tag_pool[:3],
            "status": "hypothesis",
            "expected_outcome": "回测夏普比率优于基准策略",
            "actual_outcome": None,
        })
    return hypotheses


def _build_experiments(*, topic: str, run_id: str, created_at: str) -> List[dict]:
    stages = [
        {
            "id": "exp_1",
            "title": "实验1: 文献综述与假设生成",
            "method": "种子论文解析 + 主题抽取 + 研究空白/创新点 → 假设",
            "stage_phases": ["starting", "literature_review", "hypothesis"],
        },
        {
            "id": "exp_2",
            "title": "实验2: 引用/作者图谱构建",
            "method": "引用关系图 + 作者-机构合作网络",
            "stage_phases": ["experimenting"],
        },
        {
            "id": "exp_3",
            "title": "实验3: 写作与产物落盘",
            "method": "论文生成 + 实验产物聚合 + 下载中心落盘",
            "stage_phases": ["writing", "completed"],
        },
    ]
    experiments: List[dict] = []
    for stage in stages:
        experiments.append({
            "id": stage["id"],
            "title": stage["title"],
            "status": "pending",
            "paper_id": None,
            "method": stage["method"],
            "topic": topic,
            "run_id": run_id,
            "created_at": created_at,
            "stage_phases": stage["stage_phases"],
            "started_at": None,
            "completed_at": None,
        })
    return experiments


class ResearchRunner:
    def __init__(
        self,
        *,
        load_papers: Callable[[], dict],
        save_papers: Callable[[dict], None],
        load_workflow: Callable[[], dict],
        save_workflow: Callable[[dict], None],
        create_paper: Callable[..., dict],
        add_log: Callable[..., dict],
    ):
        self.load_papers = load_papers
        self.save_papers = save_papers
        self.load_workflow = load_workflow
        self.save_workflow = save_workflow
        self.create_paper = create_paper
        self.add_log = add_log

    def is_running(self) -> bool:
        global _running
        with _lock:
            return bool(_running)

    def kickoff(self, *, topic: str, branch_id: int, resume: bool = False) -> Dict[str, Any]:
        global _running
        with _lock:
            papers = self.load_papers()
            if _running and (not papers.get("is_generating")):
                _running = False
            if papers.get("is_generating"):
                if _running:
                    return {
                        "success": True,
                        "already_running": True,
                        "message": "研究正在进行中",
                        "research_activity": papers.get("research_activity"),
                    }
                papers["is_generating"] = False
            if _running:
                return {"success": True, "already_running": True, "message": "研究正在启动"}
            _running = True

            now = datetime.now().isoformat()
            settings = papers.get("settings") or {}
            papers["settings"] = settings
            current_run = papers.get("current_run") if isinstance(papers.get("current_run"), dict) else None
            activity = papers.get("research_activity") or {}
            phase = activity.get("phase") or "idle"

            effective_topic = topic
            effective_branch_id = branch_id
            pending_ok = False
            if current_run:
                pending_ok = bool(
                    current_run.get("pending_research_id")
                    and current_run.get("pending_research_dir")
                    and current_run.get("pending_paper_id")
                )

            if resume and current_run and pending_ok:
                effective_topic = current_run.get("topic") or topic
                effective_branch_id = int(current_run.get("branch_id") or branch_id)
                current_run["status"] = "in_progress"
                current_run["updated_at"] = now
                papers["current_run"] = current_run
                papers["stop_requested"] = False
                papers["is_generating"] = True
                papers["is_paused"] = False
                papers["research_activity"] = {
                    "phase": "writing",
                    "message": "写作续传：正在恢复并继续撰写…",
                    "progress": 0.78,
                    "updated_at": now,
                }
                self.save_papers(papers)

                thread = threading.Thread(
                    target=self._run_writing_resume,
                    args=(effective_topic, effective_branch_id),
                    daemon=True,
                    name="research-writing-resume",
                )
                thread.start()
                return {
                    "success": True,
                    "message": "写作续传已启动",
                    "topic": effective_topic,
                    "branch_id": effective_branch_id,
                    "is_generating": True,
                    "research_activity": {
                        "phase": "writing",
                        "message": "写作续传：正在恢复并继续撰写…",
                        "progress": 0.78,
                    },
                }
            if resume and current_run and (current_run.get("status") in (None, "in_progress", "paused")) and (phase not in ("completed", "error")):
                effective_topic = current_run.get("topic") or topic
                effective_branch_id = int(current_run.get("branch_id") or branch_id)
                current_run["status"] = "in_progress"
                current_run["updated_at"] = now
                papers["current_run"] = current_run
            else:
                run_id = f"RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
                papers["current_run"] = {
                    "run_id": run_id,
                    "branch_id": effective_branch_id,
                    "topic": effective_topic,
                    "status": "in_progress",
                    "started_at": now,
                    "updated_at": now,
                    "last_checkpoint_phase": None,
                }
                papers["hypotheses"] = []
                papers["experiments"] = _build_experiments(topic=effective_topic, run_id=run_id, created_at=now)
                papers["generation_queue"] = []
                papers["live_graphs"] = {}
                papers["run_metrics"] = {"run_id": run_id, "phases": {}, "started_at": now, "updated_at": now}

            papers["stop_requested"] = False

            # 立即写入状态，避免前端轮询时仍读到 idle
            papers["is_generating"] = True
            papers["is_paused"] = False
            papers["research_activity"] = {
                "phase": "starting",
                "message": "正在启动研究…",
                "progress": 0.05,
                "updated_at": now,
            }
            self.save_papers(papers)

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(effective_topic, effective_branch_id),
            daemon=True,
            name="research-pipeline",
        )
        thread.start()
        return {
            "success": True,
            "message": "研究已启动",
            "topic": effective_topic,
            "branch_id": effective_branch_id,
            "is_generating": True,
            "research_activity": {
                "phase": "starting",
                "message": "正在启动研究…",
                "progress": 0.05,
            },
        }

    def _run_writing_resume(self, topic: str, branch_id: int) -> None:
        global _running
        try:
            if not self._gate():
                return
            self._set_activity("writing", "写作续传：正在撰写研究论文…", 0.78)
            write_started = time.perf_counter()
            papers = self.load_papers()
            current_run = papers.get("current_run") if isinstance(papers.get("current_run"), dict) else {}
            run_id = current_run.get("run_id")
            if run_id:
                papers = _merge_run_phase_metrics(
                    papers,
                    run_id=run_id,
                    phase="writing",
                    patch={"started_at": datetime.now().isoformat()},
                )
                self.save_papers(papers)

            workflow = self.load_workflow() or {}
            workflow["current_phase"] = "writing"
            workflow["status"] = "in_progress"
            self.save_workflow(workflow)

            paper = self.create_paper(topic, branch_id)
            paper_status = str(paper.get("status") or "")
            paper_ok = paper_status == "generated"
            now = datetime.now().isoformat()

            if paper_status == "paused":
                refreshed = self.load_papers()
                if run_id:
                    refreshed = _merge_run_phase_metrics(
                        refreshed,
                        run_id=run_id,
                        phase="writing",
                        patch={
                            "completed_at": now,
                            "writing_seconds": max(0.0, time.perf_counter() - write_started),
                            "paper_status": paper_status,
                        },
                    )
                refreshed["is_generating"] = False
                refreshed["is_paused"] = True
                if isinstance(refreshed.get("current_run"), dict):
                    refreshed["current_run"]["status"] = "paused"
                    refreshed["current_run"]["paper_id"] = paper.get("id")
                    refreshed["current_run"]["research_id"] = paper.get("research_id")
                    refreshed["current_run"]["updated_at"] = now
                refreshed["generation_queue"] = [{
                    "topic": topic,
                    "branch_id": branch_id,
                    "added_at": datetime.now().isoformat(),
                    "priority": "normal",
                    "status": "paused",
                    "paper_id": paper.get("id"),
                    "run_id": run_id,
                }]
                self.save_papers(refreshed)
                self._set_activity("paused", f"写作已暂停（可继续）· {paper.get('research_id', '')}", 0.78)
                return

            refreshed = self.load_papers()
            refreshed["live_graphs"] = {}
            if run_id:
                refreshed = _merge_run_phase_metrics(
                    refreshed,
                    run_id=run_id,
                    phase="writing",
                    patch={
                        "completed_at": now,
                        "writing_seconds": max(0.0, time.perf_counter() - write_started),
                        "paper_status": paper_status,
                    },
                )
            self.save_papers(refreshed)

            hypotheses = refreshed.get("hypotheses") or []
            experiments = refreshed.get("experiments") or []
            for exp in experiments:
                if exp.get("id") == "exp_3":
                    exp["paper_id"] = paper.get("id")
                    exp["status"] = "success" if paper_ok else "failed"
                    exp["completed_at"] = now
                    exp["updated_at"] = now

            papers = self.load_papers()
            papers["hypotheses"] = hypotheses
            papers["experiments"] = experiments
            papers["generation_queue"] = [{
                "topic": topic,
                "branch_id": branch_id,
                "added_at": datetime.now().isoformat(),
                "priority": "normal",
                "status": "completed" if paper_ok else "failed",
                "paper_id": paper.get("id"),
                "run_id": run_id,
            }]
            if isinstance(papers.get("current_run"), dict):
                papers["current_run"]["paper_id"] = paper.get("id")
                papers["current_run"]["research_id"] = paper.get("research_id")
                papers["current_run"]["updated_at"] = datetime.now().isoformat()
                papers["current_run"]["status"] = "completed" if paper_ok else "failed"
                papers["current_run"]["failure_reason"] = None if paper_ok else paper.get("content", "")[:300]
            self.save_papers(papers)

            if not paper_ok:
                self._set_activity("error", f"论文生成失败 · {paper.get('research_id', '')}", 0.0)
                papers = self.load_papers()
                papers["is_generating"] = False
                if isinstance(papers.get("current_run"), dict):
                    papers["current_run"]["status"] = "failed"
                    papers["current_run"]["updated_at"] = datetime.now().isoformat()
                self.save_papers(papers)
                return

            self._set_activity("completed", f"研究完成 · {paper.get('research_id', '')}", 1.0)
            papers = self.load_papers()
            papers["is_generating"] = False
            papers["live_graphs"] = {}
            if isinstance(papers.get("current_run"), dict):
                papers["current_run"]["status"] = "completed"
                papers["current_run"]["updated_at"] = datetime.now().isoformat()
            self.save_papers(papers)
        except Exception as exc:
            self._set_activity("error", f"写作续传失败: {exc}", 0.0)
            papers = self.load_papers()
            papers["is_generating"] = False
            papers["live_graphs"] = {}
            if isinstance(papers.get("current_run"), dict):
                papers["current_run"]["status"] = "error"
                papers["current_run"]["updated_at"] = datetime.now().isoformat()
            self.save_papers(papers)
            self.add_log(0, "", "error", str(exc), {})
        finally:
            with _lock:
                _running = False

    def _set_activity(self, phase: str, message: str, progress: float) -> None:
        papers = self.load_papers()
        if (not papers.get("is_paused")) and (not papers.get("stop_requested")):
            papers["is_generating"] = phase not in ("completed", "error", "idle", "paused")
        self._sync_stage_experiments(papers, phase=phase)
        papers["research_activity"] = {
            "phase": phase,
            "message": message,
            "progress": progress,
            "updated_at": datetime.now().isoformat(),
        }
        if isinstance(papers.get("current_run"), dict):
            papers["current_run"]["last_checkpoint_phase"] = phase
            papers["current_run"]["updated_at"] = datetime.now().isoformat()
        self.save_papers(papers)

    def _sync_stage_experiments(self, papers: dict, *, phase: str) -> None:
        current_run = papers.get("current_run") if isinstance(papers.get("current_run"), dict) else {}
        run_id = current_run.get("run_id")
        if not run_id:
            return

        experiments = papers.get("experiments") or []
        now = datetime.now().isoformat()

        if (not experiments) or (experiments[0].get("run_id") != run_id) or (not experiments[0].get("stage_phases")):
            topic = str(current_run.get("topic") or "")
            created_at = str(current_run.get("started_at") or now)
            experiments = _build_experiments(topic=topic, run_id=run_id, created_at=created_at)

        phase_to_stage = {
            "starting": 0,
            "literature_review": 0,
            "hypothesis": 0,
            "experimenting": 1,
            "writing": 2,
            "completed": 2,
            "paused": 2,
            "error": 2,
            "idle": 0,
        }
        stage_idx = int(phase_to_stage.get(phase, 2))

        for idx, exp in enumerate(experiments):
            if idx < stage_idx:
                if exp.get("status") not in ("success", "failed"):
                    exp["status"] = "success"
                if not exp.get("started_at"):
                    exp["started_at"] = current_run.get("started_at") or now
                if not exp.get("completed_at"):
                    exp["completed_at"] = now
            elif idx == stage_idx:
                if exp.get("status") not in ("success", "failed"):
                    exp["status"] = "experimenting"
                if not exp.get("started_at"):
                    exp["started_at"] = now
            else:
                if exp.get("status") is None or exp.get("status") == "experimenting":
                    exp["status"] = "pending"
            exp["updated_at"] = now

        papers["experiments"] = experiments

    def _gate(self) -> bool:
        while True:
            papers = self.load_papers()
            if papers.get("stop_requested"):
                return False
            if not papers.get("is_generating"):
                return False
            if papers.get("is_paused"):
                time.sleep(0.5)
                continue
            return True

    def _run_pipeline(self, topic: str, branch_id: int) -> None:
        global _running
        try:
            while True:
                if not self._gate():
                    return

                manifest = _load_json_manifest()
                seed_count = len(manifest.get("seed_papers") or list_seed_papers())

                workflow = self.load_workflow() or {}

                papers = self.load_papers()
                current_run = papers.get("current_run") if isinstance(papers.get("current_run"), dict) else {}
                run_id = current_run.get("run_id") or ""

                hypotheses = papers.get("hypotheses") or []
                experiments = papers.get("experiments") or []
                if hypotheses and hypotheses[0].get("run_id") != run_id:
                    hypotheses = []
                if experiments and experiments[0].get("run_id") != run_id:
                    experiments = []

                if not hypotheses:
                    self._set_activity("literature_review", f"正在分析 {seed_count} 篇种子文献…", 0.12)
                    self.add_log(0, "", "literature_review", f"开始解析 {seed_count} 篇种子文献并生成综述分析", {"topic": topic, "run_id": run_id})
                    papers = self.load_papers()
                    papers = _merge_run_phase_metrics(
                        papers,
                        run_id=run_id,
                        phase="literature_review",
                        patch={"started_at": datetime.now().isoformat(), "seed_count": seed_count},
                    )
                    self.save_papers(papers)
                    workflow = self.load_workflow() or {}
                    workflow["project_name"] = topic
                    workflow["status"] = "in_progress"
                    workflow["current_phase"] = "literature_review"
                    workflow["updated_at"] = datetime.now().isoformat()
                    self.save_workflow(workflow)

                    literature = _build_literature_review(topic)
                    timing = literature.get("timings") if isinstance(literature.get("timings"), dict) else {}
                    workflow = self.load_workflow() or {}
                    workflow["project_name"] = topic
                    workflow["status"] = "in_progress"
                    workflow["current_phase"] = "literature_review"
                    workflow["literature_review"] = {
                        "papers_read": literature.get("papers_read") or [],
                        "papers_to_read": literature.get("papers_to_read") or [],
                        "key_themes": literature.get("key_themes") or [],
                        "research_questions": literature.get("research_questions") or [],
                        "research_gaps": literature.get("research_gaps") or [],
                        "potential_innovations": literature.get("potential_innovations") or [],
                        "analysis_markdown": str(literature.get("analysis_markdown") or "")[:8000],
                        "extraction_stats": literature.get("extraction_stats") or {},
                        "timings": timing,
                        "analysis_generated_at": datetime.now().isoformat(),
                    }
                    workflow = _record_phase(
                        workflow,
                        phase="literature_review",
                        run_id=run_id,
                        details={
                            "seed_count": seed_count,
                            "papers_read_count": len(literature.get("papers_read") or []),
                            "papers_to_read_count": len(literature.get("papers_to_read") or []),
                            "key_themes": literature.get("key_themes") or [],
                            "research_questions": literature.get("research_questions") or [],
                            "research_gaps": literature.get("research_gaps") or [],
                            "potential_innovations": literature.get("potential_innovations") or [],
                            "timings": timing,
                            "analysis_excerpt": str(literature.get("analysis_markdown") or "")[:1500],
                        },
                    )
                    self.save_workflow(workflow)
                    papers = self.load_papers()
                    papers = _merge_run_phase_metrics(
                        papers,
                        run_id=run_id,
                        phase="literature_review",
                        patch={
                            "completed_at": datetime.now().isoformat(),
                            "papers_read_count": int(timing.get("papers_read_count") or len(literature.get("papers_read") or [])),
                            "read_seconds": float(timing.get("read_seconds") or 0.0),
                            "analysis_seconds": float(timing.get("analysis_seconds") or 0.0),
                            "total_seconds": float(timing.get("total_seconds") or 0.0),
                            "avg_read_seconds_per_paper": float(timing.get("avg_read_seconds_per_paper") or 0.0),
                            "avg_analysis_seconds_per_paper": float(timing.get("avg_analysis_seconds_per_paper") or 0.0),
                            "theme_count": len(literature.get("key_themes") or []),
                            "question_count": len(literature.get("research_questions") or []),
                        },
                    )
                    self.save_papers(papers)
                    self.add_log(
                        0,
                        "",
                        "literature_review",
                        f"完成种子论文分析：已解析 {len(literature.get('papers_read') or [])} 篇，提炼 {len(literature.get('key_themes') or [])} 个主题",
                        {
                            "topic": topic,
                            "run_id": run_id,
                            "papers_read_count": len(literature.get("papers_read") or []),
                            "papers_to_read_count": len(literature.get("papers_to_read") or []),
                            "key_themes": literature.get("key_themes") or [],
                        },
                    )
                    if not self._gate():
                        return

                    self._set_activity("hypothesis", "正在从文献空白生成研究假设…", 0.32)
                    papers = self.load_papers()
                    papers = _merge_run_phase_metrics(
                        papers,
                        run_id=run_id,
                        phase="hypothesis",
                        patch={"started_at": datetime.now().isoformat()},
                    )
                    self.save_papers(papers)
                    workflow = self.load_workflow() or {}
                    hypotheses = _build_hypotheses(workflow, topic, run_id=run_id)
                    for h in hypotheses:
                        h["run_id"] = run_id
                    workflow["current_phase"] = "hypothesis"
                    workflow = _record_phase(
                        workflow,
                        phase="hypothesis",
                        run_id=run_id,
                        details={
                            "count": len(hypotheses),
                            "hypotheses": [
                                {
                                    "id": h.get("id"),
                                    "title": h.get("title"),
                                    "tags": h.get("tags") or [],
                                }
                                for h in hypotheses
                            ],
                        },
                    )
                    self.save_workflow(workflow)
                    papers = self.load_papers()
                    papers["hypotheses"] = hypotheses
                    papers = _merge_run_phase_metrics(
                        papers,
                        run_id=run_id,
                        phase="hypothesis",
                        patch={
                            "completed_at": datetime.now().isoformat(),
                            "hypotheses_count": len(hypotheses),
                        },
                    )
                    self.save_papers(papers)
                    self.add_log(0, "", "hypothesis", f"生成 {len(hypotheses)} 条假设", {"count": len(hypotheses), "run_id": run_id})

                if not self._gate():
                    return

                if not experiments:
                    experiments = _build_experiments(topic=topic, run_id=run_id, created_at=datetime.now().isoformat())
                    papers = self.load_papers()
                    papers["experiments"] = experiments
                    self.save_papers(papers)

                self._set_activity("experimenting", "正在构建引用/作者图谱…", 0.55)
                graph_started = time.perf_counter()
                papers = self.load_papers()
                papers = _merge_run_phase_metrics(
                    papers,
                    run_id=run_id,
                    phase="experimenting",
                    patch={"started_at": datetime.now().isoformat()},
                )
                self.save_papers(papers)
                seed_papers = list_seed_papers()
                author_network = build_author_network_from_seed_papers(seed_papers)
                graph_papers_data = self.load_papers()
                citation_network = build_citation_network(papers_data=graph_papers_data, seed_papers=seed_papers)
                papers = self.load_papers()
                papers["live_graphs"] = {
                    "run_id": run_id,
                    "author_network": author_network,
                    "citation_network": citation_network,
                    "updated_at": datetime.now().isoformat(),
                }
                papers = _merge_run_phase_metrics(
                    papers,
                    run_id=run_id,
                    phase="experimenting",
                    patch={
                        "completed_at": datetime.now().isoformat(),
                        "graph_build_seconds": max(0.0, time.perf_counter() - graph_started),
                        "author_count": len(author_network.get("authors") or []),
                        "institution_count": len(author_network.get("institutions") or []),
                        "collaboration_count": len(author_network.get("collaborations") or []),
                        "reference_count": len(citation_network.get("references") or []),
                        "citation_edge_count": len(citation_network.get("edges") or []),
                    },
                )
                self.save_papers(papers)
                workflow = self.load_workflow() or {}
                workflow["current_phase"] = "experimenting"
                workflow["status"] = "in_progress"
                workflow = _record_phase(
                    workflow,
                    phase="experimenting",
                    run_id=run_id,
                    details={
                        "topic": topic,
                        "author_count": len(author_network.get("authors") or []),
                        "institution_count": len(author_network.get("institutions") or []),
                        "collaboration_count": len(author_network.get("collaborations") or []),
                        "reference_count": len(citation_network.get("references") or []),
                        "citation_edge_count": len(citation_network.get("edges") or []),
                        "planned_outputs": ["author_network", "citation_network", "experiment_bundle"],
                    },
                )
                self.save_workflow(workflow)
                self.add_log(0, "", "experimenting", "构建引用关系与作者网络", {"run_id": run_id})

                if not self._gate():
                    return

                self._set_activity("writing", "正在撰写研究论文…", 0.78)
                write_started = time.perf_counter()
                papers = self.load_papers()
                papers = _merge_run_phase_metrics(
                    papers,
                    run_id=run_id,
                    phase="writing",
                    patch={"started_at": datetime.now().isoformat()},
                )
                self.save_papers(papers)
                workflow = self.load_workflow() or {}
                workflow["current_phase"] = "writing"
                workflow["status"] = "in_progress"
                self.save_workflow(workflow)
                paper = self.create_paper(topic, branch_id)
                paper_status = str(paper.get("status") or "")
                paper_ok = paper_status == "generated"
                now = datetime.now().isoformat()

                if paper_status == "paused":
                    refreshed = self.load_papers()
                    refreshed = _merge_run_phase_metrics(
                        refreshed,
                        run_id=run_id,
                        phase="writing",
                        patch={
                            "completed_at": now,
                            "writing_seconds": max(0.0, time.perf_counter() - write_started),
                            "paper_status": paper_status,
                        },
                    )
                    refreshed["is_generating"] = False
                    refreshed["is_paused"] = True
                    if isinstance(refreshed.get("current_run"), dict):
                        refreshed["current_run"]["status"] = "paused"
                        refreshed["current_run"]["paper_id"] = paper.get("id")
                        refreshed["current_run"]["research_id"] = paper.get("research_id")
                        refreshed["current_run"]["updated_at"] = now
                    refreshed["generation_queue"] = [{
                        "topic": topic,
                        "branch_id": branch_id,
                        "added_at": datetime.now().isoformat(),
                        "priority": "normal",
                        "status": "paused",
                        "paper_id": paper.get("id"),
                        "run_id": run_id,
                    }]
                    self.save_papers(refreshed)
                    self._set_activity("paused", f"写作已暂停（可继续）· {paper.get('research_id', '')}", 0.78)
                    return

                refreshed = self.load_papers()
                refreshed["live_graphs"] = {
                    "run_id": run_id,
                    "author_network": build_author_network_from_seed_papers(list_seed_papers()),
                    "citation_network": build_citation_network(papers_data=refreshed, seed_papers=list_seed_papers()),
                    "updated_at": now,
                }
                refreshed = _merge_run_phase_metrics(
                    refreshed,
                    run_id=run_id,
                    phase="writing",
                    patch={
                        "completed_at": now,
                        "writing_seconds": max(0.0, time.perf_counter() - write_started),
                        "paper_status": paper_status,
                    },
                )
                self.save_papers(refreshed)

                for hyp in hypotheses:
                    hyp["status"] = "success" if paper_ok else "failed"
                    hyp["actual_outcome"] = (
                        f"论文与实验产物已落盘，研究编号 {paper.get('research_id', '')}"
                        if paper_ok else
                        f"写作阶段失败，未完成验证：{paper.get('title', topic)}"
                    )
                for exp in experiments:
                    exp["paper_id"] = paper.get("id")
                    artifacts = paper.get("artifacts") or {}
                    if exp.get("id") == "exp_1":
                        exp["status"] = "success" if (workflow.get("literature_review") or {}).get("papers_read") else "failed"
                        exp["artifacts"] = {
                            "docs": artifacts.get("hypotheses_doc"),
                            "data_spec": artifacts.get("experiment_data_spec"),
                        }
                    elif exp.get("id") == "exp_2":
                        exp["status"] = "success" if (artifacts.get("author_network_json") and artifacts.get("citation_network_json")) else "failed"
                        exp["artifacts"] = {
                            "author_network": artifacts.get("author_network_json"),
                            "citation_network": artifacts.get("citation_network_json"),
                            "docs": artifacts.get("author_network_md") or artifacts.get("citation_network_md"),
                        }
                    elif exp.get("id") == "exp_3":
                        exp["status"] = "success" if paper_ok else "failed"
                        exp["artifacts"] = {
                            "data": artifacts.get("backtest_results") or artifacts.get("experiment_data"),
                            "indicators": artifacts.get("indicator_sample"),
                            "code": artifacts.get("code"),
                            "docs": artifacts.get("experiment_results_doc"),
                        }
                    exp["completed_at"] = now
                    exp["updated_at"] = now

                papers = self.load_papers()
                papers["hypotheses"] = hypotheses
                papers["experiments"] = experiments
                papers["generation_queue"] = [{
                    "topic": topic,
                    "branch_id": branch_id,
                    "added_at": datetime.now().isoformat(),
                    "priority": "normal",
                    "status": "completed" if paper_ok else "failed",
                    "paper_id": paper.get("id"),
                    "run_id": run_id,
                }]

                completed_run = dict(papers.get("current_run") or {})
                if completed_run:
                    completed_run["status"] = "completed" if paper_ok else "failed"
                    completed_run["paper_id"] = paper.get("id")
                    completed_run["research_id"] = paper.get("research_id")
                    completed_run["failure_reason"] = None if paper_ok else paper.get("content", "")[:300]
                    completed_run["updated_at"] = datetime.now().isoformat()
                    runs = papers.get("runs") or []
                    runs.append(completed_run)
                    papers["runs"] = runs

                self.save_papers(papers)

                workflow = self.load_workflow() or {}
                workflow["current_phase"] = "completed" if paper_ok else "error"
                workflow["status"] = "completed" if paper_ok else "error"
                workflow = _record_phase(
                    workflow,
                    phase="writing",
                    run_id=run_id,
                    details={
                        "paper_id": paper.get("id"),
                        "research_id": paper.get("research_id"),
                        "title": paper.get("title"),
                        "status": paper_status,
                    },
                    status="completed" if paper_ok else "failed",
                )
                self.save_workflow(workflow)

                self.add_log(
                    paper.get("id", 0),
                    paper.get("research_id", ""),
                    "completed" if paper_ok else "error",
                    f"研究{'完成' if paper_ok else '失败'}: {paper.get('title', topic)}",
                    {"research_id": paper.get("research_id"), "run_id": run_id, "paper_status": paper_status},
                )

                if not paper_ok:
                    reason = (paper.get("content", "") or "")[:300]
                    self._set_activity("paused", f"论文失败已暂停 · {paper.get('research_id', '')}", 0.78)
                    papers = self.load_papers()
                    papers["is_generating"] = False
                    papers["is_paused"] = True
                    if isinstance(papers.get("current_run"), dict):
                        papers["current_run"]["status"] = "paused"
                        papers["current_run"]["failure_reason"] = reason
                        papers["current_run"]["updated_at"] = datetime.now().isoformat()
                    papers["generation_queue"] = [{
                        "topic": topic,
                        "branch_id": branch_id,
                        "added_at": datetime.now().isoformat(),
                        "priority": "normal",
                        "status": "paused",
                        "paper_id": paper.get("id"),
                        "run_id": run_id,
                    }]
                    self.save_papers(papers)
                    return

                papers = self.load_papers()
                if not papers.get("is_generating"):
                    self._set_activity("completed", f"已停止（完成当前一篇）· {paper.get('research_id', '')}", 1.0)
                    return
                pause_after_next = bool((papers.get("settings") or {}).get("pause_after_next"))
                auto_continue = bool((papers.get("settings") or {}).get("auto_continue", True))

                if pause_after_next:
                    papers["settings"]["pause_after_next"] = False
                    now = datetime.now().isoformat()
                    seeds = list_seed_papers()
                    base_title = (seeds[len(papers.get("runs") or []) % len(seeds)].get("title") if seeds else None) or topic
                    next_topic = f"{base_title}（扩展 {datetime.now().strftime('%H%M%S')}）"
                    papers["current_run"] = {
                        "run_id": f"RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
                        "branch_id": branch_id,
                        "topic": next_topic,
                        "status": "paused",
                        "started_at": now,
                        "updated_at": now,
                        "last_checkpoint_phase": None,
                    }
                    papers["hypotheses"] = []
                    papers["experiments"] = []
                    papers["generation_queue"] = []
                    papers["is_paused"] = True
                    papers["is_generating"] = True
                    papers["research_activity"] = {
                        "phase": "paused",
                        "message": f"已暂停（完成一篇）· {paper.get('research_id', '')}",
                        "progress": 1.0,
                        "updated_at": now,
                    }
                    papers["live_graphs"] = {}
                    self.save_papers(papers)
                    continue

                if not auto_continue:
                    self._set_activity("completed", f"研究完成 · {paper.get('research_id', '')}", 1.0)
                    papers = self.load_papers()
                    papers["is_generating"] = False
                    if isinstance(papers.get("current_run"), dict):
                        papers["current_run"]["status"] = "completed"
                        papers["current_run"]["updated_at"] = datetime.now().isoformat()
                    papers["live_graphs"] = {}
                    self.save_papers(papers)
                    return

                now = datetime.now().isoformat()
                seeds = list_seed_papers()
                base_title = (seeds[len(papers.get("runs") or []) % len(seeds)].get("title") if seeds else None) or topic
                next_topic = f"{base_title}（扩展 {datetime.now().strftime('%H%M%S')}）"
                papers["current_run"] = {
                    "run_id": f"RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
                    "branch_id": branch_id,
                    "topic": next_topic,
                    "status": "in_progress",
                    "started_at": now,
                    "updated_at": now,
                    "last_checkpoint_phase": None,
                }
                papers["hypotheses"] = []
                papers["experiments"] = []
                papers["generation_queue"] = []
                papers["is_generating"] = True
                papers["is_paused"] = False
                papers["live_graphs"] = {}
                papers["research_activity"] = {
                    "phase": "starting",
                    "message": "自动继续：正在启动下一轮研究…",
                    "progress": 0.05,
                    "updated_at": now,
                }
                self.save_papers(papers)
                topic = next_topic
        except Exception as exc:
            self._set_activity("error", f"研究失败: {exc}", 0.0)
            papers = self.load_papers()
            papers["is_generating"] = False
            papers["live_graphs"] = {}
            if isinstance(papers.get("current_run"), dict):
                papers["current_run"]["status"] = "error"
                papers["current_run"]["updated_at"] = datetime.now().isoformat()
            self.save_papers(papers)
            self.add_log(0, "", "error", str(exc), {})
        finally:
            with _lock:
                _running = False
