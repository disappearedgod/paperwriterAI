import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


def _wait_http_ready(url: str, timeout_s: int) -> None:
    started = time.time()
    last_err: Optional[Exception] = None
    while time.time() - started < timeout_s:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code < 500:
                return
            last_err = RuntimeError(f"HTTP {r.status_code}")
        except Exception as exc:
            last_err = exc
        time.sleep(0.5)
    raise RuntimeError(f"server not ready: {last_err}")


def _start_server(port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["PORT"] = str(port)
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc


def _stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _http_json(method: str, url: str, *, json_body: Optional[dict] = None, timeout_s: int = 30) -> Dict[str, Any]:
    r = requests.request(method, url, json=json_body, timeout=timeout_s)
    if r.status_code >= 400:
        snippet = (r.text or "")[:300]
        raise RuntimeError(f"HTTP {r.status_code} {snippet}")
    try:
        return r.json()
    except Exception:
        snippet = (r.text or "")[:300]
        raise RuntimeError(f"Non-JSON response: HTTP {r.status_code} {snippet}")


def _api_tests(base_url: str) -> List[Result]:
    rs: List[Result] = []

    def _t(name: str, fn):
        try:
            fn()
            rs.append(Result(name=name, ok=True))
        except Exception as exc:
            rs.append(Result(name=name, ok=False, detail=str(exc)))

    _t("GET /api/research/state", lambda: _http_json("GET", f"{base_url}/api/research/state"))
    _t("GET /api/data/registry", lambda: _http_json("GET", f"{base_url}/api/data/registry"))
    _t("GET /api/config/llm", lambda: _http_json("GET", f"{base_url}/api/config/llm"))
    _t("GET /api/config/llm/providers", lambda: _http_json("GET", f"{base_url}/api/config/llm/providers"))
    _t("GET /api/branches", lambda: _http_json("GET", f"{base_url}/api/branches"))
    _t("GET /api/papers", lambda: _http_json("GET", f"{base_url}/api/papers"))
    _t("GET /api/research/run", lambda: _http_json("GET", f"{base_url}/api/research/run"))
    _t("GET /api/research/checkpoints", lambda: _http_json("GET", f"{base_url}/api/research/checkpoints"))
    _t("GET /api/research/logs", lambda: _http_json("GET", f"{base_url}/api/research/logs"))
    _t("GET /api/research/author-network/latest", lambda: _http_json("GET", f"{base_url}/api/research/author-network/latest"))
    _t("GET /api/research/citation-network/latest", lambda: _http_json("GET", f"{base_url}/api/research/citation-network/latest"))

    def _seed_papers():
        data = _http_json("GET", f"{base_url}/api/seed-papers")
        if not data.get("success"):
            raise RuntimeError("seed-papers success=false")
        papers = data.get("papers") or []
        if not papers:
            raise RuntimeError("seed-papers empty")
        pid = None
        for p in papers:
            if p.get("has_pdf") and p.get("id") is not None:
                pid = int(p["id"])
                break
        if pid is None:
            pid = int(papers[0].get("id") or 0)
        r = requests.get(f"{base_url}/api/seed-papers/{pid}/pdf", timeout=30)
        if r.status_code not in (200, 404):
            raise RuntimeError(f"seed pdf HTTP {r.status_code}")

    _t("GET /api/seed-papers (+pdf)", _seed_papers)

    def _wait_for_live_graphs(timeout_s: int = 20) -> None:
        started = time.time()
        last = None
        while time.time() - started < timeout_s:
            state = _http_json("GET", f"{base_url}/api/research/state")
            phase = ((state.get("research_activity") or {}).get("phase") or "")
            if phase in ("experimenting", "writing", "paused"):
                author = _http_json("GET", f"{base_url}/api/research/author-network/latest")
                citation = _http_json("GET", f"{base_url}/api/research/citation-network/latest")
                if author.get("source") == "live" and citation.get("source") == "live":
                    return
                last = {"author_source": author.get("source"), "citation_source": citation.get("source"), "phase": phase}
            else:
                last = {"phase": phase}
            time.sleep(0.8)
        raise RuntimeError(f"live graphs not ready: {last}")

    def _wait_for_timing_metrics(timeout_s: int = 20) -> None:
        started = time.time()
        last = None
        while time.time() - started < timeout_s:
            state = _http_json("GET", f"{base_url}/api/research/state")
            experiments = state.get("experiments") or []
            exp1 = next((x for x in experiments if x.get("id") == "exp_1"), None)
            metrics = (exp1 or {}).get("metrics") or {}
            if ("阅读耗时(s)" in metrics) and ("分析耗时(s)" in metrics):
                return
            last = metrics
            time.sleep(0.8)
        raise RuntimeError(f"timing metrics not ready: {last}")

    def _reset_and_controls():
        data = _http_json("POST", f"{base_url}/api/research/reset", json_body={"keep_seed_papers": True, "keep_workflow": True, "remove_archives": False})
        if not data.get("success"):
            raise RuntimeError("reset failed")
        start = _http_json("POST", f"{base_url}/api/generate/start", json_body={"topic": "E2E API Test Topic", "branch_id": 1})
        if not start.get("success"):
            raise RuntimeError("generate start failed")
        _wait_for_live_graphs()
        _wait_for_timing_metrics()
        _http_json("POST", f"{base_url}/api/generate/pause", json_body={})
        _http_json("POST", f"{base_url}/api/generate/resume", json_body={})
        _http_json("POST", f"{base_url}/api/generate/stop", json_body={})

    _t("POST reset + start/live-graphs/pause/resume/stop", _reset_and_controls)

    return rs


def _run_playwright_e2e(base_url: str) -> Tuple[bool, str]:
    try:
        import playwright  # noqa: F401
    except Exception:
        return False, "playwright_not_installed"

    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "e2e_dashboard_playwright.py"), "--base-url", base_url, "--require-llm"]
    proc = subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(__file__)), capture_output=True, text=True)
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if proc.returncode != 0:
        return False, out[-2000:]
    return True, out[-2000:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18080)
    ap.add_argument("--skip-e2e", action="store_true")
    ap.add_argument("--timeout-s", type=int, default=45)
    args = ap.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"
    server = _start_server(args.port)
    try:
        _wait_http_ready(base_url + "/api/research/state", timeout_s=int(args.timeout_s))
        api_results = _api_tests(base_url)

        e2e_ok = None
        e2e_detail = ""
        if not args.skip_e2e:
            e2e_ok, e2e_detail = _run_playwright_e2e(base_url)

        ok_count = sum(1 for r in api_results if r.ok)
        fail = [r for r in api_results if not r.ok]

        print("=== API Tests ===")
        for r in api_results:
            print(f"[{'PASS' if r.ok else 'FAIL'}] {r.name}" + (f" :: {r.detail}" if r.detail else ""))
        print(f"API summary: {ok_count}/{len(api_results)} passed")

        if e2e_ok is not None:
            print("\n=== Frontend E2E (Playwright) ===")
            print("PASS" if e2e_ok else "FAIL")
            if e2e_detail:
                print(e2e_detail)

        if fail:
            return 1
        if e2e_ok is False:
            return 2
        return 0
    finally:
        _stop_server(server)


if __name__ == "__main__":
    raise SystemExit(main())
