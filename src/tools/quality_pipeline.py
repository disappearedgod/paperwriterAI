"""
论文质量流水线 (Quality Pipeline)
集成 AI 痕迹检测 + 论文评审 + 综合报告生成

Step 4: AI 痕迹检测 - 基于 Fast-DetectGPT (本地模型)
Step 5: 论文评审 - Claude API / PaperReview.ai
Step 6: 综合报告 - 7 维度雷达图 + PDF 导出
"""

import re
import json
import time
import subprocess
import threading
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


# ─────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────

@dataclass
class AIDetectionResult:
    """AI 痕迹检测结果"""
    ai_probability: float          # AI 生成概率 0.0-1.0
    confidence: float              # 置信度 0.0-1.0
    criterion_score: float         # Fast-DetectGPT 判据值
    is_ai_generated: bool          # 是否判定为 AI 生成
    suspicious_segments: List[Dict]  # 可疑段落列表
    model_used: str                # 使用的检测模型
    detection_time_ms: float       # 检测耗时 ms

    def risk_level(self) -> str:
        """风险等级"""
        if self.ai_probability < 0.3:
            return "low"
        elif self.ai_probability < 0.7:
            return "medium"
        else:
            return "high"


@dataclass
class PaperReviewResult:
    """论文评审结果"""
    overall_score: float
    merit_score: float
    clarity_score: float
    reproducibility_score: float
    originality_score: float
    utility_score: float
    strengths: List[str]
    weaknesses: List[str]
    detailed_feedback: str
    recommended_venue: Optional[str]
    reviewer_model: str  # claude-3-5-sonnet / paperreview-ai


@dataclass
class QualityReport:
    """综合质量报告"""
    paper_id: Optional[int]
    paper_title: str
    generated_at: str
    # Step 4
    ai_detection: Optional[AIDetectionResult]
    # Step 5
    paper_review: Optional[PaperReviewResult]
    # 内部评分
    internal_score: Optional[float]
    internal_criteria: Optional[Dict]
    # 综合判定
    overall_pass: bool
    quality_stars: int  # 1-5 星
    summary: str
    recommendations: List[str]


# ─────────────────────────────────────────────
# Step 4: AI 痕迹检测 (Fast-DetectGPT)
# ─────────────────────────────────────────────

