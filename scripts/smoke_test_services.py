import time

import requests


def main():
    base = "http://127.0.0.1:8080"

    cfg = (requests.get(f"{base}/api/config/llm").json().get("llm") or {})
    print("llm", {k: cfg.get(k) for k in ["provider", "model", "base_url", "max_tokens", "api_key_configured"]})

    res = requests.post(
        f"{base}/api/research/reset",
        json={"keep_seed_papers": True, "keep_workflow": False, "remove_archives": False},
    ).json()
    print("reset", {k: res.get(k) for k in ["success", "backup_dir", "remove_archives"]})

    net = (requests.get(f"{base}/api/research/author-network/latest").json().get("author_network") or {})
    print(
        "author_net",
        {
            "authors": len(net.get("authors") or []),
            "inst": len(net.get("institutions") or []),
            "collab": len(net.get("collaborations") or []),
        },
    )

    requests.post(f"{base}/api/generate/stop")
    start = requests.post(
        f"{base}/api/generate/start",
        json={"branch_id": 1, "resume": False, "topic": "LLM Agent in Financial Trading: A Survey"},
    ).json()
    print("start", {k: start.get(k) for k in ["success", "message", "error", "code"]})

    for i in range(24):
        time.sleep(5)
        st = requests.get(f"{base}/api/research/state").json()
        act = st.get("research_activity") or {}
        msg = (act.get("message") or "")
        phase = act.get("phase")
        if i % 2 == 0:
            print("phase", phase, "progress", act.get("progress"), "msg", msg[:140])
        if ("login fail" in msg) or ("1004" in msg) or ("LLM 未就绪" in msg) or (phase in ("error", "completed")):
            print("stop_on", phase, msg[:240])
            break


if __name__ == "__main__":
    main()

