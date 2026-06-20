"""
FARS Tools Module
工具模块封装
"""

from .fetchers import (
    PaperFetcher,
    MarketDataFetcher,
    LLMCaller,
    CodeExecutor
)

from .backtest import (
    BacktestEngine,
    BacktestResult,
    FARSStrategy,
    MomentumStrategy,
    MeanReversionStrategy,
    calculate_ic,
    calculate_ir,
    evaluate_factor
)

__all__ = [
    "PaperFetcher",
    "MarketDataFetcher",
    "LLMCaller",
    "CodeExecutor",
    "BacktestEngine",
    "BacktestResult",
    "FARSStrategy",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "calculate_ic",
    "calculate_ir",
    "evaluate_factor"
]