import json
import re
from datetime import datetime
from pathlib import Path


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_seq(research_id: str):
    m = re.match(r"^RS-(\d{8})-(\d{3})$", str(research_id or "").strip())
    if not m:
        return None
    return m.group(1), int(m.group(2))


def main():
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    cur_path = data_dir / "papers_state.json"
    src_path = data_dir / "tmp_state2.json"

    if not cur_path.exists():
        raise SystemExit(f"missing: {cur_path}")
    if not src_path.exists():
        raise SystemExit(f"missing: {src_path}")

    cur = _load_json(cur_path)
    src = _load_json(src_path)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = data_dir / "bac" / f"manual_restore_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "papers_state.json").write_text(
        json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    default = {
        "papers": [],
        "current_paper_id": None,
        "next_research_seq": 1,
        "generation_queue": [],
        "is_generating": False,
        "is_paused": False,
        "hypotheses": [],
        "experiments": [],
        "live_graphs": {},
        "run_metrics": {},
        "current_run": None,
        "runs": [],
        "research_activity": {"phase": "idle", "message": "等待开始", "progress": 0},
        "settings": {"auto_continue": True, "pause_after_next": False},
        "stop_requested": False,
    }

    out = dict(default)
    for k in (
        "hypotheses",
        "experiments",
        "live_graphs",
        "run_metrics",
        "runs",
        "settings",
        "research_activity",
        "current_run",
    ):
        if k in src:
            out[k] = src.get(k)

    papers_by_rid = {}

    def ingest(items):
        for p in items or []:
            if not isinstance(p, dict):
                continue
            rid = str(p.get("research_id") or "").strip()
            if not rid:
                continue
            prev = papers_by_rid.get(rid)
            if not prev:
                papers_by_rid[rid] = p
                continue
            ca = str(p.get("created_at") or "")
            pa = str(prev.get("created_at") or "")
            if ca and (not pa or ca > pa):
                papers_by_rid[rid] = p

    ingest(src.get("papers"))
    ingest(cur.get("papers"))

    papers = list(papers_by_rid.values())
    papers.sort(key=lambda x: (str(x.get("created_at") or ""), int(x.get("id") or 0)))

    seen_ids = set()
    next_id = 1
    for p in papers:
        pid = int(p.get("id") or 0)
        if pid <= 0 or pid in seen_ids:
            while next_id in seen_ids:
                next_id += 1
            p["id"] = next_id
            pid = next_id
        seen_ids.add(pid)
        next_id = max(next_id, pid + 1)

    out["papers"] = papers
    out["current_paper_id"] = max(seen_ids) if seen_ids else None

    max_seq = 0
    for p in papers:
        parsed = _parse_seq(p.get("research_id"))
        if not parsed:
            continue
        _, seq = parsed
        max_seq = max(max_seq, seq)
    cur_seq = int(cur.get("next_research_seq") or 1)
    out["next_research_seq"] = max(cur_seq, max_seq + 1)

    out["is_generating"] = False
    out["is_paused"] = False
    out["stop_requested"] = False
    out["research_activity"] = {
        "phase": "idle",
        "message": "已从 tmp_state2.json 恢复论文列表",
        "progress": 0,
        "updated_at": datetime.now().isoformat(),
    }

    cur_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("backup_dir:", backup_dir.as_posix())
    print("papers_count:", len(out.get("papers") or []))


if __name__ == "__main__":
    main()

