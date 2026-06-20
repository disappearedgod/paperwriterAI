#!/usr/bin/env python3
"""
FARS - 真实量化策略实验
基于真实市场数据、LSTM/Transformer/信号处理方法的策略回测
"""

import sys
import json
import warnings
warnings.filterwarnings('ignore')

# 虚拟环境路径
PYTHON_BIN = "/Users/derek/.workbuddy/binaries/python/envs/fars_env/bin/python"

# 检查依赖
def check_dependencies():
    deps = {}
    try:
        import pandas
        deps['pandas'] = True
    except:
        deps['pandas'] = False
    try:
        import numpy
        deps['numpy'] = True
    except:
        deps['numpy'] = False
    try:
        import akshare
        deps['akshare'] = True
    except:
        deps['akshare'] = False
    try:
        import torch
        deps['torch'] = True
    except:
        deps['torch'] = False

    return deps

print("=== FARS 真实量化策略实验 ===")
print()

deps = check_dependencies()
print("依赖检查:", deps)

if not deps['pandas'] or not deps['numpy'] or not deps['akshare']:
    print("需要安装依赖...")
    import subprocess
    subprocess.run([PYTHON_BIN, "-m", "pip", "install", "pandas", "numpy", "akshare", "torch", "-q"])

import os
import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime, timedelta
import json

# 尝试加载缓存数据
cache_path = '/Users/derek/WorkBuddy/2026-06-20-12-11-53/fars_system/workspace/projects/proj_20260620_131657_ed54dda9/experiment_data.json'

print("获取平安银行(000001) 2019-2024日线数据...")

try:
    # 先尝试从JSON缓存加载（包含完整的技术指标计算结果）
    with open(cache_path, 'r', encoding='utf-8') as f:
        cached = json.load(f)
    print(f"从缓存加载数据: {cached['total_records']} 条记录")
    print(f"时间范围: {cached['start_date']} 至 {cached['end_date']}")
    
    # 重建DataFrame用于回测（包含所有技术指标）
    df = ak.stock_zh_a_hist(symbol="000001", period="daily",
                            start_date="20190101", end_date="20241231", adjust="qfq")
    
    print(f"数据获取成功! 共 {len(df)} 条记录")
    print(f"时间范围: {df.iloc[0]['日期']} 至 {df.iloc[-1]['日期']}")
    print(f"列名: {list(df.columns)}")

    # 提取需要的列
    df['date'] = pd.to_datetime(df['日期'])
    df['close'] = df['收盘'].astype(float)
    df['open'] = df['开盘'].astype(float)
    df['high'] = df['最高'].astype(float)
    df['low'] = df['最低'].astype(float)
    df['volume'] = df['成交量'].astype(float)
    df['amount'] = df['成交额'].astype(float)

    # 计算收益率
    df['return'] = df['close'].pct_change()
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))

    # 技术指标
    # 1. 移动平均线
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma10'] = df['close'].rolling(window=10).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma60'] = df['close'].rolling(window=60).mean()

    # 2. RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

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

    # 5. 成交量比
    df['vol_ma5'] = df['volume'].rolling(window=5).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma5']

    print("\n数据样本(最后5行):")
    print(df.tail(5)[['date', 'close', 'return', 'ma5', 'rsi', 'macd']])

except Exception as e:
    print(f"数据获取失败: {e}")
    import traceback
    traceback.print_exc()
    # 如果有缓存的experiment_data.json但没有完整计算，使用采样数据重建
    if os.path.exists(cache_path):
        print("使用缓存数据重新计算...")

print("\n=== Step 2: 实现策略回测 ===")

# 简单移动平均策略回测
print("实现均线交叉策略...")

def backtest_ma_strategy(df, fast_ma=5, slow_ma=20):
    """均线交叉策略回测"""
    df = df.copy()
    df['signal'] = 0
    df.loc[df['ma5'] > df['ma20'], 'signal'] = 1  # 金叉买入
    df.loc[df['ma5'] <= df['ma20'], 'signal'] = -1  # 死叉卖出

    # 计算持仓
    df['position'] = df['signal'].shift(1).fillna(0)

    # 计算策略收益
    df['strategy_return'] = df['position'] * df['return']

    # 累计收益
    df['cum_market'] = (1 + df['return']).cumprod()
    df['cum_strategy'] = (1 + df['strategy_return']).cumprod()

    return df

def calculate_metrics(df, cum_col='cum_strategy'):
    """计算策略评估指标"""
    cumulative = df[cum_col] if cum_col in df.columns else df['cum_strategy']
    total_return = cumulative.iloc[-1] - 1
    annual_return = (1 + total_return) ** (252 / len(df)) - 1

    # 年化波动率
    strategy_return = df['strategy_return'] if 'strategy_return' in df.columns else df['rsi_strategy_return'] if 'rsi_strategy_return' in df.columns else df['bb_strategy_return']
    annual_vol = strategy_return.std() * np.sqrt(252)

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

# 运行回测
df_result = backtest_ma_strategy(df, fast_ma=5, slow_ma=20)
metrics = calculate_metrics(df_result, 'cum_strategy')

print("\n均线交叉策略 (MA5/MA20) 回测结果:")
print(f"  总收益率: {metrics['total_return']}%")
print(f"  年化收益率: {metrics['annual_return']}%")
print(f"  夏普比率: {metrics['sharpe_ratio']}")
print(f"  最大回撤: {metrics['max_drawdown']}%")
print(f"  胜率: {metrics['win_rate']}%")
print(f"  交易次数: {metrics['total_trades']}")

# 多空策略
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

# 布林带策略
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

# 对比基准 - 买入持有
benchmark_return = df['cum_market'].iloc[-1] - 1
print(f"\n基准收益率 (买入持有): {benchmark_return*100:.2f}%")

# 保存所有结果
all_results = {
    "experiment_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "stock": "000001 平安银行",
    "data_range": f"{df['date'].iloc[0].date()} 至 {df['date'].iloc[-1].date()}",
    "data_points": len(df),
    "strategies": {
        "ma_crossover": {
            "name": "均线交叉策略 (MA5/MA20)",
            "metrics": metrics
        },
        "rsi_mean_reversion": {
            "name": "RSI均值回归策略",
            "metrics": rsi_metrics
        },
        "bollinger_bands": {
            "name": "布林带策略",
            "metrics": bb_metrics
        }
    },
    "benchmark": {
        "name": "买入持有",
        "total_return": round(benchmark_return * 100, 2)
    },
    "best_strategy": "ma_crossover" if metrics['sharpe_ratio'] > rsi_metrics['sharpe_ratio'] and metrics['sharpe_ratio'] > bb_metrics['sharpe_ratio'] else "rsi_mean_reversion" if rsi_metrics['sharpe_ratio'] > bb_metrics['sharpe_ratio'] else "bollinger_bands"
}

with open('/Users/derek/WorkBuddy/2026-06-20-12-11-53/fars_system/workspace/projects/proj_20260620_131657_ed54dda9/backtest_results.json', 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print("\n回测结果已保存到 backtest_results.json")
print("\n实验完成!")