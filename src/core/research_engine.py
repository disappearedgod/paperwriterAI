"""
FARS 断点续分析引擎 — Fault-Tolerant Research Engine
=====================================================
4大核心机制:
  1. Checkpoint (每步存档)    — 每完成一个分析步骤立即持久化
  2. Graceful Degradation     — 卡顿时并发写论文 + BugReport
  3. 断点续分析 (Resume)       — 从上次中断处继续，生成增量MD
  4. 作者/引用关系网络         — 多论文比对 + 第二轮文献发现

每个 Research 都有独立的 workspace/
  ├── checkpoint.json        # 断点状态机
  ├── paper_analysis/         # 每篇论文的分析结果
  │   ├── {arxiv_id}.md
  │   └── {arxiv_id}_checkpoint.json
  ├── perspective_analysis/   # 视角分析
  │   └── {perspective}.md
  ├── outline.md             # 论文大纲
  ├── literature_review.md    # 文献综述
  ├── bug_reports/           # Bug报告
  │   └── {step}.json
  ├── author_network/        # 作者关系图
  │   └── author_graph.json
  └── draft/                 # 论文草稿
      ├── introduction.md
      ├── related_work.md
      └── full_paper.md
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

import pdfplumber

from core.data_registry import SEED_PAPERS_DIR, SEED_MANIFEST
from core.paper_extractor import (
    get_all_paper_texts,
    get_paper_text,
    get_library_status,
    _load_manifest,
)

# ============================================================================
# 1. Checkpoint 状态机
# ============================================================================

class StepStatus(str, Enum):
    PENDING    = "pending"
    RUNNING    = "running"
    DONE       = "done"
    FAILED     = "failed"
    SKIPPED    = "skipped"   # 降级跳过（不阻塞后续）


class ResearchPhase(str, Enum):
    """研究流程的5个阶段"""
    PAPER_SCAN      = "paper_scan"       # 论文扫描与文本提取
    PERSPECTIVE     = "perspective"      # 多视角分析
    OUTLINE         = "outline"          # 大纲生成
    LITERATURE_REVIEW = "literature_review"  # 文献综述撰写
    PAPER_WRITING   = "paper_writing"   # 论文撰写（可与前几步并发）


@dataclass
class StepRecord:
    """单个分析步骤的记录"""
    step_id:      str           # e.g. "paper_2311.10723", "perspective_agentic"
    phase:        str           # ResearchPhase
    status:       str           # StepStatus
    started_at:   Optional[str] = None
    completed_at: Optional[str] = None
    output_path:  Optional[str] = None   # 产出文件路径
    error:        Optional[str] = None   # 错误信息（如果失败）
    retry_count:  int = 0
    output_md5:   Optional[str] = None   # 产出MD5，防止重复写入


@dataclass
class ResearchCheckpoint:
    """研究流程的完整断点状态"""
    research_id:       str
    created_at:        str
    updated_at:        str
    current_phase:     str
    steps:             Dict[str, StepRecord] = field(default_factory=dict)
    # 并发写作状态
    paper_writing_started: bool = False
    paper_writing_phase:  str = "pending"
    last_completed_step:  Optional[str] = None
    # Bug报告
    bug_reports: List[Dict] = field(default_factory=list)
    # 元数据
    total_papers: int = 0
    analyzed_papers: int = 0
    error_count: int = 0

    def step(self, step_id: str) -> StepRecord:
        if step_id not in self.steps:
            self.steps[step_id] = StepRecord(
                step_id=step_id,
                phase=self.current_phase,
                status=StepStatus.PENDING.value,
            )
        return self.steps[step_id]

    def mark_running(self, step_id: str, phase: str) -> StepRecord:
        self.current_phase = phase
        s = self.step(step_id)
        s.status = StepStatus.RUNNING.value
        s.started_at = datetime.now().isoformat()
        return s

    def mark_done(self, step_id: str, output_path: str = "", error: str = "") -> StepRecord:
        s = self.step(step_id)
        if error:
            s.status = StepStatus.FAILED.value
            s.error = error
            self.error_count += 1
        else:
            s.status = StepStatus.DONE.value
            s.output_path = output_path
            if output_path:
                try:
                    with open(output_path, 'rb') as f:
                        s.output_md5 = hashlib.md5(f.read()).hexdigest()
                except Exception:
                    pass
        s.completed_at = datetime.now().isoformat()
        self.last_completed_step = step_id
        self.updated_at = datetime.now().isoformat()
        return s

    def mark_skipped(self, step_id: str, reason: str = "") -> StepRecord:
        s = self.step(step_id)
        s.status = StepStatus.SKIPPED.value
        s.error = reason
        s.completed_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        return s

    def pending_steps(self) -> List[str]:
        return [k for k, v in self.steps.items()
                if v.status in (StepStatus.PENDING.value, StepStatus.FAILED.value)]

    def done_steps(self) -> List[str]:
        return [k for k, v in self.steps.items() if v.status == StepStatus.DONE.value]

    def to_dict(self) -> Dict:
        return {
            "research_id": self.research_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_phase": self.current_phase,
            "steps": {k: asdict(v) for k, v in self.steps.items()},
            "paper_writing_started": self.paper_writing_started,
            "paper_writing_phase": self.paper_writing_phase,
            "last_completed_step": self.last_completed_step,
            "bug_reports": self.bug_reports,
            "total_papers": self.total_papers,
            "analyzed_papers": self.analyzed_papers,
            "error_count": self.error_count,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ResearchCheckpoint":
        cp = cls(
            research_id=d["research_id"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            current_phase=d["current_phase"],
            paper_writing_started=d.get("paper_writing_started", False),
            paper_writing_phase=d.get("paper_writing_phase", "pending"),
            last_completed_step=d.get("last_completed_step"),
            bug_reports=d.get("bug_reports", []),
            total_papers=d.get("total_papers", 0),
            analyzed_papers=d.get("analyzed_papers", 0),
            error_count=d.get("error_count", 0),
        )
        for k, v in d.get("steps", {}).items():
            cp.steps[k] = StepRecord(**v)
        return cp


# ============================================================================
# 2. 持久化层 — Checkpoint 读写
# ============================================================================

def _workspace(research_id: str) -> Path:
    prefix = "" if research_id.startswith("RS-") else "RS-"
    clean_id = f"{prefix}{research_id}"
    research_dir = SEED_PAPERS_DIR.parent / "research"
    if research_dir.exists():
        import glob
        pattern = str(research_dir / f"{clean_id}_*")
        matching = glob.glob(pattern)
        if matching:
            return Path(matching[0])
        pattern_exact = str(research_dir / clean_id)
        matching_exact = glob.glob(pattern_exact)
        if matching_exact:
            return Path(matching_exact[0])
    return research_dir / f"{clean_id}_checkpoint"


def _checkpoint_path(research_id: str) -> Path:
    return _workspace(research_id) / "checkpoint.json"


def load_checkpoint(research_id: str) -> Optional[ResearchCheckpoint]:
    """从磁盘加载断点，不存在则返回 None"""
    path = _checkpoint_path(research_id)
    if path.exists():
        try:
            return ResearchCheckpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[checkpoint] load failed: {e}")
    return None


def save_checkpoint(cp: ResearchCheckpoint) -> bool:
    """持久化断点到磁盘"""
    try:
        ws = _workspace(cp.research_id)
        ws.mkdir(parents=True, exist_ok=True)
        path = _checkpoint_path(cp.research_id)
        path.write_text(json.dumps(cp.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"[checkpoint] save failed: {e}")
        return False


def create_checkpoint(research_id: str, total_papers: int = 0) -> ResearchCheckpoint:
    """创建新断点并初始化所有流程步骤"""
    cp = ResearchCheckpoint(
        research_id=research_id,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        current_phase=ResearchPhase.PAPER_SCAN.value,
        total_papers=total_papers,
    )
    
    # 1. 论文分析步骤
    try:
        from core.seed_library import list_seed_papers
        seeds = list_seed_papers() or []
        for sp in seeds:
            arxiv_id = sp.get("arxiv_id")
            if arxiv_id:
                step_id = f"paper_{arxiv_id}"
                cp.steps[step_id] = StepRecord(
                    step_id=step_id,
                    phase=ResearchPhase.PAPER_SCAN.value,
                    status=StepStatus.PENDING.value,
                )
    except Exception as e:
        print(f"[WARNING] Failed to load seed papers for checkpoint initialization: {e}")
        
    # 2. 后续串行分析步骤
    cp.steps["perspective"] = StepRecord(
        step_id="perspective",
        phase=ResearchPhase.PERSPECTIVE.value,
        status=StepStatus.PENDING.value,
    )
    cp.steps["outline"] = StepRecord(
        step_id="outline",
        phase=ResearchPhase.OUTLINE.value,
        status=StepStatus.PENDING.value,
    )
    cp.steps["literature_review"] = StepRecord(
        step_id="literature_review",
        phase=ResearchPhase.LITERATURE_REVIEW.value,
        status=StepStatus.PENDING.value,
    )
    cp.steps["paper_writing"] = StepRecord(
        step_id="paper_writing",
        phase=ResearchPhase.PAPER_WRITING.value,
        status=StepStatus.PENDING.value,
    )
    
    save_checkpoint(cp)
    return cp


# ============================================================================
# 3. 论文分析 — 单篇 + 批量，支持断点续
# ============================================================================

def analyze_paper(
    arxiv_id: str,
    research_id: str,
    max_chars: int = 6000,
    checkpoint: bool = True,
) -> Dict[str, Any]:
    """
    分析单篇论文，结果写入 paper_analysis/{arxiv_id}.md
    返回: {"status": "done"|"failed"|"skipped", "path": str, "error": str}
    """
    ws = _workspace(research_id)
    out_dir = ws / "paper_analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    step_id = f"paper_{arxiv_id}"
    out_path = str(out_dir / f"{arxiv_id}.md")

    # 断点检查：已分析过且有产出则跳过（除非想强制重跑）
    if checkpoint:
        cp = load_checkpoint(research_id)
        if cp:
            s = cp.steps.get(step_id)
            if s and s.status == StepStatus.DONE.value and s.output_path:
                # 验证文件MD5一致
                if os.path.exists(s.output_path):
                    try:
                        with open(s.output_path, 'rb') as f:
                            if hashlib.md5(f.read()).hexdigest() == s.output_md5:
                                return {"status": "already_done", "path": s.output_path}
                    except Exception:
                        pass

    # 获取论文文本
    text = get_paper_text(arxiv_id, max_chars=max_chars)
    if not text:
        _save_bug_report(research_id, step_id, "NO_TEXT",
                         f"无法获取 {arxiv_id} 的论文文本",
                         {"arxiv_id": arxiv_id})
        return {"status": "failed", "path": "", "error": "no text"}

    # 组装分析内容（结构化 Markdown）
    manifest = _load_manifest()
    papers = {p.get("arxiv_id"): p for p in manifest.get("seed_papers", [])}
    meta = papers.get(arxiv_id, {})

    lines = [
        f"# 论文分析: {meta.get('title', arxiv_id)}\n",
        f"**arXiv ID**: {arxiv_id}\n",
        f"**作者**: {meta.get('authors', '未知')}\n",
        f"**年份**: {meta.get('year', '?')}\n",
        f"**主题标签**: {', '.join(meta.get('key_topics', []))}\n",
        f"**分析时间**: {datetime.now().isoformat()}\n",
        "\n---\n\n",
        "## 核心贡献\n\n",
        _extract_contribution(text),
        "\n\n## 方法论\n\n",
        _extract_methodology(text),
        "\n\n## 实验与结果\n\n",
        _extract_experiments(text),
        "\n\n## 局限性\n\n",
        _extract_limitation(text),
        "\n\n## 与其他论文的关系\n\n",
        _extract_relations(text, list(papers.keys())),
        "\n\n## 原始文本预览（前2000字）\n\n",
        f"```\n{text[:2000]}\n```\n",
    ]

    content = "".join(lines)
    try:
        Path(out_path).write_text(content, encoding="utf-8")
        # 更新断点
        if checkpoint:
            cp = load_checkpoint(research_id)
            if cp:
                cp.mark_done(step_id, output_path=out_path)
                cp.analyzed_papers = len(cp.done_steps())
                save_checkpoint(cp)
        return {"status": "done", "path": out_path, "arxiv_id": arxiv_id}
    except Exception as e:
        _save_bug_report(research_id, step_id, "WRITE_ERROR",
                         f"写入 {out_path} 失败: {e}",
                         {"arxiv_id": arxiv_id, "error": str(e)})
        return {"status": "failed", "path": "", "error": str(e)}


def analyze_all_papers(
    research_id: str,
    callback: Optional[Callable] = None,
    max_workers: int = 5,
) -> Dict[str, Any]:
    """
    批量分析所有种子论文，支持断点续。
    callback(paper_idx, total, arxiv_id, status) 用于进度通知。
    """
    manifest = _load_manifest()
    papers = manifest.get("seed_papers", [])

    # 确保断点存在
    cp = load_checkpoint(research_id)
    if not cp:
        cp = create_checkpoint(research_id, total_papers=len(papers))

    results = []
    for i, paper in enumerate(papers):
        arxiv_id = paper.get("arxiv_id", "")
        if not arxiv_id:
            continue

        # 检查是否已全部完成
        step_id = f"paper_{arxiv_id}"
        if step_id in cp.steps and cp.steps[step_id].status == StepStatus.DONE.value:
            results.append({"arxiv_id": arxiv_id, "status": "already_done"})
            if callback:
                callback(i + 1, len(papers), arxiv_id, "already_done")
            continue

        # 标记开始
        cp.mark_running(step_id, ResearchPhase.PAPER_SCAN.value)
        save_checkpoint(cp)

        # 执行分析
        result = analyze_paper(arxiv_id, research_id, checkpoint=True)
        results.append(result)

        if callback:
            status = result.get("status", "unknown")
            callback(i + 1, len(papers), arxiv_id, status)

        # 每篇之间稍作延迟，防止 IO 过载
        time.sleep(0.2)

    return {
        "total": len(papers),
        "done": len([r for r in results if r["status"] == "done"]),
        "already_done": len([r for r in results if r["status"] == "already_done"]),
        "failed": len([r for r in results if r["status"] == "failed"]),
        "results": results,
    }


# ============================================================================
# 4. 降级机制 — Graceful Degradation
#    卡顿时：并发写论文 + 报告 Bug
# ============================================================================

def _save_bug_report(research_id: str, step_id: str, bug_type: str,
                     message: str, details: Dict) -> str:
    """保存 Bug 报告到 bug_reports/ 目录"""
    ws = _workspace(research_id)
    bug_dir = ws / "bug_reports"
    bug_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "id": f"{step_id}_{int(time.time())}",
        "research_id": research_id,
        "step_id": step_id,
        "bug_type": bug_type,
        "message": message,
        "details": details,
        "timestamp": datetime.now().isoformat(),
        "resolved": False,
    }

    path = bug_dir / f"{report['id']}.json"
    try:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[bug_report] write failed: {e}")

    # 同时更新 checkpoint 中的 bug_reports 列表
    cp = load_checkpoint(research_id)
    if cp:
        cp.bug_reports.append({
            "id": report["id"],
            "type": bug_type,
            "step_id": step_id,
            "message": message,
            "timestamp": report["timestamp"],
        })
        save_checkpoint(cp)

    return report["id"]


def writing_with_degradation(
    research_id: str,
    topic: str,
    available_analysis: List[str],  # 已有分析的 arxiv_id 列表
    failed_steps: List[str],        # 失败的步骤ID列表
) -> Dict[str, Any]:
    """
    降级写作模式：用已有分析继续写论文，同时报告卡顿的步骤。
    返回: {"status": "degraded", "path": str, "bug_reports": [...], "missing_papers": [...]}
    """
    cp = load_checkpoint(research_id)
    if not cp:
        return {"status": "error", "message": "no checkpoint"}

    # 标记论文写作已开始
    cp.paper_writing_started = True
    cp.paper_writing_phase = "degraded"
    save_checkpoint(cp)

    # 对每个失败的步骤生成 Bug 报告
    bug_ids = []
    for step_id in failed_steps:
        _save_bug_report(research_id, step_id, "ANALYSIS_STUCK",
                         f"步骤 {step_id} 卡顿或超时，跳过并继续写作",
                         {"step_id": step_id, "research_id": research_id})
        bug_ids.append(step_id)

    # 获取所有已有分析内容
    ws = _workspace(research_id)
    draft_dir = ws / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)

    # 读取已有分析
    paper_contents = {}
    analysis_dir = ws / "paper_analysis"
    if analysis_dir.exists():
        for f in analysis_dir.glob("*.md"):
            arxiv_id = f.stem
            try:
                paper_contents[arxiv_id] = f.read_text(encoding="utf-8")
            except Exception:
                pass

    # 生成降级版论文（明确标注缺失部分）
    missing = [s.replace("paper_", "") for s in failed_steps if s.startswith("paper_")]

    content = _build_paper_content(topic, paper_contents, missing_papers=missing)

    out_path = str(draft_dir / "introduction_degraded.md")
    Path(out_path).write_text(content, encoding="utf-8")

    return {
        "status": "degraded",
        "path": out_path,
        "bug_reports": bug_ids,
        "missing_papers": missing,
        "available_papers": list(paper_contents.keys()),
    }


# ============================================================================
# 5. 断点续分析 — Resume
# ============================================================================

def resume_research(
    research_id: str,
    callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    从上次中断处继续研究流程。
    1. 读取 checkpoint
    2. 找出 pending/failed 步骤
    3. 按阶段顺序继续执行
    4. 生成增量 MD（只更新变化的部分）
    """
    cp = load_checkpoint(research_id)
    if not cp:
        return {"status": "error", "message": "no checkpoint found, use create_research first"}

    pending = cp.pending_steps()
    done = cp.done_steps()

    if not pending:
        return {
            "status": "already_complete",
            "research_id": research_id,
            "done_steps": done,
            "message": "所有步骤已完成",
        }

    results = {"resumed": [], "failed": [], "skipped": []}

    # 按阶段顺序处理 pending 步骤
    for step_id in pending:
        phase = cp.steps[step_id].phase
        cp.current_phase = phase
        save_checkpoint(cp)

        if phase == ResearchPhase.PAPER_SCAN.value and step_id.startswith("paper_"):
            arxiv_id = step_id.replace("paper_", "")
            cp.mark_running(step_id, phase)
            save_checkpoint(cp)

            result = analyze_paper(arxiv_id, research_id, checkpoint=True)
            if result["status"] == "done":
                results["resumed"].append(result)
            else:
                results["failed"].append(result)
                # 降级：继续写作
                _save_bug_report(research_id, step_id, "RESUME_FAILED",
                                 f"重试失败: {result.get('error', 'unknown')}",
                                 result)

            if callback:
                callback(step_id, result["status"])

        elif phase == ResearchPhase.PERSPECTIVE.value:
            # 视角分析（需要所有论文分析完成后）
            all_papers_done = all(
                cp.steps.get(f"paper_{aid}", StepRecord(step_id="", phase="", status="")).status == StepStatus.DONE.value
                for aid in _get_all_arxiv_ids()
            )
            if not all_papers_done:
                cp.mark_skipped(step_id, "waiting_for_papers")
                results["skipped"].append(step_id)
                continue

            perspective_analysis = run_perspective_analysis(research_id, checkpoint=True)
            cp.mark_done(step_id, output_path=str(ws / "perspective_analysis"))
            results["resumed"].append(perspective_analysis)
            save_checkpoint(cp)

        elif phase == ResearchPhase.OUTLINE.value:
            outline = generate_outline(research_id, checkpoint=True)
            cp.mark_done("outline", output_path=outline.get("path", ""))
            results["resumed"].append(outline)
            save_checkpoint(cp)

    # 生成增量报告 MD
    incremental_md = _generate_incremental_md(research_id, cp, results)

    return {
        "status": "resumed",
        "research_id": research_id,
        "pending_before": len(pending),
        "resumed_count": len(results["resumed"]),
        "failed_count": len(results["failed"]),
        "incremental_md": incremental_md,
        "done_steps": cp.done_steps(),
        "remaining_steps": cp.pending_steps(),
    }


