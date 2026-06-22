from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from core.data_registry import get_mongodb_config


def _sha256_text(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


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


class MongoStateStore:
    def __init__(self) -> None:
        self._cfg = get_mongodb_config()

    def _db(self, client: Any):
        return client[self._cfg["db"]]

    def ensure_indexes(self) -> Dict[str, Any]:
        client, err = _get_client()
        if err:
            return {"success": False, "error": err}
        db = self._db(client)
        db["state_current"].create_index([("_id", 1)], unique=True)
        db["state_snapshots"].create_index([("name", 1), ("ts", -1)])
        db["papers"].create_index([("research_id", 1)], unique=True, sparse=True)
        db["papers"].create_index([("paper_id", 1)], unique=True, sparse=True)
        db["branches"].create_index([("branch_id", 1)], unique=True, sparse=True)
        db["research_archives"].create_index([("research_id", 1)], unique=True, sparse=True)
        db["artifact_index"].create_index([("research_id", 1), ("rel_path", 1)], unique=True)
        db["code_index"].create_index([("scope", 1), ("rel_path", 1)], unique=True)
        client.close()
        return {"success": True}

    def put_state(self, name: str, payload: Any) -> Dict[str, Any]:
        client, err = _get_client()
        if err:
            return {"success": False, "error": err}
        db = self._db(client)
        now = datetime.now().isoformat()
        sha = _sha256_text(payload)
        db["state_current"].update_one(
            {"_id": name},
            {"$set": {"name": name, "payload": payload, "sha256": sha, "updated_at": now}},
            upsert=True,
        )
        db["state_snapshots"].insert_one(
            {"name": name, "payload": payload, "sha256": sha, "ts": now}
        )
        if isinstance(payload, dict):
            if name == "papers_state":
                papers = payload.get("papers") or []
                for p in papers:
                    if not isinstance(p, dict):
                        continue
                    rid = p.get("research_id")
                    key = {"research_id": rid} if rid else {"paper_id": p.get("id")}
                    doc = dict(p)
                    doc["paper_id"] = p.get("id")
                    doc["updated_at"] = now
                    db["papers"].update_one(key, {"$set": doc}, upsert=True)
            if name == "branches_state":
                branches = payload.get("branches") or []
                for b in branches:
                    if not isinstance(b, dict):
                        continue
                    bid = b.get("id")
                    if bid is None:
                        continue
                    doc = dict(b)
                    doc["branch_id"] = bid
                    doc["updated_at"] = now
                    db["branches"].update_one({"branch_id": bid}, {"$set": doc}, upsert=True)
        client.close()
        return {"success": True, "sha256": sha}

    def get_state(self, name: str) -> Optional[Any]:
        client, err = _get_client()
        if err:
            return None
        db = self._db(client)
        doc = db["state_current"].find_one({"_id": name})
        client.close()
        if not doc:
            return None
        return doc.get("payload")
