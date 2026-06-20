#!/usr/bin/env python3
"""
FARS - MiniMax API 测试脚本
验证 MiniMax API 连接是否正常工作
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.fetchers import LLMCaller

# MiniMax API 配置 (用户提供)
MINIMAX_CONFIG = {
    "base_url": "https://token.juda.dev/v1",
    "api_key": "sk-EM9y8cMhuiSEWEZb13Df397b7d274eAfBbC9227fAeE8Db2b",
    "model": "MiniMax-M2.7-highspeed"
}

def test_minimax_connection():
    """测试 MiniMax API 连接"""
    print("=" * 60)
    print("FARS - MiniMax API 连接测试")
    print("=" * 60)
    print(f"\nAPI 地址: {MINIMAX_CONFIG['base_url']}")
    print(f"模型: {MINIMAX_CONFIG['model']}")
    print(f"API Key: {MINIMAX_CONFIG['api_key'][:20]}...{MINIMAX_CONFIG['api_key'][-10:]}")

    # 创建 LLM Caller
    llm = LLMCaller(
        provider="minimax",
        model=MINIMAX_CONFIG["model"],
        api_key=MINIMAX_CONFIG["api_key"],
        base_url=MINIMAX_CONFIG["base_url"]
    )

    # 简单的测试提示
    test_prompt = """请用一句话简单介绍一下自己，包括：
1. 你的模型名称
2. 你擅长的任务类型
3. 你的主要特点

请用中文回答。"""

    print("\n" + "-" * 60)
    print("发送测试请求...")
    print("-" * 60)
    print(f"\n提示词: {test_prompt}\n")

    try:
        response = llm.call(
            prompt=test_prompt,
            temperature=0.7,
            max_tokens=1024
        )

        if response:
            print("-" * 60)
            print("✅ API 调用成功!")
            print("-" * 60)
            print("\n模型回复:")
            print(response)
            print("\n" + "=" * 60)
            print("测试完成 - MiniMax API 连接正常")
            print("=" * 60)
            return True
        else:
            print("-" * 60)
            print("❌ API 调用失败 - 未获取到回复")
            print("-" * 60)
            return False

    except Exception as e:
        print("-" * 60)
        print(f"❌ API 调用异常: {e}")
        print("-" * 60)
        return False


def test_minimax_with_system_prompt():
    """测试带系统提示的调用"""
    print("\n" + "=" * 60)
    print("测试带系统提示的调用")
    print("=" * 60)

    llm = LLMCaller(
        provider="minimax",
        model=MINIMAX_CONFIG["model"],
        api_key=MINIMAX_CONFIG["api_key"],
        base_url=MINIMAX_CONFIG["base_url"]
    )

    system_prompt = "你是一个量化交易研究助手，专门帮助分析金融论文和开发交易策略。"
    user_prompt = "假设你是一个量化研究员，请用 3 句话总结一下为什么量化交易策略需要因子多样性。"

    try:
        response = llm.call(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.5,
            max_tokens=512
        )

        if response:
            print("✅ 带系统提示的调用成功!")
            print("\n回复:")
            print(response)
            return True
        else:
            print("❌ 带系统提示的调用失败")
            return False

    except Exception as e:
        print(f"❌ 异常: {e}")
        return False


if __name__ == "__main__":
    success1 = test_minimax_connection()
    if success1:
        success2 = test_minimax_with_system_prompt()

    print("\n" + "=" * 60)
    if success1:
        print("🎉 MiniMax API 测试全部通过!")
    else:
        print("⚠️  MiniMax API 测试失败，请检查配置")
    print("=" * 60)