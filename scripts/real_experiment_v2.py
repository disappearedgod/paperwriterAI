#!/usr/bin/env python3
"""
FARS - 真实量化策略实验
基于真实市场数据的技术分析策略回测
"""

import json
import os
import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional

import akshare as ak
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

EXPERIMENT_TEMPLATE_VERSION = "v3_multi_asset_cost_freq"

print("=== FARS 真实量化策略实验 ===")
print()

for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(key, None)
os.environ["NO_PROXY"] = "*"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or "")
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or "")
    except Exception:
        return default


def _env_list(name: str, default: str) -> List[str]:
    raw = str(os.environ.get(name) or default).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _norm_ashare_symbol(sym: str) -> str:
    s = str(sym or "").strip()
    s = s.replace("sz.", "").replace("sh.", "").replace(".SZ", "").replace(".SS", "").upper()
    if s.isdigit() and len(s) == 6:
        return s
    return s


def _try_load_from_mongo(symbol: str, *, start: str, end: str) -> Optional[pd.DataFrame]:
    try:
        from pymongo import MongoClient  # type: ignore
    except Exception:
        return None

    uri = os.environ.get("MONGO_URI") or os.environ.get("MONGODB_URI")
    db = os.environ.get("MONGO_DB")
    col = os.environ.get("MONGO_COLLECTION")
    if not uri or not db or not col:
        return None

    code = _norm_ashare_symbol(symbol)
    variants: List[str] = []
    if code.isdigit() and len(code) == 6:
        variants = [f"sz.{code}", f"sh.{code}", code]
    else:
        variants = [symbol]

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        collection = client[db][col]
        q = {"date": {"$gte": start, "$lte": end}, "symbol": {"$in": variants}}
        rows = list(collection.find(q, {"_id": 0}).sort("date", 1))
        if not rows:
            return None
        df = pd.DataFrame(rows)
        if "date" not in df.columns:
            return None
        df["date"] = pd.to_datetime(df["date"])
        if "amount" not in df.columns and ("close" in df.columns) and ("volume" in df.columns):
            df["amount"] = df["close"] * df["volume"]
        if "pctChg" not in df.columns and "close" in df.columns:
            df["pctChg"] = df["close"].pct_change() * 100
        df = df.sort_values("date").reset_index(drop=True)
        return df
    except Exception:
        return None


def _try_load_from_akshare_daily(symbol: str, *, start: str, end: str) -> Optional[pd.DataFrame]:
    try:
        raw = ak.stock_zh_a_hist(
            symbol=_norm_ashare_symbol(symbol),
            period="daily",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="qfq",
        )
        if raw is None or len(raw) == 0:
            return None
        return raw.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "涨跌幅": "pctChg",
            }
        )
    except Exception:
        return None


def _try_load_from_akshare_60m(symbol: str, *, start: str, end: str) -> Optional[pd.DataFrame]:
    try:
        raw = ak.stock_zh_a_hist_min_em(
            symbol=_norm_ashare_symbol(symbol),
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            period="60",
            adjust="qfq",
        )
        if raw is None or len(raw) == 0:
            return None
        df = raw.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
            }
        )
        df["pctChg"] = df["close"].pct_change() * 100
        return df
    except Exception:
        return None


def _try_load_from_yfinance(symbol: str, *, freq: str, start: str, end: str) -> Optional[pd.DataFrame]:
    interval = "1d"
    if freq == "1h":
        interval = "60m"

    yf_symbol = symbol
    if symbol.isdigit() and len(symbol) == 6:
        yf_symbol = f"{symbol}.SZ"

    try:
        raw = yf.download(yf_symbol, start=start, end=end, interval=interval, progress=False)
        if raw is None or raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.reset_index().rename(
            columns={
                "Datetime": "date",
                "Date": "date",
                "Open": "open",
                "Close": "close",
                "High": "high",
                "Low": "low",
                "Volume": "volume",
            }
        )
        raw["amount"] = raw["close"] * raw["volume"]
        raw["pctChg"] = raw["close"].pct_change() * 100
        return raw
    except Exception:
        return None


