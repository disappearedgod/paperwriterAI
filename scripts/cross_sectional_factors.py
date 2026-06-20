"""
量化横截面因子框架 - CrossSectionalFactorFramework
实现多种因子库和分析方法，用于量化研究论文的因子分析部分

包含因子类型:
1. 风险因子 (Risk Factors) - Fama-French系列
2. 技术因子 (Technical Factors) - 动量、趋势、波动率
3. 情绪因子 (Sentiment Factors) - 市场情绪指标
4. 基本面因子 (Fundamental Factors) - 估值、盈利、质量

作者: 魏宏 (Wei Hong)
用于: FARS量化研究系统的因子库构建
"""

import json
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Callable
from enum import Enum
from datetime import datetime
import numpy as np


class FactorCategory(Enum):
    """因子类别"""
    RISK = "risk"                          # 风险因子
    TECHNICAL = "technical"                # 技术因子
    SENTIMENT = "sentiment"                # 情绪因子
    FUNDAMENTAL = "fundamental"            # 基本面因子
    MICROSTRUCTURE = "microstructure"      # 市场微结构因子


class FactorType(Enum):
    """因子类型"""
    MOMENTUM = "momentum"                 # 动量
    VALUE = "value"                       # 价值
    QUALITY = "quality"                   # 质量
    VOLATILITY = "volatility"             # 波动率
    SIZE = "size"                         # 规模
    LIQUIDITY = "liquidity"               # 流动性
    GROWTH = "growth"                     # 成长
    TURNOVER = "turnover"                 # 换手率


@dataclass
class FactorDefinition:
    """因子定义"""
    name: str                              # 因子名称（英文）
    name_cn: str                           # 因子名称（中文）
    category: FactorCategory              # 因子类别
    factor_type: FactorType                # 因子类型
    description: str                       # 因子描述
    formula: str                           # 计算公式（LaTeX格式）
    data_required: List[str]               # 所需数据字段
    lookback_period: int = 252             # 回看期（交易日）
    neutralization: Optional[str] = None   # 中性化方式 (industry/size)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'name_cn': self.name_cn,
            'category': self.category.value,
            'factor_type': self.factor_type.value,
            'description': self.description,
            'formula': self.formula,
            'data_required': self.data_required,
            'lookback_period': self.lookback_period,
            'neutralization': self.neutralization
        }


@dataclass
class FactorSignal:
    """因子信号"""
    factor_name: str                       # 因子名称
    stock_code: str                        # 股票代码
    value: float                           # 因子值
    percentile: float                      # 百分位排名 (0-1)
    z_score: float                         # Z-score标准化值
    signal_date: str                       # 信号日期

    def is_outlier(self, threshold: float = 3.0) -> bool:
        """判断是否为异常值"""
        return abs(self.z_score) > threshold


@dataclass
class FactorPortfolioResult:
    """因子组合回测结果"""
    factor_name: str
    top_quantile_return: float            # top组合收益
    bottom_quantile_return: float         # bottom组合收益
    spread_return: float                 # 多空组合收益
    spread_volatility: float              # 价差波动率
    information_coefficient: float        # IC (信息系数)
    information_ratio: float             # IR (信息比率)
    turnover_rate: float                  # 换手率
    t_statistic: float                   # t统计量
    p_value: float                       # p值


