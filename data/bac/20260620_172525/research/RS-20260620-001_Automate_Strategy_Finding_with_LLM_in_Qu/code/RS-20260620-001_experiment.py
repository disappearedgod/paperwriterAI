"""
研究编号: RS-20260620-001
论文标题: 种子综述：Automate Strategy Finding with LLM in Quant Investment
研究主题: 种子综述：Automate Strategy Finding with LLM in Quant Investment
"""

#!/usr/bin/env python3
"""
FARS - 真实量化策略实验
基于真实市场数据的技术分析策略回测
使用baostock获取中国A股数据，无代理问题
"""

import sys
import json
import warnings
warnings.filterwarnings('ignore')

import os
import pandas as pd
import numpy as np
import baostock as bs
from datetime import datetime

print("=== FARS 真实量化策略实验 ===")
print()

# 登录baostock
print("连接baostock数据源...")
lg = bs.login()
print(f"登录结果: {lg.error_code} {lg.error_msg}")

# 获取平安银行(000001)日线数据
print("\n获取平安银行(000001) 2019-2024日线数据...")
rs = bs.query_history_k_data_plus(
    "sz.000001",
    "date,code,open,high,low,close,volume,amount,pctChg",
    start_date='2019-01-01',
    end_date='2024-12-31',
    frequency="d"
)

print(f"查询结果: {rs.error_code} {rs.error_msg}")

# 转换为DataFrame
data_list = []
while (rs.error_code == '0') & rs.next():
    data_list.append(rs.get_row_data())

df = pd.DataFrame(data_list, columns=rs.fields)
print(f"数据获取成功! 共 {len(df)} 条记录")

# 数据预处理
df['date'] = pd.to_datetime(df['date'])
for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'pctChg']:
    df[col] = pd.to_numeric(df[col], errors='coerce')

df = df.dropna().reset_index(drop=True)
df['return'] = df['pctChg'] / 100  # 涨跌幅转换为收益率

print(f"有效数据: {len(df)} 条")
print(f"时间范围: {df['date'].iloc[0].date()} 至 {df['date'].iloc[-1].date()}")

# 计算技术指标
print("\n计算技术指标...")

# 1. 移动平均线
df['ma5'] = df['close'].rolling(window=5).mean()
df['ma10'] = df['close'].rolling(window=10).mean()
df['ma20'] = df['close'].rolling(window=20).mean()
df['ma60'] = df['close'].rolling(window=60).mean()

