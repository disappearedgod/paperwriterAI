from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.data_registry import get_mongodb_config


ALLOWED_RESEARCH_EXTS = {".md", ".tex", ".pdf", ".json", ".png", ".svg", ".log", ".csv"}


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_client() -> Tuple[Optional[Any], Optional[str]]:
    try:
        from pymongo import MongoClient
    except Exception:
        return None, "pymongo_unavailable"

    cfg = get_mongodb_config()
    try:
        client = MongoClient(cfg["uri"], serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return client, None
    except Exception as e:
        return None, str(e)


def sync_research_file(*, research_root: Path, research_id: str, file_path: Path) -> Dict[str, Any]:
    """
    将研究目录内的单个文件写入 Mongo GridFS，并更新 artifact_index。
    失败时返回 success=False，但不抛异常（不阻断主流程）。
    """
    try:
        rp = Path(research_root)
        fp = Path(file_path)
        if (not fp.exists()) or (not fp.is_file()):
            return {"success": False, "error": "file_not_found"}
        ext = fp.suffix.lower()
        if ext not in ALLOWED_RESEARCH_EXTS:
            return {"success": False, "error": "ext_not_allowed"}
        rel_path = fp.relative_to(rp).as_posix()
    except Exception:
        return {"success": False, "error": "invalid_path"}

    client, err = _get_client()
    if err:
        return {"success": False, "error": err}

    try:
        from gridfs import GridFS
    except Exception:
        client.close()
        return {"success": False, "error": "gridfs_unavailable"}

    cfg = get_mongodb_config()
    db = client[cfg["db"]]
    fs = GridFS(db)

    try:
        sha = _sha256_path(fp)
        existing = db["artifact_index"].find_one({"research_id": research_id, "rel_path": rel_path})
        if existing and existing.get("sha256") == sha:
            client.close()
            return {"success": True, "synced": False, "reason": "unchanged"}

        data = fp.read_bytes()
        gridfs_id = fs.put(
            data,
            filename=fp.name,
            metadata={
                "scope": "research",
                "research_id": research_id,
                "rel_path": rel_path,
                "sha256": sha,
                "ext": ext,
                "mtime": fp.stat().st_mtime,
            },
        )

        doc = {
            "scope": "research",
            "research_id": research_id,
            "rel_path": rel_path,
            "sha256": sha,
            "ext": ext,
            "size": len(data),
            "mtime": fp.stat().st_mtime,
            "gridfs_id": gridfs_id,
            "updated_at": datetime.now().isoformat(),
        }
        db["artifact_index"].update_one(
            {"research_id": research_id, "rel_path": rel_path},
            {"$set": doc},
            upsert=True,
        )
        client.close()
        return {"success": True, "synced": True, "rel_path": rel_path}
    except Exception as e:
        client.close()
        return {"success": False, "error": str(e)[:200]}

