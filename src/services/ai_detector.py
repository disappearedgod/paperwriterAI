#!/usr/bin/env python3
"""
AI Detection Service - Fast-DetectGPT 封装

基于 ICLR 2024 论文: Fast-DetectGPT: Efficient Zero-Shot Detection of Machine-Generated Text
via Conditional Probability Curvature

GitHub: https://github.com/baoguangsheng/fast-detect-gpt

依赖模型: gpt-neo-2.7B / gpt-j-6B / Llama3-8B
支持 GPU (Tesla A100 80GB) 和 CPU 回退
"""

import os
import sys
import subprocess
import json
import tempfile
from typing import Optional

# Vendor path
VENDOR_FAST_DETECT = os.path.join(
    os.path.dirname(__file__), '..', '..', 'vendor', 'fast-detect-gpt'
)
SCRIPTS_LOCAL_INFER = os.path.join(VENDOR_FAST_DETECT, 'scripts', 'local_infer.py')

# 默认检测阈值 (criterion)
DEFAULT_CRITICION = 1.9299

class FastDetectResult:
    """Fast-DetectGPT 检测结果"""

    def __init__(self, text: str, criterion: float, ai_probability: float,
                 is_ai_generated: bool, detector_version: str = "fast-detectgpt"):
        self.text = text
        self.criterion = criterion
        self.ai_probability = ai_probability  # 0.0 ~ 1.0
        self.is_ai_generated = is_ai_generated
        self.detector_version = detector_version

    def to_dict(self) -> dict:
        return {
            "ai_probability": round(self.ai_probability, 4),
            "criterion": round(self.criterion, 4),
            "is_ai_generated": self.is_ai_generated,
            "detector": self.detector_version,
            "confidence": "high" if abs(self.ai_probability - 0.5) > 0.3 else "medium",
            "verdict": "AI生成" if self.is_ai_generated else "人类撰写",
            "ai_percentage": f"{self.ai_probability * 100:.1f}%"
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def check_fast_detect_installed() -> bool:
    """检查 fast-detect-gpt 是否已安装"""
    return os.path.exists(SCRIPTS_LOCAL_INFER)


def run_local_infer(text: str, sampling_model: str = "gpt-neo-2.7B",
                    criterion: float = DEFAULT_CRITICION) -> Optional[dict]:
    """
    调用 local_infer.py 进行检测

    Args:
        text: 待检测文本
        sampling_model: 采样模型 (gpt-neo-2.7B / gpt-j-6B / Llama3-8B)
        criterion: 判定阈值

    Returns:
        {"criterion": float, "ai_probability": float} 或 None
    """
    if not check_fast_detect_installed():
        print(f"[ERROR] fast-detect-gpt not found at {SCRIPTS_LOCAL_INFER}")
        return None

    # 写入临时文件（避免命令行转义问题）
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(text)
        input_file = f.name

    try:
        cmd = [
            sys.executable,  # 使用当前 Python 解释器
            SCRIPTS_LOCAL_INFER,
            "--sampling_model_name", sampling_model,
            "--input_file", input_file
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=VENDOR_FAST_DETECT
        )

        # 解析输出
        # 输出格式: "Fast-DetectGPT criterion is X.XXXX, suggesting that the text has a probability of XX% to be machine-generated."
        output = result.stdout + result.stderr

        criterion_match = None
        prob_match = None

        for line in output.split('\n'):
            line_lower = line.lower()
            if 'criterion is' in line_lower and 'probability' in line_lower:
                # 解析 criterion 和 probability
                import re
                crit_m = re.search(r'criterion is ([0-9.]+)', line_lower)
                prob_m = re.search(r'probability of ([0-9.]+)%', line_lower)
                if crit_m:
                    criterion_match = float(crit_m.group(1))
                if prob_m:
                    prob_match = float(prob_m.group(1)) / 100.0

        if criterion_match is not None and prob_match is not None:
            return {"criterion": criterion_match, "ai_probability": prob_match}

        # 备用：尝试从完整输出匹配
        import re
        crit_all = re.search(r'criterion is ([0-9.]+)', output)
        prob_all = re.search(r'probability of ([0-9.]+)%', output)
        if crit_all and prob_all:
            return {
                "criterion": float(crit_all.group(1)),
                "ai_probability": float(prob_all.group(1)) / 100.0
            }

        print(f"[ERROR] Failed to parse fast-detect-gpt output: {output[:500]}")
        return None

    except subprocess.TimeoutExpired:
        print("[ERROR] fast-detect-gpt timeout (>300s)")
        return None
    except Exception as e:
        print(f"[ERROR] fast-detect-gpt error: {e}")
        return None
    finally:
        # 清理临时文件
        if os.path.exists(input_file):
            os.unlink(input_file)


def detect_ai_text(text: str, sampling_model: str = "gpt-neo-2.7B",
                   threshold: float = DEFAULT_CRITICION) -> FastDetectResult:
    """
    主检测函数

    Args:
        text: 待检测文本
        sampling_model: 采样模型
        threshold: 判定阈值（>0 = AI生成）

    Returns:
        FastDetectResult 对象
    """
    result_data = run_local_infer(text, sampling_model, threshold)

    if result_data is None:
        # 回退：返回未知
        return FastDetectResult(
            text=text[:200],
            criterion=0.0,
            ai_probability=0.5,
            is_ai_generated=False,
            detector_version="fast-detectgpt-fallback"
        )

    criterion = result_data["criterion"]
    ai_prob = result_data["ai_probability"]

    # criterion > 0 表示更可能是 AI 生成
    is_ai = criterion > threshold

    return FastDetectResult(
        text=text[:200],
        criterion=criterion,
        ai_probability=ai_prob,
        is_ai_generated=is_ai,
        detector_version=f"fast-detectgpt-{sampling_model}"
    )


def detect_text_segments(text: str, sampling_model: str = "gpt-neo-2.7B",
                        segment_length: int = 500) -> list[dict]:
    """
    对文本分段检测，返回每段的 AI 概率

    Args:
        text: 待检测文本
        sampling_model: 采样模型
        segment_length: 每段字符数

    Returns:
        [{"segment": str, "start": int, "end": int, "ai_probability": float, "is_ai": bool}, ...]
    """
    segments = []
    for start in range(0, len(text), segment_length):
        end = min(start + segment_length, len(text))
        segment = text[start:end]

        if len(segment.strip()) < 50:
            continue

        result = detect_ai_text(segment, sampling_model)
        segments.append({
            "segment": segment[:100] + "..." if len(segment) > 100 else segment,
            "start": start,
            "end": end,
            "ai_probability": result.ai_probability,
            "criterion": result.criterion,
            "is_ai": result.is_ai_generated,
            "verdict": result.to_dict()["verdict"]
        })

    return segments


def batch_detect(texts: list[str], sampling_model: str = "gpt-neo-2.7B") -> list[dict]:
    """
    批量检测多个文本

    Returns:
        [{"text": str, "ai_probability": float, "is_ai": bool, "verdict": str}, ...]
    """
    results = []
    for text in texts:
        result = detect_ai_text(text, sampling_model)
        results.append(result.to_dict())
    return results


# ============ API 层（供 server.py 调用）============

def detect_paper_ai_content(paper_content: str,
                              sampling_model: str = "gpt-neo-2.7B",
                              segment_length: int = 500) -> dict:
    """
    检测整篇论文的 AI 痕迹

    Returns:
    {
        "overall_ai_probability": float,
        "is_likely_ai_generated": bool,
        "segments": [...],  # 分段结果
        "high_ai_risk_segments": [...],  # 高风险段落
        "summary": str,
        "detector": str,
        "model": str
    }
    """
    segments = detect_text_segments(paper_content, sampling_model, segment_length)

    if not segments:
        return {
            "overall_ai_probability": 0.5,
            "is_likely_ai_generated": False,
            "segments": [],
            "high_ai_risk_segments": [],
            "summary": "文本太短，无法检测",
            "detector": "fast-detectgpt",
            "model": sampling_model
        }

    # 计算整体 AI 概率（加权平均）
    total_prob = sum(s["ai_probability"] for s in segments)
    avg_prob = total_prob / len(segments)

    # 找出高风险段落（AI 概率 > 0.7）
    high_risk = [s for s in segments if s["ai_probability"] > 0.7]

    # 统计
    ai_count = sum(1 for s in segments if s["is_ai"])
    human_count = len(segments) - ai_count

    summary = (
        f"共检测 {len(segments)} 个段落，"
        f"{ai_count} 个疑似AI生成，{human_count} 个疑似人类撰写。"
        f"整体AI概率: {avg_prob*100:.1f}%。"
        f"{'⚠️ 建议人工核查' if avg_prob > 0.6 else '✓ 未检测到明显AI痕迹'}"
    )

    return {
        "overall_ai_probability": round(avg_prob, 4),
        "is_likely_ai_generated": avg_prob > 0.6,
        "segments": segments,
        "high_ai_risk_segments": high_risk,
        "high_risk_count": len(high_risk),
        "total_segments": len(segments),
        "ai_segment_count": ai_count,
        "human_segment_count": human_count,
        "summary": summary,
        "detector": "fast-detectgpt",
        "model": sampling_model
    }


# ============ CLI 入口 ============

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fast-DetectGPT AI 文本检测")
    parser.add_argument("text", nargs="?", help="待检测文本（省略则从 stdin 读取）")
    parser.add_argument("--model", "-m", default="gpt-neo-2.7B",
                       choices=["gpt-neo-2.7B", "gpt-j-6B", "Llama3-8B", "Llama3-8B-Instruct"],
                       help="采样模型 (default: gpt-neo-2.7B)")
    parser.add_argument("--segment", "-s", action="store_true",
                       help="分段检测（每500字符一段）")
    parser.add_argument("--format", "-f", default="text",
                       choices=["text", "json"], help="输出格式")

    args = parser.parse_args()

    if args.text:
        text = args.text
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("Error: no text provided", file=sys.stderr)
        sys.exit(1)

    if args.segment:
        result = detect_paper_ai_content(text, args.model)
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("=" * 60)
            print("Fast-DetectGPT 论文 AI 痕迹检测报告")
            print("=" * 60)
            print(f"采样模型: {result['model']}")
            print(f"检测段落: {result['total_segments']} 段")
            print(f"AI生成段落: {result['ai_segment_count']} 个")
            print(f"人类撰写段落: {result['human_segment_count']} 个")
            print(f"整体AI概率: {result['overall_ai_probability']*100:.1f}%")
            print(f"结论: {'⚠️ 可能为AI生成' if result['is_likely_ai_generated'] else '✓ 可能是人类撰写'}")
            print()
            if result['high_ai_risk_segments']:
                print(f"⚠️ 高风险段落 ({result['high_risk_count']} 个):")
                for i, seg in enumerate(result['high_ai_risk_segments'][:3]):
                    print(f"  段落 {i+1} (位置 {seg['start']}-{seg['end']}): "
                          f"AI概率 {seg['ai_probability']*100:.1f}%")
                    print(f"    内容: {seg['segment'][:80]}...")
                    print()
            print(f"摘要: {result['summary']}")
    else:
        result = detect_ai_text(text, args.model)
        if args.format == "json":
            print(result.to_json())
        else:
            print(f"Fast-DetectGPT criterion: {result.criterion:.4f}")
            print(f"AI生成概率: {result.ai_probability*100:.1f}%")
            print(f"判定: {result.to_dict()['verdict']}")
            print(f"置信度: {result.to_dict()['confidence']}")
