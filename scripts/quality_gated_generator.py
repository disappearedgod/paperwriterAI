"""
质量门控论文生成器 - QualityGatedPaperGenerator
实现"生成→评估→优化"的迭代循环，直到论文质量达到5.5分以上

工作流程:
1. 接收论文主题和约束条件
2. 调用LLM生成论文初稿
3. 评估论文质量 (PaperEvaluator)
4. 如果分数 < 5.5，根据反馈优化后重新生成
5. 重复直到通过评估或达到最大迭代次数

作者: 魏宏 (Wei Hong)
用于: FARS量化研究系统的自动化论文生成
"""

import json
import time
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, Generator
from pathlib import Path
from datetime import datetime

from paper_evaluator import PaperEvaluator, EvaluationResult, QualityLevel
from cross_sectional_factors import CrossSectionalFactorFramework, FactorPortfolioResult


@dataclass
class GenerationConfig:
    """生成配置"""
    max_iterations: int = 5                   # 最大迭代次数
    pass_threshold: float = 5.5              # 通过阈值
    save_checkpoints: bool = True             # 保存检查点
    checkpoint_dir: str = "./checkpoints"     # 检查点目录
    verbose: bool = True                      # 详细输出
    auto_optimize: bool = True                # 自动优化
    use_real_data: bool = True                # 使用真实数据


@dataclass
class GenerationRecord:
    """生成记录"""
    iteration: int                            # 迭代次数
    timestamp: str                            # 时间戳
    score: float                              # 本次评分
    quality_level: QualityLevel               # 质量等级
    issues: List[str]                        # 发现的问题
    content_preview: str                      # 内容预览（前200字符）
    optimization_applied: Optional[str] = None  # 应用的优化策略

    def to_dict(self) -> Dict[str, Any]:
        return {
            'iteration': self.iteration,
            'timestamp': self.timestamp,
            'score': round(self.score, 2),
            'quality_level': self.quality_level.value,
            'issues': self.issues,
            'content_preview': self.content_preview[:200],
            'optimization_applied': self.optimization_applied
        }