def load_ohlcv(symbol: str, *, freq: str, start: str, end: str) -> pd.DataFrame:
    df: Optional[pd.DataFrame] = None
    if freq == "1d":
        df = _try_load_from_mongo(symbol, start=start, end=end)
        if df is None:
            df = _try_load_from_akshare_daily(symbol, start=start, end=end)
        if df is None:
            df = _try_load_from_yfinance(symbol, freq=freq, start=start, end=end)
    elif freq == "1h":
        df = _try_load_from_akshare_60m(symbol, start=start, end=end)
        if df is None:
            df = _try_load_from_yfinance(symbol, freq=freq, start=start, end=end)

    if df is None or len(df) == 0:
        raise RuntimeError(f"数据获取失败: symbol={symbol}, freq={freq}")

    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            raise RuntimeError(f"缺少必要字段: {col} (symbol={symbol}, freq={freq})")
        series = df[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        df[col] = pd.to_numeric(series, errors="coerce")

    if "amount" not in df.columns:
        df["amount"] = df["close"] * df["volume"]
    if "pctChg" not in df.columns:
        df["pctChg"] = df["close"].pct_change() * 100

    df = df.dropna().sort_values("date").reset_index(drop=True)
    df["return"] = df["pctChg"] / 100
    df["symbol"] = _norm_ashare_symbol(symbol)
    df["freq"] = freq
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ma5"] = df["close"].rolling(window=5).mean()
    df["ma10"] = df["close"].rolling(window=10).mean()
    df["ma20"] = df["close"].rolling(window=20).mean()
    df["ma60"] = df["close"].rolling(window=60).mean()

    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs_val = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs_val))

    exp12 = df["close"].ewm(span=12, adjust=False).mean()
    exp26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = exp12 - exp26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    df["bb_mid"] = df["close"].rolling(window=20).mean()
    bb_std = df["close"].rolling(window=20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std

    df["vol_ma5"] = df["volume"].rolling(window=5).mean()
    df["vol_ratio"] = df["volume"] / df["vol_ma5"]

    return df.dropna().reset_index(drop=True)


def calculate_metrics(df: pd.DataFrame, cum_col: str = "cum_strategy") -> Dict[str, Any]:
    cumulative = df[cum_col].dropna() if cum_col in df.columns else pd.Series([], dtype=float)
    if len(cumulative) == 0:
        return {"total_return": 0, "annual_return": 0, "sharpe_ratio": 0, "max_drawdown": 0, "win_rate": 0, "total_trades": 0, "annual_vol": 0}

    total_return = float(cumulative.iloc[-1] - 1)
    annual_return = float((1 + total_return) ** (252 / len(df)) - 1)

    strategy_return = df["strategy_return"].fillna(0) if "strategy_return" in df.columns else df["return"].fillna(0) * 0
    annual_vol = float(strategy_return.std() * np.sqrt(252)) if float(strategy_return.std() or 0.0) > 0 else 0.001

    risk_free = 0.03
    sharpe = float((annual_return - risk_free) / annual_vol) if annual_vol > 0 else 0.0

    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = float(drawdown.min())

    winning_trades = int((strategy_return > 0).sum())
    total_trades = int((strategy_return != 0).sum())
    win_rate = float(winning_trades / total_trades) if total_trades > 0 else 0.0

    return {
        "total_return": round(total_return * 100, 2),
        "annual_return": round(annual_return * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "win_rate": round(win_rate * 100, 2),
        "total_trades": int(total_trades),
        "annual_vol": round(annual_vol * 100, 2),
    }


symbols = [_norm_ashare_symbol(s) for s in _env_list("EXPERIMENT_SYMBOLS", "000001")] or ["000001"]
frequencies = [f.strip() for f in _env_list("EXPERIMENT_FREQUENCIES", "1d") if f.strip()] or ["1d"]
start_date = str(os.environ.get("EXPERIMENT_START_DATE") or "2019-01-01")
end_date = str(os.environ.get("EXPERIMENT_END_DATE") or "2024-12-31")

commission_bps = _env_float("COST_COMMISSION_BPS", 3.0)
slippage_bps = _env_float("COST_SLIPPAGE_BPS", 2.0)
total_cost_bps = float(commission_bps) + float(slippage_bps)
cost_rate = total_cost_bps / 10000.0

print(f"标的: {symbols}")
print(f"频率: {frequencies}")
print(f"区间: {start_date} 至 {end_date}")
print(f"成本模型: commission_bps={commission_bps}, slippage_bps={slippage_bps}, total_bps={total_cost_bps}")


def _apply_costs(df: pd.DataFrame, *, pos_col: str, ret_col: str, out_col: str) -> pd.DataFrame:
    df = df.copy()
    pos = df[pos_col].fillna(0.0)
    prev_pos = pos.shift(1).fillna(0.0)
    turnover = (pos - prev_pos).abs()
    df[out_col] = df[ret_col].fillna(0.0) - (turnover * float(cost_rate))
    return df


def backtest_ma_strategy(df: pd.DataFrame, fast_ma: int = 5, slow_ma: int = 20) -> pd.DataFrame:
    df = df.copy()
    df["fast_ma"] = df["close"].rolling(window=int(fast_ma)).mean()
    df["slow_ma"] = df["close"].rolling(window=int(slow_ma)).mean()
    df["signal"] = 0
    df.loc[df["fast_ma"] > df["slow_ma"], "signal"] = 1
    df.loc[df["fast_ma"] <= df["slow_ma"], "signal"] = -1
    df["position"] = df["signal"].shift(1).fillna(0)
    df["gross_return"] = df["position"] * df["return"]
    df = _apply_costs(df, pos_col="position", ret_col="gross_return", out_col="strategy_return")
    df["cum_strategy"] = (1 + df["strategy_return"]).cumprod()
    return df


def backtest_rsi_strategy(df: pd.DataFrame, lookback: int = 14, lower: int = 30, upper: int = 70, hold_days: int = 3) -> pd.DataFrame:
    df = df.copy()
    df["rsi_signal"] = 0
    df.loc[df["rsi"] < lower, "rsi_signal"] = 1
    df.loc[df["rsi"] > upper, "rsi_signal"] = -1
    df.loc[(df["rsi"] >= lower) & (df["rsi"] <= upper), "rsi_signal"] = 0
    df["rsi_position"] = df["rsi_signal"].rolling(int(hold_days)).mean().fillna(0)
    df["rsi_position"] = df["rsi_position"].clip(-1, 1)
    df["gross_return"] = df["rsi_position"] * df["return"]
    df = _apply_costs(df, pos_col="rsi_position", ret_col="gross_return", out_col="rsi_strategy_return")
    df["cum_rsi"] = (1 + df["rsi_strategy_return"]).cumprod()
    return df


def backtest_bb_strategy(df: pd.DataFrame, window: int = 20, std_mult: float = 2) -> pd.DataFrame:
    df = df.copy()
    df["bb_mid"] = df["close"].rolling(window=int(window)).mean()
    bb_std = df["close"].rolling(window=int(window)).std()
    df["bb_upper"] = df["bb_mid"] + float(std_mult) * bb_std
    df["bb_lower"] = df["bb_mid"] - float(std_mult) * bb_std
    df["bb_signal"] = 0
    df.loc[df["close"] < df["bb_lower"], "bb_signal"] = 1
    df.loc[df["close"] > df["bb_upper"], "bb_signal"] = -1
    df.loc[(df["close"] >= df["bb_lower"]) & (df["close"] <= df["bb_upper"]), "bb_signal"] = 0
    df["bb_position"] = df["bb_signal"].shift(1).fillna(0)
    df["gross_return"] = df["bb_position"] * df["return"]
    df = _apply_costs(df, pos_col="bb_position", ret_col="gross_return", out_col="bb_strategy_return")
    df["cum_bb"] = (1 + df["bb_strategy_return"]).cumprod()
    return df


def backtest_quantagent_vote(df: pd.DataFrame, *, use_trend: bool = True, use_meanrev: bool = True, use_vol: bool = True) -> pd.DataFrame:
    df = df.copy()
    df["agent_trend"] = np.where(df["ma5"] > df["ma20"], 1, -1)
    df["agent_meanrev"] = np.select([df["rsi"] < 30, df["rsi"] > 70], [1, -1], default=0)
    df["agent_vol"] = np.select([df["close"] < df["bb_lower"], df["close"] > df["bb_upper"]], [1, -1], default=0)

    parts = []
    if use_trend:
        parts.append(df["agent_trend"])
    if use_meanrev:
        parts.append(df["agent_meanrev"])
    if use_vol:
        parts.append(df["agent_vol"])

    vote_sum = sum(parts) if parts else df["agent_trend"] * 0
    df["agent_vote"] = np.where(vote_sum > 0, 1, np.where(vote_sum < 0, -1, 0))
    df["position"] = df["agent_vote"].shift(1).fillna(0)
    df["gross_return"] = df["position"] * df["return"]
    df = _apply_costs(df, pos_col="position", ret_col="gross_return", out_col="strategy_return")
    df["cum_quantagent"] = (1 + df["strategy_return"]).cumprod()
    return df


def _run_single(df: pd.DataFrame) -> Dict[str, Any]:
    ma_candidates = []
    for fast in (5, 8, 10, 12):
        for slow in (20, 30, 60):
            if fast >= slow:
                continue
            df_ma = backtest_ma_strategy(df, fast_ma=fast, slow_ma=slow)
            ma_candidates.append({"fast_ma": fast, "slow_ma": slow, "metrics": calculate_metrics(df_ma, "cum_strategy")})
    ma_best = max(ma_candidates, key=lambda x: x["metrics"]["sharpe_ratio"])

    rsi_candidates = []
    for lower in (20, 25, 30):
        for upper in (70, 75, 80):
            for hold in (2, 3, 5):
                df_rsi = backtest_rsi_strategy(df, lower=lower, upper=upper, hold_days=hold)
                rsi_candidates.append({"lookback": 14, "lower_threshold": lower, "upper_threshold": upper, "hold_days": hold, "metrics": calculate_metrics(df_rsi, "cum_rsi")})
    rsi_best = max(rsi_candidates, key=lambda x: x["metrics"]["sharpe_ratio"])

    bb_candidates = []
    for window in (20, 30, 40):
        for std_mult in (1.8, 2.0, 2.2):
            df_bb = backtest_bb_strategy(df, window=window, std_mult=std_mult)
            bb_candidates.append({"window": window, "std_mult": std_mult, "metrics": calculate_metrics(df_bb, "cum_bb")})
    bb_best = max(bb_candidates, key=lambda x: x["metrics"]["sharpe_ratio"])

    benchmark_cum = (1 + df["return"]).cumprod()
    benchmark_return = float(benchmark_cum.iloc[-1] - 1)
    benchmark_annual = float((1 + benchmark_return) ** (252 / len(df)) - 1)

    all_sharpe = {"ma_crossover": ma_best["metrics"]["sharpe_ratio"], "rsi_mean_reversion": rsi_best["metrics"]["sharpe_ratio"], "bollinger_bands": bb_best["metrics"]["sharpe_ratio"]}
    best_strategy = max(all_sharpe, key=all_sharpe.get)

    df_qa = backtest_quantagent_vote(df)
    qa_metrics = calculate_metrics(df_qa, "cum_quantagent")

    return {
        "strategies": {
            "ma_crossover": {"name": f"均线交叉策略 (MA{ma_best['fast_ma']}/MA{ma_best['slow_ma']})", "fast_ma": ma_best["fast_ma"], "slow_ma": ma_best["slow_ma"], "metrics": ma_best["metrics"]},
            "rsi_mean_reversion": {"name": "RSI均值回归策略", "lookback": rsi_best["lookback"], "lower_threshold": rsi_best["lower_threshold"], "upper_threshold": rsi_best["upper_threshold"], "hold_days": rsi_best["hold_days"], "metrics": rsi_best["metrics"]},
            "bollinger_bands": {"name": "布林带策略", "window": bb_best["window"], "std_mult": bb_best["std_mult"], "metrics": bb_best["metrics"]},
        },
        "benchmark": {"name": "买入持有", "total_return": round(benchmark_return * 100, 2), "annual_return": round(benchmark_annual * 100, 2)},
        "best_strategy": best_strategy,
        "quantagent": {
            "name": "QuantAgent 投票模拟（Trend/MeanRev/Vol 三智能体）",
            "agents": [{"id": "trend", "signal": "ma5 > ma20 => +1 else -1"}, {"id": "meanrev", "signal": "rsi<30 => +1; rsi>70 => -1; else 0"}, {"id": "vol", "signal": "close<bb_lower => +1; close>bb_upper => -1; else 0"}],
            "aggregator": "majority_vote_on_sign(sum(signals))",
            "metrics": qa_metrics,
            "ablations": {},
        },
        "trace_tail": df_qa[["date", "close", "return", "agent_trend", "agent_meanrev", "agent_vol", "agent_vote", "position", "strategy_return"]].tail(200).copy(),
    }


def _merge_portfolio(rets: Dict[str, pd.Series]) -> pd.Series:
    parts = []
    for _, s in rets.items():
        if s is None:
            continue
        parts.append(s.rename_axis("date"))
    if not parts:
        return pd.Series([], dtype=float)
    df = pd.concat(parts, axis=1)
    return df.mean(axis=1).fillna(0.0)


def _metrics_from_returns(returns: pd.Series) -> Dict[str, Any]:
    if returns is None or len(returns) == 0:
        return {"total_return": 0, "annual_return": 0, "sharpe_ratio": 0, "max_drawdown": 0, "win_rate": 0, "total_trades": 0, "annual_vol": 0}
    cum = (1 + returns.fillna(0.0)).cumprod()
    df = pd.DataFrame({"strategy_return": returns.fillna(0.0), "cum_strategy": cum})
    return calculate_metrics(df, "cum_strategy")


print("\n=== Step: 多标的/多频率实验运行 ===")
run_results: Dict[str, Any] = {}

primary_symbol = symbols[0]
primary_freq = frequencies[0]
primary_df: Optional[pd.DataFrame] = None
primary_trace: Optional[pd.DataFrame] = None

for freq in frequencies:
    by_symbol: Dict[str, Any] = {}
    portfolio_collect: Dict[str, Dict[str, pd.Series]] = {"benchmark": {}, "ma_crossover": {}, "rsi_mean_reversion": {}, "bollinger_bands": {}, "quantagent": {}}

    for sym in symbols:
        print(f"\n加载数据: symbol={sym}, freq={freq}")
        raw = load_ohlcv(sym, freq=freq, start=start_date, end=end_date)
        df = add_indicators(raw)
        if sym == primary_symbol and freq == primary_freq:
            primary_df = df

        single = _run_single(df)
        trace_tail = single.pop("trace_tail")
        if sym == primary_symbol and freq == primary_freq:
            primary_trace = trace_tail.copy()

        by_symbol[sym] = {
            "symbol": sym,
            "freq": freq,
            "data_range": f"{df['date'].iloc[0]} 至 {df['date'].iloc[-1]}",
            "data_points": int(len(df)),
            **single,
        }

        benchmark_ret = df["return"].copy()
        benchmark_ret.index = pd.to_datetime(df["date"])
        portfolio_collect["benchmark"][sym] = benchmark_ret

        df_ma = backtest_ma_strategy(df, fast_ma=by_symbol[sym]["strategies"]["ma_crossover"]["fast_ma"], slow_ma=by_symbol[sym]["strategies"]["ma_crossover"]["slow_ma"])
        s = df_ma["strategy_return"].copy()
        s.index = pd.to_datetime(df_ma["date"])
        portfolio_collect["ma_crossover"][sym] = s

        df_rsi = backtest_rsi_strategy(df, lower=by_symbol[sym]["strategies"]["rsi_mean_reversion"]["lower_threshold"], upper=by_symbol[sym]["strategies"]["rsi_mean_reversion"]["upper_threshold"], hold_days=by_symbol[sym]["strategies"]["rsi_mean_reversion"]["hold_days"])
        s = df_rsi["rsi_strategy_return"].copy()
        s.index = pd.to_datetime(df_rsi["date"])
        portfolio_collect["rsi_mean_reversion"][sym] = s

        df_bb = backtest_bb_strategy(df, window=by_symbol[sym]["strategies"]["bollinger_bands"]["window"], std_mult=by_symbol[sym]["strategies"]["bollinger_bands"]["std_mult"])
        s = df_bb["bb_strategy_return"].copy()
        s.index = pd.to_datetime(df_bb["date"])
        portfolio_collect["bollinger_bands"][sym] = s

        df_qa = backtest_quantagent_vote(df)
        s = df_qa["strategy_return"].copy()
        s.index = pd.to_datetime(df_qa["date"])
        portfolio_collect["quantagent"][sym] = s

    portfolio = {
        "benchmark": {"name": "买入持有(等权组合)", "metrics": _metrics_from_returns(_merge_portfolio(portfolio_collect["benchmark"]))},
        "strategies": {
            "ma_crossover": {"name": "均线交叉(等权组合)", "metrics": _metrics_from_returns(_merge_portfolio(portfolio_collect["ma_crossover"]))},
            "rsi_mean_reversion": {"name": "RSI均值回归(等权组合)", "metrics": _metrics_from_returns(_merge_portfolio(portfolio_collect["rsi_mean_reversion"]))},
            "bollinger_bands": {"name": "布林带(等权组合)", "metrics": _metrics_from_returns(_merge_portfolio(portfolio_collect["bollinger_bands"]))},
        },
        "quantagent": {"name": "QuantAgent(等权组合, 每标的独立投票后等权聚合收益)", "metrics": _metrics_from_returns(_merge_portfolio(portfolio_collect["quantagent"]))},
    }
    best_strategy = max(portfolio["strategies"].keys(), key=lambda k: portfolio["strategies"][k]["metrics"]["sharpe_ratio"])
    portfolio["best_strategy"] = best_strategy

    run_results[freq] = {"portfolio": portfolio, "by_symbol": by_symbol}


root_dir = os.environ.get("RESEARCH_ROOT") or os.environ.get("RESEARCH_WORKSPACE")
if not root_dir:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir) if os.path.basename(script_dir) == "code" else script_dir

rid = os.environ.get("RESEARCH_ID")
if not rid:
    try:
        rid = RESEARCH_ID
    except NameError:
        rid = "RS-default"

os.makedirs(os.path.join(root_dir, "metrics"), exist_ok=True)
os.makedirs(os.path.join(root_dir, "data"), exist_ok=True)

backtest_payload = {
    "experiment_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "template_version": EXPERIMENT_TEMPLATE_VERSION,
    "universe": {"symbols": symbols, "frequencies": frequencies, "start_date": start_date, "end_date": end_date},
    "cost_model": {"commission_bps": commission_bps, "slippage_bps": slippage_bps, "total_bps": total_cost_bps},
    "results": run_results,
}

backtest_path = os.path.join(root_dir, "metrics", f"{rid}_backtest_results.json")
with open(backtest_path, "w", encoding="utf-8") as f:
    json.dump(backtest_payload, f, ensure_ascii=False, indent=2, default=str)
print(f"\n回测结果已保存到: {backtest_path}")

freq0 = primary_freq
portfolio0 = run_results.get(freq0, {}).get("portfolio", {})
baseline_best = str(portfolio0.get("best_strategy") or "ma_crossover")
baseline_metrics = ((portfolio0.get("strategies") or {}).get(baseline_best) or {}).get("metrics") or {}
benchmark_metrics = (portfolio0.get("benchmark") or {}).get("metrics") or {}
qa_metrics = (portfolio0.get("quantagent") or {}).get("metrics") or {}

qa_payload = {
    "experiment_date": backtest_payload["experiment_date"],
    "template_version": EXPERIMENT_TEMPLATE_VERSION,
    "frequency": freq0,
    "stock": "PORTFOLIO_EQ_WEIGHT",
    "data_range": f"{start_date} 至 {end_date}",
    "data_points": int((primary_df["date"].shape[0] if primary_df is not None else 0)),
    "cost_model": backtest_payload["cost_model"],
    "quantagent": {
        "name": "QuantAgent 投票模拟（Trend/MeanRev/Vol 三智能体）",
        "agents": [{"id": "trend", "signal": "ma5 > ma20 => +1 else -1"}, {"id": "meanrev", "signal": "rsi<30 => +1; rsi>70 => -1; else 0"}, {"id": "vol", "signal": "close<bb_lower => +1; close>bb_upper => -1; else 0"}],
        "aggregator": "majority_vote_on_sign(sum(signals))",
        "metrics": qa_metrics,
        "ablations": {},
    },
    "baseline_best_strategy": baseline_best,
    "baseline_best_strategy_metrics": baseline_metrics,
    "benchmark": {"name": "买入持有(等权组合)", **benchmark_metrics},
    "by_symbol": run_results.get(freq0, {}).get("by_symbol", {}),
}

qa_results_path = os.path.join(root_dir, "metrics", f"{rid}_quantagent_results.json")
with open(qa_results_path, "w", encoding="utf-8") as f:
    json.dump(qa_payload, f, ensure_ascii=False, indent=2, default=str)
print(f"\nQuantAgent 结果已保存到: {qa_results_path}")

if primary_trace is not None:
    trace = primary_trace.copy()
    trace["date"] = trace["date"].astype(str)
    trace.insert(0, "symbol", primary_symbol)
    trace.insert(1, "freq", primary_freq)
    qa_trace_path = os.path.join(root_dir, "data", f"{rid}_quantagent_trace.json")
    with open(qa_trace_path, "w", encoding="utf-8") as f:
        json.dump(trace.to_dict("records"), f, ensure_ascii=False, indent=2, default=str)
    print(f"\nQuantAgent trace 已保存到: {qa_trace_path}")

if primary_df is not None:
    indicator = primary_df[["date", "close", "return", "ma5", "ma20", "ma60", "rsi", "macd", "macd_hist", "bb_upper", "bb_lower"]].tail(120).copy()
    indicator["date"] = indicator["date"].astype(str)
    indicator_payload = {"symbol": primary_symbol, "freq": primary_freq, "rows": indicator.to_dict("records")}
    indicator_path = os.path.join(root_dir, "data", f"{rid}_indicator_sample.json")
    with open(indicator_path, "w", encoding="utf-8") as f:
        json.dump(indicator_payload, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n技术指标数据已保存到: {indicator_path}")

exp_data_path = os.path.join(root_dir, "data", f"{rid}_experiment_data.json")
exp_data = {
    "research_id": rid,
    "template_version": EXPERIMENT_TEMPLATE_VERSION,
    "universe": backtest_payload["universe"],
    "cost_model": backtest_payload["cost_model"],
    "primary_symbol": primary_symbol,
    "primary_frequency": primary_freq,
    "created_at": datetime.now().isoformat(),
}
with open(exp_data_path, "w", encoding="utf-8") as f:
    json.dump(exp_data, f, ensure_ascii=False, indent=2, default=str)

print("\n实验完成!")