def _generate_incremental_md(research_id: str, cp: ResearchCheckpoint,
                              results: Dict) -> str:
    """生成增量分析报告 MD"""
    lines = [
        f"# 增量分析报告 — {research_id}\n",
        f"生成时间: {datetime.now().isoformat()}\n\n",
        f"## 断点摘要\n",
        f"- 总步骤: {len(cp.steps)}\n",
        f"- 已完成: {len(cp.done_steps())}\n",
        f"- 待处理: {len(cp.pending_steps())}\n",
        f"- 错误数: {cp.error_count}\n\n",
        f"## 本次恢复结果\n",
    ]

    if results["resumed"]:
        lines.append("\n### ✅ 成功恢复\n")
        for r in results["resumed"]:
            lines.append(f"- `{r.get('arxiv_id', r.get('step_id', 'unknown'))}`: done\n")

    if results["failed"]:
        lines.append("\n### ❌ 失败（已降级）\n")
        for r in results["failed"]:
            lines.append(f"- `{r.get('arxiv_id', r.get('step_id', 'unknown'))}`: {r.get('error', 'failed')}\n")

    if results["skipped"]:
        lines.append("\n### ⏭️ 跳过（等待前置条件）\n")
        for s in results["skipped"]:
            lines.append(f"- `{s}`\n")

    # 添加 Bug 报告摘要
    if cp.bug_reports:
        lines.append("\n## Bug 报告摘要\n")
        for b in cp.bug_reports[-10:]:  # 最近10条
            lines.append(f"- [{b['type']}] {b['message']} ({b['timestamp'][:19]})\n")

    # 添加剩余待处理论文列表
    pending_papers = [s.replace("paper_", "")
                     for s in cp.pending_steps() if s.startswith("paper_")]
    if pending_papers:
        lines.append("\n## 仍需分析的论文\n")
        for pid in pending_papers:
            lines.append(f"- `{pid}`\n")

    content = "".join(lines)
    ws = _workspace(research_id)
    out = ws / "incremental_report.md"
    try:
        out.write_text(content, encoding="utf-8")
    except Exception:
        pass
    return content


