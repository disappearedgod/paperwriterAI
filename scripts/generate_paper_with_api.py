#!/usr/bin/env python3
"""
FARS - 集成ChunkedPaperGenerator与MiniMax API
解决token限制问题，生成分块论文

用法:
    python generate_paper_with_api.py
    python generate_paper_with_api.py --title "自定义标题" --authors "作者名"
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.chunked_paper_generator import ChunkedPaperGenerator, ChunkConfig
from src.tools.fetchers import LLMCaller

# MiniMax API 配置
MINIMAX_CONFIG = {
    "base_url": "https://token.juda.dev/v1",
    "api_key": "sk-EM9y8cMhuiSEWEZb13Df397b7d274eAfBbC9227fAeE8Db2b",
    "model": "MiniMax-M2.7-highspeed"
}


def create_minimax_caller() -> LLMCaller:
    """创建MiniMax API调用器"""
    return LLMCaller(
        provider="minimax",
        model=MINIMAX_CONFIG["model"],
        api_key=MINIMAX_CONFIG["api_key"],
        base_url=MINIMAX_CONFIG["base_url"]
    )


def api_caller_wrapper(system_prompt: str, user_prompt: str, max_tokens: int = 16000) -> str:
    """
    API调用封装函数，用于ChunkedPaperGenerator

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        max_tokens: 最大输出token数

    Returns:
        API返回的文本内容
    """
    print(f"    [API调用] max_tokens={max_tokens}, prompt长度={len(user_prompt)}字符")

    llm = create_minimax_caller()
    response = llm.call(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=max_tokens
    )

    if response:
        print(f"    [API成功] 响应长度={len(response)}字符")
        return response
    else:
        print(f"    [API失败] 未能获取响应")
        return ""


def generate_paper(
    title: str = "基于技术指标的A股量化交易策略实证研究",
    authors: str = "魏宏",
    topic: str = "量化交易策略评估",
    backtest_results: dict = None,
    factor_results: list = None
) -> dict:
    """
    使用MiniMax API生成分块论文

    Args:
        title: 论文标题
        authors: 作者
        topic: 研究主题
        backtest_results: 回测结果
        factor_results: 因子分析结果

    Returns:
        生成结果字典
    """
    print("=" * 70)
    print("FARS - MiniMax API 论文生成器")
    print("=" * 70)
    print(f"模型: {MINIMAX_CONFIG['model']}")
    print(f"标题: {title}")
    print()

    # 创建分块生成器
    config = ChunkConfig(
        max_context_tokens=180000,
        max_output_tokens=16000,
        context_sections_limit=3
    )
    generator = ChunkedPaperGenerator(config)

    # 生成论文
    result = generator.generate(
        title=title,
        authors=authors,
        topic=topic,
        backtest_results=backtest_results,
        factor_results=factor_results,
        api_caller=api_caller_wrapper
    )

    return result


def generate_simple_paper(title: str, content_type: str = "abstract") -> str:
    """
    生成单个章节内容（用于测试）

    Args:
        title: 论文标题
        content_type: 章节类型

    Returns:
        生成的内容
    """
    llm = create_minimax_caller()

    prompts = {
        "abstract": f"请为论文《{title}》撰写200-300字的摘要，包含研究问题、方法、主要发现和结论。使用规范的学术中文写作。",
        "introduction": f"请为论文《{title}》撰写800-1000字的引言，包含研究背景、问题动机和研究贡献。使用学术中文，规范表达，引用文献时使用(Author, Year)格式。"
    }

    prompt = prompts.get(content_type, prompts["abstract"])
    response = llm.call(
        prompt=prompt,
        system_prompt="你是一位资深的量化交易研究学者，擅长用严谨的学术语言撰写高质量的研究论文。使用规范的学术中文写作。",
        temperature=0.7,
        max_tokens=4000
    )

    return response or ""


def demo_with_mock_data():
    """使用模拟数据演示"""
    print("\n" + "=" * 70)
    print("演示模式：使用模拟回测数据")
    print("=" * 70)

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

    factor_results = [
        {"factor_name": "动量因子", "information_coefficient": 0.031, "information_ratio": 0.42, "t_statistic": 2.15, "p_value": 0.032},
        {"factor_name": "价值因子", "information_coefficient": 0.024, "information_ratio": 0.38, "t_statistic": 1.89, "p_value": 0.059},
        {"factor_name": "质量因子", "information_coefficient": 0.018, "information_ratio": 0.31, "t_statistic": 1.45, "p_value": 0.147}
    ]

    return generate_paper(
        title="基于技术指标的A股量化交易策略实证研究",
        authors="魏宏",
        topic="量化交易策略评估",
        backtest_results=backtest_results,
        factor_results=factor_results
    )


def test_single_section():
    """测试单个章节生成"""
    print("\n" + "=" * 70)
    print("单章节测试：摘要生成")
    print("=" * 70)

    result = generate_simple_paper(
        "基于深度学习的A股价格预测研究",
        content_type="abstract"
    )

    if result:
        print("\n生成的摘要：")
        print("-" * 50)
        print(result)
        print("-" * 50)
        return True
    else:
        print("生成失败")
        return False


def save_paper(result: dict, output_path: str = None):
    """保存生成的论文到文件"""
    if output_path is None:
        output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_path = os.path.join(output_dir, "outputs", "generated_paper.md")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result['full_paper'])

    print(f"\n论文已保存至: {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FARS - 使用MiniMax API生成分块论文")
    parser.add_argument("--title", type=str, default=None, help="论文标题")
    parser.add_argument("--authors", type=str, default="魏宏", help="作者列表")
    parser.add_argument("--mock", action="store_true", help="使用模拟数据（不调用API）")
    parser.add_argument("--test", action="store_true", help="测试模式：生成单个摘要")
    parser.add_argument("--output", type=str, default=None, help="输出文件路径")

    args = parser.parse_args()

    if args.test:
        # 测试模式：生成单个章节
        if test_single_section():
            print("\n✅ 单章节测试成功!")
        else:
            print("\n❌ 单章节测试失败")
    elif args.mock:
        # 演示模式：使用模拟数据（不调用真实API）
        from scripts.chunked_paper_generator import ChunkedPaperGenerator, ChunkConfig

        config = ChunkConfig()
        generator = ChunkedPaperGenerator(config)

        backtest_results = {
            "stock": "000001 平安银行",
            "data_range": "2019-01-02 至 2024-12-31",
            "data_points": 1456,
            "strategies": {
                "MA交叉": {"metrics": {"total_return": -63.68, "annual_return": -16.08, "sharpe_ratio": -0.61, "max_drawdown": -71.54}},
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

        output_path = save_paper(result, args.output)
        print(f"\n✅ 演示完成! 论文已保存")
    else:
        # 真实API模式
        if args.title:
            result = generate_paper(title=args.title, authors=args.authors)
        else:
            result = demo_with_mock_data()

        output_path = save_paper(result, args.output)
        print(f"\n✅ 论文生成完成! 总计 {len(result['sections'])} 个章节")
        if result['errors']:
            print(f"⚠️ 部分章节生成失败: {result['errors']}")