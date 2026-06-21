"""
研究图谱构建器：作者合作网络与引用关系网络。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

from pypdf import PdfReader

from core.seed_library import get_pdf_path


def build_author_network_from_seed_papers(papers: List[dict]) -> Dict[str, Any]:
    if not papers:
        return {"authors": [], "institutions": [], "papers": [], "collaborations": []}

    def _norm_name(name: str) -> str:
        n = (name or "").strip().lower()
        n = re.sub(r"\s+", " ", n)
        n = re.sub(r"[^a-z0-9\u4e00-\u9fff _.-]+", "", n)
        return n

    def _make_id(prefix: str, raw: str) -> str:
        h = hashlib.md5((raw or "").encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{h}"

    def _inst_type(name: str) -> str:
        n = name or ""
        if any(k in n for k in ("大学", "学院", "University", "College", "Institute of Technology", "School of")):
            return "university"
        if any(k in n for k in ("公司", "Inc", "Corp", "Ltd", "Research", "研究院", "实验室", "Laboratory", "Lab", "AI Lab", "Group")):
            return "company"
        return "university"

    def _extract_institutions_from_pdf(sp: dict) -> List[str]:
        val = sp.get("institutions")
        if isinstance(val, list) and val:
            return [str(x).strip() for x in val if str(x).strip()]
        inst = sp.get("institution")
        if isinstance(inst, str) and inst.strip():
            return [inst.strip()]

        pid = sp.get("id")
        pdf_path = get_pdf_path(pid) if pid is not None else None
        if not pdf_path:
            return []

        try:
            reader = PdfReader(str(pdf_path))
            if not reader.pages:
                return []
            text = reader.pages[0].extract_text() or ""
        except Exception:
            return []

        text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " ", text)
        tokens = [re.sub(r"\s+", " ", t).strip() for t in re.split(r"[\n;]+", text)]
        hits: List[str] = []
        keywords = (
            "University",
            "College",
            "Institute",
            "Laboratory",
            "Lab",
            "School of",
            "Academy",
            "Inc",
            "Corp",
            "Ltd",
            "Company",
            "大学",
            "学院",
            "研究院",
            "实验室",
            "公司",
        )
        for t in tokens:
            s = t.strip()
            if not s or len(s) < 6:
                continue
            low = s.lower()
            if any(bad in low for bad in ("http://", "https://", "www.", "github", "arxiv")):
                continue
            if any(k in s for k in keywords):
                s = re.sub(r"\b(\d+|[*†‡]+)\b", " ", s).strip()
                s = re.sub(r"\s{2,}", " ", s)
                if 8 <= len(s) <= 120:
                    hits.append(s)

        uniq: List[str] = []
        seen = set()
        for h in hits:
            key = h.lower()
            if key not in seen:
                seen.add(key)
                uniq.append(h)
        return uniq[:4]

    institutions_map: Dict[str, Dict[str, Any]] = {}
    authors_map: Dict[str, Dict[str, Any]] = {}
    collab_map: Dict[str, Dict[str, Any]] = {}
    paper_records: List[Dict[str, Any]] = []

    for sp in papers:
        paper_id = sp.get("arxiv_id") or str(sp.get("id") or "")
        paper_title = sp.get("title") or paper_id
        raw = sp.get("authors") or ""
        names = [a.strip() for a in raw.split(",") if a.strip()]
        insts = _extract_institutions_from_pdf(sp)
        if not insts:
            insts = ["未知机构"]

        inst_ids: List[str] = []
        for inst in insts:
            if inst not in institutions_map:
                institutions_map[inst] = {
                    "id": _make_id("inst", inst),
                    "name": inst,
                    "type": _inst_type(inst),
                }
            inst_ids.append(institutions_map[inst]["id"])

        paper_records.append({"id": paper_id, "title": paper_title, "authors": names, "institutions": insts})

        author_ids: List[str] = []
        for idx, name in enumerate(names):
            role = "other"
            if idx == 0:
                role = "first"
            elif idx == 1:
                role = "second"
            if names and idx == len(names) - 1 and len(names) > 1:
                role = "corresponding"

            norm = _norm_name(name)
            if not norm:
                continue
            aid = _make_id("author", norm)
            author_ids.append(aid)
            if aid not in authors_map:
                authors_map[aid] = {
                    "id": aid,
                    "name": name,
                    "role": role,
                    "institutions": [],
                    "institution_ids": [],
                    "paper_ids": [],
                }

            a = authors_map[aid]
            if role in ("first", "corresponding"):
                a["role"] = role
            if paper_id not in a["paper_ids"]:
                a["paper_ids"].append(paper_id)
            for inst_name, inst_id in zip(insts, inst_ids):
                if inst_name not in a["institutions"]:
                    a["institutions"].append(inst_name)
                if inst_id not in a["institution_ids"]:
                    a["institution_ids"].append(inst_id)

        for i in range(len(author_ids)):
            for j in range(i + 1, len(author_ids)):
                a1, a2 = sorted([author_ids[i], author_ids[j]])
                key = f"{a1}__{a2}"
                if key not in collab_map:
                    collab_map[key] = {"author1": a1, "author2": a2, "weight": 0, "paper_ids": []}
                collab_map[key]["weight"] += 1
                if paper_id not in collab_map[key]["paper_ids"]:
                    collab_map[key]["paper_ids"].append(paper_id)

    return {
        "authors": list(authors_map.values()),
        "institutions": list(institutions_map.values()),
        "papers": paper_records,
        "collaborations": list(collab_map.values()),
    }


def _tokenize_for_overlap(text: str) -> List[str]:
    t = (text or "").lower()
    parts = re.split(r"[^a-z0-9\u4e00-\u9fff]+", t)
    return [p for p in parts if p and len(p) >= 2]


def build_citation_network(*, papers_data: dict, seed_papers: List[dict]) -> Dict[str, Any]:
    ai_papers = []
    for p in papers_data.get("papers") or []:
        ai_papers.append({
            "id": f"paper_{p.get('id')}",
            "title": p.get("title") or (p.get("topic") or f"paper_{p.get('id')}"),
            "status": p.get("status") or "generated",
            "arxiv": p.get("research_id") or None,
        })

    references = []
    for i, sp in enumerate(seed_papers or [], start=1):
        sid = sp.get("id") or i
        references.append({
            "id": f"ref_{sid}",
            "title": sp.get("title") or f"ref_{sid}",
            "authors": sp.get("authors") or "",
            "arxiv": sp.get("arxiv_id") or None,
            "year": sp.get("year"),
            "key_contribution": ", ".join(sp.get("key_topics") or []),
            "key_topics": sp.get("key_topics") or [],
        })

    ref_tokens = {}
    for r in references:
        txt = " ".join([r.get("title") or "", r.get("key_contribution") or ""])
        ref_tokens[r["id"]] = set(_tokenize_for_overlap(txt))

    edges = []
    ref_ids = [r["id"] for r in references]
    for i in range(len(ref_ids)):
        for j in range(i + 1, len(ref_ids)):
            r1, r2 = ref_ids[i], ref_ids[j]
            s1, s2 = ref_tokens.get(r1) or set(), ref_tokens.get(r2) or set()
            inter = s1 & s2
            if len(inter) >= 2:
                w = min(1.0, len(inter) / 8.0)
                edges.append({"source": r1, "target": r2, "type": "bibliographic_coupling", "weight": float(max(0.1, w))})

    cited_by_paper: Dict[str, List[str]] = {}
    for ap in ai_papers:
        pid = ap["id"]
        paper_obj = next((x for x in (papers_data.get("papers") or []) if f"paper_{x.get('id')}" == pid), None)
        ptxt = " ".join([ap.get("title") or "", (paper_obj or {}).get("topic") or "", (paper_obj or {}).get("content_preview") or ""])
        ptokens = set(_tokenize_for_overlap(ptxt))
        if not ptokens:
            continue
        scored = []
        for ref in references:
            rt = ref_tokens.get(ref["id"]) or set()
            if not rt:
                continue
            overlap = len(ptokens & rt)
            denom = max(1, min(len(ptokens), len(rt)))
            w = overlap / denom
            if w >= 0.08:
                scored.append((w, ref["id"]))
        scored.sort(reverse=True)
        top = scored[:8]
        cited = []
        for w, rid in top:
            edges.append({"source": pid, "target": rid, "type": "citation", "weight": float(min(1.0, max(0.1, w)))})
            cited.append(rid)
        cited_by_paper[pid] = cited

    paper_ids = [p["id"] for p in ai_papers]
    for i in range(len(paper_ids)):
        for j in range(i + 1, len(paper_ids)):
            p1, p2 = paper_ids[i], paper_ids[j]
            s1, s2 = set(cited_by_paper.get(p1) or []), set(cited_by_paper.get(p2) or [])
            inter = s1 & s2
            if len(inter) >= 2:
                w = min(1.0, len(inter) / 6.0)
                edges.append({"source": p1, "target": p2, "type": "co_citation", "weight": float(max(0.1, w))})

    return {"aiPapers": ai_papers, "references": references, "edges": edges}