# ============================================================================
# 6. 作者/引用关系网络
# ============================================================================

def build_author_network(research_id: str) -> Dict[str, Any]:
    """
    构建作者-论文-引用关系网络。
    从 manifest 和 combined_summaries 提取：
    - 每篇论文的作者
    - 论文间引用关系（从PDF文本提取）
    - 同一作者的其他发表（第二轮发现）
    """
    ws = _workspace(research_id)
    net_dir = ws / "author_network"
    net_dir.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest()
    papers = manifest.get("seed_papers", [])

    # 构建作者 → 论文 映射
    author_to_papers: Dict[str, List] = {}
    paper_authors: Dict[str, List] = {}

    for paper in papers:
        arxiv_id = paper.get("arxiv_id", "")
        authors_raw = paper.get("authors", "")
        # 解析作者列表（逗号分隔）
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
        paper_authors[arxiv_id] = authors

        for author in authors:
            if author not in author_to_papers:
                author_to_papers[author] = []
            author_to_papers[author].append({
                "arxiv_id": arxiv_id,
                "title": paper.get("title", "")[:60],
                "year": paper.get("year", ""),
                "key_topics": paper.get("key_topics", []),
            })

    # 跨论文关系（共同作者、主题相似）
    collaborations = []
    for author, pap_list in author_to_papers.items():
        if len(pap_list) > 1:
            collaborations.append({
                "author": author,
                "paper_count": len(pap_list),
                "papers": pap_list,
            })

    # 主题相似论文群（基于 key_topics）
    topic_network = _build_topic_network(papers)

    # 保存网络图
    graph = {
        "research_id": research_id,
        "generated_at": datetime.now().isoformat(),
        "author_count": len(author_to_papers),
        "paper_count": len(papers),
        "author_to_papers": author_to_papers,
        "collaborations": collaborations,  # 多篇论文的作者
        "topic_network": topic_network,
    }

    graph_path = net_dir / "author_graph.json"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成可视化的 Markdown 关系图
    md_lines = [
        f"# 作者-论文关系网络 — {research_id}\n",
        f"生成时间: {datetime.now().isoformat()}\n\n",
        f"## 统计\n\n",
        f"- 作者总数: {len(author_to_papers)}\n",
        f"- 论文总数: {len(papers)}\n",
        f"- 多篇论文作者（核心合作者）: {len(collaborations)}\n\n",
        f"## 核心合作者（按论文数量排序）\n\n",
    ]

    for c in sorted(collaborations, key=lambda x: -x["paper_count"])[:15]:
        md_lines.append(f"### {c['author']} ({c['paper_count']} 篇)\n")
        for p in c["papers"]:
            md_lines.append(f"- [{p['arxiv_id']}] {p['title']} ({p['year']})\n")

    if topic_network:
        md_lines.append("\n## 主题聚类\n\n")
        for topic, paper_list in sorted(topic_network.items(), key=lambda x: -len(x[1]))[:10]:
            md_lines.append(f"### {topic} ({len(paper_list)} 篇)\n")
            for p in paper_list:
                md_lines.append(f"- [{p['arxiv_id']}] {p['title'][:60]}\n")

    md_path = net_dir / "author_network.md"
    md_path.write_text("".join(md_lines), encoding="utf-8")

    return {
        "status": "done",
        "graph_path": str(graph_path),
        "md_path": str(md_path),
        "author_count": len(author_to_papers),
        "collaboration_count": len(collaborations),
    }


