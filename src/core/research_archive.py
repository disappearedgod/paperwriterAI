"""
研究档案管理 — 每篇论文独立目录，统一研究编号与命名规范。

目录结构:
  data/research/{research_id}_{slug}/
    meta.json
    article/{research_id}_paper.md
    data/{research_id}_experiment_data.json
    data/{research_id}_indicator_sample.json
    metrics/{research_id}_backtest_results.json
    code/{research_id}_experiment.py
    logs/
    ideas/
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RESEARCH_DIR = PROJECT_ROOT / "data" / "research"
EXPERIMENT_TEMPLATE = PROJECT_ROOT / "scripts" / "real_experiment_v2.py"

SUBDIRS = ("article", "data", "metrics", "code", "logs", "ideas")


def slugify_title(title: str, max_len: int = 40) -> str:
    """将标题转为目录安全的 slug（保留英文与数字）。"""
    if not title:
        return "untitled"
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", title.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    # 优先保留 ASCII 片段作为目录名
    ascii_parts = re.findall(r"[A-Za-z0-9]+", title)
    if ascii_parts:
        slug = "_".join(ascii_parts)[:max_len]
    else:
        slug = slug[:max_len]
    return slug or "untitled"


def allocate_research_id(papers_data: Optional[dict] = None, created_at: Optional[datetime] = None) -> str:
    """分配全局唯一研究编号 RS-YYYYMMDD-NNN。"""
    when = created_at or datetime.now()
    date_part = when.strftime("%Y%m%d")

    seq = 1
    if papers_data:
        seq = int(papers_data.get("next_research_seq", 1))
        existing_ids = {p.get("research_id") for p in papers_data.get("papers", []) if p.get("research_id")}
        while f"RS-{date_part}-{seq:03d}" in existing_ids:
            seq += 1

    return f"RS-{date_part}-{seq:03d}"


def bump_research_seq(papers_data: dict) -> None:
    papers_data["next_research_seq"] = int(papers_data.get("next_research_seq", 1)) + 1


def research_folder_name(research_id: str, title: str) -> str:
    return f"{research_id}_{slugify_title(title)}"


def research_root(research_id: str, title: str) -> Path:
    return RESEARCH_DIR / research_folder_name(research_id, title)


def artifact_filenames(research_id: str) -> Dict[str, str]:
    return {
        "article_md": f"{research_id}_paper.md",
        "article_tex": f"{research_id}_paper.tex",
        "experiment_data": f"{research_id}_experiment_data.json",
        "indicator_sample": f"{research_id}_indicator_sample.json",
        "backtest_results": f"{research_id}_backtest_results.json",
        "experiment_code": f"{research_id}_experiment.py",
    }


def ensure_research_layout(root: Path) -> Dict[str, Path]:
    """创建研究目录骨架，返回各子目录路径。"""
    root.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, Path] = {"root": root}
    for name in SUBDIRS:
        sub = root / name
        sub.mkdir(exist_ok=True)
        paths[name] = sub
    return paths


def write_meta(
    root: Path,
    *,
    research_id: str,
    paper_id: int,
    branch_id: int,
    title: str,
    topic: str,
    status: str = "generated",
    parent_research_id: Optional[str] = None,
    legacy_project_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Path:
    meta = {
        "research_id": research_id,
        "paper_id": paper_id,
        "branch_id": branch_id,
        "title": title,
        "topic": topic,
        "status": status,
        "parent_research_id": parent_research_id,
        "legacy_project_id": legacy_project_id,
        "created_at": datetime.now().isoformat(),
        "artifacts": build_artifacts_record(root, research_id),
    }
    if extra:
        meta.update(extra)
    meta_path = root / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path


def build_artifacts_record(root: Path, research_id: str) -> Dict[str, str]:
    """构建相对项目根路径的 artifacts 映射（供 API / 前端使用）。"""
    names = artifact_filenames(research_id)
    mapping = {
        "markdown": str(root / "article" / names["article_md"]),
        "latex": str(root / "article" / names["article_tex"]),
        "experiment_data": str(root / "data" / names["experiment_data"]),
        "indicator_sample": str(root / "data" / names["indicator_sample"]),
        "backtest_results": str(root / "metrics" / names["backtest_results"]),
        "code": str(root / "code" / names["experiment_code"]),
    }
    # 仅返回已存在的文件
    return {k: v for k, v in mapping.items() if Path(v).exists()}


def artifacts_for_api(root: Path, research_id: str) -> Dict[str, str]:
    """返回供前端下载的 URL 路径（相对于站点根）。"""
    record = build_artifacts_record(root, research_id)
    api_paths = {}
    for key, abs_path in record.items():
        try:
            rel = Path(abs_path).relative_to(PROJECT_ROOT)
            api_paths[key] = f"/research_files/{rel.as_posix()}"
        except ValueError:
            api_paths[key] = abs_path
    return api_paths


def save_article_markdown(root: Path, research_id: str, content: str) -> Path:
    names = artifact_filenames(research_id)
    path = root / "article" / names["article_md"]
    path.write_text(content, encoding="utf-8")
    return path


def save_article_tex(root: Path, research_id: str, content: str) -> Path:
    names = artifact_filenames(research_id)
    path = root / "article" / names["article_tex"]
    path.write_text(content, encoding="utf-8")
    return path


def scaffold_placeholder_data(root: Path, research_id: str, title: str, topic: str) -> None:
    """为新论文创建带研究编号命名的占位数据/指标文件。"""
    names = artifact_filenames(research_id)
    experiment_data = {
        "research_id": research_id,
        "title": title,
        "topic": topic,
        "status": "pending",
        "note": "实验数据待运行 code 目录下实验脚本后生成",
        "created_at": datetime.now().isoformat(),
    }
    indicator_sample = {
        "research_id": research_id,
        "title": title,
        "sample": [],
    }
    backtest_results = {
        "research_id": research_id,
        "title": title,
        "status": "pending",
        "strategies": {},
        "benchmark": {},
    }
    (root / "data" / names["experiment_data"]).write_text(
        json.dumps(experiment_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "data" / names["indicator_sample"]).write_text(
        json.dumps(indicator_sample, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "metrics" / names["backtest_results"]).write_text(
        json.dumps(backtest_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def scaffold_experiment_code(root: Path, research_id: str, title: str, topic: str) -> Path:
    """基于模板生成以研究编号命名的实验代码。"""
    from core.data_registry import get_mongodb_config, SEED_PAPERS_DIR, RESEARCH_DIR

    names = artifact_filenames(research_id)
    dest = root / "code" / names["experiment_code"]
    mongo = get_mongodb_config()
    header = (
        f'"""\n'
        f"研究编号: {research_id}\n"
        f"论文标题: {title}\n"
        f"研究主题: {topic}\n"
        f"\n"
        f"数据位置:\n"
        f"  - MongoDB: {mongo['uri']} / {mongo['db']} / {mongo['collection_daily_bars']}\n"
        f"  - 种子文献: {SEED_PAPERS_DIR}\n"
        f"  - 本研究档案: {root}\n"
        f'"""\n\n'
        f"MONGO_URI = {mongo['uri']!r}\n"
        f"MONGO_DB = {mongo['db']!r}\n"
        f"MONGO_COLLECTION = {mongo['collection_daily_bars']!r}\n"
        f"RESEARCH_ID = {research_id!r}\n\n"
    )
    if EXPERIMENT_TEMPLATE.exists():
        body = EXPERIMENT_TEMPLATE.read_text(encoding="utf-8")
        # 去掉原文件 docstring，避免重复
        body = re.sub(r'^"""[\s\S]*?"""\n+', "", body, count=1)
        dest.write_text(header + body, encoding="utf-8")
    else:
        dest.write_text(
            header
            + f"# Experiment for {research_id}\n"
            + f"# Title: {title}\n"
            + "print('experiment template missing')\n",
            encoding="utf-8",
        )
    return dest


