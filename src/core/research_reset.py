"""
研究重置 — 从 0 开始前备份现有数据，避免误删种子文献。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from core.data_registry import (
    BACKUP_DIR,
    BRANCHES_FILE,
    DATA_DIR,
    PAPERS_STATE_FILE,
    RESEARCH_DIR,
    WORKFLOW_STATE_FILE,
    PROJECT_ROOT,
)

RESEARCH_LOGS = DATA_DIR / "research_logs.json"
GRADING_HISTORY = DATA_DIR / "grading_history.json"


def _empty_papers_state() -> dict:
    return {
        "papers": [],
        "current_paper_id": None,
        "next_research_seq": 1,
        "generation_queue": [],
        "is_generating": False,
        "is_paused": False,
        "hypotheses": [],
        "experiments": [],
        "research_activity": {"phase": "idle", "message": "等待开始", "progress": 0},
        "settings": {"auto_continue": True, "pause_after_next": False},
    }


def _empty_workflow_state() -> dict:
    return {
        "version": "2.0",
        "project_name": "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
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


def reset_research(*, keep_seed_papers: bool = True, keep_workflow: bool = False) -> Dict[str, Any]:
    """
    从 0 开始：备份后清空论文与研究档案，默认保留 seed_papers。
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = BACKUP_DIR / ts
    backup_root.mkdir(parents=True, exist_ok=True)

    backed_up: List[str] = []

    def backup_path(src: Path, rel: str) -> None:
        if not src.exists():
            return
        dest = backup_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)
        backed_up.append(rel)

    # 备份研究档案 RS-* 目录
    if RESEARCH_DIR.exists():
        for item in RESEARCH_DIR.iterdir():
            if item.name.startswith("RS-"):
                backup_path(item, f"research/{item.name}")

    for rel_path in [
        "papers_state.json",
        "research_state.json",
        "research_branches.json",
        "research_logs.json",
        "grading_history.json",
    ]:
        backup_path(DATA_DIR / rel_path, rel_path)

    # 删除 RS-* 研究档案
    removed_archives = []
    if RESEARCH_DIR.exists():
        for item in RESEARCH_DIR.iterdir():
            if item.is_dir() and item.name.startswith("RS-"):
                shutil.rmtree(item)
                removed_archives.append(item.name)

    # 重置状态文件
    PAPERS_STATE_FILE.write_text(
        json.dumps(_empty_papers_state(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if not keep_workflow:
        WORKFLOW_STATE_FILE.write_text(
            json.dumps(_empty_workflow_state(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    BRANCHES_FILE.write_text(
        json.dumps({"branches": [], "current_branch_id": None}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    RESEARCH_LOGS.write_text("[]", encoding="utf-8")
    if GRADING_HISTORY.exists():
        GRADING_HISTORY.write_text("[]", encoding="utf-8")

    return {
        "success": True,
        "backup_dir": str(backup_root),
        "backed_up": backed_up,
        "removed_archives": removed_archives,
        "kept_seed_papers": keep_seed_papers,
        "kept_workflow": keep_workflow,
        "message": f"已重置；备份位于 data/bac/{ts}/",
    }
