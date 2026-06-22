import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


ALLOWED_RESEARCH_EXTS = {".md", ".tex", ".pdf", ".json", ".png", ".svg", ".log", ".csv"}
ALLOWED_CODE_EXTS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".html",
    ".css",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".sh",
    ".bat",
    ".ps1",
}

DEFAULT_CODE_EXCLUDES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_mongo() -> Tuple[Any, Any, Any]:
    from pymongo import MongoClient
    from core.data_registry import get_mongodb_config

    cfg = get_mongodb_config()
    client = MongoClient(cfg["uri"], serverSelectionTimeoutMS=3000)
    client.admin.command("ping")
    db = client[cfg["db"]]
    return client, db, cfg


def _ensure_indexes(db: Any):
    db["state_current"].create_index([("_id", 1)], unique=True)
    db["state_snapshots"].create_index([("name", 1), ("ts", -1)])
    db["papers"].create_index([("research_id", 1)], unique=True, sparse=True)
    db["papers"].create_index([("paper_id", 1)], unique=True, sparse=True)
    db["branches"].create_index([("branch_id", 1)], unique=True, sparse=True)
    db["research_archives"].create_index([("research_id", 1)], unique=True, sparse=True)
    db["artifact_index"].create_index([("research_id", 1), ("rel_path", 1)], unique=True)
    db["artifact_index"].create_index([("sha256", 1)])
    db["code_index"].create_index([("scope", 1), ("rel_path", 1)], unique=True)
    db["code_index"].create_index([("sha256", 1)])


def _upsert_state(db: Any, name: str, payload: Dict[str, Any], source_path: str):
    now = datetime.now().isoformat()
    sha = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    db["state_current"].update_one(
        {"_id": name},
        {"$set": {"name": name, "payload": payload, "sha256": sha, "updated_at": now}},
        upsert=True,
    )
    db["state_snapshots"].insert_one(
        {"name": name, "payload": payload, "sha256": sha, "ts": now, "source_path": source_path}
    )


def cmd_init(args):
    client, db, _ = _get_mongo()
    _ensure_indexes(db)
    db["meta"].update_one(
        {"_id": "schema_version"},
        {"$set": {"version": 1, "updated_at": datetime.now().isoformat()}},
        upsert=True,
    )
    client.close()
    print("ok")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def cmd_import_state(args):
    root = _project_root()
    data = root / "data"
    mapping = {
        "papers_state": data / "papers_state.json",
        "workflow_state": data / "research_state.json",
        "branches_state": data / "research_branches.json",
        "research_logs": data / "research_logs.json",
        "grading_history": data / "grading_history.json",
    }

    client, db, _ = _get_mongo()
    _ensure_indexes(db)

    for name, path in mapping.items():
        payload = _load_json(path)
        if not payload:
            continue
        _upsert_state(db, name, payload, str(path))
        if name == "papers_state":
            now = datetime.now().isoformat()
            for p in payload.get("papers") or []:
                if not isinstance(p, dict):
                    continue
                rid = p.get("research_id")
                key = {"research_id": rid} if rid else {"paper_id": p.get("id")}
                doc = dict(p)
                doc["paper_id"] = p.get("id")
                doc["updated_at"] = now
                db["papers"].update_one(key, {"$set": doc}, upsert=True)
        if name == "branches_state":
            now = datetime.now().isoformat()
            for b in payload.get("branches") or []:
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
    print("ok")


def cmd_import_archives(args):
    root = _project_root()
    research = root / "data" / "research"
    client, db, _ = _get_mongo()
    _ensure_indexes(db)
    now = datetime.now().isoformat()

    for meta_path in research.glob("RS-*/meta.json"):
        meta = _load_json(meta_path)
        if not meta:
            continue
        rid = str(meta.get("research_id") or "").strip()
        if not rid:
            continue
        doc = dict(meta)
        doc["updated_at"] = now
        doc["path"] = str(meta_path.parent)
        db["research_archives"].update_one({"research_id": rid}, {"$set": doc}, upsert=True)

    client.close()
    print("ok")