def create_research_workspace(
    *,
    research_id: str,
    paper_id: int,
    branch_id: int,
    title: str,
    topic: str,
    content: str,
    status: str = "generated",
    parent_research_id: Optional[str] = None,
    legacy_project_id: Optional[str] = None,
    scaffold: bool = True,
) -> Dict[str, Any]:
    """创建完整研究档案并保存论文正文。"""
    root = research_root(research_id, title)
    ensure_research_layout(root)
    article_path = save_article_markdown(root, research_id, content)

    if scaffold:
        scaffold_placeholder_data(root, research_id, title, topic)
        scaffold_experiment_code(root, research_id, title, topic)

    write_meta(
        root,
        research_id=research_id,
        paper_id=paper_id,
        branch_id=branch_id,
        title=title,
        topic=topic,
        status=status,
        parent_research_id=parent_research_id,
        legacy_project_id=legacy_project_id,
    )

    return {
        "research_id": research_id,
        "research_dir": str(root),
        "file_path": str(article_path),
        "artifacts": artifacts_for_api(root, research_id),
    }


def copy_file_if_exists(src: Path, dest: Path) -> bool:
    if src.exists() and src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return True
    return False


def import_legacy_project(
    *,
    research_id: str,
    paper_id: int,
    branch_id: int,
    title: str,
    topic: str,
    project_dir: Path,
    status: str = "imported",
    markdown_src: Optional[Path] = None,
) -> Dict[str, Any]:
    """将 workspace/projects/proj_* 历史目录导入统一研究档案。"""
    root = research_root(research_id, title)
    paths = ensure_research_layout(root)
    names = artifact_filenames(research_id)

    # 文章
    article_md = paths["article"] / names["article_md"]
    article_tex = paths["article"] / names["article_tex"]
    if markdown_src and markdown_src.exists():
        copy_file_if_exists(markdown_src, article_md)
    elif (project_dir / "papers" / "paper.tex").exists():
        tex = (project_dir / "papers" / "paper.tex").read_text(encoding="utf-8", errors="replace")
        save_article_tex(root, research_id, tex)
        # 简易 md 索引
        article_md.write_text(f"# {title}\n\n> LaTeX 原文见 `{names['article_tex']}`\n", encoding="utf-8")
    else:
        save_article_markdown(root, research_id, f"# {title}\n\n{topic}\n")

    # 复制 tex 变体
    papers_dir = project_dir / "papers"
    if papers_dir.exists():
        for tex in papers_dir.glob("*.tex"):
            if tex.name != names["article_tex"]:
                copy_file_if_exists(tex, paths["article"] / f"{research_id}_{tex.stem}.tex")
        for meta_file in ("icml_submission.json", "paperreview_submission.json", "compile_info.json", "workflow_summary.json"):
            copy_file_if_exists(papers_dir / meta_file, paths["article"] / f"{research_id}_{meta_file}")

    # 数据与指标
    copy_file_if_exists(project_dir / "experiment_data.json", paths["data"] / names["experiment_data"])
    copy_file_if_exists(project_dir / "indicator_sample.json", paths["data"] / names["indicator_sample"])
    copy_file_if_exists(project_dir / "backtest_results.json", paths["metrics"] / names["backtest_results"])

    # 实验代码 — 优先项目 experiments 目录，否则用全局模板
    exp_py = None
    exp_dir = project_dir / "experiments"
    if exp_dir.exists():
        py_files = list(exp_dir.glob("*.py"))
        if py_files:
            exp_py = py_files[0]
    if exp_py:
        copy_file_if_exists(exp_py, paths["code"] / names["experiment_code"])
    else:
        scaffold_experiment_code(root, research_id, title, topic)

    # 日志与 ideas
    logs_src = project_dir / "logs"
    if logs_src.exists():
        for log_file in logs_src.glob("*"):
            if log_file.is_file():
                copy_file_if_exists(log_file, paths["logs"] / f"{research_id}_{log_file.name}")
    if (project_dir / "ideas").exists():
        for idea in (project_dir / "ideas").glob("*.json"):
            copy_file_if_exists(idea, paths["ideas"] / f"{research_id}_{idea.name}")

    write_meta(
        root,
        research_id=research_id,
        paper_id=paper_id,
        branch_id=branch_id,
        title=title,
        topic=topic,
        status=status,
        legacy_project_id=project_dir.name,
    )

    return {
        "research_id": research_id,
        "research_dir": str(root),
        "file_path": str(article_md),
        "artifacts": artifacts_for_api(root, research_id),
    }


def paper_record_paths(workspace: Dict[str, Any]) -> Dict[str, Any]:
    """将 workspace 结果合并进 paper 记录字段。"""
    return {
        "research_id": workspace["research_id"],
        "research_dir": workspace["research_dir"],
        "file_path": workspace["file_path"],
        "artifacts": workspace["artifacts"],
    }
