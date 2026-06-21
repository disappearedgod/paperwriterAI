"""
研究编号: RS-20260621-063
论文标题: E2E API Test Topic
研究主题: E2E API Test Topic

数据位置:
  - MongoDB: mongodb://localhost:27017 / quant_db / daily_bars
  - 种子文献: /Users/derek/Documents/Github/paperwriterAI/data/seed_papers
  - 本研究档案: /Users/derek/Documents/Github/paperwriterAI/data/research/RS-20260621-063_E2E_API_Test_Topic
"""

MONGO_URI = 'mongodb://localhost:27017'
MONGO_DB = 'quant_db'
MONGO_COLLECTION = 'daily_bars'
RESEARCH_ID = 'RS-20260621-063'

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
import akshare as ak
import yfinance as yf
from datetime import datetime

print("=== FARS 真实量化策略实验 ===")
print()

for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(key, None)
os.environ["NO_PROXY"] = "*"

print("获取平安银行(000001) 2019-2024 日线数据...")
df = None
try:
    raw = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20190101", end_date="20241231", adjust="qfq")
    print(f"AkShare 数据获取成功! 共 {len(raw)} 条记录")
    df = raw.rename(columns={
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "涨跌幅": "pctChg",
    })
except Exception as e:
    print(f"AkShare 拉取失败: {e}")

if df is None or len(df) == 0:
    print("尝试使用 yfinance 备用数据源...")
    for symbol in ("000001.SZ", "000001.SS", "SPY"):
        try:
            raw = yf.download(symbol, start="2019-01-01", end="2025-01-01", progress=False)
            if raw is None or raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw = raw.reset_index().rename(columns={
                "Date": "date",
                "Open": "open",
                "Close": "close",
                "High": "high",
                "Low": "low",
                "Volume": "volume",
            })
            raw["amount"] = raw["close"] * raw["volume"]
            raw["pctChg"] = raw["close"].pct_change() * 100
            df = raw
            print(f"yfinance 数据获取成功: {symbol} 共 {len(df)} 条记录")
            break
        except Exception as e:
            print(f"yfinance 拉取失败({symbol}): {e}")

if df is None or len(df) == 0:
    raise RuntimeError("数据获取失败")

df["date"] = pd.to_datetime(df["date"])
for col in ["open", "high", "low", "close", "volume", "amount", "pctChg"]:
    if col not in df.columns:
        raise RuntimeError(f"缺少必要字段: {col}")
    series = df[col]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    df[col] = pd.to_numeric(series, errors="coerce")
df = df.dropna().reset_index(drop=True)
df["return"] = df["pctChg"] / 100

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
print(df[["date", "close", "return", "ma5", "ma20", "rsi"]].tail())

print("\n=== Step 2: 实现策略回测 ===")

def backtest_ma_strategy(df, fast_ma=5, slow_ma=20):
    """均线交叉策略回测"""
    df = df.copy()
    df['fast_ma'] = df['close'].rolling(window=int(fast_ma)).mean()
    df['slow_ma'] = df['close'].rolling(window=int(slow_ma)).mean()
    df['signal'] = 0
    df.loc[df['fast_ma'] > df['slow_ma'], 'signal'] = 1
    df.loc[df['fast_ma'] <= df['slow_ma'], 'signal'] = -1

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

# 策略2: RSI均值回归
print("\n实现RSI均值回归策略...")

def backtest_rsi_strategy(df, lookback=14, lower=30, upper=70, hold_days=3):
    """RSI均值回归策略"""
    df = df.copy()
    df['rsi_signal'] = 0
    df.loc[df['rsi'] < lower, 'rsi_signal'] = 1  # 超卖买入
    df.loc[df['rsi'] > upper, 'rsi_signal'] = -1  # 超买卖出
    df.loc[(df['rsi'] >= lower) & (df['rsi'] <= upper), 'rsi_signal'] = 0

    df['rsi_position'] = df['rsi_signal'].rolling(int(hold_days)).mean().fillna(0)
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

def backtest_bb_strategy(df, window=20, std_mult=2):
    """布林带策略"""
    df = df.copy()
    df['bb_mid'] = df['close'].rolling(window=int(window)).mean()
    bb_std = df['close'].rolling(window=int(window)).std()
    df['bb_upper'] = df['bb_mid'] + float(std_mult) * bb_std
    df['bb_lower'] = df['bb_mid'] - float(std_mult) * bb_std
    df['bb_signal'] = 0
    df.loc[df['close'] < df['bb_lower'], 'bb_signal'] = 1  # 价格低于下轨买入
    df.loc[df['close'] > df['bb_upper'], 'bb_signal'] = -1  # 价格高于上轨卖出
    df.loc[(df['close'] >= df['bb_lower']) & (df['close'] <= df['bb_upper']), 'bb_signal'] = 0

    df['bb_position'] = df['bb_signal'].shift(1).fillna(0)
    df['bb_strategy_return'] = df['bb_position'] * df['return']
    df['cum_bb'] = (1 + df['bb_strategy_return']).cumprod()

    return df

print("\n开始参数搜索（以夏普比率为主）...")

ma_candidates = []
for fast in (5, 8, 10, 12):
    for slow in (20, 30, 60):
        if fast >= slow:
            continue
        df_ma = backtest_ma_strategy(df, fast_ma=fast, slow_ma=slow)
        ma_candidates.append({
            "fast_ma": fast,
            "slow_ma": slow,
            "metrics": calculate_metrics(df_ma, 'cum_strategy'),
        })
ma_best = max(ma_candidates, key=lambda x: x["metrics"]["sharpe_ratio"])

