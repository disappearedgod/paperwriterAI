#!/usr/bin/env python3
"""
将 WorkBuddy 历史研究与现有 paper 记录迁移到统一研究档案目录。

用法:
  python3 scripts/migrate_workbuddy_history.py
  python3 scripts/migrate_workbuddy_history.py --workbuddy /path/to/WorkBuddy/2026-06-20-12-11-53/fars_system
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core.research_archive import (  # noqa: E402
    RESEARCH_DIR,
    allocate_research_id,
    bump_research_seq,
    create_research_workspace,
    import_legacy_project,
    paper_record_paths,
)

STATE_FILE = PROJECT_ROOT / "data" / "research_state.json"
BRANCHES_FILE = PROJECT_ROOT / "data" / "research_branches.json"
WORKSPACE_PROJECTS = PROJECT_ROOT / "workspace" / "projects"

DEFAULT_WORKBUDDY = Path("/Users/derek/WorkBuddy/2026-06-20-12-11-53/fars_system")


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_title_from_md(path: Path) -> str:
    if not path.exists():
        return path.stem
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def migrate_existing_papers(state: dict) -> int:
    """为 research_state 中尚无 research_id 的论文建立档案。"""
    count = 0
    state.setdefault("next_research_seq", 1)

    for paper in state.get("papers", []):
        if paper.get("research_id"):
            continue

        research_id = allocate_research_id(state)
        workspace = create_research_workspace(
            research_id=research_id,
            paper_id=paper["id"],
            branch_id=paper.get("branch_id", 1),
            title=paper.get("title") or paper.get("topic", "未命名"),
            topic=paper.get("topic", ""),
            content=paper.get("content", ""),
            status=paper.get("status", "generated"),
        )
        bump_research_seq(state)
        paper.update(paper_record_paths(workspace))
        count += 1
        print(f"  [migrate] paper #{paper['id']} -> {research_id}")

    return count


def add_imported_paper(
    state: dict,
    *,
    title: str,
    topic: str,
    branch_id: int = 1,
    status: str = "imported",
    workspace: dict,
    content: str = "",
) -> dict:
    paper_id = len(state.get("papers", [])) + 1
    record = {
        "id": paper_id,
        "research_id": workspace["research_id"],
        "branch_id": branch_id,
        "topic": topic,
        "title": title,
        "content": content,
        "status": status,
        "quality_score": None,
        "iteration_count": 0,
        "created_at": datetime.now().isoformat(),
        "parent_paper_id": None,
        **paper_record_paths(workspace),
    }
    state.setdefault("papers", []).append(record)
    state["current_paper_id"] = paper_id
    bump_research_seq(state)
    return record


def import_historical_projects(state: dict, workbuddy_root: Path) -> int:
    """导入 WorkBuddy / workspace 中有实质内容的项目。"""
    count = 0

    imports = [
        {
            "project": "proj_20260620_131657_ed54dda9",
            "title": "LLM Multi-Agent Quantitative Investment Framework",
            "topic": "Automate Strategy Finding with LLM in Quant Investment",
        },
        {
            "project": "proj_20260620_130630_6f4f3667",
            "title": "Transformer-Based Momentum Strategies in Quantitative Trading",
            "topic": "Transformer momentum strategies for quantitative trading",
        },
    ]

    existing_legacy = set()
    for p in state.get("papers", []):
        if p.get("research_dir"):
            existing_legacy.add(Path(p["research_dir"]).name.split("_")[0])

    for spec in imports:
        proj_name = spec["project"]
        proj_dir = WORKSPACE_PROJECTS / proj_name
        if not proj_dir.exists():
            wb_proj = workbuddy_root / "workspace" / "projects" / proj_name
            if wb_proj.exists():
                proj_dir = wb_proj
            else:
                print(f"  [warn] project not found: {proj_name}")
                continue

        research_id = allocate_research_id(state)
        if research_id in existing_legacy:
            print(f"  [skip] {proj_name}")
            continue

        workspace = import_legacy_project(
            research_id=research_id,
            paper_id=len(state.get("papers", [])) + 1,
            branch_id=1,
            title=spec["title"],
            topic=spec["topic"],
            project_dir=proj_dir,
        )
        content = f"# {spec['title']}\n\n> 完整 LaTeX 见研究档案 article 目录\n"

        add_imported_paper(
            state,
            title=spec["title"],
            topic=spec["topic"],
            workspace=workspace,
            content=content,
        )
        count += 1
        print(f"  [import] {proj_name} -> {research_id}")

    md_sources = [
        workbuddy_root / "outputs" / "generated_paper.md",
        PROJECT_ROOT / "outputs" / "generated_paper.md",
    ]
    md_src = next((p for p in md_sources if p.exists()), None)
    if md_src:
        title = extract_title_from_md(md_src)
        already = any(p.get("title") == title for p in state.get("papers", []))
        if not already:
            research_id = allocate_research_id(state)
            content = md_src.read_text(encoding="utf-8", errors="replace")
            workspace = create_research_workspace(
                research_id=research_id,
                paper_id=len(state.get("papers", [])) + 1,
                branch_id=1,
                title=title,
                topic=title,
                content=content,
                status="imported",
                scaffold=True,
            )
            add_imported_paper(
                state,
                title=title,
                topic=title,
                workspace=workspace,
                content=content,
            )
            count += 1
            print(f"  [import] generated_paper.md -> {research_id}")

    return count


def update_branches(state: dict) -> None:
    branches = load_json(BRANCHES_FILE)
    paper_ids = [p["id"] for p in state.get("papers", [])]
    for branch in branches.get("branches", []):
        branch["paper_ids"] = paper_ids
        branch["iterations_count"] = len(paper_ids)
    save_json(BRANCHES_FILE, branches)


def main() -> None:
    parser = argparse.ArgumentParser(description="迁移 WorkBuddy 历史到研究档案")
    parser.add_argument("--workbuddy", type=Path, default=DEFAULT_WORKBUDDY)
    args = parser.parse_args()

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    state = load_json(STATE_FILE)
    state.setdefault("papers", [])
    state.setdefault("next_research_seq", 1)

    print("=== 迁移现有论文记录 ===")
    n1 = migrate_existing_papers(state)

    print("=== 导入 WorkBuddy 历史项目 ===")
    n2 = import_historical_projects(state, args.workbuddy)

    update_branches(state)
    save_json(STATE_FILE, state)

    manifest = {
        "migrated_at": datetime.now().isoformat(),
        "existing_migrated": n1,
        "historical_imported": n2,
        "papers": [
            {
                "id": p["id"],
                "research_id": p.get("research_id"),
                "title": p.get("title"),
                "research_dir": p.get("research_dir"),
            }
            for p in state.get("papers", [])
        ],
    }
    manifest_path = RESEARCH_DIR / "migration_manifest.json"
    save_json(manifest_path, manifest)

    print(f"\n完成: 迁移 {n1} 篇, 新导入 {n2} 篇")
    print(f"清单: {manifest_path}")


if __name__ == "__main__":
    main()