class FastDetectGPTDetector:
    """
    Fast-DetectGPT 本地检测器

    使用条件概率曲率检测 AI 生成文本
    模型优先级: gpt-j-6B > gpt-neo-2.7B > falcon-7b

    安装方法:
    1. cd /path/to/fast-detect-gpt
    2. bash setup.sh  # 下载模型 (~10GB)
    3. python scripts/local_infer.py  # 测试

    也支持远程 API 模式 (fastdetect.net)
    """

    DEFAULT_VENV_PATH = "/tmp/fast-detectgpt-venv"
    VENDOR_DIR = Path(__file__).parent.parent.parent / "vendor" / "fast-detect-gpt"
    FAST_DETECTGPT_REPO = str(VENDOR_DIR.resolve())
    CRITERION_THRESHOLD = 1.9299  # Fast-DetectGPT 默认阈值

    def __init__(self, model_name: str = "gpt-neo-2.7B",
                 scoring_model: str = "gpt-neo-2.7B",
                 remote_api_url: Optional[str] = None,
                 remote_api_key: Optional[str] = None):
        self.model_name = model_name
        self.scoring_model = scoring_model
        self.remote_api_url = remote_api_url
        self.remote_api_key = remote_api_key
        self._local_detector = None
        self._local_available = None

    @property
    def is_local_available(self) -> bool:
        """检查本地模型是否可用"""
        if self._local_available is not None:
            return self._local_available

        venv_python = Path(self.DEFAULT_VENV_PATH) / "bin" / "python"
        repo_model = Path(self.FAST_DETECTGPT_REPO)

        if not venv_python.exists():
            self._local_available = False
            return False

        if not (repo_model / "model.py").exists():
            self._local_available = False
            return False

        # 检查模型缓存
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        model_cached = any(
            model_name.lower() in str(p).lower()
            for p in cache_dir.glob("**/models--*")
            for model_name in [self.model_name, self.scoring_model]
        ) if cache_dir.exists() else False

        self._local_available = model_cached
        return self._local_available

    def detect(self, text: str) -> AIDetectionResult:
        """
        检测文本的 AI 生成概率

        Returns:
            AIDetectionResult: 包含检测结果的 dataclass
        """
        start_time = time.time()

        # 优先使用本地模型
        if self.is_local_available:
            return self._detect_local(text, start_time)

        # 远程 API
        if self.remote_api_url:
            return self._detect_remote(text, start_time)

        # 降级方案: 统计检测
        return self._detect_fallback(text, start_time)

    def _detect_local(self, text: str, start_time: float) -> AIDetectionResult:
        """使用本地 Fast-DetectGPT 模型检测

        直接使用 transformers 加载模型，inline 了 get_sampling_discrepancy_analytic
        以避免 fast_detect_gpt.py 的依赖链问题 (datasets, sklearn, matplotlib)
        """
        import sys
        import os
        import torch

        # 内联的 Fast-DetectGPT 条件概率曲率计算
        # 原始实现: https://github.com/baoguangsheng/fast-detect-gpt
        def get_sampling_discrepancy_analytic(logits_ref, logits_score, labels):
            assert logits_ref.shape[0] == 1
            assert logits_score.shape[0] == 1
            assert labels.shape[0] == 1
            if logits_ref.size(-1) != logits_score.size(-1):
                vocab_size = min(logits_ref.size(-1), logits_score.size(-1))
                logits_ref = logits_ref[:, :, :vocab_size]
                logits_score = logits_score[:, :, :vocab_size]
            labels = labels.unsqueeze(-1) if labels.ndim == logits_score.ndim - 1 else labels
            lprobs_score = torch.log_softmax(logits_score, dim=-1)
            probs_ref = torch.softmax(logits_ref, dim=-1)
            log_likelihood = lprobs_score.gather(dim=-1, index=labels).squeeze(-1)
            mean_ref = (probs_ref * lprobs_score).sum(dim=-1)
            var_ref = (probs_ref * torch.square(lprobs_score)).sum(dim=-1) - torch.square(mean_ref)
            discrepancy = (log_likelihood.sum(dim=-1) - mean_ref.sum(dim=-1)) / var_ref.sum(dim=-1).sqrt()
            discrepancy = discrepancy.mean()
            return discrepancy.item()

        # gpt-neo-2.7B 在 MPS 上会 OOM，强制使用 CPU
        # CUDA GPU 用户可将 device 改为 "cuda"
        device = "cpu"

        try:
            # 加载模型 (延迟加载，缓存到实例)
            if not hasattr(self, "_scoring_tokenizer"):
                from transformers import AutoModelForCausalLM, AutoTokenizer
                cache_dir = str(Path.home() / ".cache" / "huggingface" / "hub")
                # gpt-neo-2.7B 需要 float16 以节省内存
                self._scoring_tokenizer = AutoTokenizer.from_pretrained(
                    f"EleutherAI/{self.scoring_model}" if "gpt-" in self.scoring_model else self.scoring_model,
                    cache_dir=cache_dir
                )
                if self._scoring_tokenizer.pad_token_id is None:
                    self._scoring_tokenizer.pad_token_id = self._scoring_tokenizer.eos_token_id
                dtype = torch.float16 if "gpt-neo-2.7B" in self.scoring_model else torch.float32
                self._scoring_model = AutoModelForCausalLM.from_pretrained(
                    f"EleutherAI/{self.scoring_model}" if "gpt-" in self.scoring_model else self.scoring_model,
                    cache_dir=cache_dir,
                    torch_dtype=dtype,
                ).to(device)
                self._scoring_model.eval()

            scoring_tokenizer = self._scoring_tokenizer
            scoring_model = self._scoring_model

            # Tokenize
            tokenized = scoring_tokenizer(
                text,
                truncation=True,
                return_tensors="pt",
                padding=True,
                return_token_type_ids=False
            ).to(scoring_model.device)

            labels = tokenized.input_ids[:, 1:]

            # 计算条件概率曲率
            with torch.no_grad():
                logits_score = scoring_model(**tokenized).logits[:, :-1]
                crit = get_sampling_discrepancy_analytic(
                    logits_score, logits_score, labels
                )

            crit_val = float(crit.item())
            ntoken = labels.size(1)

            # 计算 AI 概率 (使用正态分布参数)
            mu0, sigma0 = -0.2489, 0.9968
            mu1, sigma1 = 1.8983, 1.9935

            pdf0 = np.exp(-0.5 * ((crit_val - mu0) / sigma0) ** 2) / (sigma0 * np.sqrt(2 * np.pi))
            pdf1 = np.exp(-0.5 * ((crit_val - mu1) / sigma1) ** 2) / (sigma1 * np.sqrt(2 * np.pi))
            ai_prob = float(pdf1 / (pdf0 + pdf1))

            elapsed_ms = (time.time() - start_time) * 1000

            return AIDetectionResult(
                ai_probability=min(ai_prob, 1.0),
                confidence=0.82,  # gpt-neo-2.7B 准确率
                criterion_score=crit_val,
                is_ai_generated=crit_val > self.CRITERION_THRESHOLD,
                suspicious_segments=self._find_suspicious_segments(text, crit_val),
                model_used=f"fast-detectgpt-{self.scoring_model}",
                detection_time_ms=elapsed_ms
            )

        except ImportError as e:
            self._local_available = False
            return self._detect_fallback(text, start_time)
        except Exception as e:
            return AIDetectionResult(
                ai_probability=0.5,
                confidence=0.0,
                criterion_score=0.0,
                is_ai_generated=False,
                suspicious_segments=[],
                model_used="error",
                detection_time_ms=(time.time() - start_time) * 1000
            )

    def _detect_remote(self, text: str, start_time: float) -> AIDetectionResult:
        """使用远程 Fast-DetectGPT API 检测"""
        import requests

        headers = {"Content-Type": "application/json"}
        if self.remote_api_key:
            headers["Authorization"] = f"Bearer {self.remote_api_key}"

        try:
            resp = requests.post(
                f"{self.remote_api_url}/detect",
                headers=headers,
                json={"text": text, "model": self.scoring_model},
                timeout=30
            )
            data = resp.json()
            elapsed_ms = (time.time() - start_time) * 1000

            return AIDetectionResult(
                ai_probability=float(data.get("ai_probability", 0.5)),
                confidence=float(data.get("confidence", 0.8)),
                criterion_score=float(data.get("criterion", 0.0)),
                is_ai_generated=bool(data.get("is_ai_generated", False)),
                suspicious_segments=data.get("suspicious_segments", []),
                model_used=f"fast-detectgpt-remote-{self.scoring_model}",
                detection_time_ms=elapsed_ms
            )
        except Exception:
            return self._detect_fallback(text, start_time)

    def _detect_fallback(self, text: str, start_time: float) -> AIDetectionResult:
        """
        降级方案: 基于统计特征的 AI 文本检测

        检测特征:
        1. 词汇丰富度 (AI 文本通常词汇更丰富但更均匀)
        2. 句子长度方差 (AI 文本句子长度更一致)
        3. 常见 AI 套话模式
        4. 标点符号使用模式
        """
        import math

        # 清理文本
        clean_text = re.sub(r'\s+', ' ', text).strip()
        sentences = re.split(r'[.!?。！？]+', clean_text)
        sentences = [s.strip() for s in sentences if s.strip()]

        words = clean_text.split()
        n_words = len(words)
        n_sentences = max(len(sentences), 1)

        # 特征 1: 平均词长
        avg_word_len = sum(len(w) for w in words) / max(n_words, 1)

        # 特征 2: 句子长度标准差
        sent_lens = [len(s.split()) for s in sentences]
        mean_len = sum(sent_lens) / n_sentences
        variance = sum((l - mean_len) ** 2 for l in sent_lens) / n_sentences
        sent_std = math.sqrt(variance) if variance > 0 else 0

        # 特征 3: 词汇丰富度 (Type-Token Ratio)
        unique_words = len(set(w.lower() for w in words))
        ttr = unique_words / max(n_words, 1)

        # 特征 4: AI 套话检测
        ai_phrases = [
            r'\b(it is worth noting that)\b',
            r'\b(this suggests that)\b',
            r'\b(importantly,)\b',
            r'\b(in conclusion,)\b',
            r'\b(however, it is important to)\b',
            r'\b(the results indicate that)\b',
            r'\b(furthermore,)\b',
            r'\b(moreover,)\b',
            r'\b(in this paper, we)\b',
            r'\b(we demonstrate that)\b',
        ]
        phrase_count = sum(
            len(re.findall(p, clean_text.lower()))
            for p in ai_phrases
        )
        phrase_ratio = phrase_count / max(n_sentences, 1)

        # 特征 5: 数字和引用密度
        num_count = len(re.findall(r'\d+', clean_text))
        quote_count = len(re.findall(r'["\""]', clean_text))
        special_ratio = (num_count + quote_count) / max(n_words, 1)

        # 综合评分 (0.0 = 人类, 1.0 = AI)
        score = 0.0
        score += 0.15 * min(phrase_ratio * 3, 1.0)  # AI 套话
        score += 0.15 * min(ttr * 1.5, 1.0)         # 高词汇丰富度
        score += 0.10 * min(sent_std / 10, 1.0)      # 低句子长度方差
        score += 0.10 * min(avg_word_len / 8, 1.0) # 平均词长
        score += 0.10 * min(special_ratio * 5, 1.0)   # 低特殊符号

        # 短文本惩罚
        if n_words < 50:
            score *= 0.7
        elif n_words < 100:
            score *= 0.85

        ai_prob = min(max(score, 0.0), 1.0)
        elapsed_ms = (time.time() - start_time) * 1000

        return AIDetectionResult(
            ai_probability=ai_prob,
            confidence=0.55,  # 统计方法置信度较低
            criterion_score=score * 10,
            is_ai_generated=ai_prob > 0.5,
            suspicious_segments=self._find_suspicious_segments_fallback(text, score),
            model_used="statistical-fallback",
            detection_time_ms=elapsed_ms
        )

    def _find_suspicious_segments(self, text: str, crit_val: float) -> List[Dict]:
        """找出可疑段落 (Fast-DetectGPT 版本)"""
        sentences = re.split(r'[.!?。！？]+', text)
        segments = []
        for i, sent in enumerate(sentences):
            if len(sent.strip()) < 20:
                continue
            # 简单启发式: 越像 AI 套话，可疑度越高
            ai_markers = [
                'furthermore', 'moreover', 'importantly', 'in conclusion',
                'this suggests', 'the results indicate', 'it is worth noting'
            ]
            marker_count = sum(1 for m in ai_markers if m in sent.lower())
            if marker_count > 0:
                segments.append({
                    "text": sent.strip()[:200],
                    "marker_count": marker_count,
                    "position": i
                })
        return segments[:5]  # 最多返回 5 个

    def _find_suspicious_segments_fallback(self, text: str, score: float) -> List[Dict]:
        """找出可疑段落 (降级版本)"""
        sentences = re.split(r'[.!?。！？]+', text)
        segments = []
        for i, sent in enumerate(sentences):
            sent_clean = sent.strip()
            if len(sent_clean) < 20:
                continue
            ai_markers = [
                'furthermore', 'moreover', 'importantly', 'in conclusion',
                'this suggests', 'the results indicate', 'it is worth noting',
                'additionally', 'significantly', 'notably'
            ]
            marker_count = sum(1 for m in ai_markers if m in sent_clean.lower())
            if marker_count >= 2:
                segments.append({
                    "text": sent_clean[:200],
                    "marker_count": marker_count,
                    "position": i
                })
        return segments[:5]


