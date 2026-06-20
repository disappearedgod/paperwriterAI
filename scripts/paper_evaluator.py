"""
论文质量评估器 - PaperEvaluator
评估量化研究论文质量，判断是否达到"比人类写得更好"的标准

评分维度:
1. 学术规范性 (Academic Norms) - 25%
2. 量化方法正确性 (Quantitative Rigor) - 30%
3. 数据真实性 (Data Authenticity) - 20%
4. 逻辑连贯性 (Logical Coherence) - 15%
5. 公式完整性 (Mathematical Completeness) - 10%

总分 >= 5.5 分视为通过，可与人类写的论文媲美

作者: 魏宏 (Wei Hong)
用于: FARS量化研究系统的质量门控
"""

import re
import json
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


class QualityLevel(Enum):
    """论文质量等级"""
    EXCELLENT = "excellent"       # >= 8.5
    GOOD = "good"                 # >= 7.0
    ACCEPTABLE = "acceptable"     # >= 5.5
    NEEDS_IMPROVEMENT = "needs_improvement"  # >= 4.0
    POOR = "poor"                 # < 4.0


@dataclass
class EvaluationResult:
    """评估结果"""
    total_score: float                     # 总分 (0-10)
    quality_level: QualityLevel            # 质量等级
    dimensions: Dict[str, float]           # 各维度得分
    dimension_weights: Dict[str, float]    # 各维度权重
    issues: List[str]                      # 发现的问题
    strengths: List[str]                   # 优点
    detailed_feedback: str                 # 详细反馈
    passed: bool                           # 是否通过 (>= 5.5)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_score': round(self.total_score, 2),
            'quality_level': self.quality_level.value,
            'dimensions': {k: round(v, 2) for k, v in self.dimensions.items()},
            'dimension_weights': self.dimension_weights,
            'issues': self.issues,
            'strengths': self.strengths,
            'detailed_feedback': self.detailed_feedback,
            'passed': self.passed
        }

    def get_improvement_hints(self) -> List[str]:
        """根据评估结果生成改进建议"""
        hints = []

        for dim, score in self.dimensions.items():
            if score < 5.0:
                if dim == 'academic_norms':
                    hints.append("【学术规范性】建议加强文献综述，规范引用格式，检查语法错误")
                elif dim == 'quantitative_rigor':
                    hints.append("【量化方法】建议补充方法论细节，验证公式正确性，增加稳健性检验")
                elif dim == 'data_authenticity':
                    hints.append("【数据真实性】建议提供数据来源描述，补充描述性统计，增加数据可视化")
                elif dim == 'logical_coherence':
                    hints.append("【逻辑连贯性】建议强化段落之间的逻辑衔接，补充过渡语句")
                elif dim == 'math_completeness':
                    hints.append("【公式完整性】建议补充关键公式推导，完善符号说明")

        return hints