class QualityGatedPaperGenerator:
    """
    质量门控论文生成器

    核心思想：论文生成不是一次性完成，而是通过迭代不断优化，
    直到达到可发表的质量标准。

    示例用法:
        generator = QualityGatedPaperGenerator(config)
        result = generator.generate(
            title="基于技术指标的A股量化交易策略实证研究",
            authors="魏宏",
            abstract="本文研究...",
            backtest_results=backtest_data,
            api_caller=call_minimax_api
        )

        print(f"最终评分: {result['final_score']}")
        print(f"迭代次数: {result['iterations_used']}")
        print(f"论文内容: {result['content']}")
    """

    def __init__(self, config: Optional[GenerationConfig] = None):
        self.config = config or GenerationConfig()
        self.evaluator = PaperEvaluator(pass_threshold=self.config.pass_threshold)
        self.factor_framework = CrossSectionalFactorFramework()
        self.generation_history: List[GenerationRecord] = []

        # 创建检查点目录
        if self.config.save_checkpoints:
            Path(self.config.checkpoint_dir).mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        title: str,
        authors: str,
        abstract: str,
        backtest_results: Optional[Dict] = None,
        factor_results: Optional[List[FactorPortfolioResult]] = None,
        api_caller: Callable[[str, str], str] = None
    ) -> Dict[str, Any]:
        """
        生成论文并通过质量门控

        参数:
            title: 论文标题
            authors: 作者列表
            abstract: 摘要
            backtest_results: 回测结果数据
            factor_results: 因子分析结果
            api_caller: LLM API调用函数 (system_prompt, user_prompt) -> response

        返回:
            {
                'passed': bool,
                'final_score': float,
                'iterations_used': int,
                'content': str,
                'evaluation': EvaluationResult,
                'history': List[GenerationRecord]
            }
        """
        print("=" * 70)
        print(f"质量门控论文生成 - 开始")
        print(f"标题: {title}")
        print(f"通过阈值: {self.config.pass_threshold}")
        print("=" * 70)
        print()

        best_score = 0.0
        best_content = ""
        best_evaluation = None
        iterations_used = 0

        for iteration in range(1, self.config.max_iterations + 1):
            print(f"\n【迭代 {iteration}/{self.config.max_iterations}】")
            print("-" * 40)

            # 构建当前迭代的提示词
            if iteration == 1:
                # 第一次生成：完整提示
                system_prompt, user_prompt = self._build_initial_prompts(
                    title, authors, abstract, backtest_results, factor_results
                )
            else:
                # 后续迭代：根据反馈优化
                system_prompt, user_prompt = self._build_optimized_prompts(
                    title, authors, abstract, backtest_results, factor_results,
                    previous_content=best_content,
                    previous_evaluation=best_evaluation
                )

            # 生成内容
            if api_caller:
                content = api_caller(system_prompt, user_prompt)
            else:
                # 使用模拟生成（演示用）
                content = self._mock_generate(iteration, best_content)

            iterations_used = iteration

            # 评估质量
            evaluation = self.evaluator.evaluate(content, backtest_results)
            current_score = evaluation.total_score

            # 记录生成历史
            record = GenerationRecord(
                iteration=iteration,
                timestamp=datetime.now().isoformat(),
                score=current_score,
                quality_level=evaluation.quality_level,
                issues=evaluation.issues,
                content_preview=content[:500]
            )
            self.generation_history.append(record)

            # 打印评估结果
            print(f"\n评分: {current_score:.2f}/10 ({evaluation.quality_level.value})")
            print(f"通过: {'✅ 是' if evaluation.passed else '❌ 否'}")

            if evaluation.issues:
                print(f"问题: {', '.join(evaluation.issues[:3])}")

            # 保存检查点
            if self.config.save_checkpoints:
                self._save_checkpoint(iteration, content, evaluation)

            # 检查是否通过
            if evaluation.passed:
                best_score = current_score
                best_content = content
                best_evaluation = evaluation
                print(f"\n🎉 论文质量已达标！")
                break

            # 更新最佳内容
            if current_score > best_score:
                best_score = current_score
                best_content = content
                best_evaluation = evaluation

            print(f"\n当前最佳分数: {best_score:.2f}")

        # 返回结果
        return {
            'passed': best_evaluation.passed if best_evaluation else False,
            'final_score': best_score,
            'iterations_used': iterations_used,
            'content': best_content,
            'evaluation': best_evaluation,
            'history': [r.to_dict() for r in self.generation_history]
        }

    def _build_initial_prompts(
        self,
        title: str,
        authors: str,
        abstract: str,
        backtest_results: Optional[Dict],
        factor_results: Optional[List[FactorPortfolioResult]]
    ) -> tuple:
        """构建初始提示词"""
        system_prompt = """你是一位资深的量化交易研究学者，擅长用严谨的学术语言撰写高质量的研究论文。

写作要求:
1. 使用规范的学术中文写作
2. 数学公式使用LaTeX格式: $公式$ 或 $$公式$$
3. 表格使用标准LaTeX格式
4. 保持逻辑连贯，论述严谨
5. 每个主要部分应充分展开（摘要200-300字，引言800-1000字）
6. 真实描述数据和分析结果，不虚构

论文结构:
1. 摘要 (Abstract)
2. 引言 (Introduction) - 研究背景、问题、贡献
3. 相关工作 (Related Work) - 文献综述
4. 方法论 (Methodology) - 策略设计、因子构建
5. 实验设置 (Experimental Setup) - 数据、评估指标
6. 实验结果 (Results) - 回测结果、因子分析
7. 讨论 (Discussion) - 结果分析、局限性
8. 结论 (Conclusion)
9. 参考文献 (References)
"""

        # 构建用户提示
        user_parts = [
            f"# 论文主题\n{title}",
            f"# 作者\n{authors}",
            f"# 摘要\n/{abstract}/",
        ]

        # 添加回测数据
        if backtest_results:
            user_parts.append(f"""
# 真实回测数据
- 股票: {backtest_results.get('stock', 'N/A')}
- 时间范围: {backtest_results.get('data_range', 'N/A')}
- 数据点数: {backtest_results.get('data_points', 0)}

## 策略回测结果
""")
            for name, data in backtest_results.get('strategies', {}).items():
                metrics = data.get('metrics', {})
                user_parts.append(f"### {name}")
                for k, v in metrics.items():
                    user_parts.append(f"- {k}: {v:.4f}" if isinstance(v, float) else f"- {k}: {v}")

            benchmark = backtest_results.get('benchmark', {})
            if benchmark:
                user_parts.append(f"\n## 基准收益")
                for k, v in benchmark.items():
                    user_parts.append(f"- {k}: {v:.4f}" if isinstance(v, float) else f"- {k}: {v}")

        # 添加因子分析
        if factor_results:
            user_parts.append("""
# 因子分析结果
""")
            for res in factor_results[:5]:
                user_parts.append(f"- {res.factor_name}: IC={res.information_coefficient:.4f}, p={res.p_value:.4f}")

        user_parts.append("""
# 写作要求
请撰写一篇完整的学术论文，包含以上所有真实数据。确保：
1. 每个章节都有实质性内容
2. 公式使用LaTeX格式
3. 结果部分与提供的回测数据一致
4. 逻辑连贯，论证严密
""")

        return system_prompt, "\n".join(user_parts)

    def _build_optimized_prompts(
        self,
        title: str,
        authors: str,
        abstract: str,
        backtest_results: Optional[Dict],
        factor_results: Optional[List[FactorPortfolioResult]],
        previous_content: str,
        previous_evaluation: EvaluationResult
    ) -> tuple:
        """根据评估反馈构建优化提示词"""
        system_prompt = """你是一位资深的量化交易研究学者，擅长用严谨的学术语言撰写高质量的研究论文。

重要：你正在对一篇论文进行修订，需要根据评审意见进行优化。

写作要求:
1. 使用规范的学术中文写作
2. 数学公式使用LaTeX格式
3. 保持逻辑连贯，论述严谨
4. 保留上一版本的优秀内容，只改进问题部分
"""

        # 收集优化建议
        improvements = []

        if previous_evaluation:
            for issue in previous_evaluation.issues:
                if "结构" in issue or "章节" in issue:
                    improvements.append("增加论文结构的完整性，确保包含所有必要的章节（摘要、引言、方法、实验、结论等）")
                if "公式" in issue or "推导" in issue:
                    improvements.append("补充更多的数学公式和推导过程，使用标准LaTeX格式")
                if "数据" in issue or "描述性" in issue:
                    improvements.append("增加数据描述的详细程度，包括描述性统计和数据来源说明")
                if "引用" in issue:
                    improvements.append("增加文献引用的数量，确保引用格式规范")
                if "逻辑" in issue or "过渡" in issue:
                    improvements.append("加强段落之间的逻辑衔接，增加过渡语句")

        user_parts = [
            f"# 论文主题\n{title}",
            f"# 作者\n{authors}",
            f"# 摘要\n/{abstract}/",
            "\n# 上一版本评审意见",
            f"评分: {previous_evaluation.total_score:.2f}/10",
            "\n问题列表:"
        ]

        if previous_evaluation:
            for i, issue in enumerate(previous_evaluation.issues, 1):
                user_parts.append(f"{i}. {issue}")

        user_parts.append("\n# 优化建议")
        for imp in improvements:
            user_parts.append(f"- {imp}")

        user_parts.append(f"""
# 上一版本论文内容
---开始---
{previous_content[:3000]}...
---结束---

# 写作要求
1. 保留上一版本中好的内容
2. 重点改进评审中指出的问题
3. 保持论文的完整性和连贯性
4. 确保与回测数据一致
5. 如果添加新内容，确保质量不低于原有内容
""")

        return system_prompt, "\n".join(user_parts)

    def _mock_generate(self, iteration: int, previous_content: str) -> str:
        """模拟生成（用于演示）"""
        print("  [使用模拟生成器]")

        if iteration == 1:
            # 初版模拟
            return f"""
# 摘要

本文研究了中国A股市场中基于技术指标的量化交易策略。我们使用2019-2024年的历史数据对三种主流策略进行了全面回测。

# 引言

量化交易是现代金融领域的重要研究方向...

# 方法论

我们采用移动平均线交叉、RSI均值回归、布林带策略进行回测...

# 实验结果

回测结果显示，所有策略均未能超越买入持有基准...

# 结论

本文为量化交易策略的评估提供了实证依据。
"""
        else:
            # 改进版模拟
            improvement = min(iteration * 0.8, 2.0)
            return f"""
# 摘要

本文研究了中国A股市场中基于技术指标的量化交易策略。我们使用2019-2024年共{1456}条真实日线数据，对三种主流策略进行了严谨的回测分析。研究发现，在考虑交易成本后，所有策略均未能超越买入持有基准（年化收益6.96%），揭示了技术分析策略在实际应用中的局限性。

# 引言

量化交易作为一种系统化的投资方法，在过去二十年间获得了广泛关注（Fama & French, 1993; Jegadeesh & Titman, 1993）。与主观判断交易不同，量化交易依赖于数学模型和计算机程序来识别交易机会。

本研究聚焦于以下问题：
1. 常见技术分析策略在中国A股市场的表现如何？
2. 这些策略在扣除交易成本后是否仍能获得正收益？

# 相关工作

技术分析策略基于历史价格数据进行交易决策。移动平均线交叉策略（MA Crossover）由George Lane于1950年代提出...相对强弱指数（RSI）由J. Welles Wilder Jr.于1978年提出...

# 方法论

## 因子构建

我们使用以下技术因子进行策略设计：

动量因子：
$$Momentum_t = \\frac{{P_t - P_{{t-22}}}}{{P_{{t-22}}}}$$

波动率因子：
$$\\sigma_{{20d}} = \\sqrt{{252}} \\cdot \\sqrt{{\\frac{{\\sum_{{t=1}}^{{20}}(r_t - \\bar{{r}})^2}}{{19}}}}$$

## 策略设计

1. **MA交叉策略**: 当MA5上穿MA20时买入，下穿时卖出
2. **RSI均值回归**: RSI<30时买入，RSI>70时卖出
3. **布林带策略**: 价格触及下轨时买入，上轨时卖出

# 实验设置

## 数据描述

- 数据来源: baostock
- 时间范围: 2019-01-02 至 2024-12-31
- 样本股票: 平安银行(000001)
- 观测数量: 1456个交易日

描述性统计:
- 日均收益率: 0.03%
- 收益率标准差: 1.42%
- 最大单日收益: 9.87%
- 最大单日亏损: -10.15%

## 评估指标

我们使用以下指标评估策略表现：
- 总收益率 (Total Return)
- 年化收益率 (Annual Return)
- 夏普比率 (Sharpe Ratio)
- 最大回撤 (Maximum Drawdown)
- 卡玛比率 (Calmar Ratio)

# 实验结果

## 回测结果汇总

| 策略 | 总收益 | 年化收益 | 夏普比率 | 最大回撤 |
|------|--------|----------|----------|----------|
| MA交叉 | -63.68% | -16.08% | -0.61 | -71.54% |
| RSI均值回归 | -65.89% | -16.98% | -0.52 | -66.63% |
| 布林带 | -30.43% | -6.09% | -0.28 | -38.77% |
| 买入持有 | 47.54% | 6.96% | 0.45 | -28.32% |

## 结果分析

实验结果表明，在考虑0.1%的交易成本后，所有技术分析策略均未能战胜买入持有基准。其中：
- MA交叉策略表现最差，主要原因是频繁交易导致的交易成本累积
- 布林带策略相对较好，但仍有较大的改进空间

# 讨论

本研究存在以下局限性：
1. 仅使用单一股票进行回测，结论的普适性需要进一步验证
2. 未考虑流动性限制和滑点
3. 回测期间（2019-2024）包含了特殊市场环境（如2020年新冠疫情）

未来研究可以从以下方向改进：
1. 扩展到多股票组合
2. 加入止损和仓位管理机制
3. 结合机器学习方法优化策略参数

# 结论

本文通过实证研究表明，技术分析策略在中国A股市场的表现不如预期。这一发现与有效市场假说相一致，表明通过技术分析难以获得超额收益。

# 参考文献

[1] Fama, E. F., & French, K. R. (1993). Common risk factors in the returns on stocks and bonds. Journal of Financial Economics.
[2] Jegadeesh, N., & Titman, S. (1993). Returns to Buying Winners and Selling Losers. Journal of Finance.
[3] Wilder, J. W. (1978). New Concepts in Technical Trading Systems. Greensboro: Trend Research.
"""
    def _save_checkpoint(self, iteration: int, content: str, evaluation: EvaluationResult):
        """保存检查点"""
        checkpoint = {
            'iteration': iteration,
            'timestamp': datetime.now().isoformat(),
            'score': evaluation.total_score,
            'quality_level': evaluation.quality_level.value,
            'content': content,
            'evaluation': evaluation.to_dict()
        }

        filepath = Path(self.config.checkpoint_dir) / f"iteration_{iteration}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)

        if self.config.verbose:
            print(f"  检查点已保存: {filepath}")

    def get_generation_summary(self) -> str:
        """获取生成总结"""
        if not self.generation_history:
            return "暂无生成记录"

        lines = []
        lines.append("=" * 60)
        lines.append("论文生成历史")
        lines.append("=" * 60)
        lines.append("")

        for record in self.generation_history:
            lines.append(f"迭代 {record.iteration} [{record.timestamp[:19]}]")
            lines.append(f"  评分: {record.score:.2f}/10 ({record.quality_level.value})")
            if record.issues:
                lines.append(f"  问题: {', '.join(record.issues[:2])}")
            lines.append(f"  预览: {record.content_preview[:100]}...")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


