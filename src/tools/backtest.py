"""
FARS - 回测工具模块
基于Backtrader的量化回测框架
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import json

# Backtrader相关
try:
    import backtrader as bt
    from backtrader import Strategy, Analyzer
    BT_AVAILABLE = True
except ImportError:
    BT_AVAILABLE = False
    print("Warning: backtrader not installed. Run: pip install backtrader")


@dataclass
class BacktestResult:
    """回测结果数据类"""
    total_return: float  # 总收益率
    sharpe_ratio: float  # 夏普比率
    max_drawdown: float  # 最大回撤
    max_drawdown_period: tuple  # 最大回撤期间
    annual_return: float  # 年化收益率
    annual_volatility: float  # 年化波动率
    calmar_ratio: float  # 卡玛比率
    sortino_ratio: float  # 索提诺比率
    win_rate: float  # 胜率
    profit_factor: float  # 盈利因子
    total_trades: int  # 总交易次数
    equity_curve: List[Dict]  # 权益曲线
    trades: List[Dict]  # 交易记录

    def to_dict(self) -> Dict:
        return {
            "total_return": f"{self.total_return:.2%}",
            "sharpe_ratio": f"{self.sharpe_ratio:.3f}",
            "max_drawdown": f"{self.max_drawdown:.2%}",
            "annual_return": f"{self.annual_return:.2%}",
            "annual_volatility": f"{self.annual_volatility:.2%}",
            "calmar_ratio": f"{self.calmar_ratio:.3f}",
            "sortino_ratio": f"{self.sortino_ratio:.3f}",
            "win_rate": f"{self.win_rate:.2%}",
            "profit_factor": f"{self.profit_factor:.3f}",
            "total_trades": self.total_trades
        }


class FARSStrategy(Strategy if BT_AVAILABLE else object):
    """
    FARS策略基类
    用户需要继承此类并实现signal_generation方法
    """

    def __init__(self):
        if not BT_AVAILABLE:
            raise ImportError("backtrader is required for backtesting")

        super().__init__()
        self.order = None
        self.buy_price = None
        self.buy_comm = None
        self.trades_log = []
        self.equity_curve = []

    def log(self, txt, dt=None):
        '''日志记录'''
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} - {txt}')

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, '
                         f'Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
                self.buy_price = order.executed.price
                self.buy_comm = order.executed.comm
            elif order.issell():
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, '
                         f'Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f'TRADE PROFIT, GROSS: {trade.pnl:.2f}, NET: {trade.pnl - trade.commission:.2f}')
            self.trades_log.append({
                "date": self.datas[0].datetime.date(0).isoformat(),
                "type": "close",
                "pnl": trade.pnl,
                "pnl_net": trade.pnl - trade.commission
            })
        elif trade.isopen:
            self.trades_log.append({
                "date": self.datas[0].datetime.date(0).isoformat(),
                "type": "open",
                "pnl": 0
            })

    def next(self):
        '''每个bar调用一次，子类需要重写此方法'''
        raise NotImplementedError("Subclass must implement signal_generation")

    def get_equity_curve(self):
        """获取权益曲线"""
        return [{
            "date": self.datas[0].datetime.date(i).isoformat(),
            "equity": self.broker.getvalue()
        } for i in range(len(self))]


class MomentumStrategy(FARSStrategy):
    """动量策略示例"""

    def __init__(self, lookback_period: int = 20, threshold: float = 0.02):
        super().__init__()
        self.lookback_period = lookback_period
        self.threshold = threshold

    def next(self):
        if len(self) < self.lookback_period:
            return

        # 计算动量
        momentum = (self.data.close[0] - self.data.close[-self.lookback_period]) / self.data.close[-self.lookback_period]

        # 获取当前持仓
        size = self.position.size

        if not size:  # 无持仓
            if momentum > self.threshold:
                self.order = self.buy()
        else:  # 有持仓
            if momentum < -self.threshold:
                self.order = self.sell()


class MeanReversionStrategy(FARSStrategy):
    """均值回归策略示例"""

    def __init__(self, lookback_period: int = 20, threshold: float = 0.02):
        super().__init__()
        self.lookback_period = lookback_period
        self.threshold = threshold

    def next(self):
        if len(self) < self.lookback_period:
            return

        # 计算移动平均
        sma = np.mean([self.data.close[-i] for i in range(self.lookback_period)])
        current_price = self.data.close[0]

        # 计算偏离度
        deviation = (current_price - sma) / sma

        size = self.position.size

        if not size:  # 无持仓
            if deviation < -threshold:  # 价格低于均值，买入
                self.order = self.buy()
        else:  # 有持仓
            if deviation > threshold:  # 价格高于均值，卖出
                self.order = self.sell()


class BacktestEngine:
    """回测引擎"""

    def __init__(self, initial_cash: float = 1000000.0, commission: float = 0.001):
        if not BT_AVAILABLE:
            raise ImportError("backtrader is required")

        self.initial_cash = initial_cash
        self.commission = commission
        self.cerebro = None
        self.results = None

    def setup(self, strategy_class, **strategy_params):
        """设置回测"""
        self.cerebro = bt.Cerebro()

        # 添加策略
        self.cerebro.addstrategy(strategy_class, **strategy_params)

        # 设置初始资金
        self.cerebro.broker.setcash(self.initial_cash)

        # 设置佣金
        self.cerebro.broker.setcommission(commission=self.commission)

        # 添加分析器
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        self.cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

        return self

    def add_data(self, datafeed):
        """添加数据"""
        if self.cerebro is None:
            self.setup(bt.Strategy)

        self.cerebro.adddata(datafeed)
        return self

    def add_data_from_df(self, df: pd.DataFrame, name: str = "data"):
        """从DataFrame添加数据"""
        if not BT_AVAILABLE:
            raise ImportError("backtrader is required")

        # 准备数据格式
        df = df.copy()
        if 'Date' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
            df['datetime'] = pd.to_datetime(df['Date'])
            df.set_index('datetime', inplace=True)
        elif not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # 重命名列以符合backtrader要求
        column_map = {
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }
        df.rename(columns=column_map, inplace=True)

        data = bt.feeds.PandasData(dataname=df)
        return self.add_data(data)

    def run(self) -> BacktestResult:
        """运行回测"""
        if self.cerebro is None:
            raise ValueError("Cerebro not initialized. Call setup() first.")

        print(f'Starting Portfolio Value: {self.cerebro.broker.getvalue():.2f}')

        # 运行
        self.results = self.cerebro.run()

        print(f'Final Portfolio Value: {self.cerebro.broker.getvalue():.2f}')

        # 提取结果
        strategy = self.results[0]

        # 获取分析器结果
        sharpe_ratio = self._get_analyzer_value(strategy, 'sharpe', 'sharperatio', 0)
        drawdown = self._get_analyzer_value(strategy, 'drawdown', 'max', {}).get('drawdown', 0) / 100
        returns = self._get_analyzer_value(strategy, 'returns', 'rtot', 0)
        trades = self._get_analyzer_value(strategy, 'trades', 'total', {})

        # 计算指标
        final_value = self.cerebro.broker.getvalue()
        total_return = (final_value - self.initial_cash) / self.initial_cash

        # 权益曲线
        equity_curve = strategy.get_equity_curve()

        # 交易记录
        trades_log = strategy.trades_log

        # 计算更多指标
        annual_return = total_return / (len(strategy) / 252) if len(strategy) > 0 else 0

        # 年化波动率
        returns_list = [e['equity'] for e in equity_curve]
        if len(returns_list) > 1:
            returns_series = pd.Series(returns_list).pct_change().dropna()
            annual_volatility = returns_series.std() * np.sqrt(252)
        else:
            annual_volatility = 0

        # 索提诺比率 (只考虑下行波动率)
        if len(returns_list) > 1:
            downside_returns = returns_series[returns_series < 0]
            if len(downside_returns) > 0 and downside_returns.std() != 0:
                sortino_ratio = returns_series.mean() / downside_returns.std() * np.sqrt(252)
            else:
                sortino_ratio = 0
        else:
            sortino_ratio = 0

        # 卡玛比率
        calmar_ratio = annual_return / abs(drawdown) if drawdown != 0 else 0

        # 胜率
        total_trades = trades.get('total', {}).get('total', 0)
        won_trades = trades.get('long', {}).get('won', 0) + trades.get('short', {}).get('won', 0)
        win_rate = won_trades / total_trades if total_trades > 0 else 0

        # 盈利因子
        gross_profit = trades.get('long', {}).get('pnl', {}).get('total', 0) + trades.get('short', {}).get('pnl', {}).get('total', 0)
        gross_loss = abs(trades.get('long', {}).get('pnl', {}).get('lost', 0)) + abs(trades.get('short', {}).get('pnl', {}).get('lost', 0))
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else 0

        return BacktestResult(
            total_return=total_return,
            sharpe_ratio=sharpe_ratio if sharpe_ratio is not None else 0,
            max_drawdown=drawdown,
            max_drawdown_period=(None, None),
            annual_return=annual_return,
            annual_volatility=annual_volatility,
            calmar_ratio=calmar_ratio,
            sortino_ratio=sortino_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            equity_curve=equity_curve,
            trades=trades_log
        )

    def _get_analyzer_value(self, strategy, analyzer_name, key, default=None):
        """获取分析器值"""
        try:
            analyzer = getattr(strategy.analyzers, analyzer_name).get_analysis()
            keys = key.split('.')
            value = analyzer
            for k in keys:
                value = value.get(k, default)
                if value is None:
                    return default
            return value
        except:
            return default

    def plot_results(self, file_path: str = None):
        """绘制回测结果"""
        if self.results is not None:
            self.cerebro.plot(savefig=file_path)


# ============== 指标计算工具 ==============

def calculate_ic(predictions: pd.Series, actuals: pd.Series) -> float:
    """
    计算信息系数 (Information Coefficient)

    Args:
        predictions: 预测值序列
        actuals: 实际值序列

    Returns:
        IC值
    """
    return predictions.corr(actuals)


def calculate_ir(ic_series: pd.Series) -> float:
    """
    计算信息比率 (Information Ratio)

    Args:
        ic_series: IC时间序列

    Returns:
        IR值 (IC均值 / IC标准差)
    """
    if len(ic_series) == 0 or ic_series.std() == 0:
        return 0
    return ic_series.mean() / ic_series.std()


def calculate_rank_ic(predictions: pd.Series, actuals: pd.Series) -> float:
    """
    计算Rank IC (Spearman相关系数)

    Args:
        predictions: 预测值序列
        actuals: 实际值序列

    Returns:
        Rank IC值
    """
    return predictions.rank().corr(actuals.rank())


def evaluate_factor(factor_values: pd.Series, forward_returns: pd.Series,
                   metrics: List[str] = None) -> Dict:
    """
    评估因子性能

    Args:
        factor_values: 因子值序列
        forward_returns: 未来收益序列
        metrics: 要计算的指标列表

    Returns:
        评估指标字典
    """
    if metrics is None:
        metrics = ['ic', 'rank_ic', 'ir', 'returns']

    results = {}

    if 'ic' in metrics:
        results['ic'] = calculate_ic(factor_values, forward_returns)

    if 'rank_ic' in metrics:
        results['rank_ic'] = calculate_rank_ic(factor_values, forward_returns)

    if 'ir' in metrics and 'ic' in results:
        results['ir'] = results['ic']  # 简化计算

    if 'returns' in metrics:
        # 按因子值分组计算收益
        quantile_returns = {}
        for q in range(1, 6):
            low = q * 20
            high = (q + 1) * 20
            mask = (factor_values.rank(pct=True) >= q/5) & (factor_values.rank(pct=True) < (q+1)/5)
            quantile_returns[f'Q{q}'] = forward_returns[mask].mean()

        results['quantile_returns'] = quantile_returns
        results['long_short_return'] = quantile_returns.get('Q5', 0) - quantile_returns.get('Q1', 0)

    return results