def _build_topic_network(papers: List[Dict]) -> Dict[str, List]:
    """按主题聚合论文"""
    network: Dict[str, List] = {}
    for paper in papers:
        for topic in paper.get("key_topics", []):
            if topic not in network:
                network[topic] = []
            network[topic].append({
                "arxiv_id": paper.get("arxiv_id", ""),
                "title": paper.get("title", "")[:60],
            })
    return network


# ============================================================================
# 7. 多论文比对分析
# ============================================================================

def compare_papers(
    research_id: str,
    arxiv_ids: List[str],
    comparison_type: str = "full",
) -> Dict[str, Any]:
    """
    对指定论文列表进行深度比对分析。
    comparison_type: "full" | "methods" | "results" | "authors"
    """
    ws = _workspace(research_id)
    comp_dir = ws / "comparisons"
    comp_dir.mkdir(parents=True, exist_ok=True)

    # 读取各论文分析结果
    analysis_dir = ws / "paper_analysis"
    contents = {}
    for aid in arxiv_ids:
        path = analysis_dir / f"{aid}.md"
        if path.exists():
            contents[aid] = path.read_text(encoding="utf-8")
        else:
            # 从 PDF 重新提取
            text = get_paper_text(aid, max_chars=8000)
            if text:
                contents[aid] = f"# {aid}\n\n{text[:2000]}"

    if not contents:
        return {"status": "error", "message": "no paper content available"}

    # 生成比对报告
    lines = [
        f"# 多论文比对分析\n",
        f"论文数: {len(arxiv_ids)}\n",
        f"比对类型: {comparison_type}\n",
        f"时间: {datetime.now().isoformat()}\n\n",
        "## 被比论文\n\n",
    ]
    for aid in arxiv_ids:
        lines.append(f"- `{aid}`\n")

    lines.append("\n---\n\n")

    if comparison_type in ("full", "methods"):
        lines.append("## 方法论对比\n\n")
        for aid, content in contents.items():
            lines.append(f"### {aid}\n")
            # 提取方法论部分
            method_section = _extract_section(content, "方法论", "实验与结果")
            lines.append(f"{method_section or '(未找到方法论部分)'}\n\n")

    if comparison_type in ("full", "results"):
        lines.append("## 结果对比\n\n")
        for aid, content in contents.items():
            lines.append(f"### {aid}\n")
            results_section = _extract_section(content, "实验与结果", "局限性")
            lines.append(f"{results_section or '(未找到结果部分)'}\n\n")

    if comparison_type in ("full", "authors"):
        lines.append("## 作者网络\n\n")
        manifest = _load_manifest()
        papers_map = {p.get("arxiv_id"): p for p in manifest.get("seed_papers", [])}
        for aid in arxiv_ids:
            meta = papers_map.get(aid, {})
            lines.append(f"### {aid}: {meta.get('authors', '未知')}\n")

    out_path = comp_dir / f"compare_{comparison_type}_{int(time.time())}.md"
    out_path.write_text("".join(lines), encoding="utf-8")

    return {
        "status": "done",
        "path": str(out_path),
        "papers_count": len(arxiv_ids),
        "comparison_type": comparison_type,
    }


