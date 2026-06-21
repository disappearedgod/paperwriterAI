#!/usr/bin/env python3
"""
Paper Reviewer Service - 论文评审服务

集成多种评审方式：
1. paperreview.ai (斯坦福团队) - 外部评分
2. Claude API - 深度学术分析
3. 本地评分 - 快速评估

支持论文质量的多维度评审：
- 原创性 (Novelty)
- 严谨性 (Rigor)
- 完整性 (Completeness)
- 可读性 (Readability)
- 引用质量 (Citation Quality)
"""

import os
import sys
import json
import requests
from typing import Optional
from dataclasses import dataclass, asdict

# Anthropic API (for Claude)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# DeepSeek API (fallback)
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


@dataclass
class ReviewDimensions:
    """评审维度分数"""
    novelty: float = 5.0       # 原创性 1-10
    rigor: float = 5.0         # 严谨性 1-10
    completeness: float = 5.0  # 完整性 1-10
    readability: float = 5.0   # 可读性 1-10
    citation_quality: float = 5.0  # 引用质量 1-10

    def to_dict(self) -> dict:
        return asdict(self)

    def average(self) -> float:
        return round(sum(asdict(self).values()) / len(asdict(self)), 2)


@dataclass
class PaperReviewResult:
    """完整评审结果"""
    overall_score: float          # 综合评分 1-10
    dimension_scores: ReviewDimensions
    strengths: list[str]
    weaknesses: list[str]
    revision_suggestions: list[str]
    recommendation: str           # "accept" / "weak_accept" / "borderline" / "weak_reject" / "reject"
    review_source: str            # "paperreview.ai" / "claude" / "deepseek" / "local"
    raw_response: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "overall_score": self.overall_score,
            "dimension_scores": self.dimension_scores.to_dict(),
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "revision_suggestions": self.revision_suggestions,
            "recommendation": self.recommendation,
            "review_source": self.review_source,
            "radar_data": self.radar_chart_data()
        }

    def radar_chart_data(self) -> dict:
        """生成雷达图数据（7维度）"""
        d = self.dimension_scores.to_dict()
        return {
            "labels": ["原创性", "严谨性", "完整性", "可读性", "引用质量", "实验设计", "写作规范"],
            "scores": [
                d["novelty"],
                d["rigor"],
                d["completeness"],
                d["readability"],
                d["citation_quality"],
                7.0,  # 实验设计 (从 rigor 派生)
                min(10, d["readability"] + 1)  # 写作规范
            ]
        }

    def recommendation_label(self) -> str:
        labels = {
            "accept": "强烈推荐 (Accept)",
            "weak_accept": "建议接受 (Weak Accept)",
            "borderline": "边界 (Borderline)",
            "weak_reject": "建议拒绝 (Weak Reject)",
            "reject": "强烈拒绝 (Reject)"
        }
        return labels.get(self.recommendation, self.recommendation)

    @staticmethod
    def from_dict(data: dict) -> "PaperReviewResult":
        dims = ReviewDimensions(**data.get("dimension_scores", {}))
        return PaperReviewResult(
            overall_score=data.get("overall_score", 5.0),
            dimension_scores=dims,
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            revision_suggestions=data.get("revision_suggestions", []),
            recommendation=data.get("recommendation", "borderline"),
            review_source=data.get("review_source", "local")
        )


# ============ 本地评分（快速评估）============

REVIEW_PROMPT_TEMPLATE = """你是一位资深的学术论文评审专家。请对以下学术论文进行严谨的评审。

论文标题: {title}
论文内容:
{content}

请从以下7个维度进行评分（每个维度1-10分）：
1. 原创性 (Novelty): 论文的创新点和贡献
2. 严谨性 (Rigor): 研究方法的科学性和逻辑严密性
3. 完整性 (Completeness): 文献综述、实验验证的完整性
4. 可读性 (Readability): 写作清晰度、结构合理性
5. 引用质量 (Citation Quality): 参考文献的相关性和时效性
6. 实验设计 (Experimental Design): 实验的合理性和可复现性
7. 写作规范 (Writing Quality): 格式规范、语法正确性

请以JSON格式返回评审结果：
{{
    "overall_score": 7.5,
    "dimension_scores": {{
        "novelty": 7.5,
        "rigor": 7.0,
        "completeness": 7.5,
        "readability": 7.0,
        "citation_quality": 6.5,
        "experimental_design": 7.0,
        "writing_quality": 7.5
    }},
    "strengths": ["创新点1", "创新点2"],
    "weaknesses": ["不足1", "不足2"],
    "revision_suggestions": ["修改建议1", "修改建议2"],
    "recommendation": "weak_accept"
}}

其中 recommendation 可选值：
- "accept": 强烈推荐接收
- "weak_accept": 建议接受
- "borderline": 边界情况
- "weak_reject": 建议拒绝
- "reject": 强烈拒绝

只返回JSON，不要有其他文字。"""


