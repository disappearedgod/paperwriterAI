"""
分块论文生成器 - ChunkedPaperGenerator
通过将论文分成多个章节生成，解决 LLM API 的 token 限制问题

原理：
- MiniMax API context window = 196608 tokens
- 每次调用时，输入 prompt + 输出 tokens 必须 < 196608
- 通过分章节生成，每章节独立构建紧凑 prompt，保持输入在安全范围内

章节生成策略：
1. 摘要 → 引言 → 相关工作 → 方法论 → 实验设置 → 实验结果 → 讨论 → 结论
2. 每章节携带"上下文摘要"（前面章节的关键信息），但控制总 prompt 大小
3. 最后组装成完整论文

作者: 魏宏 (Wei Hong)
用于: FARS量化研究系统的自动化论文生成
"""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, Generator
from pathlib import Path
from datetime import datetime


@dataclass
class ChunkConfig:
    """分块生成配置"""
    # API 限制
    max_context_tokens: int = 180000  # 预留 buffer，实际 limit 是 196608
    max_output_tokens: int = 16000    # 每次输出 token 上限
    # 章节配置
    sections_order: List[str] = field(default_factory=lambda: [
        "abstract", "introduction", "related_work", "methodology",
        "experimental_setup", "experimental_results", "discussion", "conclusion"
    ])
    # 上下文保留策略：只保留前 N 个章节的摘要
    context_sections_limit: int = 3   # 只携带前 3 个章节的摘要作为上下文


@dataclass
class SectionResult:
    """单个章节生成结果"""
    section_name: str
    content: str
    section_index: int
    prompt_tokens: int = 0
    output_tokens: int = 0
    success: bool = True
    error: str = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_name": self.section_name,
            "content": self.content,
            "section_index": self.section_index,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "success": self.success,
            "error": self.error
        }


# 章节提示词模板 - 保持简洁
SECTION_PROMPTS = {
    "abstract": """你是一位资深的量化交易研究学者。请为论文撰写摘要。

要求：
- 200-300字
- 使用规范的学术中文
- 包含：研究问题、方法、主要发现、结论
- 不要使用"首先、其次"等词，直接写

论文信息：
- 标题：{title}
- 作者：{authors}
- 主题：{topic}

{backtest_summary}
{factor_summary}

请直接输出摘要内容：""",

    "introduction": """你是一位资深的量化交易研究学者。请撰写论文引言。

要求：
- 800-1000字
- 包含：研究背景、问题动机、研究贡献
- 使用学术中文，规范表达
- 引用相关文献时使用 (Author, Year) 格式

论文信息：
- 标题：{title}
- 主题：{topic}

前章摘要：
{context_summary}

请直接输出引言内容：""",

    "related_work": """你是一位资深的量化交易研究学者。请撰写相关工作章节。

要求：
- 600-800字
- 综述相关文献
- 分类整理：技术分析、量化策略、机器学习应用
- 指出现有研究的不足

论文信息：
- 标题：{title}

前章摘要：
{context_summary}

请直接输出相关工作内容：""",

    "methodology": """你是一位资深的量化交易研究学者。请撰写方法论章节。

要求：
- 800-1000字
- 详细描述策略设计和因子构建
- 使用 LaTeX 公式：$公式$ 或 $$公式组$$
- 清晰描述数据处理方法

论文信息：
- 标题：{title}

{backtest_summary}

前章摘要：
{context_summary}

请直接输出方法论内容：""",

    "experimental_setup": """你是一位资深的量化交易研究学者。请撰写实验设置章节。

要求：
- 500-600字
- 描述数据集：来源、时间范围、样本
- 描述评估指标：收益率、夏普比率、最大回撤等
- 描述实验环境/参数设置

论文信息：
- 标题：{title}

{backtest_summary}

请直接输出实验设置内容：""",

    "experimental_results": """你是一位资深的量化交易研究学者。请撰写实验结果章节。

要求：
- 800-1000字
- 包含数据表格（使用 LaTeX tabular）
- 分析策略表现
- 与基准对比

论文信息：
- 标题：{title}

{backtest_results_text}

{factor_results_text}

前章摘要：
{context_summary}

请直接输出实验结果内容：""",

    "discussion": """你是一位资深的量化交易研究学者。请撰写讨论章节。

要求：
- 600-800字
- 分析结果的原因和意义
- 讨论研究局限性
- 展望未来研究方向

论文信息：
- 标题：{title}

前章摘要：
{context_summary}

请直接输出讨论内容：""",

    "conclusion": """你是一位资深的量化交易研究学者。请撰写结论章节。

要求：
- 300-400字
- 总结研究发现
- 强调研究贡献
- 提出实践意义

论文信息：
- 标题：{title}

前章摘要：
{context_summary}

请直接输出结论内容："""
}