# 2. RSI
delta = df['close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs_val = gain / loss
df['rsi'] = 100 - (100 / (1 + rs_val))

# 3. MACD
exp12 = df['close'].ewm(span=12, adjust=False).mean()
exp26 = df['close'].ewm(span=26, adjust=False).mean()
df['macd'] = exp12 - exp26
df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
df['macd_hist'] = df['macd'] - df['macd_signal']

# 4. 布林带
df['bb_mid'] = df['close'].rolling(window=20).mean()
bb_std = df['close'].rolling(window=20).std()
df['bb_upper'] = df['bb_mid'] + 2 * bb_std
df['bb_lower'] = df['bb_mid'] - 2 * bb_std

# 5. 成交量均线比
df['vol_ma5'] = df['volume'].rolling(window=5).mean()
df['vol_ratio'] = df['volume'] / df['vol_ma5']

print("\n数据样本(最后5行):")
print(df[['date', 'close', 'return', 'ma5', 'ma20', 'rsi']].tail())

# 登出
bs.logout()

print("\n=== Step 2: 实现策略回测 ===")

def backtest_ma_strategy(df, fast_ma=5, slow_ma=20):
    """均线交叉策略回测"""
    df = df.copy()
    df['signal'] = 0
    df.loc[df['ma5'] > df['ma20'], 'signal'] = 1  # 金叉买入
    df.loc[df['ma5'] <= df['ma20'], 'signal'] = -1  # 死叉卖出

    # 计算持仓 (次日执行信号)
    df['position'] = df['signal'].shift(1).fillna(0)

    # 计算策略收益
    df['strategy_return'] = df['position'] * df['return']

    # 累计收益
    df['cum_market'] = (1 + df['return']).cumprod()
    df['cum_strategy'] = (1 + df['strategy_return']).cumprod()

    return df

def calculate_metrics(df, cum_col='cum_strategy'):
    """计算策略评估指标"""
    if cum_col not in df.columns:
        cum_col = 'cum_strategy'

    cumulative = df[cum_col].dropna()
    if len(cumulative) == 0:
        return {"total_return": 0, "annual_return": 0, "sharpe_ratio": 0,
                "max_drawdown": 0, "win_rate": 0, "total_trades": 0, "annual_vol": 0}

    total_return = cumulative.iloc[-1] - 1
    annual_return = (1 + total_return) ** (252 / len(df)) - 1

    # 获取策略收益列
    strat_ret_col = 'strategy_return' if 'strategy_return' in df.columns else None
    if strat_ret_col:
        strategy_return = df[strat_ret_col].fillna(0)
    else:
        strategy_return = df['return'] * 0

    annual_vol = strategy_return.std() * np.sqrt(252) if strategy_return.std() > 0 else 0.001

    # 夏普比率 (假设无风险利率 3%)
    risk_free = 0.03
    sharpe = (annual_return - risk_free) / annual_vol if annual_vol > 0 else 0

    # 最大回撤
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()

    # 胜率
    winning_trades = (strategy_return > 0).sum()
    total_trades = (strategy_return != 0).sum()
    win_rate = winning_trades / total_trades if total_trades > 0 else 0

    return {
        "total_return": round(total_return * 100, 2),
        "annual_return": round(annual_return * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "win_rate": round(win_rate * 100, 2),
        "total_trades": int(total_trades),
        "annual_vol": round(annual_vol * 100, 2)
    }

# 策略1: 均线交叉 (MA5/MA20)
print("实现均线交叉策略...")
df_ma = backtest_ma_strategy(df, fast_ma=5, slow_ma=20)
ma_metrics = calculate_metrics(df_ma, 'cum_strategy')

print("\n均线交叉策略 (MA5/MA20) 回测结果:")
print(f"  总收益率: {ma_metrics['total_return']}%")
print(f"  年化收益率: {ma_metrics['annual_return']}%")
print(f"  夏普比率: {ma_metrics['sharpe_ratio']}")
print(f"  最大回撤: {ma_metrics['max_drawdown']}%")
print(f"  胜率: {ma_metrics['win_rate']}%")
print(f"  交易次数: {ma_metrics['total_trades']}")

# 策略2: RSI均值回归
print("\n实现RSI均值回归策略...")

def backtest_rsi_strategy(df, lookback=14, lower=30, upper=70):
    """RSI均值回归策略"""
    df = df.copy()
    df['rsi_signal'] = 0
    df.loc[df['rsi'] < lower, 'rsi_signal'] = 1  # 超卖买入
    df.loc[df['rsi'] > upper, 'rsi_signal'] = -1  # 超买卖出
    df.loc[(df['rsi'] >= lower) & (df['rsi'] <= upper), 'rsi_signal'] = 0

    # 持仓保持3天
    df['rsi_position'] = df['rsi_signal'].rolling(3).mean().fillna(0)
    df['rsi_position'] = df['rsi_position'].clip(-1, 1)

    df['rsi_strategy_return'] = df['rsi_position'] * df['return']
    df['cum_rsi'] = (1 + df['rsi_strategy_return']).cumprod()

    return df

df_rsi = backtest_rsi_strategy(df)
rsi_metrics = calculate_metrics(df_rsi, 'cum_rsi')

print("\nRSI均值回归策略 回测结果:")
print(f"  总收益率: {rsi_metrics['total_return']}%")
print(f"  年化收益率: {rsi_metrics['annual_return']}%")
print(f"  夏普比率: {rsi_metrics['sharpe_ratio']}")
print(f"  最大回撤: {rsi_metrics['max_drawdown']}%")
print(f"  胜率: {rsi_metrics['win_rate']}%")
print(f"  交易次数: {rsi_metrics['total_trades']}")

# 策略3: 布林带策略
print("\n实现布林带均值回归策略...")

def backtest_bb_strategy(df):
    """布林带策略"""
    df = df.copy()
    df['bb_signal'] = 0
    df.loc[df['close'] < df['bb_lower'], 'bb_signal'] = 1  # 价格低于下轨买入
    df.loc[df['close'] > df['bb_upper'], 'bb_signal'] = -1  # 价格高于上轨卖出
    df.loc[(df['close'] >= df['bb_lower']) & (df['close'] <= df['bb_upper']), 'bb_signal'] = 0

    df['bb_position'] = df['bb_signal'].shift(1).fillna(0)
    df['bb_strategy_return'] = df['bb_position'] * df['return']
    df['cum_bb'] = (1 + df['bb_strategy_return']).cumprod()

    return df

df_bb = backtest_bb_strategy(df)
bb_metrics = calculate_metrics(df_bb, 'cum_bb')

print("\n布林带策略 回测结果:")
print(f"  总收益率: {bb_metrics['total_return']}%")
print(f"  年化收益率: {bb_metrics['annual_return']}%")
print(f"  夏普比率: {bb_metrics['sharpe_ratio']}")
print(f"  最大回撤: {bb_metrics['max_drawdown']}%")
print(f"  胜率: {bb_metrics['win_rate']}%")
print(f"  交易次数: {bb_metrics['total_trades']}")

# 基准 - 买入持有
benchmark_cum = (1 + df['return']).cumprod()
benchmark_return = benchmark_cum.iloc[-1] - 1
benchmark_annual = (1 + benchmark_return) ** (252 / len(df)) - 1

print(f"\n基准收益率 (买入持有): {benchmark_return*100:.2f}%")
print(f"基准年化收益率: {benchmark_annual*100:.2f}%")

# 确定最佳策略
all_sharpe = {
    'ma_crossover': ma_metrics['sharpe_ratio'],
    'rsi_mean_reversion': rsi_metrics['sharpe_ratio'],
    'bollinger_bands': bb_metrics['sharpe_ratio']
}
best_strategy = max(all_sharpe, key=all_sharpe.get)
best_name = {
    'ma_crossover': '均线交叉策略 (MA5/MA20)',
    'rsi_mean_reversion': 'RSI均值回归策略',
    'bollinger_bands': '布林带策略'
}

print(f"\n最佳策略: {best_name[best_strategy]} (夏普比率: {all_sharpe[best_strategy]})")

# 保存所有结果
all_results = {
    "experiment_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "stock": "000001 平安银行 (sz.000001)",
    "data_range": f"{df['date'].iloc[0].date()} 至 {df['date'].iloc[-1].date()}",
    "data_points": len(df),
    "strategies": {
        "ma_crossover": {
            "name": "均线交叉策略 (MA5/MA20)",
            "fast_ma": 5,
            "slow_ma": 20,
            "metrics": ma_metrics
        },
        "rsi_mean_reversion": {
            "name": "RSI均值回归策略",
            "lookback": 14,
            "lower_threshold": 30,
            "upper_threshold": 70,
            "metrics": rsi_metrics
        },
        "bollinger_bands": {
            "name": "布林带策略",
            "window": 20,
            "std_mult": 2,
            "metrics": bb_metrics
        }
    },
    "benchmark": {
        "name": "买入持有",
        "total_return": round(benchmark_return * 100, 2),
        "annual_return": round(benchmark_annual * 100, 2)
    },
    "best_strategy": best_strategy
}

output_path = '/Users/derek/WorkBuddy/2026-06-20-12-11-53/fars_system/workspace/projects/proj_20260620_131657_ed54dda9/backtest_results.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print(f"\n回测结果已保存到: {output_path}")

# 保存技术指标数据供论文使用
indicator_data = df[['date', 'close', 'return', 'ma5', 'ma20', 'ma60', 'rsi', 'macd', 'macd_hist', 'bb_upper', 'bb_lower']].tail(100).to_dict('records')
with open('/Users/derek/WorkBuddy/2026-06-20-12-11-53/fars_system/workspace/projects/proj_20260620_131657_ed54dda9/indicator_sample.json', 'w', encoding='utf-8') as f:
    json.dump(indicator_data, f, ensure_ascii=False, indent=2, default=str)

print("\n实验完成!")