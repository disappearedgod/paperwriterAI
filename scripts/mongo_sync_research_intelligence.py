import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.research_intelligence import (  # noqa: E402
    get_action_tasks,
    get_benchmark_alignment,
    get_benchmark_comparison,
    get_replication_runs,
    get_research_intelligence_summary,
    sync_research_intelligence,
)


def main():
    result = sync_research_intelligence()
    print(result)
    if result.get("success"):
        print(get_research_intelligence_summary())
        print(get_benchmark_alignment(limit=3))
        print(get_benchmark_comparison(limit=3))
        print(get_replication_runs(limit=3))
        print(get_action_tasks(limit=5))


if __name__ == "__main__":
    main()
