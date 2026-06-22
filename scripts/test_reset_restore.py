import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _count_papers() -> int:
    p = DATA_DIR / "papers_state.json"
    if not p.exists():
        return 0
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0
    return len(d.get("papers") or [])


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    before = _count_papers()
    print("papers_before:", before)

    from core.research_reset import reset_research
    from core.research_restore import restore_latest

    reset = reset_research(keep_seed_papers=True, keep_workflow=True, remove_archives=False)
    print("reset_ok:", bool(reset.get("success")), "backup_dir:", reset.get("backup_dir"))

    after_reset = _count_papers()
    print("papers_after_reset:", after_reset)

    restored = restore_latest(prefer="file")
    print("restore_ok:", bool(restored.get("success")), "restored_from:", restored.get("restored_from"))

    after_restore = _count_papers()
    print("papers_after_restore:", after_restore)

    if before and after_restore:
        print("restore_delta:", after_restore - before)


if __name__ == "__main__":
    main()