def _iter_artifacts(research_dir: Path) -> Iterable[Tuple[str, Path]]:
    for p in research_dir.glob("RS-*/*"):
        if p.is_file():
            rel = p.relative_to(research_dir).as_posix()
            yield rel, p
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(research_dir).as_posix()
                    yield rel, f


def cmd_import_artifacts(args):
    from gridfs import GridFS

    root = _project_root()
    research = root / "data" / "research"
    client, db, _ = _get_mongo()
    _ensure_indexes(db)
    fs = GridFS(db)

    inserted = 0
    skipped = 0
    for rel_path, path in _iter_artifacts(research):
        ext = path.suffix.lower()
        if ext not in ALLOWED_RESEARCH_EXTS:
            continue
        parts = rel_path.split("/", 1)
        research_id = parts[0]
        inner_rel = parts[1] if len(parts) > 1 else path.name
        sha = _sha256_path(path)
        existing = db["artifact_index"].find_one({"research_id": research_id, "rel_path": inner_rel})
        if existing and existing.get("sha256") == sha:
            skipped += 1
            continue
        data = path.read_bytes()
        gridfs_id = fs.put(
            data,
            filename=path.name,
            metadata={
                "research_id": research_id,
                "rel_path": inner_rel,
                "sha256": sha,
                "ext": ext,
                "mtime": path.stat().st_mtime,
                "scope": "research",
            },
        )
        doc = {
            "research_id": research_id,
            "rel_path": inner_rel,
            "sha256": sha,
            "ext": ext,
            "size": len(data),
            "mtime": path.stat().st_mtime,
            "gridfs_id": gridfs_id,
            "updated_at": datetime.now().isoformat(),
            "scope": "research",
        }
        db["artifact_index"].update_one(
            {"research_id": research_id, "rel_path": inner_rel},
            {"$set": doc},
            upsert=True,
        )
        inserted += 1

    client.close()
    print("inserted", inserted, "skipped", skipped)


def _iter_code_files(root: Path) -> Iterable[Tuple[str, Path]]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        if any(x in DEFAULT_CODE_EXCLUDES for x in parts):
            continue
        yield rel, p


def cmd_import_code(args):
    from gridfs import GridFS

    root = _project_root()
    client, db, _ = _get_mongo()
    _ensure_indexes(db)
    fs = GridFS(db)

    inserted = 0
    skipped = 0
    for rel_path, path in _iter_code_files(root):
        ext = path.suffix.lower()
        if ext and ext not in ALLOWED_CODE_EXTS:
            continue
        if not ext and path.name not in {"Dockerfile", "Makefile"}:
            continue
        sha = _sha256_path(path)
        existing = db["code_index"].find_one({"scope": "repo", "rel_path": rel_path})
        if existing and existing.get("sha256") == sha:
            skipped += 1
            continue
        data = path.read_bytes()
        gridfs_id = fs.put(
            data,
            filename=path.name,
            metadata={
                "scope": "repo",
                "rel_path": rel_path,
                "sha256": sha,
                "ext": ext,
                "mtime": path.stat().st_mtime,
            },
        )
        doc = {
            "scope": "repo",
            "rel_path": rel_path,
            "sha256": sha,
            "ext": ext,
            "size": len(data),
            "mtime": path.stat().st_mtime,
            "gridfs_id": gridfs_id,
            "updated_at": datetime.now().isoformat(),
        }
        db["code_index"].update_one(
            {"scope": "repo", "rel_path": rel_path},
            {"$set": doc},
            upsert=True,
        )
        inserted += 1

    client.close()
    print("inserted", inserted, "skipped", skipped)


def _iter_generated_files(root: Path) -> Iterable[Tuple[str, Path]]:
    for base in (root / "data" / "seed_papers",):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            yield rel, p