# ─────────────────────────────────────────────
# Step 5: 论文评审 (Claude API / PaperReview.ai)
# ─────────────────────────────────────────────

class PaperReviewer:
    """
    论文评审器

    支持多种评审方式:
    1. Claude API (anthropic) - 本地快速评审
    2. PaperReview.ai - 外部专业评审
    """

    REVIEW_PROMPT = """你是一个专业的学术论文评审专家。请对以下学术论文进行结构化评审。

论文标题: {title}
论文内容:
{content}

请从以下 6 个维度进行评审:

1. **Merit (学术价值)**: 论文的学术贡献是否重要？创新点是否明确？
2. **Clarity (清晰度)**: 论文的写作是否清晰易懂？结构是否合理？
3. **Reproducibility (可复现性)**: 实验设置是否描述充分？方法是否可复现？
4. **Originality (原创性)**: 是否有独特贡献？还是仅仅是增量改进？
5. **Utility (实用性)**: 研究结果对领域是否有实际应用价值？
6. **Overall (综合评分)**: 综合以上维度，给出 1-10 的总体评分

请严格按以下 JSON 格式输出（只输出 JSON，不要任何其他文字）:

{{
    "overall_score": 1.0-10.0,
    "merit_score": 1.0-10.0,
    "clarity_score": 1.0-10.0,
    "reproducibility_score": 1.0-10.0,
    "originality_score": 1.0-10.0,
    "utility_score": 1.0-10.0,
    "strengths": ["优点1", "优点2", "优点3"],
    "weaknesses": ["缺点1", "缺点2", "缺点3"],
    "detailed_feedback": "详细的评审意见，至少200字",
    "recommended_venue": "推荐的发表会议或期刊，如 'ICLR', 'NeurIPS', 'Nature ML' 等"
}}
"""

    def __init__(self, anthropic_api_key: Optional[str] = None,
                 use_paperreview: bool = False):
        self.anthropic_api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.use_paperreview = use_paperreview

    def review(self, title: str, content: str,
               venue: str = "ICLR") -> PaperReviewResult:
        """
        评审论文

        Args:
            title: 论文标题
            content: 论文正文
            venue: 目标会议/期刊

        Returns:
            PaperReviewResult: 评审结果
        """
        # 优先使用 Claude API
        if self.anthropic_api_key:
            return self._review_claude(title, content, venue)

        # 降级方案: 模拟评审
        return self._review_mock(title, content, venue)

    def _review_claude(self, title: str, content: str,
                       venue: str) -> PaperReviewResult:
        """使用 Claude API 评审"""
        import os
        try:
            import anthropic
        except ImportError:
            return self._review_mock(title, content, venue)

        # 截断内容避免超限
        max_chars = 50000
        truncated = content[:max_chars] if len(content) > max_chars else content

        prompt = self.REVIEW_PROMPT.format(title=title, content=truncated)

        try:
            client = anthropic.Anthropic(api_key=self.anthropic_api_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )

            raw_text = response.content[0].text.strip()
            json_match = re.search(r'\{[\s\S]*\}', raw_text)

            if json_match:
                data = json.loads(json_match.group())
                return PaperReviewResult(
                    overall_score=float(data.get("overall_score", 5.0)),
                    merit_score=float(data.get("merit_score", 5.0)),
                    clarity_score=float(data.get("clarity_score", 5.0)),
                    reproducibility_score=float(data.get("reproducibility_score", 5.0)),
                    originality_score=float(data.get("originality_score", 5.0)),
                    utility_score=float(data.get("utility_score", 5.0)),
                    strengths=data.get("strengths", []),
                    weaknesses=data.get("weaknesses", []),
                    detailed_feedback=data.get("detailed_feedback", ""),
                    recommended_venue=data.get("recommended_venue", venue),
                    reviewer_model="claude-3-5-sonnet"
                )
        except Exception:
            pass

        return self._review_mock(title, content, venue)

    def _review_mock(self, title: str, content: str,
                     venue: str) -> PaperReviewResult:
        """模拟评审 (无 API Key 时使用)"""
        # 基于内容特征生成模拟评分
        word_count = len(content.split())
        has_abstract = bool(re.search(r'abstract|摘要', content[:500], re.I))
        has_conclusion = bool(re.search(r'conclusion|结论', content[-1000:], re.I))
        has_equations = '$$' in content or '\\[' in content

        # 基础分
        base = 5.0
        if has_abstract:
            base += 0.5
        if has_conclusion:
            base += 0.5
        if has_equations:
            base += 0.3
        if word_count > 3000:
            base += 0.5
        if word_count > 6000:
            base += 0.5

        scores = {
            "merit": base + np.random.uniform(-0.5, 0.5),
            "clarity": base + np.random.uniform(-0.5, 0.5),
            "reproducibility": base - 0.5 + np.random.uniform(-0.3, 0.3),
            "originality": base - 0.3 + np.random.uniform(-0.3, 0.3),
            "utility": base + np.random.uniform(-0.3, 0.3),
        }

        return PaperReviewResult(
            overall_score=round(sum(scores.values()) / len(scores), 1),
            merit_score=round(scores["merit"], 1),
            clarity_score=round(scores["clarity"], 1),
            reproducibility_score=round(scores["reproducibility"], 1),
            originality_score=round(scores["originality"], 1),
            utility_score=round(scores["utility"], 1),
            strengths=[
                "论文结构完整，包含摘要、引言、方法和实验",
                "研究问题明确，具有一定的学术价值",
                "使用了适当的实验验证方法"
            ],
            weaknesses=[
                "创新性一般，属于增量性贡献",
                "部分章节表述可以更加精炼",
                "缺少更多消融实验"
            ],
            detailed_feedback=f"该论文（约{word_count}字）整体质量中等，涵盖了研究背景、方法、实验等基本要素。主要创新点在于研究问题的选择，但在方法论上与现有工作相比没有实质性突破。建议补充更多对比实验和消融实验以增强说服力。",
            recommended_venue=venue,
            reviewer_model="mock-reviewer"
        )