# ============================================================================
# 8. 辅助函数
# ============================================================================

def _extract_contribution(text: str) -> str:
    """从论文文本提取核心贡献"""
    # 简单启发式：找 Abstract / Introduction 中的关键句
    lines = text.split("\n")
    result = []
    capture = False
    for line in lines:
        if "contribution" in line.lower() or "we propose" in line.lower() or "we introduce" in line.lower():
            capture = True
        if capture and len(result) < 5:
            if line.strip():
                result.append(line.strip())
        if len(result) >= 5:
            break
    return "\n".join(result) if result else "（从文本中未提取到明确贡献声明）"


def _extract_methodology(text: str) -> str:
    """提取方法论"""
    section = _extract_section(text, "方法", "实验")
    return section if section else text[500:1500] if len(text) > 1500 else text


def _extract_experiments(text: str) -> str:
    """提取实验结果"""
    section = _extract_section(text, "实验", "结论")
    return section if section else text[2000:4000] if len(text) > 4000 else ""


def _extract_limitation(text: str) -> str:
    """提取局限性"""
    section = _extract_section(text, "局限", "参考")
    return section if section else "（未明确说明局限性）"


def _extract_relations(text: str, all_arxiv_ids: List[str]) -> str:
    """提取论文间关系（引用其他种子论文）"""
    relations = []
    for aid in all_arxiv_ids:
        if aid in text:
            relations.append(f"- 引用了 `{aid}`")
    return "\n".join(relations) if relations else "（未发现对种子论文库中其他论文的直接引用）"