def cmd_import_generated(args):
    from gridfs import GridFS

    root = _project_root()
    client, db, _ = _get_mongo()
    _ensure_indexes(db)
    fs = GridFS(db)

    inserted = 0
    skipped = 0
    for rel_path, path in _iter_generated_files(root):
        ext = path.suffix.lower()
        if ext and ext not in (ALLOWED_RESEARCH_EXTS | {".pdf"}):
            continue
        sha = _sha256_path(path)
        existing = db["code_index"].find_one({"scope": "generated", "rel_path": rel_path})
        if existing and existing.get("sha256") == sha:
            skipped += 1
            continue
        data = path.read_bytes()
        gridfs_id = fs.put(
            data,
            filename=path.name,
            metadata={
                "scope": "generated",
                "rel_path": rel_path,
                "sha256": sha,
                "ext": ext,
                "mtime": path.stat().st_mtime,
            },
        )
        doc = {
            "scope": "generated",
            "rel_path": rel_path,
            "sha256": sha,
            "ext": ext,
            "size": len(data),
            "mtime": path.stat().st_mtime,
            "gridfs_id": gridfs_id,
            "updated_at": datetime.now().isoformat(),
        }
        db["code_index"].update_one(
            {"scope": "generated", "rel_path": rel_path},
            {"$set": doc},
            upsert=True,
        )
        inserted += 1

    client.close()
    print("inserted", inserted, "skipped", skipped)


def cmd_import_all(args):
    cmd_import_state(args)
    cmd_import_archives(args)
    cmd_import_artifacts(args)
    cmd_import_generated(args)
    cmd_import_code(args)



    root = _project_root()
    data = root / "data"
    papers_state = _load_json(data / "papers_state.json") or {}
    branches_state = _load_json(data / "research_branches.json") or {}
    archive_count = len(list((root / "data" / "research").glob("RS-*/meta.json")))

    client, db, _ = _get_mongo()
    report = {
        "local": {
            "papers": len(papers_state.get("papers") or []),
            "branches": len(branches_state.get("branches") or []),
            "archives": archive_count,
        },
        "mongo": {
            "papers": db["papers"].estimated_document_count(),
            "branches": db["branches"].estimated_document_count(),
            "archives": db["research_archives"].estimated_document_count(),
            "artifact_index": db["artifact_index"].estimated_document_count(),
            "code_index": db["code_index"].estimated_document_count(),
            "state_snapshots": db["state_snapshots"].estimated_document_count(),
        },
    }
    client.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_export_json(args):
    root = _project_root()
    data_dir = root / "data"
    mapping = {
        "papers_state": data_dir / "papers_state.json",
        "workflow_state": data_dir / "research_state.json",
        "branches_state": data_dir / "research_branches.json",
        "research_logs": data_dir / "research_logs.json",
        "grading_history": data_dir / "grading_history.json",
    }

    client, db, _ = _get_mongo()
    for name, path in mapping.items():
        doc = db["state_current"].find_one({"_id": name})
        if not doc or not isinstance(doc.get("payload"), dict):
            continue
        payload = doc["payload"]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    client.close()
    print("ok")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("import-state")
    sub.add_parser("import-archives")
    sub.add_parser("import-artifacts")
    sub.add_parser("import-generated")
    sub.add_parser("import-code")
    sub.add_parser("import-all")
    sub.add_parser("verify")
    sub.add_parser("export-json")

    args = parser.parse_args()
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "import-state":
        return cmd_import_state(args)
    if args.cmd == "import-archives":
        return cmd_import_archives(args)
    if args.cmd == "import-artifacts":
        return cmd_import_artifacts(args)
    if args.cmd == "import-generated":
        return cmd_import_generated(args)
    if args.cmd == "import-code":
        return cmd_import_code(args)
    if args.cmd == "import-all":
        return cmd_import_all(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "export-json":
        return cmd_export_json(args)
    raise SystemExit("unknown cmd")


if __name__ == "__main__":
    main()
