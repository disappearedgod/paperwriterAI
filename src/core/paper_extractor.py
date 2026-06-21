"""
种子论文提取器 — 从所有 PDF 提取文本并生成摘要，供后续分析使用。
修复了旧 extract_papers.py 只处理前5篇的问题。
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber

from core.data_registry import SEED_PAPERS_DIR, SEED_MANIFEST

# 每个 PDF 最多读取前 N 页（平衡信息量与速度）
MAX_PAGES = 20


def _load_manifest() -> dict:
    if SEED_MANIFEST.exists():
        return json.loads(SEED_MANIFEST.read_text(encoding="utf-8"))
    return {"seed_papers": []}


def _paper_summary_path(arxiv_id: str) -> Path:
    return SEED_PAPERS_DIR / f"{arxiv_id}_summary.json"


def _combined_summaries_path() -> Path:
    """
    沙盒限制：seed_papers/ 目录禁止 Python 新建/覆盖文件。
    已写入 data/research/combined_summaries_deduped.json (手动 cp 后的去重版)。
    为保证兼容性，同时查找两个路径，优先返回存在的文件。
    """
    primary = SEED_PAPERS_DIR.parent / "research" / "combined_summaries.json"
    deduped = SEED_PAPERS_DIR.parent / "research" / "combined_summaries_deduped.json"
    fallback = SEED_PAPERS_DIR / "combined_summaries.json"
    if deduped.exists():
        return deduped
    if primary.exists():
        return primary
    return fallback


def _paper_analysis_path() -> Path:
    return SEED_PAPERS_DIR.parent.parent / "research" / "seed_paper_analysis.md"


def extract_pdf_text(pdf_path: str | Path, max_pages: int = MAX_PAGES) -> Dict[str, Any]:
    """从 PDF 提取文本，返回结构化结果。"""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {"error": f"File not found: {pdf_path}", "pages": 0, "text": ""}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            pages_to_read = min(max_pages, total_pages)
            texts = []
            for i, page in enumerate(pdf.pages[:pages_to_read]):
                text = page.extract_text()
                if text:
                    texts.append(f"--- Page {i + 1} ---\n{text}")

            combined = "\n\n".join(texts)
            return {
                "pages": total_pages,
                "pages_read": pages_to_read,
                "text": combined,
                "first_page": texts[0][18:] if texts else "",  # strip "--- Page 1 ---\n"
                "char_count": len(combined),
            }
    except Exception as e:
        return {"error": str(e), "pages": 0, "text": ""}


def extract_single_paper(arxiv_id: str, pdf_path: Path) -> Optional[Dict[str, Any]]:
    """提取单篇论文，返回摘要 JSON。"""
    result = extract_pdf_text(pdf_path)
    if result.get("error"):
        return None

    return {
        "arxiv_id": arxiv_id,
        "paper": pdf_path.name,
        "total_pages": result["pages"],
        "pages_extracted": result["pages_read"],
        "char_count": result["char_count"],
        "first_page_preview": result.get("first_page", "")[:2000],
        "text_preview": result["text"][:3000],  # 供 LLM 分析用
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _save_summary_json(arxiv_id: str, data: Dict[str, Any]) -> bool:
    """
    保存单篇摘要 JSON。
    优先写入 seed_papers/ 目录；若沙盒阻止则写入 data/research/ 目录。
    """
    # 优先尝试 seed_papers 目录
    primary = _paper_summary_path(arxiv_id)
    fallback = SEED_PAPERS_DIR.parent.parent / "research" / "summaries" / f"{arxiv_id}_summary.json"

    for path in [primary, fallback]:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            continue
    return False


def _load_combined() -> List[Dict]:
    """加载 combined_summaries.json（容错），并修复旧记录缺失 arxiv_id 的问题。"""
    path = _combined_summaries_path()
    if path.exists():
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
            # 修复旧记录：用文件名中的 arXiv ID 补全 arxiv_id 字段
            for item in items:
                if not item.get("arxiv_id") and item.get("paper"):
                    fname = item["paper"]
                    # 文件名格式: 2408.06361_LLM_Agent_Financial_Trading_Survey.pdf
                    m = re.match(r"^(\d{4}\.\d{5})_", fname)
                    if m:
                        item["arxiv_id"] = m.group(1)
            return items
        except Exception:
            pass
    return []


def _save_combined(combined: List[Dict]) -> bool:
    """保存 combined_summaries.json（容错）"""
    path = _combined_summaries_path()
    try:
        path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"[paper_extractor] cannot write combined_summaries: {e}")
        return False


def extract_all_papers(progress_callback=None) -> Dict[str, Any]:
    """
    提取 manifest 中所有已有 PDF 的论文文本。
    返回提取结果统计。
    所有摘要统一追加到 combined_summaries.json（去重）。
    """
    manifest = _load_manifest()
    papers = manifest.get("seed_papers", [])

    # 加载已有 combined（去重用）
    combined = _load_combined()
    existing_ids = {r.get("arxiv_id") for r in combined}

    extracted = []
    skipped_no_pdf = []
    skipped_already_done = []
    errors = []

    for i, paper in enumerate(papers):
        arxiv_id = paper.get("arxiv_id", "")
        fname = paper.get("file", "")
        if not fname:
            skipped_no_pdf.append({"id": paper.get("id"), "reason": "no filename"})
            continue

        pdf_path = SEED_PAPERS_DIR / fname
        if not pdf_path.exists():
            skipped_no_pdf.append({"id": paper.get("id"), "arxiv_id": arxiv_id, "file": fname})
            continue

        if arxiv_id in existing_ids:
            skipped_already_done.append({"arxiv_id": arxiv_id, "file": fname})
            if progress_callback:
                progress_callback(i + 1, len(papers), arxiv_id, "already_done")
            continue

        # 执行提取
        result = extract_single_paper(arxiv_id, pdf_path)
        if result:
            combined.append(result)
            existing_ids.add(arxiv_id)
            _save_summary_json(arxiv_id, result)

            extracted.append({
                "arxiv_id": arxiv_id,
                "file": fname,
                "status": "extracted",
                "pages": result["total_pages"],
                "chars": result["char_count"],
            })
            if progress_callback:
                progress_callback(i + 1, len(papers), arxiv_id, "extracted")
        else:
            errors.append({"arxiv_id": arxiv_id, "file": fname})
            if progress_callback:
                progress_callback(i + 1, len(papers), arxiv_id, "error")

        time.sleep(0.3)  # 防止 IO 过载

    # 一次性保存 combined
    _save_combined(combined)

    return {
        "total": len(papers),
        "extracted": len(extracted),
        "already_done": len(skipped_already_done),
        "skipped_no_pdf": len(skipped_no_pdf),
        "errors": len(errors),
        "details": {
            "extracted": extracted,
            "already_done": skipped_already_done,
            "no_pdf": skipped_no_pdf,
            "errors": errors,
        },
    }


def get_library_status() -> Dict[str, Any]:
    """返回种子文献库完整状态：哪些有 PDF，哪些有摘要，哪些缺 PDF。"""
    manifest = _load_manifest()
    papers = manifest.get("seed_papers", [])

    with_pdf = []
    without_pdf = []
    with_summary = []
    without_summary = []

    for paper in papers:
        arxiv_id = paper.get("arxiv_id", "")
        fname = paper.get("file", "")
        pid = paper.get("id")

        if fname:
            pdf_path = SEED_PAPERS_DIR / fname
            has_pdf = pdf_path.exists()
        else:
            has_pdf = False

        summary_path = _paper_summary_path(arxiv_id) if arxiv_id else None
        has_summary = bool(summary_path and summary_path.exists())

        entry = {
            "id": pid,
            "arxiv_id": arxiv_id,
            "title": paper.get("title", "")[:80],
            "file": fname,
            "has_pdf": has_pdf,
            "has_summary": has_summary,
        }

        if has_pdf:
            with_pdf.append(entry)
        else:
            without_pdf.append(entry)

        if has_summary:
            with_summary.append(entry)
        else:
            without_summary.append(entry)

    return {
        "total": len(papers),
        "with_pdf": len(with_pdf),
        "without_pdf": len(without_pdf),
        "with_summary": len(with_summary),
        "without_summary": len(without_summary),
        "needs_extraction": [e for e in without_summary if e["has_pdf"]],
        "missing_pdf": without_pdf,
        "all_papers": with_pdf + without_pdf,
    }


def get_paper_text(arxiv_id: str, max_chars: int = 8000) -> Optional[str]:
    """获取已提取的论文文本（前 max_chars 字符）。"""
    # 优先从 combined_summaries.json 读取
    combined = _load_combined()
    for item in combined:
        if item.get("arxiv_id") == arxiv_id:
            return item.get("text_preview", "")[:max_chars]

    # 次查单独文件
    for path in [_paper_summary_path(arxiv_id),
                 SEED_PAPERS_DIR.parent.parent / "research" / "summaries" / f"{arxiv_id}_summary.json"]:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("text_preview", "")[:max_chars]
            except Exception:
                pass
    return None


def get_all_paper_texts(max_chars_per_paper: int = 6000) -> List[Dict[str, str]]:
    """获取所有已提取论文的文本，供 LLM 分析用。"""
    manifest = _load_manifest()
    papers = {p.get("arxiv_id"): p for p in manifest.get("seed_papers", [])}
    combined = _load_combined()
    result = []
    for item in combined:
        arxiv_id = item.get("arxiv_id")
        paper = papers.get(arxiv_id, {})
        result.append({
            "arxiv_id": arxiv_id,
            "title": paper.get("title", item.get("paper", "")),
            "authors": paper.get("authors", ""),
            "year": paper.get("year", ""),
            "key_topics": paper.get("key_topics", []),
            "text": item.get("text_preview", "")[:max_chars_per_paper],
            "pages": item.get("total_pages", 0),
            "char_count": item.get("char_count", 0),
        })
    return result


def regenerate_analysis() -> str:
    """使用已有摘要数据重建 seed_paper_analysis.md（不含 LLM 调用，纯结构化生成）。"""
    manifest = _load_manifest()
    papers = manifest.get("seed_papers", [])
    summaries = {}

    for paper in papers:
        arxiv_id = paper.get("arxiv_id", "")
        sp = _paper_summary_path(arxiv_id)
        if sp.exists():
            try:
                summaries[arxiv_id] = json.loads(sp.read_text(encoding="utf-8"))
            except Exception:
                pass

    lines = ["# 种子论文主题分析\n"]
    lines.append(f"\n*生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n")
    lines.append(f"\n共收录 {len(papers)} 篇论文，其中 {len(summaries)} 篇已完成文本提取。\n")
    lines.append("\n---\n\n## 论文概览\n")

    for paper in papers:
        arxiv_id = paper.get("arxiv_id", "")
        pid = paper.get("id", "?")
        title = paper.get("title", "未知")
        authors = paper.get("authors", "未知")[:60]
        year = paper.get("year", "?")
        topics = ", ".join(paper.get("key_topics", []))
        fname = paper.get("file", "")

        sum_data = summaries.get(arxiv_id, {})
        pages = sum_data.get("total_pages", "?")
        chars = sum_data.get("char_count", 0)
        status = "✅ 已提取" if arxiv_id in summaries else "⚠️ 未提取"

        lines.append(f"\n### 论文{pid}: {arxiv_id} ({year})\n")
        lines.append(f"- **标题**: {title}\n")
        lines.append(f"- **作者**: {authors}\n")
        lines.append(f"- **主题**: {topics}\n")
        lines.append(f"- **页数**: {pages} 页\n")
        lines.append(f"- **字符数**: {chars:,}\n")
        lines.append(f"- **状态**: {status}\n")

    # 主题分类汇总
    topic_groups: Dict[str, List] = {}
    for paper in papers:
        for topic in paper.get("key_topics", []):
            if topic not in topic_groups:
                topic_groups[topic] = []
            topic_groups[topic].append({
                "id": paper.get("id"),
                "arxiv_id": paper.get("arxiv_id"),
                "title": paper.get("title", "")[:60],
            })

    lines.append("\n---\n\n## 主题分类汇总\n")
    for topic, pts in sorted(topic_groups.items(), key=lambda x: -len(x[1])):
        lines.append(f"\n### {topic} ({len(pts)} 篇)\n")
        for p in pts:
            lines.append(f"- [{p['arxiv_id']}] {p['title']}\n")

    # 缺失 PDF 列表
    no_pdf = [p for p in papers if not p.get("file") or not (SEED_PAPERS_DIR / p["file"]).exists()]
    if no_pdf:
        lines.append("\n---\n\n## ⚠️ 缺失 PDF 的论文\n")
        for p in no_pdf:
            lines.append(f"- [{p.get('arxiv_id')}] {p.get('title', '')}\n")

    content = "".join(lines)

    # 保存
    out_path = _paper_analysis_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    return content