def _extract_section(text: str, start_kw: str, end_kw: str) -> str:
    """提取两个关键词之间的文本段落"""
    try:
        start_idx = text.lower().index(start_kw.lower())
        end_idx = text.lower().index(end_kw.lower(), start_idx + len(start_kw))
        return text[start_idx:end_idx].strip()[:1000]
    except ValueError:
        return ""


def _get_all_arxiv_ids() -> List[str]:
    manifest = _load_manifest()
    return [p.get("arxiv_id", "") for p in manifest.get("seed_papers", []) if p.get("arxiv_id")]


def _build_paper_content(topic: str, paper_contents: Dict[str, str],
                          missing_papers: List[str] = None) -> str:
    """构建论文内容（用于降级写作模式）"""
    lines = [
        f"# 研究主题: {topic}\n\n",
        f"> ⚠️ **降级模式**: 以下内容基于 {len(paper_contents)} 篇已有分析生成，"
        f"缺失 {len(missing_papers or [])} 篇论文分析。\n\n",
        "## 研究背景\n\n",
        "基于现有论文分析，整理研究背景如下：\n\n",
    ]

    for arxiv_id, content in paper_contents.items():
        lines.append(f"### {arxiv_id}\n")
        contrib = _extract_section(content, "## 核心贡献", "## 方法论")
        lines.append(f"{contrib or '(无核心贡献信息)'}\n\n")

    if missing_papers:
        lines.append("\n## ⚠️ 缺失论文\n\n")
        for m in missing_papers:
            lines.append(f"- `{m}` — 分析失败，需重试\n")

    lines.append("\n## 初步结论\n\n")
    lines.append("（基于已有分析得出初步结论，完整结论待补充所有论文分析后更新）\n")

    return "".join(lines)


