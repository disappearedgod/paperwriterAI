"""
数据注册表 — 程序统一知晓所有数据位置，供论文生成与实验直接调用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESEARCH_DIR = DATA_DIR / "research"
SEED_PAPERS_DIR = DATA_DIR / "seed_papers"
PAPERS_STATE_FILE = DATA_DIR / "papers_state.json"
WORKFLOW_STATE_FILE = DATA_DIR / "research_state.json"
BRANCHES_FILE = DATA_DIR / "research_branches.json"
SEED_MANIFEST = SEED_PAPERS_DIR / "manifest.json"
SEED_SUMMARIES = SEED_PAPERS_DIR / "combined_summaries.json"
LITERATURE_ANALYSIS = RESEARCH_DIR / "seed_paper_analysis.md"
BACKUP_DIR = DATA_DIR / "bac"
CONFIG_FILE = PROJECT_ROOT / "config.json"


def _load_json(path: Path) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _load_config() -> dict:
    return _load_json(CONFIG_FILE) or {}


def get_mongodb_config() -> Dict[str, str]:
    cfg = _load_config().get("data", {})
    return {
        "uri": cfg.get("mongodb_uri", "mongodb://localhost:27017"),
        "db": cfg.get("mongodb_db", "quant_db"),
        "collection_daily_bars": "daily_bars",
        "collection_research_index": "research_papers",
    }


def get_registry() -> Dict[str, Any]:
    """返回完整数据目录清单（供 API 与生成逻辑使用）。"""
    mongo = get_mongodb_config()
    seed_manifest = _load_json(SEED_MANIFEST) or {}
    workflow = _load_json(WORKFLOW_STATE_FILE) or {}
    papers_state = _load_json(PAPERS_STATE_FILE) or {}

    research_archives = []
    if RESEARCH_DIR.exists():
        for meta_path in RESEARCH_DIR.glob("RS-*/meta.json"):
            meta = _load_json(meta_path)
            if meta:
                research_archives.append({
                    "research_id": meta.get("research_id"),
                    "title": meta.get("title"),
                    "path": str(meta_path.parent),
                    "artifacts": meta.get("artifacts", {}),
                })

    return {
        "project_root": str(PROJECT_ROOT),
        "paths": {
            "data_dir": str(DATA_DIR),
            "research_archives": str(RESEARCH_DIR),
            "seed_papers": str(SEED_PAPERS_DIR),
            "papers_state": str(PAPERS_STATE_FILE),
            "workflow_state": str(WORKFLOW_STATE_FILE),
            "branches": str(BRANCHES_FILE),
            "literature_analysis": str(LITERATURE_ANALYSIS),
            "backup_dir": str(BACKUP_DIR),
        },
        "mongodb": mongo,
        "seed_papers": {
            "manifest": str(SEED_MANIFEST),
            "combined_summaries": str(SEED_SUMMARIES),
            "count": len(seed_manifest.get("seed_papers", [])),
            "papers": seed_manifest.get("seed_papers", []),
        },
        "workflow": {
            "version": workflow.get("version"),
            "project_name": workflow.get("project_name"),
            "current_phase": workflow.get("current_phase"),
            "status": workflow.get("status"),
        },
        "papers": {
            "count": len(papers_state.get("papers", [])),
            "is_generating": papers_state.get("is_generating", False),
        },
        "research_archives": research_archives,
    }


def get_literature_context(max_chars: int = 6000) -> str:
    """汇总种子文献与工作流分析，供论文生成 prompt 使用。"""
    parts: List[str] = []
    workflow = _load_json(WORKFLOW_STATE_FILE) or {}
    papers_state = _load_json(PAPERS_STATE_FILE) or {}

    if LITERATURE_ANALYSIS.exists():
        text = LITERATURE_ANALYSIS.read_text(encoding="utf-8", errors="replace")
        parts.append("## 文献综述分析\n" + text[: max_chars // 2])

    summaries = _load_json(SEED_SUMMARIES)
    if summaries:
        if isinstance(summaries, list):
            items = summaries
        elif isinstance(summaries, dict):
            items = summaries.get("papers", summaries.get("summaries", []))
        else:
            items = []
        lines = []
        for item in items[:8]:
            if isinstance(item, dict):
                lines.append(
                    f"- [{item.get('arxiv_id', item.get('id', '?'))}] "
                    f"{item.get('title', '')}: {str(item.get('summary', item.get('abstract', '')))[:200]}"
                )
        if lines:
            parts.append("## 种子论文摘要\n" + "\n".join(lines))

    manifest = _load_json(SEED_MANIFEST)
    if manifest and not parts:
        for sp in manifest.get("seed_papers", [])[:5]:
            parts.append(f"- {sp.get('arxiv_id')}: {sp.get('title')}")

    lit = workflow.get("literature_review", {})
    if lit.get("papers_read"):
        lines = []
        for item in lit.get("papers_read", [])[:6]:
            if isinstance(item, dict):
                lines.append(
                    f"- [{item.get('arxiv_id', '?')}] {item.get('title', '')} "
                    f"(topics: {', '.join(item.get('key_topics') or [])})"
                )
        if lines:
            parts.append("## 已分析种子论文\n" + "\n".join(lines))
    if lit.get("key_themes"):
        parts.append("## 研究主题\n" + "\n".join(f"- {t}" for t in lit["key_themes"]))
    if lit.get("research_questions"):
        parts.append("## 研究问题\n" + "\n".join(f"- {q}" for q in lit["research_questions"][:6]))
    if lit.get("research_gaps"):
        parts.append("## 研究空白\n" + "\n".join(f"- {g}" for g in lit["research_gaps"][:5]))
    if lit.get("potential_innovations"):
        parts.append("## 潜在创新\n" + "\n".join(f"- {g}" for g in lit["potential_innovations"][:5]))

    hypotheses = papers_state.get("hypotheses") or []
    if hypotheses:
        lines = []
        for item in hypotheses[:5]:
            if isinstance(item, dict):
                lines.append(
                    f"- {item.get('id', '?')}: {item.get('title', '')} "
                    f"(tags: {', '.join(item.get('tags') or [])})"
                )
        if lines:
            parts.append("## 当前研究假设\n" + "\n".join(lines))

    ctx = "\n\n".join(parts)
    return ctx[:max_chars]


def get_market_data_hint() -> str:
    """描述 MongoDB 市场数据位置，供实验代码引用。"""
    mongo = get_mongodb_config()
    return (
        f"市场数据存储在 MongoDB: {mongo['uri']}, 数据库 {mongo['db']}, "
        f"集合 {mongo['collection_daily_bars']}（日线 OHLCV）。"
        f"实验代码可通过 pymongo 连接读取。"
    )


def get_paper_generation_context(topic: str) -> str:
    """论文生成时注入的完整数据上下文。"""
    lit = get_literature_context()
    market = get_market_data_hint()
    return f"""研究主题: {topic}

{market}

{lit}
"""