class PaperEvaluator:
    """
    量化研究论文质量评估器

    评估标准参考:
    - 学术论文通用规范 (标题、摘要、引言、方法、实验、结论)
    - 量化研究特殊要求 (公式正确性、数据真实性、回测合规性)
    - AI生成内容检测标准 ( originality score, complexity, depth)
    """

    # 维度权重
    WEIGHTS = {
        'academic_norms': 0.25,       # 学术规范性
        'quantitative_rigor': 0.30,   # 量化方法正确性
        'data_authenticity': 0.20,   # 数据真实性
        'logical_coherence': 0.15,  # 逻辑连贯性
        'math_completeness': 0.10    # 公式完整性
    }

    # 质量等级阈值
    THRESHOLDS = {
        QualityLevel.EXCELLENT: 8.5,
        QualityLevel.GOOD: 7.0,
        QualityLevel.ACCEPTABLE: 5.5,
        QualityLevel.NEEDS_IMPROVEMENT: 4.0,
        QualityLevel.POOR: 0.0
    }

    def __init__(self, pass_threshold: float = 5.5):
        self.pass_threshold = pass_threshold

    def evaluate(self, paper_content: str, backtest_results: Optional[Dict] = None) -> EvaluationResult:
        """
        评估论文质量

        参数:
            paper_content: 论文文本内容 (LaTeX 或 Markdown)
            backtest_results: 回测结果数据 (可选，用于验证数据一致性)

        返回:
            EvaluationResult: 包含详细评分和反馈
        """
        # 各维度评估
        academic_score = self._evaluate_academic_norms(paper_content)
        quantitative_score = self._evaluate_quantitative_rigor(paper_content, backtest_results)
        data_score = self._evaluate_data_authenticity(paper_content, backtest_results)
        logic_score = self._evaluate_logical_coherence(paper_content)
        math_score = self._evaluate_math_completeness(paper_content)

        dimensions = {
            'academic_norms': academic_score,
            'quantitative_rigor': quantitative_score,
            'data_authenticity': data_score,
            'logical_coherence': logic_score,
            'math_completeness': math_score
        }

        # 加权总分
        total_score = sum(dimensions[k] * self.WEIGHTS[k] for k in self.WEIGHTS)

        # 确定质量等级
        quality_level = self._determine_quality_level(total_score)

        # 收集问题和建议
        issues, strengths = self._collect_feedback(dimensions, paper_content, backtest_results)

        # 生成详细反馈
        detailed_feedback = self._generate_feedback(dimensions, issues, strengths)

        # 判断是否通过
        passed = total_score >= self.pass_threshold

        return EvaluationResult(
            total_score=total_score,
            quality_level=quality_level,
            dimensions=dimensions,
            dimension_weights=self.WEIGHTS,
            issues=issues,
            strengths=strengths,
            detailed_feedback=detailed_feedback,
            passed=passed
        )

    def _determine_quality_level(self, score: float) -> QualityLevel:
        for level in [QualityLevel.EXCELLENT, QualityLevel.GOOD,
                      QualityLevel.ACCEPTABLE, QualityLevel.NEEDS_IMPROVEMENT]:
            if score >= self.THRESHOLDS[level]:
                return level
        return QualityLevel.POOR

    # ============================================================
    # 各维度评估方法
    # ============================================================

    def _evaluate_academic_norms(self, content: str) -> float:
        """
        评估学术规范性
        - 标题、摘要完整性
        - 引言、方法、实验、结论结构
        - 引用格式
        - 语法和表达
        """
        score = 5.0  # 基础分
        issues = []

        # 检查基本结构
        required_sections = [
            (r'\\title\{|\\textbf\{.*?\}', '标题'),
            (r'abstract|摘要', '摘要'),
            (r'introduction|引言', '引言'),
            (r'methodology?|方法', '方法论'),
            (r'experiment|实验|results?', '实验结果'),
            (r'conclusion?|结论', '结论'),
            (r'reference|bibliography|参考文献', '参考文献')
        ]

        found_sections = []
        for pattern, name in required_sections:
            if re.search(pattern, content, re.IGNORECASE):
                found_sections.append(name)

        section_coverage = len(found_sections) / len(required_sections)
        score += section_coverage * 2.0  # 最高 +2.0

        # 检查引用格式
        citation_patterns = [
            r'\\cite\{.*?\}',           # LaTeX cite
            r'\([A-Z][a-z]+ et al\., \d{4}\)',  # (Author et al., 2020)
            r'\[.*?\]',                  # [1] 格式
        ]

        citation_count = 0
        for pattern in citation_patterns:
            citation_count += len(re.findall(pattern, content))

        if citation_count >= 5:
            score +=  .5  # 引用充分
        elif citation_count > 0:
            score += 0.25
        else:
            issues.append("引用不足，建议增加文献引用")

        # 检查语法问题（简单检测）
        if re.search(r'\b(an\s+[aeiou]|\b(an|a)\s+\w{1,3}\b)', content):
            score -= 0.3
            issues.append("检测到可能的语法错误")

        # 检查字数是否充足（中文论文通常 >= 5000字，英文 >= 3000词）
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
        english_words = len(re.findall(r'[a-zA-Z]+', content))

        if chinese_chars < 3000 and english_words < 2000:
            score -= 0.5
            issues.append(f"论文篇幅较短 (中:{chinese_chars}, 英:{english_words}词)，建议扩充内容")

        return max(0.0, min(10.0, score))

    def _evaluate_quantitative_rigor(self, content: str, backtest_results: Optional[Dict]) -> float:
        """
        评估量化方法正确性
        - 公式定义和推导
        - 策略描述清晰度
        - 回测方法论
        - 统计检验
        """
        score = 4.0  # 基础分

        # 检查公式
        math_patterns = [
            (r'\$\$.*?\$\$', 'display_math'),  # $$...$$
            (r'\$.*?\$', 'inline_math'),       # $...$
            (r'\\begin\{equation', 'equation'),
            (r'\\frac\{', 'fraction'),
            (r'\\sum\{', 'summation'),
            (r'\\int\{', 'integration'),
        ]

        formula_count = 0
        for pattern, name in math_patterns:
            count = len(re.findall(pattern, content))
            formula_count += count

        if formula_count >= 5:
            score += 2.0
        elif formula_count >= 2:
            score += 1.0
        else:
            score += 0.0

        # 检查量化术语
        quant_terms = [
            r'sharpe|夏普',
            r'return|收益',
            r'volatility|波动率',
            r'drawdown|回撤',
            r'factor|因子',
            r'backtest|回测',
            r'statistic|统计',
            r'significance|显著性',
            r'p-value|p值',
            r't-stat|t统计量',
        ]

        term_matches = 0
        for term in quant_terms:
            if re.search(term, content, re.IGNORECASE):
                term_matches += 1

        if term_matches >= 6:
            score += 1.5
        elif term_matches >= 3:
            score += 1.0

        # 检查回测相关描述
        backtest_mentions = len(re.findall(r'backtest|回测', content, re.IGNORECASE))
        if backtest_mentions >= 2:
            score +=  .5

        # 检查是否提到风险控制
        if re.search(r'risk|风险', content, re.IGNORECASE):
            score += 0.5

        # 检查回测结果一致性（如果有）
        if backtest_results:
            # 验证论文中提到的数据是否与回测结果匹配
            stock_code = backtest_results.get('stock', '')
            if stock_code and stock_code in content:
                score += 1.0

            # 检查策略名称是否一致
            strategies = backtest_results.get('strategies', {}).keys()
            strategy_match = sum(1 for s in strategies if s.lower() in content.lower())
            if strategy_match >= 2:
                score += 0.5

        return max(0.0, min(10.0, score))

    def _evaluate_data_authenticity(self, content: str, backtest_results: Optional[Dict]) -> float:
        """
        评估数据真实性
        - 数据来源描述
        - 时间范围明确
        - 描述性统计
        - 数据可视化
        """
        score = 4.0  # 基础分

        # 检查数据来源描述
        data_sources = [
            r'baostock',
            r'akshare',
            r'wind',
            r'bloomberg',
            r'reuters',
            r'tushare',
            r'数据来源',
            r'source.*data',
            r'dataset',
        ]

        source_found = False
        for source in data_sources:
            if re.search(source, content, re.IGNORECASE):
                source_found = True
                score += 1.5
                break

        if not source_found:
            score -= 0.5

        # 检查时间范围
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # 2019-01-01
            r'\d{4}年.*?\d{4}年',   # 2019年-2024年
            r'from.*to',           # from 2019 to 2024
        ]

        date_found = False
        for pattern in date_patterns:
            if re.search(pattern, content):
                date_found = True
                score +=  .5
                break

        if not date_found:
            score -= 0.5

        # 检查描述性统计
        stats_terms = [
            r'mean|均值|平均',
            r'std|标准差',
            r'median|中位数',
            r'max|min|最大|最小',
            r'observations?|样本',
            r'description|描述性',
        ]

        stats_count = sum(1 for t in stats_terms if re.search(t, content, re.IGNORECASE))
        if stats_count >= 3:
            score += 1.0
        elif stats_count >= 1:
            score += 0.5

        # 检查图表
        figure_patterns = [
            r'\\begin\{figure',
            r'\\includegraphics',
            r'图\d+',
            r'figure\s*\d+',
            r'table\s*\d+',
            r'\\begin\{tabular',
        ]

        figure_count = sum(len(re.findall(p, content, re.IGNORECASE)) for p in figure_patterns)
        if figure_count >= 2:
            score += 1.0
        elif figure_count >= 1:
            score += 0.5

        # 验证回测结果数据
        if backtest_results:
            # 检查数据点数
            data_points = backtest_results.get('data_points', 0)
            if data_points > 1000:
                score += 1.0
            elif data_points > 500:
                score += 0.5

            # 检查策略结果是否有具体数值
            for name, data in backtest_results.get('strategies', {}).items():
                metrics = data.get('metrics', {})
                if metrics.get('total_return') is not None:
                    score += 0.2
                    break

        return max(0.0, min(10.0, score))

    def _evaluate_logical_coherence(self, content: str) -> float:
        """
        评估逻辑连贯性
        - 段落过渡
        - 章节衔接
        - 论证逻辑
        """
        score = 5.0  # 基础分

        # 检查过渡词和连接词
        transition_words = [
            r'however|然而',
            r'therefore|因此',
            r'furthermore|此外',
            r'moreover|而且',
            r'first|second|third|首先|其次|最后',
            r'in summary|总之',
            r'for example|例如',
        ]

        transition_count = sum(len(re.findall(t, content, re.IGNORECASE)) for t in transition_words)

        if transition_count >= 5:
            score += 1.5
        elif transition_count >= 2:
            score += 1.0
        else:
            score -= 0.5

        # 检查章节编号
        section_numbers = [
            r'\d+\.\d+',      # 1.2, 1.2.3
            r'第[一二三四五六七八九十]+',  # 第一, 第二
        ]

        number_pattern = r'\d+\.\d+'
        section_nums = re.findall(number_pattern, content)

        # 论文应该有清晰的章节结构
        if len(section_nums) >= 5:
            score += 1.0
        elif len(section_nums) >= 2:
            score += 0.5

        # 检查段落长度是否合理（避免过短或过长）
        paragraphs = re.split(r'\n\s*\n', content)
        avg_para_len = sum(len(p) for p in paragraphs) / max(len(paragraphs), 1)

        if 100 <= avg_para_len <= 500:
            score += 1.0
        elif 50 <= avg_para_len <= 800:
            score += 0.5
        else:
            score -= 0.5

        return max(0.0, min(10.0, score))

    def _evaluate_math_completeness(self, content: str) -> float:
        """
        评估公式完整性
        - 关键公式存在
        - 符号定义
        - 推导步骤
        """
        score = 4.0  # 基础分

        # 检查关键公式类型
        essential_formulas = [
            (r'\\sum|\\prod', '求和/求积'),        # 求和符号
            (r'\\frac|\\div', '分数/除法'),        # 分数
            (r'\^{2}|\^{3}|square|cubic', '幂运算'),  # 幂
            (r'\sqrt|root', '开方'),              # 开方
            (r'\\log|\\ln|logarithm', '对数'),     # 对数
            (r'\\exp|e\^{', '指数'),              # 指数
            (r'\\int', '积分'),                   # 积分
            (r'\\supset|\\subset|\\in', '集合运算'),   # 集合
        ]

        formula_types_found = 0
        for pattern, name in essential_formulas:
            if re.search(pattern, content, re.IGNORECASE):
                formula_types_found += 1

        score += formula_types_found * 0.5  # 每个公式类型 +0.5

        # 检查符号定义
        symbol_defs = [
            r'where\s+.+?=',
            r'let\s+.+?=',
            r'假设',
            r'defined as',
            r' denote',
        ]

        symbol_count = sum(len(re.findall(p, content, re.IGNORECASE)) for p in symbol_defs)
        if symbol_count >= 3:
            score += 1.0
        elif symbol_count >= 1:
            score += 0.5

        # 检查公式环境
        equation_envs = len(re.findall(r'\\begin\{equation', content))
        align_envs = len(re.findall(r'\\begin\{align', content))

        if equation_envs + align_envs >= 3:
            score += 1.5
        elif equation_envs + align_envs >= 1:
            score += 0.5

        return max(0.0, min(10.0, score))

    # ============================================================
    # 反馈生成
    # ============================================================

    def _collect_feedback(self, dimensions: Dict[str, float],
                          content: str, backtest_results: Optional[Dict]) -> Tuple[List[str], List[str]]:
        """收集问题和建议"""
        issues = []
        strengths = []

        # 根据维度得分分析问题
        if dimensions['academic_norms'] < 5.0:
            issues.append("论文结构不够完整，建议增加必要的章节")

        if dimensions['quantitative_rigor'] < 5.0:
            issues.append("量化方法描述不够严谨，建议补充公式和统计检验")

        if dimensions['data_authenticity'] < 5.0:
            issues.append("数据描述不够详细，建议补充数据来源和时间范围")

        if dimensions['logical_coherence'] < 5.0:
            issues.append("论文逻辑连贯性有待加强，建议增加过渡语句")

        if dimensions['math_completeness'] < 5.0:
            issues.append("公式完整性不足，建议补充关键公式的推导过程")

        # 发现优点
        if dimensions['academic_norms'] >= 7.0:
            strengths.append("论文结构完整，符合学术规范")

        if dimensions['quantitative_rigor'] >= 7.0:
            strengths.append("量化方法论描述严谨，公式使用得当")

        if dimensions['data_authenticity'] >= 7.0:
            strengths.append("数据描述真实可信，统计完备")

        if dimensions['math_completeness'] >= 7.0:
            strengths.append("数学公式完整，推导严谨")

        # 检查回测结果一致性
        if backtest_results and dimensions['data_authenticity'] >= 6.0:
            strengths.append(f"论文内容与回测数据一致，包含 {backtest_results.get('data_points', 0)} 条真实数据")

        return issues, strengths

    def _generate_feedback(self, dimensions: Dict[str, float],
                           issues: List[str], strengths: List[str]) -> str:
        """生成详细反馈文本"""
        lines = []
        lines.append("=" * 60)
        lines.append("论文质量评估报告")
        lines.append("=" * 60)
        lines.append("")

        lines.append("【各维度得分】")
        for dim, score in dimensions.items():
            dim_name = {
                'academic_norms': '学术规范性',
                'quantitative_rigor': '量化方法正确性',
                'data_authenticity': '数据真实性',
                'logical_coherence': '逻辑连贯性',
                'math_completeness': '公式完整性'
            }.get(dim, dim)

            bar = '█' * int(score) + '░' * (10 - int(score))
            lines.append(f"  {dim_name}: {score:.2f}/10 [{bar}]")

        lines.append("")
        lines.append("【优点】")
        if strengths:
            for s in strengths:
                lines.append(f"  ✓ {s}")
        else:
            lines.append("  (暂无明显优点)")

        lines.append("")
        lines.append("【待改进问题】")
        if issues:
            for i, issue in enumerate(issues, 1):
                lines.append(f"  {i}. {issue}")
        else:
            lines.append("  (暂无明显问题)")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    # 演示评估器使用

    print("=" * 70)
    print("PaperEvaluator 演示 - 量化论文质量评估")
    print("=" * 70)

    evaluator = PaperEvaluator(pass_threshold=5.5)

    # 模拟论文内容
    sample_paper = """
    \\title{基于技术指标的A股量化交易策略实证研究}

    \\begin{abstract}
    本文研究了中国A股市场中基于技术指标的量化交易策略表现。通过使用2019-2024年的日线数据，
    我们对三种主流策略进行了全面回测。实验结果表明，在扣除交易成本后，所有策略均未能
    超越买入持有基准。本研究为量化交易策略的评估提供了实证依据。
    \\end{abstract}

    \\section{引言}
    量化交易已成为现代金融领域的重要研究方向...

    \\section{方法论}
    我们采用以下技术指标构建交易策略...

    \\section{实验}
    数据来源: baostock
    时间范围: 2019-01-01 至 2024-12-31
    样本: 平安银行(000001) 日线数据

    回测结果:
    - MA交叉策略: 总收益 -63.68%, 夏普比率 -0.61, 最大回撤 -71.54%
    - RSI均值回归: 总收益 -65.89%, 最大回撤 -66.63%
    - 布林带策略: 总收益 -30.43%, 最大回撤 -38.77%

    \\section{结论}
    本文通过实证研究表明，技术分析策略在中国A股市场的表现不如预期...
    """

    # 模拟回测结果
    mock_backtest = {
        "stock": "000001 平安银行",
        "data_range": "2019-01-02 至 2024-12-31",
        "data_points": 1456,
        "strategies": {
            "ma_crossover": {"metrics": {"total_return": -63.68, "sharpe_ratio": -0.61}},
            "rsi_mean_reversion": {"metrics": {"total_return": -65.89}},
            "bollinger_bands": {"metrics": {"total_return": -30.43}}
        },
        "benchmark": {"total_return": 47.54}
    }

    # 执行评估
    result = evaluator.evaluate(sample_paper, mock_backtest)

    # 输出结果
    print(result.detailed_feedback)
    print()
    print(f"【最终评分】: {result.total_score:.2f}/10")
    print(f"【质量等级】: {result.quality_level.value}")
    print(f"【是否通过】: {'✅ 是' if result.passed else '❌ 否'} (>= {evaluator.pass_threshold} 分)")
    print()

    # 输出改进建议
    hints = result.get_improvement_hints()
    if hints:
        print("【改进建议】")
        for hint in hints:
            print(f"  → {hint}")
    print()
    print("=" * 70)

    # 评估另一篇较差的论文
    print("\n【对比评估】较差的论文示例:")
    poor_paper = """
    \\title{交易策略研究}

    我们研究了股票交易策略。策略效果很好，赚了很多钱。
    """

    result2 = evaluator.evaluate(poor_paper)
    print(f"评分: {result2.total_score:.2f}/10, 通过: {result2.passed}")
    print(f"问题: {', '.join(result2.issues)}")