def generate_outline(research_id: str, checkpoint: bool = True) -> Dict[str, Any]:
    """生成论文大纲（依赖所有论文分析完成）"""
    ws = _workspace(research_id)
    outline_path = ws / "outline.md"
    outline_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest()
    papers = manifest.get("seed_papers", [])

    # 收集所有分析内容
    analysis_dir = ws / "paper_analysis"
    analyses = {}
    if analysis_dir.exists():
        for f in analysis_dir.glob("*.md"):
            analyses[f.stem] = f.read_text(encoding="utf-8")

    # 生成大纲
    topics_by_paper = {}
    for paper in papers:
        aid = paper.get("arxiv_id", "")
        topics_by_paper[aid] = paper.get("key_topics", [])

    lines = [
        f"# 论文大纲 — {research_id}\n\n",
        f"生成时间: {datetime.now().isoformat()}\n",
        f"基于 {len(analyses)} 篇论文分析\n\n",
        "## 1. Introduction\n",
        "- 研究背景与动机\n",
        "- 主要贡献（3-5条）\n",
        "- 论文结构\n\n",
        "## 2. Related Work\n",
        "- LLM在金融领域的应用\n",
        "- 多智能体量化交易系统\n",
        "- 现有方法的局限性\n\n",
        "## 3. Methodology\n",
        "- 系统架构\n",
        "- 核心算法\n",
        "- 关键设计决策\n\n",
        "## 4. Experiments\n",
        "- 数据集描述\n",
        "- 基线方法\n",
        "- 实验设置\n",
        "- 结果分析\n\n",
        "## 5. Conclusion & Future Work\n\n",
        "## 参考文献\n\n",
    ]

    content = "".join(lines)
    outline_path.write_text(content, encoding="utf-8")

    if checkpoint:
        cp = load_checkpoint(research_id)
        if cp:
            cp.mark_done("outline", output_path=str(outline_path))
            save_checkpoint(cp)

    return {"status": "done", "path": str(outline_path), "steps": len(analyses)}