class ChunkedPaperGenerator:
    """
    分块论文生成器

    核心思想：将长论文分成多个独立章节生成，每个章节构建紧凑的 prompt，
    携带前续章节摘要作为上下文，确保总 token 数在 LLM 限制内。

    使用示例:
        generator = ChunkedPaperGenerator(config)
        result = generator.generate(
            title="基于技术指标的A股量化交易策略实证研究",
            authors="魏宏",
            topic="量化交易策略评估",
            backtest_results=backtest_data,
            api_caller=call_minimax_api
        )
        print(f"论文: {result['full_paper']}")
    """

    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()
        self.section_results: List[SectionResult] = []

    def generate(
        self,
        title: str,
        authors: str,
        topic: str,
        backtest_results: Optional[Dict] = None,
        factor_results: Optional[List[Dict]] = None,
        api_caller: Callable[[str, str], str] = None
    ) -> Dict[str, Any]:
        """
        生成分块论文

        Args:
            title: 论文标题
            authors: 作者列表
            topic: 研究主题
            backtest_results: 回测结果
            factor_results: 因子分析结果
            api_caller: LLM API 调用函数 (system_prompt, user_prompt) -> response

        Returns:
            {
                'success': bool,
                'full_paper': str,
                'sections': List[SectionResult],
                'total_tokens': int,
                'errors': List[str]
            }
        """
        print("=" * 60)
        print("分块论文生成器 - 开始")
        print("=" * 60)
        print(f"标题: {title}")
        print(f"章节数: {len(self.config.sections_order)}")
        print()

        self.section_results = []
        all_sections_content = []
        total_tokens = 0
        errors = []

        # 构建回测结果摘要文本
        backtest_summary = self._build_backtest_summary(backtest_results)
        backtest_results_text = self._build_backtest_results_text(backtest_results)

        # 构建因子结果摘要文本
        factor_summary = self._build_factor_summary(factor_results)
        factor_results_text = self._build_factor_results_text(factor_results)

        # 逐章节生成
        for idx, section_name in enumerate(self.config.sections_order):
            print(f"\n【章节 {idx + 1}/{len(self.config.sections_order)}】: {section_name}")

            # 构建上下文摘要（只保留前 N 个章节）
            context_summary = self._build_context_summary(idx)

            # 构建章节 prompt
            section_prompt = self._build_section_prompt(
                section_name=section_name,
                title=title,
                authors=authors,
                topic=topic,
                backtest_summary=backtest_summary,
                backtest_results_text=backtest_results_text,
                factor_summary=factor_summary,
                factor_results_text=factor_results_text,
                context_summary=context_summary
            )

            # 估算 prompt tokens（简单估算：中文 1 token ≈ 1.5 字符）
            prompt_tokens = len(section_prompt) // 2
            total_tokens += prompt_tokens

            print(f"  Prompt 长度: ~{prompt_tokens} tokens")

            # 调用 API 生成
            if api_caller:
                system_prompt = "你是一位资深的量化交易研究学者，擅长用严谨的学术语言撰写高质量的研究论文。使用规范的学术中文写作。"
                content = api_caller(system_prompt, section_prompt)
            else:
                # 模拟生成
                content = self._mock_generate_section(section_name, idx)
                print("  [模拟生成]")

            # 处理生成结果
            if content:
                section_result = SectionResult(
                    section_name=section_name,
                    content=content,
                    section_index=idx,
                    prompt_tokens=prompt_tokens,
                    output_tokens=len(content) // 2,
                    success=True
                )
                all_sections_content.append(content)
                print(f"  ✅ 成功 ({len(content)} 字符)")
            else:
                section_result = SectionResult(
                    section_name=section_name,
                    content=f"[{section_name} 生成失败]",
                    section_index=idx,
                    success=False,
                    error="API 返回为空"
                )
                errors.append(f"{section_name}: API 返回为空")
                all_sections_content.append(f"\n\n## {section_name.upper()}\n\n[{section_name} 内容缺失]\n\n")
                print(f"  ❌ 失败")

            self.section_results.append(section_result)

        # 组装完整论文
        full_paper = self._assemble_paper(title, authors, all_sections_content)

        # 打印摘要
        print()
        print("=" * 60)
        print("生成完成")
        print("=" * 60)
        print(f"成功章节: {sum(1 for s in self.section_results if s.success)}/{len(self.section_results)}")
        print(f"总 prompt tokens: ~{total_tokens}")
        if errors:
            print(f"错误: {errors}")

        return {
            'success': sum(1 for s in self.section_results if s.success) == len(self.section_results),
            'full_paper': full_paper,
            'sections': [s.to_dict() for s in self.section_results],
            'total_tokens': total_tokens,
            'errors': errors
        }

    def _build_backtest_summary(self, backtest_results: Optional[Dict]) -> str:
        """构建回测结果摘要"""
        if not backtest_results:
            return "回测数据：N/A"

        lines = ["回测数据："]
        lines.append(f"- 股票: {backtest_results.get('stock', 'N/A')}")
        lines.append(f"- 时间范围: {backtest_results.get('data_range', 'N/A')}")
        lines.append(f"- 数据点数: {backtest_results.get('data_points', 0)}")

        strategies = backtest_results.get('strategies', {})
        if strategies:
            lines.append("- 策略回测结果:")
            for name, data in list(strategies.items())[:3]:
                metrics = data.get('metrics', {})
                ret = metrics.get('total_return', 'N/A')
                sharpe = metrics.get('sharpe_ratio', 'N/A')
                if isinstance(ret, float) and isinstance(sharpe, float):
                    lines.append(f"  {name}: 收益 {ret:.2f}%, 夏普比率 {sharpe:.2f}")
                else:
                    lines.append(f"  {name}: 收益 {ret}, 夏普比率 {sharpe}")

        return "\n".join(lines)

    def _build_backtest_results_text(self, backtest_results: Optional[Dict]) -> str:
        """构建完整的回测结果文本（用于实验结果章节）"""
        if not backtest_results:
            return "回测数据：N/A"

        lines = ["## 回测结果\n"]

        strategies = backtest_results.get('strategies', {})
        if strategies:
            lines.append("| 策略 | 总收益 | 年化收益 | 夏普比率 | 最大回撤 |")
            lines.append("|------|--------|----------|----------|----------|")
            for name, data in strategies.items():
                metrics = data.get('metrics', {})
                ret = metrics.get('total_return', 0)
                annual = metrics.get('annual_return', 0)
                sharpe = metrics.get('sharpe_ratio', 0)
                mdd = metrics.get('max_drawdown', 0)
                if all(isinstance(x, (int, float)) for x in [ret, annual, sharpe, mdd]):
                    lines.append(f"| {name} | {ret:.2f}% | {annual:.2f}% | {sharpe:.2f} | {mdd:.2f}% |")
                else:
                    lines.append(f"| {name} | {ret} | {annual} | {sharpe} | {mdd} |")

        benchmark = backtest_results.get('benchmark', {})
        if benchmark:
            lines.append(f"\n基准收益: {benchmark.get('annual_return', 0):.2f}%")

        return "\n".join(lines)

    def _build_factor_summary(self, factor_results: Optional[List[Dict]]) -> str:
        """构建因子结果摘要"""
        if not factor_results:
            return "因子分析：N/A"

        lines = ["因子分析结果："]
        for res in factor_results[:5]:
            name = res.get('factor_name', 'unknown')
            ic = res.get('information_coefficient', 0)
            p_val = res.get('p_value', 1)
            lines.append(f"- {name}: IC={ic:.4f}, p={p_val:.4f}")

        return "\n".join(lines)

    def _build_factor_results_text(self, factor_results: Optional[List[Dict]]) -> str:
        """构建因子结果文本（用于实验结果章节）"""
        if not factor_results:
            return "因子分析：N/A"

        lines = ["## 因子分析结果\n"]
        lines.append("| 因子 | IC | IR | t统计量 | p值 |")
        lines.append("|------|----|----|---------|-----|")

        for res in factor_results[:10]:
            name = res.get('factor_name', 'unknown')
            ic = res.get('information_coefficient', 0)
            ir = res.get('information_ratio', 0)
            t_stat = res.get('t_statistic', 0)
            p_val = res.get('p_value', 1)
            lines.append(f"| {name} | {ic:.4f} | {ir:.2f} | {t_stat:.2f} | {p_val:.4f} |")

        return "\n".join(lines)

    def _build_context_summary(self, current_idx: int) -> str:
        """构建前续章节摘要作为上下文"""
        if current_idx == 0:
            return ""

        context_sections = []
        for i in range(max(0, current_idx - self.config.context_sections_limit), current_idx):
            section = self.section_results[i]
            if section.success and section.content:
                # 提取前200字符作为摘要
                content_preview = section.content[:200].replace('\n', ' ')
                context_sections.append(f"- {section.section_name}: {content_preview}...")

        if context_sections:
            return "\n".join(context_sections)
        return ""

    def _build_section_prompt(
        self,
        section_name: str,
        title: str,
        authors: str,
        topic: str,
        backtest_summary: str,
        backtest_results_text: str,
        factor_summary: str,
        factor_results_text: str,
        context_summary: str
    ) -> str:
        """构建特定章节的 prompt"""
        template = SECTION_PROMPTS.get(section_name, SECTION_PROMPTS["abstract"])

        # 替换模板变量
        prompt = template.format(
            title=title,
            authors=authors,
            topic=topic,
            backtest_summary=backtest_summary,
            backtest_results_text=backtest_results_text,
            factor_summary=factor_summary,
            factor_results_text=factor_results_text,
            context_summary=context_summary or "（无前章摘要）"
        )

        return prompt

    def _mock_generate_section(self, section_name: str, idx: int) -> str:
        """模拟生成章节内容（用于测试）"""
        mock_content = {
            "abstract": """本研究对中国A股市场中基于技术指标的量化交易策略进行了全面评估。我们使用2019-2024年共1456条真实日线数据，对三种主流策略（移动平均线交叉、RSI均值回归、布林带策略）进行了严谨的回测分析。研究发现，在考虑0.1%交易成本后，所有策略均未能超越买入持有基准（年化收益6.96%），揭示了技术分析策略在实际应用中的局限性。""",

            "introduction": """量化交易作为一种系统化的投资方法，在过去二十年间获得了广泛关注。与主观判断交易不同，量化交易依赖于数学模型和计算机程序来识别交易机会。

本研究聚焦于以下核心问题：常见技术分析策略在中国A股市场的表现如何？这些策略在扣除交易成本后是否仍能获得正收益？

本文的主要贡献包括：（1）首次对三种主流技术分析策略在A股市场进行全面的历史回测；（2）考虑了现实交易成本和流动性限制；（3）为个人投资者和机构提供了策略选择的实证依据。""",

            "related_work": """技术分析策略基于历史价格数据进行交易决策。移动平均线交叉策略（MA Crossover）由George Lane于1950年代提出，是最为广泛使用的趋势跟踪策略之一。

相对强弱指数（RSI）由J. Welles Wilder Jr.于1978年提出，用于衡量价格变动的速度和幅度。布林带策略基于统计原理，利用价格的标准差构建交易通道。

近年来，机器学习方法也被应用于技术分析策略的优化。Zhang et al. (2020) 提出了基于LSTM网络的短期价格预测模型。""",

            "methodology": """我们采用以下三种技术分析策略进行回测：

1. MA交叉策略：当MA5上穿MA20时买入，下穿时卖出
2. RSI均值回归策略：RSI<30时买入，RSI>70时卖出
3. 布林带策略：价格触及下轨时买入，上轨时卖出

因子构建：
动量因子：$Momentum_t = \\frac{P_t - P_{t-22}}{P_{t-22}}$
波动率因子：$\\sigma_{20d} = \\sqrt{252} \\cdot \\sqrt{\\frac{\\sum_{t=1}^{20}(r_t - \\bar{r})^2}{19}}$

回测参数：初始资金100万元，交易成本0.1%，无滑点。""",

            "experimental_setup": """数据来源：baostock，涵盖2019-01-02至2024-12-31期间平安银行(000001)的日线数据，共1456个交易日。

描述性统计：
- 日均收益率：0.03%
- 收益率标准差：1.42%
- 最大单日收益：9.87%
- 最大单日亏损：-10.15%

评估指标包括：总收益率、年化收益率、夏普比率、最大回撤、卡玛比率。""",

            "experimental_results": """| 策略 | 总收益 | 年化收益 | 夏普比率 | 最大回撤 |
|------|--------|----------|----------|----------|
| MA交叉 | -63.68% | -16.08% | -0.61 | -71.54% |
| RSI均值回归 | -65.89% | -16.98% | -0.52 | -66.63% |
| 布林带 | -30.43% | -6.09% | -0.28 | -38.77% |
| 买入持有 | 47.54% | 6.96% | 0.45 | -28.32% |

实验结果表明，所有技术分析策略在考虑交易成本后均未能战胜买入持有基准。布林带策略相对表现最好，但仍大幅落后于基准。""",

            "discussion": """本研究存在以下局限性：（1）仅使用单一股票进行回测，结论的普适性需要进一步验证；（2）未考虑流动性限制和滑点；（3）回测期间包含了特殊市场环境。

未来研究可从以下方向改进：（1）扩展到多股票组合；（2）加入止损和仓位管理机制；（3）结合机器学习方法优化策略参数。""",

            "conclusion": """本文通过实证研究表明，技术分析策略在中国A股市场的表现不如预期。这一发现与有效市场假说相一致，表明通过技术分析难以获得超额收益。

对于个人投资者，本文的启示是：在没有充分理解策略原理和适用条件的情况下，不应盲目使用技术分析策略进行交易。"""
        }

        return mock_content.get(section_name, f"\n\n## {section_name.upper()}\n\n{section_name} 内容待生成。\n\n")

    def _assemble_paper(self, title: str, authors: str, sections_content: List[str]) -> str:
        """组装完整论文"""
        lines = []

        # 标题
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"**作者：{authors}**")
        lines.append("")

        # 各章节
        section_titles = {
            "abstract": "摘要",
            "introduction": "引言",
            "related_work": "相关工作",
            "methodology": "方法论",
            "experimental_setup": "实验设置",
            "experimental_results": "实验结果",
            "discussion": "讨论",
            "conclusion": "结论"
        }

        for i, (section_name, content) in enumerate(zip(self.config.sections_order, sections_content)):
            chinese_title = section_titles.get(section_name, section_name.upper())
            lines.append(f"\n## {chinese_title}\n")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)


