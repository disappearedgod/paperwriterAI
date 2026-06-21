import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass

import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


@dataclass
class E2EConfig:
    base_url: str
    headed: bool
    require_llm: bool
    timeout_ms: int
    start_server: bool
    port: int


def _wait_http_ready(url: str, timeout_s: int = 30) -> None:
    started = time.time()
    last_err = None
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
        cwd=str(os.path.dirname(os.path.dirname(__file__))),
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


def _assert_contains(text: str, needle: str, msg: str) -> None:
    if needle not in text:
        raise AssertionError(msg)


def _get_text(locator) -> str:
    try:
        return (locator.inner_text() or "").strip()
    except Exception:
        return ""

def _wait_svg_nodes(page, selector: str, *, min_count: int, timeout_ms: int) -> None:
    page.wait_for_function(
        "(args) => (document.querySelectorAll(args.sel).length || 0) >= args.n",
        arg={"sel": selector, "n": int(min_count)},
        timeout=timeout_ms,
    )


def _wait_element_sized(page, selector: str, *, timeout_ms: int) -> None:
    page.wait_for_function(
        "(sel) => { const el=document.querySelector(sel); if(!el) return false; return el.clientWidth>0 && el.clientHeight>0; }",
        arg=selector,
        timeout=timeout_ms,
    )

def run_e2e(cfg: E2EConfig) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not cfg.headed)
        page = browser.new_page()

        dialogs = []

        def _on_dialog(d):
            dialogs.append(d.message)
            d.accept()

        page.on("dialog", _on_dialog)

        page.goto(cfg.base_url + "/", wait_until="domcontentloaded", timeout=cfg.timeout_ms)
        try:
            page.wait_for_function("() => !!window.d3", timeout=cfg.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("E2E step failed: d3_not_loaded") from exc
        page.get_by_role("button", name=re.compile("^实验记录$")).click(timeout=cfg.timeout_ms)
        try:
            page.wait_for_selector("#experiments-list", state="visible", timeout=cfg.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("E2E step failed: experiments_panel_not_visible") from exc

        reset_btn = page.get_by_role("button", name=re.compile("从0开始"))
        reset_btn.click(timeout=cfg.timeout_ms)
        page.wait_for_timeout(1200)

        page.wait_for_timeout(1200)
        exp_text = _get_text(page.locator("#experiments-list"))
        if "暂无实验" in exp_text:
            page.wait_for_timeout(2500)
            exp_text = _get_text(page.locator("#experiments-list"))
        _assert_contains(exp_text, "实验1:", "实验记录未包含「实验1」卡片")
        _assert_contains(exp_text, "实验2:", "实验记录未包含「实验2」卡片")
        _assert_contains(exp_text, "实验3:", "实验记录未包含「实验3」卡片")

        page.wait_for_selector("#mini-papers", timeout=cfg.timeout_ms)
        papers_cnt = _get_text(page.locator("#mini-papers"))
        if papers_cnt and papers_cnt != "0":
            raise AssertionError(f"从0开始后 papers 计数未归零: {papers_cnt}")

        page.wait_for_timeout(1500)
        start_btn = page.locator("#btn-start")
        stop_btn = page.locator("#btn-stop")
        start_visible = start_btn.is_visible()

        if start_visible:
            start_disabled = bool(start_btn.get_attribute("disabled"))
            if start_disabled:
                if cfg.require_llm:
                    raise AssertionError("LLM 未就绪导致「开始」按钮被禁用（require_llm=true）")
                browser.close()
                return
            start_btn.click(timeout=cfg.timeout_ms)
            page.wait_for_timeout(1500)
        else:
            page.wait_for_selector("#btn-stop", state="visible", timeout=cfg.timeout_ms)

        status = _get_text(page.locator("#status-text"))
        if status in ("空闲", "", None):
            raise AssertionError("点击开始后状态未更新（仍为空闲）")

        page.wait_for_timeout(1500)
        exp_text_after = _get_text(page.locator("#experiments-list"))
        if ("进行中" not in exp_text_after) and ("✓ 成功" not in exp_text_after):
            raise AssertionError("开始后实验卡片未出现进行中/成功状态")

        page.get_by_role("button", name=re.compile("引用关系图")).click(timeout=cfg.timeout_ms)
        page.wait_for_timeout(800)
        try:
            page.wait_for_function("() => document.getElementById('citations-section') && document.getElementById('citations-section').classList.contains('active')", timeout=cfg.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("E2E step failed: citations_tab_not_active") from exc
        try:
            page.wait_for_function("() => (typeof farsData !== 'undefined') && farsData.citations && (farsData.citations.references || []).length > 0", timeout=cfg.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("E2E step failed: citations_data_not_ready") from exc
        try:
            _wait_element_sized(page, "#citations-container", timeout_ms=cfg.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("E2E step failed: citations_container_not_sized") from exc
        try:
            _wait_svg_nodes(page, "#citations-graph circle", min_count=1, timeout_ms=cfg.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("E2E step failed: citations_svg_no_nodes") from exc

        page.get_by_role("button", name=re.compile("作者关系图")).click(timeout=cfg.timeout_ms)
        page.wait_for_timeout(800)
        try:
            page.wait_for_function("() => document.getElementById('authors-section') && document.getElementById('authors-section').classList.contains('active')", timeout=cfg.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("E2E step failed: authors_tab_not_active") from exc
        try:
            page.wait_for_function("() => (typeof authorNetworkData !== 'undefined') && (authorNetworkData.authors || []).length > 0", timeout=cfg.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("E2E step failed: authors_data_not_ready") from exc
        try:
            _wait_element_sized(page, "#authors-container", timeout_ms=cfg.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("E2E step failed: authors_container_not_sized") from exc
        try:
            _wait_svg_nodes(page, "#authors-graph circle", min_count=1, timeout_ms=cfg.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("E2E step failed: authors_svg_no_nodes") from exc

        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--require-llm", action="store_true")
    ap.add_argument("--timeout-ms", type=int, default=30000)
    ap.add_argument("--start-server", action="store_true")
    ap.add_argument("--port", type=int, default=18080)
    args = ap.parse_args()

    base_url = args.base_url
    proc = None
    if args.start_server:
        base_url = f"http://127.0.0.1:{args.port}"
        proc = _start_server(args.port)
        _wait_http_ready(base_url + "/api/research/state", timeout_s=45)
    else:
        _wait_http_ready(base_url + "/api/research/state", timeout_s=20)

    cfg = E2EConfig(
        base_url=base_url,
        headed=bool(args.headed),
        require_llm=bool(args.require_llm),
        timeout_ms=int(args.timeout_ms),
        start_server=bool(args.start_server),
        port=int(args.port),
    )

    try:
        run_e2e(cfg)
        print("E2E PASS")
        return 0
    except (AssertionError, PlaywrightTimeoutError, PlaywrightError, requests.RequestException, RuntimeError) as exc:
        print(f"E2E FAIL: {exc}")
        return 1
    finally:
        if proc is not None:
            _stop_server(proc)


if __name__ == "__main__":
    raise SystemExit(main())