# ─────────────────────────────────────────────
# Step 6: 综合报告生成器
# ─────────────────────────────────────────────

class QualityReporter:
    """综合质量报告生成器"""

    def generate_report(
        self,
        paper_id: Optional[int],
        paper_title: str,
        content: str,
        ai_detection: Optional[AIDetectionResult] = None,
        paper_review: Optional[PaperReviewResult] = None,
        internal_score: Optional[float] = None,
        internal_criteria: Optional[Dict] = None
    ) -> QualityReport:
        """生成综合质量报告"""

        # 计算综合通过判定
        checks = []

        # AI 痕迹检测
        if ai_detection:
            checks.append(("AI痕迹", ai_detection.ai_probability < 0.6))

        # 论文评审
        if paper_review:
            checks.append(("学术价值", paper_review.overall_score >= 5.0))
            checks.append(("创新性", paper_review.originality_score >= 4.0))
            checks.append(("可复现性", paper_review.reproducibility_score >= 4.0))

        # 内部评分
        if internal_score is not None:
            checks.append(("内部评分", internal_score >= 6.0))

        passed_checks = sum(1 for _, r in checks if r)
        total_checks = len(checks)
        overall_pass = total_checks > 0 and passed_checks >= total_checks * 0.6

        # 计算质量星级
        quality_score = 0
        if ai_detection and ai_detection.ai_probability < 0.3:
            quality_score += 1
        if paper_review:
            quality_score += int(paper_review.overall_score / 2)
        elif internal_score:
            quality_score += int(internal_score / 2)

        stars = min(max(quality_score, 1), 5)

        # 生成建议
        recommendations = []
        if ai_detection and ai_detection.ai_probability > 0.5:
            recommendations.append(f"⚠️ AI 痕迹明显 (概率 {ai_detection.ai_probability:.0%})，建议人工润色")
        if paper_review:
            if paper_review.originality_score < 5.0:
                recommendations.append(f"📝 创新性不足 ({paper_review.originality_score}/10)，建议强化创新点描述")
            if paper_review.reproducibility_score < 5.0:
                recommendations.append(f"🔬 可复现性待提升 ({paper_review.reproducibility_score}/10)，建议补充更多实现细节")
            if paper_review.clarity_score < 5.0:
                recommendations.append(f"✍️ 清晰度待改进 ({paper_review.clarity_score}/10)，建议精简表述")
        if internal_score and internal_score < 7.0:
            recommendations.append(f"📊 内部评分偏低 ({internal_score}/10)，建议迭代优化")

        # 生成摘要
        summary_parts = []
        if ai_detection:
            risk = ai_detection.risk_level()
            risk_text = {"low": "低风险", "medium": "中风险", "high": "高风险"}[risk]
            summary_parts.append(f"AI痕迹{risk_text} ({ai_detection.ai_probability:.0%})")
        if paper_review:
            summary_parts.append(f"评审综合分 {paper_review.overall_score:.1f}/10")
        elif internal_score:
            summary_parts.append(f"内部评分 {internal_score:.1f}/10")
        summary = "；".join(summary_parts) if summary_parts else "缺少评审数据"

        return QualityReport(
            paper_id=paper_id,
            paper_title=paper_title,
            generated_at=datetime.now().isoformat(),
            ai_detection=ai_detection,
            paper_review=paper_review,
            internal_score=internal_score,
            internal_criteria=internal_criteria,
            overall_pass=overall_pass,
            quality_stars=stars,
            summary=summary,
            recommendations=recommendations
        )

    def to_dict(self, report: QualityReport) -> Dict[str, Any]:
        """将报告转换为字典格式 (JSON 序列化)"""
        result = {
            "paper_id": report.paper_id,
            "paper_title": report.paper_title,
            "generated_at": report.generated_at,
            "overall_pass": report.overall_pass,
            "quality_stars": report.quality_stars,
            "summary": report.summary,
            "recommendations": report.recommendations,
        }

        if report.ai_detection:
            result["ai_detection"] = {
                "ai_probability": report.ai_detection.ai_probability,
                "confidence": report.ai_detection.confidence,
                "criterion_score": report.ai_detection.criterion_score,
                "is_ai_generated": report.ai_detection.is_ai_generated,
                "risk_level": report.ai_detection.risk_level(),
                "suspicious_segments": report.ai_detection.suspicious_segments,
                "model_used": report.ai_detection.model_used,
                "detection_time_ms": round(report.ai_detection.detection_time_ms, 1),
            }

        if report.paper_review:
            result["paper_review"] = {
                "overall_score": report.paper_review.overall_score,
                "dimensions": {
                    "merit": report.paper_review.merit_score,
                    "clarity": report.paper_review.clarity_score,
                    "reproducibility": report.paper_review.reproducibility_score,
                    "originality": report.paper_review.originality_score,
                    "utility": report.paper_review.utility_score,
                },
                "strengths": report.paper_review.strengths,
                "weaknesses": report.paper_review.weaknesses,
                "detailed_feedback": report.paper_review.detailed_feedback,
                "recommended_venue": report.paper_review.recommended_venue,
                "reviewer_model": report.paper_review.reviewer_model,
            }

        if report.internal_score is not None:
            result["internal_score"] = report.internal_score
            result["internal_criteria"] = report.internal_criteria

        return result


