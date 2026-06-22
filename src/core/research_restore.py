from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.data_registry import BACKUP_DIR, DATA_DIR, RESEARCH_DIR
from core.mongo_store import MongoStateStore


_STATE_FILES = (
    "papers_state.json",
    "research_state.json",
    "research_branches.json",
    "research_logs.json",
    "grading_history.json",
)


def _parse_backup_ts(name: str) -> Optional[datetime]:
    s = str(name or "")
    s = re.sub(r"^(manual_restore_|reset_|restore_)", "", s)
    m = re.search(r"(\d{8}_\d{6})", s)
    if not m:
        m = re.search(r"(\d{14})", s)
    if not m:
        return None
    raw = m.group(1)
    try:
        if "_" in raw:
            return datetime.strptime(raw, "%Y%m%d_%H%M%S")
        return datetime.strptime(raw, "%Y%m%d%H%M%S")
    except Exception:
        return None


def list_local_backups(*, limit: int = 20) -> List[Dict[str, Any]]:
    if not BACKUP_DIR.exists():
        return []
    rows: List[Tuple[datetime, Path]] = []
    for p in BACKUP_DIR.iterdir():
        if not p.is_dir():
            continue
        ts = _parse_backup_ts(p.name)
        if ts is None:
            try:
                ts = datetime.fromtimestamp(p.stat().st_mtime)
            except Exception:
                continue
        rows.append((ts, p))
    rows.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict[str, Any]] = []
    for ts, p in rows[: max(1, int(limit))]:
        out.append({
            "name": p.name,
            "path": str(p),
            "ts": ts.isoformat(),
            "has_research_archives": (p / "research").exists(),
            "state_files": [f for f in _STATE_FILES if (p / f).exists()],
        })
    return out


def _restore_files_from_backup_dir(backup_dir: Path) -> Dict[str, Any]:
    restored: List[str] = []
    skipped: List[str] = []
    for name in _STATE_FILES:
        src = backup_dir / name
        if not src.exists():
            skipped.append(name)
            continue
        dest = DATA_DIR / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        restored.append(name)

    research_src = backup_dir / "research"
    archives_restored: List[str] = []
    archives_skipped: List[str] = []
    if research_src.exists() and research_src.is_dir():
        for item in research_src.iterdir():
            if not item.is_dir():
                continue
            if not item.name.startswith("RS-"):
                continue
            dest = RESEARCH_DIR / item.name
            if dest.exists():
                shutil.copytree(item, dest, dirs_exist_ok=True)
                archives_skipped.append(item.name)
            else:
                shutil.copytree(item, dest, dirs_exist_ok=True)
                archives_restored.append(item.name)

    return {
        "state_restored": restored,
        "state_missing_in_backup": skipped,
        "archives_restored": archives_restored,
        "archives_merged": archives_skipped,
    }


def _sync_state_to_mongo(*, papers: Any, workflow: Any, branches: Any, logs: Any, grading: Any) -> Dict[str, Any]:
    try:
        store = MongoStateStore()
        store.ensure_indexes()
        store.put_state("papers_state", papers if papers is not None else {})
        store.put_state("workflow_state", workflow if workflow is not None else {})
        store.put_state("branches_state", branches if branches is not None else {})
        store.put_state("research_logs", logs if logs is not None else [])
        store.put_state("grading_history", grading if grading is not None else [])
        return {"attempted": True, "success": True, "error": ""}
    except Exception as e:
        return {"attempted": True, "success": False, "error": str(e)[:200]}