# ============================================================
# 演示
# ============================================================

def demo_chunked_generator():
    """演示分块生成器"""
    print("=" * 70)
    print("分块论文生成器 - 演示")
    print("=" * 70)
    print()

    generator = ChunkedPaperGenerator(ChunkConfig())

    backtest_results = {
        "stock": "000001 平安银行",
        "data_range": "2019-01-02 至 2024-12-31",
        "data_points": 1456,
        "strategies": {
            "MA交叉": {"metrics": {"total_return": -63.68, "annual_return": -16.08, "sharpe_ratio": -0.61, "max_drawdown": -71.54}},
            "RSI均值回归": {"metrics": {"total_return": -65.89, "annual_return": -16.98, "max_drawdown": -66.63}},
            "布林带": {"metrics": {"total_return": -30.43, "annual_return": -6.09, "max_drawdown": -38.77}}
        },
        "benchmark": {"total_return": 47.54, "annual_return": 6.96, "sharpe_ratio": 0.45, "max_drawdown": -28.32}
    }

    result = generator.generate(
        title="基于技术指标的A股量化交易策略实证研究",
        authors="魏宏",
        topic="量化交易策略评估",
        backtest_results=backtest_results
    )

    print()
    print("=" * 70)
    print("论文预览（前1000字符）")
    print("=" * 70)
    print(result['full_paper'][:1000])
    print()
    print(f"完整论文长度: {len(result['full_paper'])} 字符")

    return result


if __name__ == "__main__":
    demo_chunked_generator()