# ─────────────────────────────────────────────
# 快捷调用函数
# ─────────────────────────────────────────────

def run_quality_pipeline(
    paper_id: Optional[int],
    paper_title: str,
    content: str,
    anthropic_api_key: Optional[str] = None,
    fast_detectgpt_remote_url: Optional[str] = None,
    fast_detectgpt_remote_key: Optional[str] = None,
    run_ai_detection: bool = True,
    run_paper_review: bool = True,
    run_internal_score: bool = False,
) -> QualityReport:
    """
    运行完整质量流水线

    Args:
        paper_id: 论文 ID
        paper_title: 论文标题
        content: 论文正文
        anthropic_api_key: Claude API Key
        fast_detectgpt_remote_url: Fast-DetectGPT 远程 API URL
        fast_detectgpt_remote_key: Fast-DetectGPT 远程 API Key
        run_ai_detection: 是否运行 AI 痕迹检测
        run_paper_review: 是否运行论文评审
        run_internal_score: 是否运行内部评分

    Returns:
        QualityReport: 综合质量报告
    """
    ai_detection_result = None
    paper_review_result = None
    internal_score = None
    internal_criteria = None

    # Step 4: AI 痕迹检测
    if run_ai_detection:
        detector = FastDetectGPTDetector(
            remote_api_url=fast_detectgpt_remote_url,
            remote_api_key=fast_detectgpt_remote_key
        )
        ai_detection_result = detector.detect(content)

    # Step 5: 论文评审
    if run_paper_review:
        reviewer = PaperReviewer(anthropic_api_key=anthropic_api_key)
        paper_review_result = reviewer.review(paper_title, content)

    # 生成综合报告
    reporter = QualityReporter()
    report = reporter.generate_report(
        paper_id=paper_id,
        paper_title=paper_title,
        content=content,
        ai_detection=ai_detection_result,
        paper_review=paper_review_result,
        internal_score=internal_score,
        internal_criteria=internal_criteria,
    )

    return report
