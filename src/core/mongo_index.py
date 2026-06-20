"""
MongoDB 研究索引 — 将论文、实验数据与研究档案元数据写入 MongoDB 供检索。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.data_registry import get_mongodb_config, PROJECT_ROOT


def _get_client():
    try:
        from pymongo import MongoClient
    except ImportError:
        return None, "pymongo 未安装"

    cfg = get_mongodb_config()
    try:
        client = MongoClient(cfg["uri"], serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return client, None
    except Exception as e:
        return None, str(e)


def index_paper_record(paper: Dict[str, Any]) -> Dict[str, Any]:
    """将论文记录索引到 MongoDB research_papers 集合。"""
    client, err = _get_client()
    if err:
        return {"success": False, "indexed": False, "error": err}

    cfg = get_mongodb_config()
    db = client[cfg["db"]]
    col = db[cfg["collection_research_index"]]

    doc = {
        "paper_id": paper.get("id"),
        "research_id": paper.get("research_id"),
        "branch_id": paper.get("branch_id"),
        "title": paper.get("title"),
        "topic": paper.get("topic"),
        "status": paper.get("status"),
        "quality_score": paper.get("quality_score"),
        "file_path": paper.get("file_path"),
        "research_dir": paper.get("research_dir"),
        "artifacts": paper.get("artifacts", {}),
        "generation_mode": paper.get("generation_mode"),
        "created_at": paper.get("created_at") or datetime.now().isoformat(),
        "indexed_at": datetime.now().isoformat(),
        "source": "paperwriterAI",
    }

    key = {"research_id": doc["research_id"]} if doc.get("research_id") else {"paper_id": doc["paper_id"]}
    col.update_one(key, {"$set": doc}, upsert=True)
    client.close()
    return {"success": True, "indexed": True, "collection": cfg["collection_research_index"]}


def index_research_meta(meta_path: Path) -> Dict[str, Any]:
    """将研究档案 meta.json 索引到 MongoDB。"""
    if not meta_path.exists():
        return {"success": False, "error": "meta.json 不存在"}

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    paper_like = {
        "id": meta.get("paper_id"),
        "research_id": meta.get("research_id"),
        "branch_id": meta.get("branch_id"),
        "title": meta.get("title"),
        "topic": meta.get("topic"),
        "status": meta.get("status"),
        "research_dir": str(meta_path.parent),
        "artifacts": meta.get("artifacts", {}),
        "legacy_project_id": meta.get("legacy_project_id"),
    }
    return index_paper_record(paper_like)


def query_papers(limit: int = 50) -> Dict[str, Any]:
    """从 MongoDB 查询已索引论文。"""
    client, err = _get_client()
    if err:
        return {"success": False, "papers": [], "error": err}

    cfg = get_mongodb_config()
    col = client[cfg["db"]][cfg["collection_research_index"]]
    papers = list(col.find({}, {"_id": 0}).sort("indexed_at", -1).limit(limit))
    client.close()
    return {"success": True, "papers": papers, "count": len(papers)}


def check_market_data() -> Dict[str, Any]:
    """检查 MongoDB 市场数据是否可用。"""
    client, err = _get_client()
    if err:
        return {"available": False, "error": err}

    cfg = get_mongodb_config()
    try:
        col = client[cfg["db"]][cfg["collection_daily_bars"]]
        count = col.estimated_document_count()
        sample = col.find_one()
        client.close()
        return {
            "available": count > 0,
            "collection": cfg["collection_daily_bars"],
            "document_count": count,
            "sample_keys": list(sample.keys()) if sample else [],
        }
    except Exception as e:
        client.close()
        return {"available": False, "error": str(e)}