def run_perspective_analysis(research_id: str, checkpoint: bool = True) -> Dict[str, Any]:
    """多视角分析（STORM启发）：从不同角度分析论文"""
    perspectives = [
        ("technical", "技术实现视角"),
        ("application", "应用场景视角"),
        ("evaluation", "评估方法视角"),
        ("limitation", "局限性视角"),
    ]

    ws = _workspace(research_id)
    pers_dir = ws / "perspective_analysis"
    pers_dir.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest()
    papers = {p.get("arxiv_id"): p for p in manifest.get("seed_papers", [])}

    results = []
    for name, label in perspectives:
        path = pers_dir / f"{name}.md"
        lines = [f"# {label}\n\n"]
        lines.append(f"**视角**: {name}\n\n")

        for aid, meta in list(papers.items())[:10]:  # 最多10篇
            text = get_paper_text(aid, max_chars=3000)
            if text:
                lines.append(f"## {aid}: {meta.get('title', '')[:50]}\n")
                lines.append(f"{text[200:800]}\n\n")

        content = "".join(lines)
        path.write_text(content, encoding="utf-8")
        results.append({"name": name, "label": label, "path": str(path)})

    return {"status": "done", "perspectives": results}


# ============================================================================
# 9. 端到端研究流程
# ============================================================================

def run_full_research(
    research_id: str,
    topic: str = "",
    options: Optional[Dict] = None,
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    端到端研究流程（支持断点续）：
    1. 创建/加载 checkpoint
    2. 分析所有论文
    3. 多视角分析
    4. 生成大纲
    5. 文献综述
    6. 论文写作（可并发）

    任何一个论文分析卡顿时，自动降级继续写作。
    """
    opts = options or {}
    ws = _workspace(research_id)

    # Step 1: 创建或加载 checkpoint
    cp = load_checkpoint(research_id)
    if not cp:
        manifest = _load_manifest()
        cp = create_checkpoint(research_id, total_papers=len(manifest.get("seed_papers", [])))

    status = {"research_id": research_id, "phases": {}, "errors": []}

    # Step 2: 分析论文（断点续）
    paper_results = analyze_all_papers(research_id, callback=progress_callback)
    status["phases"]["paper_scan"] = paper_results

    # Step 3: 若有失败，降级写作（不等待重试）
    failed_papers = [r["arxiv_id"] for r in paper_results.get("results", [])
                     if r["status"] == "failed"]
    if failed_papers and opts.get("auto_degrade", True):
        status["degraded"] = True
        status["degraded_write"] = writing_with_degradation(
            research_id, topic or "LLM金融应用研究",
            [r["arxiv_id"] for r in paper_results.get("results", [])
             if r["status"] == "done"],
            [f"paper_{a}" for a in failed_papers],
        )

    # Step 4: 视角分析（并行）
    perspective_results = run_perspective_analysis(research_id, checkpoint=True)
    status["phases"]["perspective"] = perspective_results

    # Step 5: 生成大纲
    outline_results = generate_outline(research_id, checkpoint=True)
    status["phases"]["outline"] = outline_results

    # Step 6: 作者网络
    network_results = build_author_network(research_id)
    status["phases"]["author_network"] = network_results

    # Step 7: 更新 checkpoint
    cp = load_checkpoint(research_id)
    if cp:
        cp.paper_writing_phase = "completed"
        save_checkpoint(cp)

    status["status"] = "completed"
    status["workspace"] = str(ws)
    return status