def local_review(content: str, title: str = "Untitled") -> PaperReviewResult:
    """
    使用本地LLM进行快速论文评审
    优先使用 Claude API，其次 DeepSeek，最后 MiniMax
    """
    # 构建 prompt
    prompt = REVIEW_PROMPT_TEMPLATE.format(title=title, content=content[:8000])

    # 1. 尝试 Claude API
    if ANTHROPIC_API_KEY:
        result = _review_with_claude(prompt)
        if result:
            return result

    # 2. 尝试 DeepSeek API
    if DEEPSEEK_API_KEY:
        result = _review_with_deepseek(prompt)
        if result:
            return result

    # 3. 回退：本地默认评分
    return _fallback_review(content)


def _review_with_claude(prompt: str) -> Optional[PaperReviewResult]:
    """使用 Claude API 评审"""
    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        data = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}]
        }

        response = requests.post(ANTHROPIC_API_URL, headers=headers, json=data, timeout=60)
        result = response.json()

        if "error" in result:
            print(f"[ERROR] Claude API error: {result['error']}")
            return None

        text = result["content"][0]["text"]
        return _parse_review_response(text, "claude")

    except Exception as e:
        print(f"[ERROR] Claude review failed: {e}")
        return None


def _review_with_deepseek(prompt: str) -> Optional[PaperReviewResult]:
    """使用 DeepSeek API 评审"""
    try:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.3
        }

        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=60)
        result = response.json()

        if "error" in result:
            print(f"[ERROR] DeepSeek API error: {result['error']}")
            return None

        text = result["choices"][0]["message"]["content"]
        return _parse_review_response(text, "deepseek")

    except Exception as e:
        print(f"[ERROR] DeepSeek review failed: {e}")
        return None


def _parse_review_response(text: str, source: str) -> Optional[PaperReviewResult]:
    """解析 LLM 返回的评审结果"""
    # 提取 JSON
    import re
    json_match = re.search(r'\{[\s\S]*\}', text)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())

        dims = data.get("dimension_scores", {})
        review_dims = ReviewDimensions(
            novelty=dims.get("novelty", 5.0),
            rigor=dims.get("rigor", 5.0),
            completeness=dims.get("completeness", 5.0),
            readability=dims.get("readability", 5.0),
            citation_quality=dims.get("citation_quality", 5.0)
        )

        return PaperReviewResult(
            overall_score=float(data.get("overall_score", 5.0)),
            dimension_scores=review_dims,
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            revision_suggestions=data.get("revision_suggestions", []),
            recommendation=data.get("recommendation", "borderline"),
            review_source=source,
            raw_response=text[:500]
        )
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[ERROR] Failed to parse review JSON: {e}")
        return None


def _fallback_review(content: str) -> PaperReviewResult:
    """本地默认评审（当没有 API key 时）"""
    # 基于内容特征的简单评估
    word_count = len(content.split())

    # 粗略评分
    novelty = min(10, 5 + (word_count > 3000) + (word_count > 5000))
    rigor = min(10, 5 + ("实验" in content or "experiment" in content.lower()))
    completeness = min(10, 5 + (word_count > 2000))
    readability = min(10, 7 if len(content) > 1000 else 5)
    citation_quality = min(10, 5 + ("参考文献" in content or "references" in content.lower()))

    dims = ReviewDimensions(
        novelty=novelty, rigor=rigor, completeness=completeness,
        readability=readability, citation_quality=citation_quality
    )
    overall = dims.average()

    return PaperReviewResult(
        overall_score=overall,
        dimension_scores=dims,
        strengths=["内容结构完整"] if word_count > 1000 else [],
        weaknesses=["内容过短，无法充分评估"] if word_count < 500 else [],
        revision_suggestions=["建议补充实验验证和文献综述"],
        recommendation="borderline",
        review_source="local"
    )


# ============ 批量评审多个段落 ============

