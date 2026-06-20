"""
种子文献库 — 近五年量化 / 信号系统 / 金融工程 / LLM 顶级方向论文，支持 PDF 下载。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.data_registry import SEED_PAPERS_DIR, SEED_MANIFEST

# 检索主题：量化、信号、金融工程、LLM 交易
ARXIV_QUERIES = [
    '(all:"large language model" OR all:LLM) AND (all:"quantitative trading" OR all:"quantitative finance")',
    'all:"alpha" AND (all:"machine learning" OR all:"deep learning") AND cat:q-fin*',
    'all:"trading agent" AND (all:"LLM" OR all:"language model")',
    'all:"financial engineering" AND (all:"signal" OR all:"factor")',
    'all:"portfolio optimization" AND (all:"reinforcement learning" OR all:"neural")',
    'cat:q-fin.TR AND (all:"transformer" OR all:"attention")',
]

ARXIV_CATEGORIES = ["q-fin.TR", "q-fin.PM", "q-fin.CP", "q-fin.ST", "cs.LG", "cs.AI"]
MIN_YEAR = datetime.now().year - 5

# 补充已知高质量论文（arXiv ID）
CURATED_ARXIV_IDS = [
    "2409.06289",   # Automate Strategy Finding with LLM in Quant Investment
    "2307.10485",   # FinGPT
    "2402.18485",   # FinAgent
    "2406.14540",   # MarketSenseAI
    "2312.11818",   # Alpha-GPT
    "2403.07974",   # FinMem
    "2410.03777",   # FinRobot
    "2501.10709",   # recent quant LLM
]


def _load_manifest() -> dict:
    if SEED_MANIFEST.exists():
        return json.loads(SEED_MANIFEST.read_text(encoding="utf-8"))
    return {"seed_papers": [], "research_focus": {}, "created_at": datetime.now().isoformat()}


def _save_manifest(data: dict) -> None:
    SEED_PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    SEED_MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_filename(arxiv_id: str, title: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", title)[:50].strip("_")
    return f"{arxiv_id}_{slug}.pdf" if slug else f"{arxiv_id}.pdf"


def _paper_year(paper: dict) -> int:
    y = paper.get("year")
    if y:
        return int(y)
    pub = paper.get("published", "")
    if pub and len(pub) >= 4:
        try:
            return int(pub[:4])
        except ValueError:
            pass
    return 0


def list_seed_papers() -> List[dict]:
    """返回种子文献列表（含本地下载状态与 PDF URL）。"""
    manifest = _load_manifest()
    papers = []
    for p in manifest.get("seed_papers", []):
        pid = p.get("id")
        fname = p.get("file", "")
        pdf_path = SEED_PAPERS_DIR / fname if fname else None
        has_pdf = pdf_path.exists() if pdf_path else False
        papers.append({
            **p,
            "has_pdf": has_pdf,
            "pdf_url": f"/api/seed-papers/{pid}/pdf" if pid else None,
            "arxiv_url": f"https://arxiv.org/abs/{p.get('arxiv_id', '')}" if p.get("arxiv_id") else None,
        })
    return papers


def get_seed_paper(paper_id: int) -> Optional[dict]:
    for p in list_seed_papers():
        if p.get("id") == paper_id:
            return p
    return None


def get_pdf_path(paper_id: int) -> Optional[Path]:
    paper = get_seed_paper(paper_id)
    if not paper or not paper.get("file"):
        return None
    path = SEED_PAPERS_DIR / paper["file"]
    return path if path.exists() else None


def _arxiv_fetch(query: str, max_results: int = 15) -> List[dict]:
    import arxiv

    results = []
    search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate)
    client = arxiv.Client()
    for paper in client.results(search):
        arxiv_id = paper.entry_id.split("/")[-1].replace("v", "").split("v")[0]
        # normalize id without version suffix for dedup
        base_id = re.sub(r"v\d+$", "", paper.entry_id.split("/")[-1])
        year = paper.published.year if paper.published else 0
        if year < MIN_YEAR:
            continue
        cats = paper.categories or []
        if ARXIV_CATEGORIES and not any(
            any(cat.startswith(c.rstrip("*")) for cat in cats) for c in ARXIV_CATEGORIES
        ):
            # allow if title clearly finance/LLM related
            text = (paper.title + " " + paper.summary).lower()
            if not any(k in text for k in ("quant", "financ", "trading", "alpha", "llm", "portfolio")):
                continue
        results.append({
            "title": paper.title.replace("\n", " "),
            "authors": ", ".join(a.name for a in paper.authors[:5]),
            "abstract": paper.summary.replace("\n", " "),
            "arxiv_id": base_id,
            "year": year,
            "published": paper.published.strftime("%Y-%m-%d") if paper.published else "",
            "categories": cats,
            "venue": paper.journal_ref or paper.comment or "arXiv",
            "pdf_url_remote": paper.pdf_url,
        })
    return results


def _download_pdf(arxiv_id: str, filename: str) -> Optional[Path]:
    import time
    import requests

    dest = SEED_PAPERS_DIR / filename
    SEED_PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest

    clean_id = re.sub(r"v\d+$", "", arxiv_id)
    pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"

    for attempt in range(3):
        try:
            resp = requests.get(pdf_url, timeout=60, headers={"User-Agent": "paperwriterAI/1.0"})
            if resp.status_code == 429:
                time.sleep(8 * (attempt + 1))
                continue
            resp.raise_for_status()
            if len(resp.content) < 1000:
                time.sleep(3)
                continue
            dest.write_bytes(resp.content)
            return dest
        except Exception as e:
            print(f"[seed_library] PDF download attempt {attempt + 1} failed {arxiv_id}: {e}")
            time.sleep(5 * (attempt + 1))

    # fallback: arxiv client
    try:
        import arxiv
        import time as _time

        _time.sleep(3)
        paper = next(arxiv.Client().results(arxiv.Search(id_list=[clean_id])))
        paper.download_pdf(dirpath=str(SEED_PAPERS_DIR), filename=filename)
        return dest if dest.exists() else None
    except Exception as e:
        print(f"[seed_library] PDF download failed {arxiv_id}: {e}")
        return None


def fetch_new_papers(target_count: int = 15, max_total: int = 20) -> Dict[str, Any]:
    """
    从 arXiv 检索并下载近五年相关论文，补足至 target_count 篇新论文（上限 max_total）。
  已有 manifest 中的 arXiv ID 不重复下载。
    """
    manifest = _load_manifest()
    existing = manifest.get("seed_papers", [])
    existing_ids = {p.get("arxiv_id", "").split("v")[0] for p in existing}
    next_id = max((p.get("id", 0) for p in existing), default=0) + 1

    candidates: Dict[str, dict] = {}

    # 1) 检索
    for q in ARXIV_QUERIES:
        for p in _arxiv_fetch(q, max_results=12):
            aid = p["arxiv_id"]
            if aid not in existing_ids and aid not in candidates:
                candidates[aid] = p

    # 2) 策展列表
    for aid in CURATED_ARXIV_IDS:
        if aid in existing_ids or aid in candidates:
            continue
        try:
            fetched = _arxiv_fetch(f"id:{aid}", max_results=1)
            if fetched:
                candidates[aid] = fetched[0]
        except Exception:
            pass

    # 按年份降序
    ordered = sorted(candidates.values(), key=lambda x: _paper_year(x), reverse=True)
    to_add = ordered[: min(target_count, max_total)]

    downloaded = []
    failed = []

    for p in to_add:
        fname = _safe_filename(p["arxiv_id"], p["title"])
        pdf_path = _download_pdf(p["arxiv_id"], fname)
        if not pdf_path:
            failed.append(p["arxiv_id"])
            continue

        import time
        time.sleep(2)

        entry = {
            "id": next_id,
            "arxiv_id": p["arxiv_id"],
            "title": p["title"],
            "authors": p.get("authors", ""),
            "year": p.get("year"),
            "venue": p.get("venue", "arXiv"),
            "file": fname,
            "path": f"./seed_papers/{fname}",
            "abstract": p.get("abstract", "")[:500],
            "key_topics": _infer_topics(p),
            "citation_count": 0,
            "source": "arxiv_fetch",
            "fetched_at": datetime.now().isoformat(),
        }
        existing.append(entry)
        existing_ids.add(p["arxiv_id"])
        downloaded.append(entry)
        next_id += 1

    manifest["seed_papers"] = existing
    manifest["total_count"] = len(existing)
    _save_manifest(manifest)

    return {
        "success": True,
        "downloaded_count": len(downloaded),
        "failed_count": len(failed),
        "failed_ids": failed,
        "total_in_library": len(existing),
        "papers": downloaded,
    }


def _infer_topics(paper: dict) -> List[str]:
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    topics = []
    mapping = {
        "LLM": ["llm", "language model", "gpt"],
        "量化交易": ["quant", "trading", "alpha"],
        "多智能体": ["multi-agent", "agent"],
        "金融工程": ["financial engineering", "portfolio", "risk"],
        "信号系统": ["signal", "factor", "momentum"],
        "深度学习": ["deep learning", "neural", "transformer"],
    }
    for label, keys in mapping.items():
        if any(k in text for k in keys):
            topics.append(label)
    return topics or ["量化金融"]
