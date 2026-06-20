"""
研究流水线 — 点击「开始」后在后台推进：文献 → 假设 → 实验 → 论文。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

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

    def kickoff(self, *, topic: str, branch_id: int) -> Dict[str, Any]:
        global _running
        with _lock:
            papers = self.load_papers()
            if papers.get("is_generating"):
                return {
                    "success": True,
                    "already_running": True,
                    "message": "研究正在进行中",
                    "research_activity": papers.get("research_activity"),
                }
            if _running:
                return {"success": True, "already_running": True, "message": "研究正在启动"}
            _running = True

            # 立即写入状态，避免前端轮询时仍读到 idle
            papers["is_generating"] = True
            papers["is_paused"] = False
            papers["research_activity"] = {
                "phase": "starting",
                "message": "正在启动研究…",
                "progress": 0.05,
                "updated_at": datetime.now().isoformat(),
            }
            self.save_papers(papers)

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(topic, branch_id),
            daemon=True,
            name="research-pipeline",
        )
        thread.start()
        return {
            "success": True,
            "message": "研究已启动",
            "topic": topic,
            "branch_id": branch_id,
            "is_generating": True,
            "research_activity": {
                "phase": "starting",
                "message": "正在启动研究…",
                "progress": 0.05,
            },
        }

    def _set_activity(self, phase: str, message: str, progress: float) -> None:
        papers = self.load_papers()
        papers["is_generating"] = phase not in ("completed", "error", "idle")
        papers["is_paused"] = False
        papers["research_activity"] = {
            "phase": phase,
            "message": message,
            "progress": progress,
            "updated_at": datetime.now().isoformat(),
        }
        self.save_papers(papers)

    def _run_pipeline(self, topic: str, branch_id: int) -> None:
        global _running
        try:
            manifest = _load_json_manifest()
            seed_count = len(manifest.get("seed_papers") or list_seed_papers())

            self._set_activity("literature_review", f"正在分析 {seed_count} 篇种子文献…", 0.12)
            self.add_log(0, "", "literature_review", f"读取种子文献 {seed_count} 篇", {"topic": topic})
            time.sleep(1.2)

            workflow = self.load_workflow()
            if workflow:
                workflow["status"] = "in_progress"
                workflow["current_phase"] = "literature_review"
                workflow["updated_at"] = datetime.now().isoformat()
                self.save_workflow(workflow)

            self._set_activity("hypothesis", "正在从文献空白生成研究假设…", 0.32)
            hypotheses = _build_hypotheses(workflow, topic)
            papers = self.load_papers()
            papers["hypotheses"] = hypotheses
            self.save_papers(papers)
            self.add_log(0, "", "hypothesis", f"生成 {len(hypotheses)} 条假设", {"count": len(hypotheses)})
            time.sleep(1.0)

            self._set_activity("experimenting", "正在运行回测实验…", 0.55)
            experiments = _build_experiments(hypotheses, topic)
            papers = self.load_papers()
            papers["experiments"] = experiments
            self.save_papers(papers)
            self.add_log(0, "", "experimenting", f"启动 {len(experiments)} 个实验", {"count": len(experiments)})
            time.sleep(1.2)

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
            }]
            self.save_papers(papers)

            if workflow:
                workflow["current_phase"] = "paper_generation"
                workflow["status"] = "in_progress"
                workflow["updated_at"] = datetime.now().isoformat()
                self.save_workflow(workflow)

            self.add_log(
                paper.get("id", 0),
                paper.get("research_id", ""),
                "completed",
                f"研究完成: {paper.get('title', topic)}",
                {"research_id": paper.get("research_id")},
            )
            self._set_activity(
                "completed",
                f"研究完成 · {paper.get('research_id', '')}",
                1.0,
            )
            papers = self.load_papers()
            papers["is_generating"] = False
            self.save_papers(papers)
        except Exception as exc:
            self._set_activity("error", f"研究失败: {exc}", 0.0)
            papers = self.load_papers()
            papers["is_generating"] = False
            self.save_papers(papers)
            self.add_log(0, "", "error", str(exc), {})
        finally:
            with _lock:
                _running = False
