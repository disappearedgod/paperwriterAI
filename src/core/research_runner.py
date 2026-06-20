"""
研究流水线 — 点击「开始」后在后台推进：文献 → 假设 → 实验 → 论文。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from core.data_registry import SEED_MANIFEST
from core.seed_library import list_seed_papers

_lock = threading.Lock()
_running = False


def _load_json_manifest() -> dict:
    if SEED_MANIFEST.exists():
        import json
        return json.loads(SEED_MANIFEST.read_text(encoding="utf-8"))
    return {}


def _build_hypotheses(workflow: dict, topic: str) -> List[dict]:
    gaps: List[str] = []
    innovations: List[str] = []

    for phase in workflow.get("phase_history", []):
        details = phase.get("details") or {}
        gaps.extend(details.get("research_gaps", []))
        innovations.extend(details.get("potential_innovations", []))

    lit = workflow.get("literature_review") or {}
    themes = lit.get("key_themes") or []

    seeds = list_seed_papers()[:5]
    seed_topics = []
    for sp in seeds:
        seed_topics.extend(sp.get("key_topics") or [])

    candidates = innovations or gaps or [
        f"基于多智能体 LLM 的{topic}信号生成",
        f"跨时间尺度量化因子与 LLM 融合",
        f"金融幻觉检测与可解释交易决策",
    ]

    hypotheses = []
    for i, title in enumerate(candidates[:5], start=1):
        tag_pool = list(dict.fromkeys(seed_topics + themes))[:4] or ["量化", "LLM"]
        hypotheses.append({
            "id": f"hyp_{i}",
            "title": title if isinstance(title, str) else str(title),
            "description": f"围绕「{title}」提出可验证假设，结合种子文献与分支综述主题「{topic}」。",
            "tags": tag_pool[:3],
            "status": "hypothesis",
            "expected_outcome": "回测夏普比率优于基准策略",
            "actual_outcome": None,
        })
    return hypotheses


def _build_experiments(hypotheses: List[dict], topic: str) -> List[dict]:
    experiments = []
    for i, hyp in enumerate(hypotheses[:3], start=1):
        experiments.append({
            "id": f"exp_{i}",
            "title": f"实验{i}: {hyp['title'][:40]}",
            "status": "experimenting",
            "hypothesis_id": hyp["id"],
            "paper_id": None,
            "method": "量化回测 + 指标对比",
            "topic": topic,
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

    def kickoff(self, *, topic: str, branch_id: int, resume: bool = False) -> Dict[str, Any]:
        global _running
        with _lock:
            papers = self.load_papers()
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
                papers["experiments"] = []
                papers["generation_queue"] = []

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

    def _set_activity(self, phase: str, message: str, progress: float) -> None:
        papers = self.load_papers()
        if (not papers.get("is_paused")) and (not papers.get("stop_requested")):
            papers["is_generating"] = phase not in ("completed", "error", "idle", "paused")
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
                    self.add_log(0, "", "literature_review", f"读取种子文献 {seed_count} 篇", {"topic": topic, "run_id": run_id})
                    time.sleep(1.2)
                    if not self._gate():
                        return

                    self._set_activity("hypothesis", "正在从文献空白生成研究假设…", 0.32)
                    hypotheses = _build_hypotheses(workflow, topic)
                    for h in hypotheses:
                        h["run_id"] = run_id
                    papers = self.load_papers()
                    papers["hypotheses"] = hypotheses
                    self.save_papers(papers)
                    self.add_log(0, "", "hypothesis", f"生成 {len(hypotheses)} 条假设", {"count": len(hypotheses), "run_id": run_id})
                    time.sleep(1.0)

                if not self._gate():
                    return

                if not experiments:
                    self._set_activity("experimenting", "正在运行回测实验…", 0.55)
                    experiments = _build_experiments(hypotheses, topic)
                    for e in experiments:
                        e["run_id"] = run_id
                    papers = self.load_papers()
                    papers["experiments"] = experiments
                    self.save_papers(papers)
                    self.add_log(0, "", "experimenting", f"启动 {len(experiments)} 个实验", {"count": len(experiments), "run_id": run_id})
                    time.sleep(1.2)

                if not self._gate():
                    return

                self._set_activity("writing", "正在撰写研究论文…", 0.78)
                paper = self.create_paper(topic, branch_id)

                for hyp in hypotheses:
                    hyp["status"] = "success"
                    hyp["actual_outcome"] = "实验指标达到预期区间（模拟回测）"
                for exp in experiments:
                    exp["status"] = "success"
                    exp["paper_id"] = paper.get("id")
                    artifacts = paper.get("artifacts") or {}
                    exp["artifacts"] = {
                        "data": artifacts.get("backtest_results") or artifacts.get("experiment_data"),
                        "indicators": artifacts.get("indicator_sample"),
                        "code": artifacts.get("code"),
                    }

                papers = self.load_papers()
                papers["hypotheses"] = hypotheses
                papers["experiments"] = experiments
                papers["generation_queue"] = [{
                    "topic": topic,
                    "branch_id": branch_id,
                    "added_at": datetime.now().isoformat(),
                    "priority": "normal",
                    "status": "completed",
                    "paper_id": paper.get("id"),
                    "run_id": run_id,
                }]

                completed_run = dict(papers.get("current_run") or {})
                if completed_run:
                    completed_run["status"] = "completed"
                    completed_run["paper_id"] = paper.get("id")
                    completed_run["research_id"] = paper.get("research_id")
                    completed_run["updated_at"] = datetime.now().isoformat()
                    runs = papers.get("runs") or []
                    runs.append(completed_run)
                    papers["runs"] = runs

                self.save_papers(papers)

                self.add_log(
                    paper.get("id", 0),
                    paper.get("research_id", ""),
                    "completed",
                    f"研究完成: {paper.get('title', topic)}",
                    {"research_id": paper.get("research_id"), "run_id": run_id},
                )

                papers = self.load_papers()
                if not papers.get("is_generating"):
                    self._set_activity("completed", f"已停止（完成当前一篇）· {paper.get('research_id', '')}", 1.0)
                    return
                pause_after_next = bool((papers.get("settings") or {}).get("pause_after_next"))
                auto_continue = bool((papers.get("settings") or {}).get("auto_continue"))

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
                    self.save_papers(papers)
                    continue

                if not auto_continue:
                    self._set_activity("completed", f"研究完成 · {paper.get('research_id', '')}", 1.0)
                    papers = self.load_papers()
                    papers["is_generating"] = False
                    if isinstance(papers.get("current_run"), dict):
                        papers["current_run"]["status"] = "completed"
                        papers["current_run"]["updated_at"] = datetime.now().isoformat()
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
            if isinstance(papers.get("current_run"), dict):
                papers["current_run"]["status"] = "error"
                papers["current_run"]["updated_at"] = datetime.now().isoformat()
            self.save_papers(papers)
            self.add_log(0, "", "error", str(exc), {})
        finally:
            with _lock:
                _running = False