def restore_latest(*, prefer: str = "auto") -> Dict[str, Any]:
    """
    prefer:
      - auto: 优先 mongo backup tag（存在则用），否则用本地 data/bac 最新目录
      - mongo: 仅从 mongo backup tag 恢复
      - file: 仅从本地 data/bac 最新目录恢复
    """
    prefer = str(prefer or "auto").strip().lower()

    mongo_result = {"attempted": False, "success": False, "tag": None, "error": ""}
    file_result = {"attempted": False, "success": False, "backup_dir": None, "error": ""}

    if prefer in ("auto", "mongo"):
        try:
            store = MongoStateStore()
            store.ensure_indexes()
            tag = _latest_mongo_reset_tag(store)
            if tag:
                mongo_result["attempted"] = True
                mongo_result["tag"] = tag
                _restore_from_mongo_tag(store, tag)
                mongo_result["success"] = True
                mongo_result["error"] = ""
                return {
                    "success": True,
                    "restored_from": "mongo",
                    "mongo": mongo_result,
                    "file": file_result,
                }
        except Exception as e:
            mongo_result["attempted"] = True
            mongo_result["success"] = False
            mongo_result["error"] = str(e)[:200]
            if prefer == "mongo":
                return {"success": False, "error": mongo_result["error"], "mongo": mongo_result}

    if prefer in ("auto", "file"):
        backups = list_local_backups(limit=1)
        if not backups:
            return {"success": False, "error": "no_backup_found", "mongo": mongo_result, "file": file_result}
        backup_dir = Path(backups[0]["path"])
        file_result["attempted"] = True
        file_result["backup_dir"] = str(backup_dir)
        try:
            detail = _restore_files_from_backup_dir(backup_dir)
            file_result["success"] = True
            file_result.update(detail)
        except Exception as e:
            file_result["success"] = False
            file_result["error"] = str(e)[:200]
            return {"success": False, "error": file_result["error"], "mongo": mongo_result, "file": file_result}

        papers = _safe_read_json(DATA_DIR / "papers_state.json")
        workflow = _safe_read_json(DATA_DIR / "research_state.json")
        branches = _safe_read_json(DATA_DIR / "research_branches.json")
        logs = _safe_read_json(DATA_DIR / "research_logs.json")
        grading = _safe_read_json(DATA_DIR / "grading_history.json")
        mongo_sync = _sync_state_to_mongo(
            papers=papers, workflow=workflow, branches=branches, logs=logs, grading=grading
        )
        return {
            "success": True,
            "restored_from": "file",
            "mongo_sync": mongo_sync,
            "mongo": mongo_result,
            "file": file_result,
        }

    return {"success": False, "error": "invalid_prefer"}


def _safe_read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _latest_mongo_reset_tag(store: MongoStateStore) -> Optional[str]:
    try:
        from pymongo import MongoClient
    except Exception:
        return None
    cfg = store._cfg if hasattr(store, "_cfg") else None
    if not isinstance(cfg, dict):
        return None
    try:
        client = MongoClient(cfg["uri"], serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        db = client[cfg["db"]]
        keys = list(db["state_current"].find({"_id": {"$regex": r"^backup:reset_"}}, {"_id": 1}))
        client.close()
    except Exception:
        return None
    tags: List[str] = []
    for row in keys:
        key = str(row.get("_id") or "")
        parts = key.split(":")
        if len(parts) >= 3 and parts[0] == "backup" and parts[1].startswith("reset_"):
            tags.append(parts[1])
    if not tags:
        return None
    tags = sorted(set(tags), reverse=True)
    return tags[0]


def _restore_from_mongo_tag(store: MongoStateStore, tag: str) -> None:
    need = {
        "papers_state": f"backup:{tag}:papers_state",
        "workflow_state": f"backup:{tag}:workflow_state",
        "branches_state": f"backup:{tag}:branches_state",
        "research_logs": f"backup:{tag}:research_logs",
        "grading_history": f"backup:{tag}:grading_history",
    }
    restored: Dict[str, Any] = {}
    for k, key in need.items():
        restored[k] = store.get_state(key)

    store.put_state("papers_state", restored.get("papers_state") or {})
    store.put_state("workflow_state", restored.get("workflow_state") or {})
    store.put_state("branches_state", restored.get("branches_state") or {})
    store.put_state("research_logs", restored.get("research_logs") or [])
    store.put_state("grading_history", restored.get("grading_history") or [])

    _write_json(DATA_DIR / "papers_state.json", restored.get("papers_state") or {})
    _write_json(DATA_DIR / "research_state.json", restored.get("workflow_state") or {})
    _write_json(DATA_DIR / "research_branches.json", restored.get("branches_state") or {})
    _write_json(DATA_DIR / "research_logs.json", restored.get("research_logs") or [])
    _write_json(DATA_DIR / "grading_history.json", restored.get("grading_history") or [])


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