class CrossSectionalFactorFramework:
    """
    量化横截面因子框架

    功能:
    1. 因子库管理 - 定义和维护多种量化因子
    2. 因子计算 - 基于市场数据计算因子值
    3. IC分析 - 计算因子IC、IR等指标
    4. 分组回测 - 因子五分位组合回测
    5. 因子报告生成 - 生成论文所需的因子分析内容
    """

    def __init__(self):
        self.factor_library: Dict[str, FactorDefinition] = {}
        self._init_factor_library()

    def _init_factor_library(self):
        """初始化因子库"""
        factors = [

            # ========== 风险因子 (Risk Factors) ==========
            FactorDefinition(
                name="market_beta",
                name_cn="市场贝塔",
                category=FactorCategory.RISK,
                factor_type=FactorType.VOLATILITY,
                description="股票收益率与市场收益率的协方差除以市场方差",
                formula=r"$$\beta_i = \frac{\text{Cov}(r_i, r_m)}{\text{Var}(r_m)}$$",
                data_required=["close", "market_close"],
                lookback_period=252,
                neutralization="industry"
            ),

            FactorDefinition(
                name="size",
                name_cn="市值因子",
                category=FactorCategory.RISK,
                factor_type=FactorType.SIZE,
                description="股票总市值的对数",
                formula=r"$$\text{Size}_i = \ln(\text{MarketCap}_i)$$",
                data_required=["market_cap"],
                lookback_period=1,
                neutralization=None
            ),

            FactorDefinition(
                name="residual_volatility",
                name_cn="残差波动率",
                category=FactorCategory.RISK,
                factor_type=FactorType.VOLATILITY,
                description="CAPM模型残差的年化标准差",
                formula=r"$$\sigma_{\epsilon,i} = \sqrt{252} \cdot \text{std}(\epsilon_i)$$",
                data_required=["close", "market_close"],
                lookback_period=252,
                neutralization="industry"
            ),

            # ========== 技术因子 (Technical Factors) ==========
            FactorDefinition(
                name="momentum_1m",
                name_cn="一个月动量",
                category=FactorCategory.TECHNICAL,
                factor_type=FactorType.MOMENTUM,
                description="过去1个月（22个交易日）累计收益率",
                formula=r"$$\text{Mom}_{1m,i} = \frac{P_i(t) - P_i(t-22)}{P_i(t-22)}$$",
                data_required=["close"],
                lookback_period=22,
                neutralization="industry"
            ),

            FactorDefinition(
                name="momentum_12m",
                name_cn="12个月动量",
                category=FactorCategory.TECHNICAL,
                factor_type=FactorType.MOMENTUM,
                description="过去12个月累计收益率（排除最近1个月）",
                formula=r"$$\text{Mom}_{12m,i} = \frac{P_i(t-22) - P_i(t-252)}{P_i(t-252)}$$",
                data_required=["close"],
                lookback_period=252,
                neutralization="industry"
            ),

            FactorDefinition(
                name="rsi_14d",
                name_cn="RSI指标",
                category=FactorCategory.TECHNICAL,
                factor_type=FactorType.MOMENTUM,
                description="14日相对强弱指数",
                formula=r"$$\text{RSI} = 100 - \frac{100}{1 + \text{RS}}, \quad \text{RS} = \frac{\text{Avg Gain}}{\text{Avg Loss}}$$",
                data_required=["close", "high", "low"],
                lookback_period=14,
                neutralization=None
            ),

            FactorDefinition(
                name="volatility_20d",
                name_cn="20日波动率",
                category=FactorCategory.TECHNICAL,
                factor_type=FactorType.VOLATILITY,
                description="过去20个交易日收益率的标准差年化值",
                formula=r"$$\sigma_{20d,i} = \sqrt{252} \cdot \sqrt{\frac{\sum_{t=1}^{20}(r_t - \bar{r})^2}{19}}$$",
                data_required=["close"],
                lookback_period=20,
                neutralization="industry"
            ),

            FactorDefinition(
                name="turnover_20d",
                name_cn="20日换手率",
                category=FactorCategory.TECHNICAL,
                factor_type=FactorType.TURNOVER,
                description="过去20个交易日平均日换手率",
                formula=r"$$\text{Turnover}_{20d} = \frac{1}{20}\sum_{t=1}^{20}\frac{\text{Volume}_t}{\text{FloatShares}}$$",
                data_required=["volume", "float_shares"],
                lookback_period=20,
                neutralization="size"
            ),

            FactorDefinition(
                name="ma_crossover_signal",
                name_cn="均线交叉信号",
                category=FactorCategory.TECHNICAL,
                factor_type=FactorType.MOMENTUM,
                description="短期均线与长期均线的比值，衡量趋势强度",
                formula=r"$$\text{MA Signal}_i = \frac{\text{MA}_{5,i}}{\text{MA}_{20,i}}$$",
                data_required=["close"],
                lookback_period=20,
                neutralization=None
            ),

            FactorDefinition(
                name="bollinger_position",
                name_cn="布林带位置",
                category=FactorCategory.TECHNICAL,
                factor_type=FactorType.VOLATILITY,
                description="当前价格在布林带中的位置",
                formula=r"$$\text{BB Position}_i = \frac{P_i - \text{LB}_i}{\text{UB}_i - \text{LB}_i}$$",
                data_required=["close", "high", "low"],
                lookback_period=20,
                neutralization=None
            ),

            # ========== 基本面因子 (Fundamental Factors) ==========
            FactorDefinition(
                name="book_to_market",
                name_cn="账市比",
                category=FactorCategory.FUNDAMENTAL,
                factor_type=FactorType.VALUE,
                description="所有者权益账面价值与市值的比率",
                formula=r"$$\text{BM}_i = \frac{\text{BookValue}_i}{\text{MarketCap}_i}$$",
                data_required=["book_value", "market_cap"],
                lookback_period=1,
                neutralization="industry"
            ),

            FactorDefinition(
                name="pe_ratio",
                name_cn="市盈率",
                category=FactorCategory.FUNDAMENTAL,
                factor_type=FactorType.VALUE,
                description="市值与净利润的比率",
                formula=r"$$\text{PE}_i = \frac{\text{MarketCap}_i}{\text{NetIncome}_i}$$",
                data_required=["market_cap", "net_income"],
                lookback_period=1,
                neutralization="industry"
            ),

            FactorDefinition(
                name="roe",
                name_cn="净资产收益率",
                category=FactorCategory.FUNDAMENTAL,
                factor_type=FactorType.QUALITY,
                description="净利润与所有者权益的比率",
                formula=r"$$\text{ROE}_i = \frac{\text{NetIncome}_i}{\text{Equity}_i}$$",
                data_required=["net_income", "equity"],
                lookback_period=1,
                neutralization="industry"
            ),

            FactorDefinition(
                name="roe_growth",
                name_cn="ROE变化",
                category=FactorCategory.FUNDAMENTAL,
                factor_type=FactorType.GROWTH,
                description="当期ROE与上期ROE的变化",
                formula=r"$$\Delta\text{ROE}_i = \text{ROE}_t - \text{ROE}_{t-1}$$",
                data_required=["net_income", "equity"],
                lookback_period=252,
                neutralization="industry"
            ),

            FactorDefinition(
                name="debt_to_equity",
                name_cn="资产负债率",
                category=FactorCategory.FUNDAMENTAL,
                factor_type=FactorType.QUALITY,
                description="总负债与所有者权益的比率",
                formula=r"$$\text{D/E}_i = \frac{\text{TotalDebt}_i}{\text{Equity}_i}$$",
                data_required=["total_debt", "equity"],
                lookback_period=1,
                neutralization="industry"
            ),

            # ========== 情绪因子 (Sentiment Factors) ==========
            FactorDefinition(
                name="analyst_sentiment",
                name_cn="分析师情绪",
                category=FactorCategory.SENTIMENT,
                factor_type=FactorType.MOMENTUM,
                description="分析师评级的一致性",
                formula=r"$$\text{AnalystSent}_i = \frac{\text{NumBuy}}{\text{NumTotal}}$$",
                data_required=["analyst_ratings"],
                lookback_period=60,
                neutralization="industry"
            ),

            FactorDefinition(
                name="short_term_reversal",
                name_cn="短期反转",
                category=FactorCategory.SENTIMENT,
                factor_type=FactorType.MOMENTUM,
                description="过去5个交易日收益率（反转效应）",
                formula=r"$$\text{Reversal}_{5d,i} = \frac{P_i(t) - P_i(t-5)}{P_i(t-5)}$$",
                data_required=["close"],
                lookback_period=5,
                neutralization="industry"
            ),
        ]

        # 注册因子
        for f in factors:
            self.factor_library[f.name] = f

    def get_factor(self, name: str) -> Optional[FactorDefinition]:
        """获取因子定义"""
        return self.factor_library.get(name)

    def list_factors(self, category: Optional[FactorCategory] = None) -> List[FactorDefinition]:
        """列出因子库中的因子"""
        if category is None:
            return list(self.factor_library.values())

        return [f for f in self.factor_library.values() if f.category == category]

    def calculate_factor_value(
        self,
        factor_name: str,
        price_data: List[float],
        market_data: Optional[List[float]] = None,
        volume_data: Optional[List[float]] = None
    ) -> Optional[float]:
        """
        计算因子值

        参数:
            factor_name: 因子名称
            price_data: 价格数据列表（从近到远）
            market_data: 市场指数数据（可选）
            volume_data: 成交量数据（可选）

        返回:
            因子值（如果计算成功）
        """
        factor = self.factor_library.get(factor_name)
        if not factor:
            return None

        try:
            if factor_name == "momentum_1m":
                if len(price_data) < 23:
                    return None
                return (price_data[0] / price_data[22]) - 1

            elif factor_name == "momentum_12m":
                if len(price_data) < 253:
                    return None
                return (price_data[22] / price_data[252]) - 1

            elif factor_name == "volatility_20d":
                if len(price_data) < 21:
                    return None
                returns = [(price_data[i-1] - price_data[i]) / price_data[i]
                          for i in range(1, min(21, len(price_data)))]
                mean_ret = sum(returns) / len(returns)
                variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
                return math.sqrt(252 * variance)

            elif factor_name == "short_term_reversal":
                if len(price_data) < 6:
                    return None
                return (price_data[0] / price_data[5]) - 1

            elif factor_name == "rsi_14d":
                if len(price_data) < 15:
                    return None
                gains = []
                losses = []
                for i in range(1, 15):
                    diff = price_data[i-1] - price_data[i]
                    if diff > 0:
                        gains.append(diff)
                    else:
                        losses.append(abs(diff))

                avg_gain = sum(gains) / 14 if gains else 0
                avg_loss = sum(losses) / 14 if losses else 0

                if avg_loss == 0:
                    return 100.0
                rs = avg_gain / avg_loss
                return 100 - (100 / (1 + rs))

            elif factor_name == "market_beta":
                if not market_data or len(price_data) < 252:
                    return None
                # 简化计算：收益率序列的协方差
                returns = []
                market_returns = []
                for i in range(1, min(253, min(len(price_data), len(market_data)))):
                    ret = (price_data[i-1] - price_data[i]) / price_data[i]
                    mkt_ret = (market_data[i-1] - market_data[i]) / market_data[i]
                    returns.append(ret)
                    market_returns.append(mkt_ret)

                mean_ret = sum(returns) / len(returns)
                mean_mkt = sum(market_returns) / len(market_returns)

                cov = sum((r - mean_ret) * (m - mean_mkt)
                         for r, m in zip(returns, market_returns)) / (len(returns) - 1)
                var_mkt = sum((m - mean_mkt) ** 2 for m in market_returns) / (len(market_returns) - 1)

                if var_mkt == 0:
                    return None
                return cov / var_mkt

            elif factor_name == "turnover_20d":
                if not volume_data or len(volume_data) < 20:
                    return None
                return sum(volume_data[-20:]) / 20

            else:
                # 默认返回None（需要更多数据）
                return None

        except Exception as e:
            print(f"Error calculating {factor_name}: {e}")
            return None

    def calculate_ic(
        self,
        factor_values: Dict[str, float],
        next_period_returns: Dict[str, float]
    ) -> Tuple[float, float, float]:
        """
        计算因子IC（信息系数）

        参数:
            factor_values: {stock_code: factor_value}
            next_period_returns: {stock_code: next_period_return}

        返回:
            (ic, ic_t_stat, ic_p_value)
        """
        # 匹配数据
        pairs = []
        for code, fv in factor_values.items():
            if code in next_period_returns and fv is not None:
                pairs.append((fv, next_period_returns[code]))

        if len(pairs) < 10:
            return 0.0, 0.0, 1.0

        # 计算IC（Pearson相关系数）
        n = len(pairs)
        factor_vals = [p[0] for p in pairs]
        returns = [p[1] for p in pairs]

        mean_f = sum(factor_vals) / n
        mean_r = sum(returns) / n

        cov = sum((f - mean_f) * (r - mean_r) for f, r in pairs) / n
        std_f = math.sqrt(sum((f - mean_f) ** 2 for f in factor_vals) / n)
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in returns) / n)

        if std_f == 0 or std_r == 0:
            return 0.0, 0.0, 1.0

        ic = cov / (std_f * std_r)

        # 计算t统计量
        # df = n - 2
        t_stat = ic * math.sqrt(n - 2) / math.sqrt(1 - ic ** 2) if n > 2 else 0.0

        # 计算p值（简化版）
        from scipy import stats
        try:
            # 如果scipy可用
            import scipy.stats as sstats
            p_value = 2 * (1 - sstats.t.cdf(abs(t_stat), n - 2))
        except ImportError:
            # 简化估计
            p_value = 0.05 if abs(ic) > 0.03 else 0.1

        return ic, t_stat, p_value

    def run_portfolio_analysis(
        self,
        factor_values: Dict[str, float],
        period_returns: Dict[str, float],
        quantile: int = 5
    ) -> FactorPortfolioResult:
        """
        运行因子组合分析

        将股票按因子值分为quantile组，计算top-bottom组合收益
        """
        # 按因子值排序
        sorted_stocks = sorted(
            [(code, fv) for code, fv in factor_values.items() if fv is not None],
            key=lambda x: x[1]
        )

        if len(sorted_stocks) < quantile:
            return FactorPortfolioResult(
                factor_name="unknown",
                top_quantile_return=0.0,
                bottom_quantile_return=0.0,
                spread_return=0.0,
                spread_volatility=0.0,
                information_coefficient=0.0,
                information_ratio=0.0,
                turnover_rate=0.0,
                t_statistic=0.0,
                p_value=1.0
            )

        # 分组
        n_per_group = len(sorted_stocks) // quantile

        groups = []
        for i in range(quantile):
            start = i * n_per_group
            end = start + n_per_group if i < quantile - 1 else len(sorted_stocks)
            group = sorted_stocks[start:end]
            groups.append(group)

        # 计算每组收益
        group_returns = []
        for group in groups:
            stocks_in_group = [code for code, _ in group]
            rets = [period_returns.get(code, 0) for code in stocks_in_group if code in period_returns]
            if rets:
                group_returns.append(sum(rets) / len(rets))
            else:
                group_returns.append(0)

        # 计算价差
        top_return = group_returns[-1] if group_returns else 0  # 因子值最高的组
        bottom_return = group_returns[0] if group_returns else 0  # 因子值最低的组
        spread = top_return - bottom_return

        # IC分析
        ic, t_stat, p_value = self.calculate_ic(factor_values, period_returns)

        # IR（简化）
        ir = ic / 0.1 if t_stat > 1.96 else 0  # 假设波动率为10%

        return FactorPortfolioResult(
            factor_name="",
            top_quantile_return=top_return,
            bottom_quantile_return=bottom_return,
            spread_return=spread,
            spread_volatility=0.1,  # 简化
            information_coefficient=ic,
            information_ratio=ir,
            turnover_rate=0.5,  # 简化
            t_statistic=t_stat,
            p_value=p_value
        )

    def generate_factor_report(
        self,
        factor_results: List[FactorPortfolioResult],
        top_n: int = 10
    ) -> str:
        """
        生成因子分析报告（用于论文）

        返回LaTeX格式的因子分析表格
        """
        lines = []

        lines.append("% ============================================================")
        lines.append("% 因子分析报告")
        lines.append("% ============================================================")
        lines.append("")

        lines.append("\\section{因子分析}")
        lines.append("")
        lines.append("本节对我们提出的因子进行横截面回归分析，评估其预测能力。")
        lines.append("")

        # IC统计表格
        lines.append("\\subsection{因子IC统计}")
        lines.append("")
        lines.append("\\begin{table}[htbp]")
        lines.append("\\centering")
        lines.append("\\caption{因子信息系数(IC)统计}")
        lines.append("\\begin{tabular}{lccc}")
        lines.append("\\toprule")
        lines.append("因子 & IC均值 & IC t统计量 & p值 \\\\")
        lines.append("\\midrule")

        for res in factor_results[:top_n]:
            ic_sign = "+" if res.information_coefficient > 0 else ""
            sig_marker = "*" if res.p_value < 0.05 else ("**" if res.p_value < 0.01 else "")
            lines.append(
                f"{res.factor_name} & {ic_sign}{res.information_coefficient:.4f} & "
                f"{res.t_statistic:.2f}{sig_marker} & {res.p_value:.4f} \\\\"
            )

        lines.append("\\bottomrule")
        lines.append("\\end{tabular}")
        lines.append("\\end{table}")
        lines.append("")
        lines.append(f"注: * 表示 p<0.05, ** 表示 p<0.01")
        lines.append("")

        # 分组回测表格
        lines.append("\\subsection{因子五分位组合回测}")
        lines.append("")
        lines.append("\\begin{table}[htbp]")
        lines.append("\\centering")
        lines.append("\\caption{因子五分位组合收益}")
        lines.append("\\begin{tabular}{lccc}")
        lines.append("\\toprule")
        lines.append("因子 & Top组合 & Bottom组合 & 多空价差 \\\\")
        lines.append("\\midrule")

        for res in factor_results[:top_n]:
            lines.append(
                f"{res.factor_name} & {res.top_quantile_return*100:.2f}\\% & "
                f"{res.bottom_quantile_return*100:.2f}\\% & {res.spread_return*100:.2f}\\% \\\\"
            )

        lines.append("\\bottomrule")
        lines.append("\\end{tabular}")
        lines.append("\\end{table}")
        lines.append("")

        # 结论
        lines.append("\\subsection{分析结论}")
        lines.append("")

        # 找出IC显著的因子
        significant_factors = [r for r in factor_results if r.p_value < 0.05]

        if significant_factors:
            lines.append("根据IC分析和分组回测结果，我们发现以下因子具有显著的预测能力:")
            for res in significant_factors[:5]:
                direction = "正向" if res.information_coefficient > 0 else "负向"
                lines.append(f"\\begin{itemize}")
                lines.append(f"\\item {res.factor_name}: {direction}预测能力 (IC={res.information_coefficient:.4f})")
                lines.append(f"\\end{itemize}")
        else:
            lines.append("当前样本期内，未发现统计上显著的因子预测能力。")

        return "\n".join(lines)

    def generate_latex_factors_section(self) -> str:
        """生成因子方法论章节的LaTeX代码"""
        lines = []

        lines.append("% ============================================================")
        lines.append("% 因子定义与方法论")
        lines.append("% ============================================================")
        lines.append("")

        lines.append("\\section{研究方法}")
        lines.append("")
        lines.append("\\subsection{因子构建}")
        lines.append("")
        lines.append("本文构建了涵盖多个维度的因子体系，包括技术因子、基本面因子和情绪因子...")
        lines.append("")

        # 列出关键因子公式
        lines.append("\\subsubsection{技术因子}")
        lines.append("")
        lines.append("本文使用的主要技术因子包括:")
        lines.append("")

        for f in self.list_factors(FactorCategory.TECHNICAL):
            lines.append(f"\\paragraph{{{f.name_cn} ({f.name})}}")
            lines.append(f"{f.description}")
            lines.append("")
            lines.append(f"计算公式: {f.formula}")
            lines.append("")

        lines.append("\\subsubsection{基本面因子}")
        lines.append("")
        for f in self.list_factors(FactorCategory.FUNDAMENTAL):
            lines.append(f"\\paragraph{{{f.name_cn} ({f.name})}}")
            lines.append(f"{f.description}")
            lines.append("")
            lines.append(f"计算公式: {f.formula}")
            lines.append("")

        lines.append("\\subsection{因子有效性检验}")
        lines.append("")
        lines.append("我们使用以下指标评估因子的有效性:")
        lines.append("")
        lines.append("\\begin{enumerate}")
        lines.append("\\item \\textbf{信息系数(IC)}: 因子值与下期收益的Pearson相关系数")
        lines.append("\\item \\textbf{t统计量}: 评估IC是否显著异于零")
        lines.append("\\item \\textbf{分组回测}: 将股票按因子值分为五组，检验组合收益差异")
        lines.append("\\end{enumerate}")
        lines.append("")

        return "\n".join(lines)


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("CrossSectionalFactorFramework 演示")
    print("=" * 70)

    # 创建框架
    framework = CrossSectionalFactorFramework()

    # 列出所有因子
    print("\n【因子库概览】")
    print(f"总因子数: {len(framework.factor_library)}")
    print()

    for cat in FactorCategory:
        factors = framework.list_factors(cat)
        print(f"{cat.value}: {len(factors)} 个因子")
        for f in factors[:3]:  # 只显示前3个
            print(f"  - {f.name_cn} ({f.name})")
        if len(factors) > 3:
            print(f"  ... 还有 {len(factors) - 3} 个")
        print()

    # 演示因子计算
    print("【因子计算演示】")
    print()

    # 模拟价格数据
    np.random.seed(42)
    n = 300
    price_data = [100 * (1 + np.random.randn() * 0.02) for _ in range(n)]

    # 计算动量因子
    mom_value = framework.calculate_factor_value("momentum_1m", price_data)
    print(f"一个月动量因子值: {mom_value:.4f}" if mom_value else "计算失败")

    vol_value = framework.calculate_factor_value("volatility_20d", price_data)
    print(f"20日波动率因子值: {vol_value:.4f}" if vol_value else "计算失败")

    rsi_value = framework.calculate_factor_value("rsi_14d", price_data)
    print(f"RSI因子值: {rsi_value:.4f}" if rsi_value else "计算失败")

    # IC分析演示
    print("\n【IC分析演示】")

    # 模拟因子值和收益
    stocks = [f"stock_{i:03d}" for i in range(100)]
    factor_values = {s: np.random.randn() for s in stocks}
    period_returns = {s: factor_values[s] * 0.1 + np.random.randn() * 0.05
                      for s in stocks}

    ic, t_stat, p_value = framework.calculate_ic(factor_values, period_returns)
    print(f"IC: {ic:.4f}, t统计量: {t_stat:.2f}, p值: {p_value:.4f}")
    print(f"IC显著性: {'显著' if p_value < 0.05 else '不显著'} (p {'<' if p_value < 0.05 else '>'} 0.05)")

    # 生成报告
    print("\n【生成因子分析LaTeX代码】")
    print()

    # 模拟一些因子结果
    mock_results = [
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
        FactorPortfolioResult(
            factor_name="volatility_20d",
            top_quantile_return=0.01,
            bottom_quantile_return=0.04,
            spread_return=-0.03,
            spread_volatility=0.12,
            information_coefficient=-0.06,
            information_ratio=-0.50,
            turnover_rate=0.55,
            t_statistic=-1.8,
            p_value=0.07
        ),
    ]

    report = framework.generate_factor_report(mock_results)
    print(report[:1000])  # 显示前1000字符

    print()
    print("=" * 70)