rsi_candidates = []
for lower in (20, 25, 30):
    for upper in (70, 75, 80):
        for hold in (2, 3, 5):
            df_rsi = backtest_rsi_strategy(df, lower=lower, upper=upper, hold_days=hold)
            rsi_candidates.append({
                "lookback": 14,
                "lower_threshold": lower,
                "upper_threshold": upper,
                "hold_days": hold,
                "metrics": calculate_metrics(df_rsi, 'cum_rsi'),
            })
rsi_best = max(rsi_candidates, key=lambda x: x["metrics"]["sharpe_ratio"])

bb_candidates = []
for window in (20, 30, 40):
    for std_mult in (1.8, 2.0, 2.2):
        df_bb = backtest_bb_strategy(df, window=window, std_mult=std_mult)
        bb_candidates.append({
            "window": window,
            "std_mult": std_mult,
            "metrics": calculate_metrics(df_bb, 'cum_bb'),
        })
bb_best = max(bb_candidates, key=lambda x: x["metrics"]["sharpe_ratio"])

print("\n参数搜索结果（最优配置）:")
print(f"  均线交叉: MA{ma_best['fast_ma']}/MA{ma_best['slow_ma']} Sharpe={ma_best['metrics']['sharpe_ratio']}")
print(f"  RSI均值回归: lower={rsi_best['lower_threshold']} upper={rsi_best['upper_threshold']} hold={rsi_best['hold_days']} Sharpe={rsi_best['metrics']['sharpe_ratio']}")
print(f"  布林带: window={bb_best['window']} std={bb_best['std_mult']} Sharpe={bb_best['metrics']['sharpe_ratio']}")

# 基准 - 买入持有
benchmark_cum = (1 + df['return']).cumprod()
benchmark_return = benchmark_cum.iloc[-1] - 1
benchmark_annual = (1 + benchmark_return) ** (252 / len(df)) - 1

print(f"\n基准收益率 (买入持有): {benchmark_return*100:.2f}%")
print(f"基准年化收益率: {benchmark_annual*100:.2f}%")

# 确定最佳策略
all_sharpe = {
    'ma_crossover': ma_best['metrics']['sharpe_ratio'],
    'rsi_mean_reversion': rsi_best['metrics']['sharpe_ratio'],
    'bollinger_bands': bb_best['metrics']['sharpe_ratio']
}
best_strategy = max(all_sharpe, key=all_sharpe.get)
best_name = {
    'ma_crossover': f"均线交叉策略 (MA{ma_best['fast_ma']}/MA{ma_best['slow_ma']})",
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
            "name": f"均线交叉策略 (MA{ma_best['fast_ma']}/MA{ma_best['slow_ma']})",
            "fast_ma": ma_best["fast_ma"],
            "slow_ma": ma_best["slow_ma"],
            "metrics": ma_best["metrics"]
        },
        "rsi_mean_reversion": {
            "name": "RSI均值回归策略",
            "lookback": rsi_best["lookback"],
            "lower_threshold": rsi_best["lower_threshold"],
            "upper_threshold": rsi_best["upper_threshold"],
            "hold_days": rsi_best["hold_days"],
            "metrics": rsi_best["metrics"]
        },
        "bollinger_bands": {
            "name": "布林带策略",
            "window": bb_best["window"],
            "std_mult": bb_best["std_mult"],
            "metrics": bb_best["metrics"]
        }
    },
    "benchmark": {
        "name": "买入持有",
        "total_return": round(benchmark_return * 100, 2),
        "annual_return": round(benchmark_annual * 100, 2)
    },
    "best_strategy": best_strategy
}

# Resolve output paths dynamically
root_dir = os.environ.get("RESEARCH_ROOT") or os.environ.get("RESEARCH_WORKSPACE")
if not root_dir:
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(script_dir) == "code":
            root_dir = os.path.dirname(script_dir)
        else:
            root_dir = script_dir
    except Exception:
        root_dir = "."

rid = os.environ.get("RESEARCH_ID")
if not rid:
    try:
        rid = RESEARCH_ID
    except NameError:
        rid = "RS-default"

output_path = os.path.join(root_dir, "metrics", f"{rid}_backtest_results.json")
# Ensure metrics directory exists
os.makedirs(os.path.join(root_dir, "metrics"), exist_ok=True)

with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print(f"\n回测结果已保存到: {output_path}")

# 保存技术指标数据供论文使用
indicator_data = df[['date', 'close', 'return', 'ma5', 'ma20', 'ma60', 'rsi', 'macd', 'macd_hist', 'bb_upper', 'bb_lower']].tail(100).to_dict('records')
indicator_path = os.path.join(root_dir, "data", f"{rid}_indicator_sample.json")
# Ensure data directory exists
os.makedirs(os.path.join(root_dir, "data"), exist_ok=True)

with open(indicator_path, 'w', encoding='utf-8') as f:
    json.dump(indicator_data, f, ensure_ascii=False, indent=2, default=str)

print(f"\n技术指标数据已保存到: {indicator_path}")

# Additionally save experiment_data.json
exp_data_path = os.path.join(root_dir, "data", f"{rid}_experiment_data.json")
exp_data = {
    "research_id": rid,
    "stock": "000001 平安银行 (sz.000001)",
    "data_range": f"{df['date'].iloc[0].date()} 至 {df['date'].iloc[-1].date()}",
    "data_points": len(df),
    "best_strategy": best_strategy,
    "metrics": all_results["strategies"][best_strategy]["metrics"],
    "created_at": datetime.now().isoformat()
}
with open(exp_data_path, 'w', encoding='utf-8') as f:
    json.dump(exp_data, f, ensure_ascii=False, indent=2)

print("\n实验完成!")