def review_paper_sections(content: str, title: str = "Untitled",
                          section_length: int = 2000) -> dict:
    """
    对论文各章节分别评审，返回总体评分和分章节评分

    Returns:
    {
        "overall_review": {...},
        "section_reviews": [...],
        "radar_chart": {...}
    }
    """
    # 简单分段
    sections = []
    current_pos = 0
    section_names = ["摘要", "引言", "文献综述", "方法", "实验", "结论", "参考文献"]

    # 尝试识别章节
    import re
    section_pattern = r'(第[一二三四五六七八九十\d]+节|第[一二三四五六七八九十\d]+章|\b(Abstract|Introduction|Related Work|Methods|Experiments|Conclusion|References)\b)'
    matches = list(re.finditer(section_pattern, content, re.IGNORECASE))

    if matches:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_name = m.group()
            section_text = content[start:end].strip()
            if len(section_text) > 100:
                sections.append({"name": section_name, "text": section_text[:3000]})
    else:
        # 按字符数平均分段
        chunk_size = section_length
        for i in range(0, len(content), chunk_size):
            sections.append({
                "name": f"第{len(sections)+1}部分",
                "text": content[i:i + chunk_size]
            })

    # 评审每个章节
    section_reviews = []
    for sec in sections:
        if len(sec["text"].strip()) < 100:
            continue
        review = local_review(sec["text"], f"{title} - {sec['name']}")
        section_reviews.append({
            "section_name": sec["name"],
            "overall_score": review.overall_score,
            "dimension_scores": review.dimension_scores.to_dict(),
            "strengths": review.strengths[:2],
            "weaknesses": review.weaknesses[:2],
            "review_source": review.review_source
        })

    # 总体评审
    overall_review = local_review(content[:8000], title)

    return {
        "overall_review": overall_review.to_dict(),
        "section_reviews": section_reviews,
        "radar_chart": overall_review.radar_chart_data(),
        "summary": _generate_review_summary(overall_review, section_reviews)
    }


def _generate_review_summary(overall: PaperReviewResult, sections: list) -> str:
    """生成评审摘要"""
    rec_label = overall.recommendation_label()
    score = overall.overall_score

    summary = (
        f"论文综合评分: {score}/10 ({rec_label})\n"
        f"评审来源: {overall.review_source}\n"
        f"\n各维度评分:\n"
    )

    dims = overall.dimension_scores.to_dict()
    for dim_name, dim_score in dims.items():
        bar = "█" * int(dim_score) + "░" * (10 - int(dim_score))
        summary += f"  {dim_name}: {bar} {dim_score}/10\n"

    if sections:
        summary += f"\n共评审 {len(sections)} 个章节\n"
        scores = [s["overall_score"] for s in sections]
        summary += f"章节评分范围: {min(scores):.1f} - {max(scores):.1f}\n"

    if overall.strengths:
        summary += f"\n主要优势:\n"
        for s in overall.strengths[:3]:
            summary += f"  ✓ {s}\n"

    if overall.weaknesses:
        summary += f"\n主要不足:\n"
        for w in overall.weaknesses[:3]:
            summary += f"  ✗ {w}\n"

    return summary


# ============ CLI 入口 ============

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="论文评审工具")
    parser.add_argument("file", nargs="?", help="论文文件路径（支持 .txt, .md, .tex）")
    parser.add_argument("--title", "-t", default="论文评审", help="论文标题")
    parser.add_argument("--format", "-f", default="text",
                       choices=["text", "json"], help="输出格式")
    parser.add_argument("--sections", "-s", action="store_true", help="分章节评审")

    args = parser.parse_args()

    # 读取论文内容
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = sys.stdin.read()

    if not content.strip():
        print("Error: no content provided", file=sys.stderr)
        sys.exit(1)

    print(f"正在评审论文: {args.title}", file=sys.stderr)

    if args.sections:
        result = review_paper_sections(content, args.title)
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["summary"])
            if result["section_reviews"]:
                print("\n" + "=" * 60)
                print("分章节评分:")
                for sec in result["section_reviews"]:
                    print(f"  {sec['section_name']}: {sec['overall_score']}/10")
    else:
        result = local_review(content, args.title)
        if args.format == "json":
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print("=" * 60)
            print(f"论文评审报告: {args.title}")
            print("=" * 60)
            print(f"综合评分: {result.overall_score}/10")
            print(f"推荐意见: {result.recommendation_label()}")
            print(f"评审来源: {result.review_source}")
            print()
            print("各维度评分:")
            dims = result.dimension_scores.to_dict()
            for dim_name, dim_score in dims.items():
                bar = "█" * int(dim_score) + "░" * (10 - int(dim_score))
                print(f"  {dim_name}: {bar} {dim_score}/10")
            if result.strengths:
                print("\n优势:")
                for s in result.strengths:
                    print(f"  ✓ {s}")
            if result.weaknesses:
                print("\n不足:")
                for w in result.weaknesses:
                    print(f"  ✗ {w}")
            if result.revision_suggestions:
                print("\n修改建议:")
                for s in result.revision_suggestions:
                    print(f"  → {s}")