# ============================================================
# 完整集成示例
# ============================================================

def demo_full_pipeline():
    """演示完整流程"""

    print("=" * 70)
    print("质量门控论文生成器 - 完整演示")
    print("=" * 70)
    print()

    # 创建生成器
    config = GenerationConfig(
        max_iterations=3,
        pass_threshold=5.5,
        verbose=True
    )
    generator = QualityGatedPaperGenerator(config)

    # 模拟回测结果
    backtest_results = {
        "stock": "000001 平安银行 (sz.000001)",
        "data_range": "2019-01-02 至 2024-12-31",
        "data_points": 1456,
        "strategies": {
            "ma_crossover": {
                "metrics": {
                    "total_return": -63.68,
                    "annual_return": -16.08,
                    "sharpe_ratio": -0.61,
                    "max_drawdown": -71.54
                }
            },
            "rsi_mean_reversion": {
                "metrics": {
                    "total_return": -65.89,
                    "annual_return": -16.98,
                    "max_drawdown": -66.63
                }
            },
            "bollinger_bands": {
                "metrics": {
                    "total_return": -30.43,
                    "annual_return": -6.09,
                    "max_drawdown": -38.77
                }
            }
        },
        "benchmark": {
            "total_return": 47.54,
            "annual_return": 6.96,
            "sharpe_ratio": 0.45,
            "max_drawdown": -28.32
        }
    }

    # 模拟因子分析结果
    factor_results = [
        FactorPortfolioResult(
            factor_name="momentum_1m",
            top_quantile_return=0.05,
            bottom_quantile_return=0.02,
            spread_return=0.03,
            spread_volatility=0.10,
            information_coefficient=0.08,
            information_ratio=0.80,
            turnover_rate=0.45,
            t_statistic=2.5,
            p_value=0.01
        ),
    ]

    # 执行生成
    result = generator.generate(
        title="基于技术指标的A股量化交易策略实证研究",
        authors="魏宏",
        abstract="本研究对中国A股市场的技术分析策略进行了全面评估...",
        backtest_results=backtest_results,
        factor_results=factor_results
    )

    # 输出结果
    print()
    print("=" * 70)
    print("生成结果")
    print("=" * 70)
    print(f"通过: {'✅ 是' if result['passed'] else '❌ 否'}")
    print(f"最终评分: {result['final_score']:.2f}/10")
    print(f"迭代次数: {result['iterations_used']}")
    print()

    # 显示历史
    print(generator.get_generation_summary())

    return result


if __name__ == "__main__":
    demo_full_pipeline()