"""
FARS Paper Generator - 使用检查点机制生成长论文
解决LLM输出截断问题

作者: 魏宏 (Wei Hong)
"""

import json
import time
import hashlib
from datetime import datetime
from pathlib import Path

# 导入检查点管理器
from chunked_generation import (
    ChunkManager, ChunkState, GenerationConfig, GenerationCheckpoint
)


# ============================================================
# FARS 论文生成器
# ============================================================

class FARSPaperGenerator:
    """
    FARS 系统的论文生成器
    
    专门用于生成量化交易领域的学术论文，支持：
    1. 分块生成，避免token限制
    2. 检查点保存，断点续生成
    3. 真实实验数据嵌入
    """
    
    # 论文结构模板
    PAPER_SECTIONS = [
        "摘要 (Abstract)",
        "引言 (Introduction)", 
        "相关工作 (Related Work)",
        "方法论 (Methodology)",
        "实验设置 (Experimental Setup)",
        "实验结果 (Results)",
        "讨论 (Discussion)",
        "结论 (Conclusion)",
        "参考文献 (References)"
    ]
    
    def __init__(self, workspace_dir: str = "./workspace"):
        self.workspace = Path(workspace_dir)
        self.checkpoint_dir = self.workspace / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        config = GenerationConfig(
            checkpoint_dir=str(self.checkpoint_dir),
            max_tokens_per_chunk=6000  # 留余量给系统提示
        )
        self.chunk_manager = ChunkManager(config)
    
    def load_backtest_results(self, results_path: str = None) -> dict:
        """加载回测结果"""
        if results_path is None:
            # 尝试从FARS默认位置加载
            results_path = self.workspace.parent / "projects/proj_20260620_131657_ed54dda9/backtest_results.json"
        
        if Path(results_path).exists():
            with open(results_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是一位资深的量化交易研究学者，专注于使用机器学习和信号处理方法研究A股市场的交易策略。

你的专长:
1. 学术论文写作：规范、严谨、有深度
2. 量化策略研究：技术指标、因子挖掘、策略回测
3. 机器学习应用：预测模型、特征工程、模型解释
4. 学术诚信：所有数据和实验结果必须真实可复现

写作规范:
1. 使用规范的学术中文/英文（根据上下文）
2. 数学公式使用LaTeX格式: $公式$
3. 表格使用标准格式
4. 保持逻辑连贯，论述严谨
5. 每个主要段落控制在500-800字
6. 在完成一个完整部分后输出 [PAUSE] 标记

重要提醒:
- 不得虚构任何实验数据或结果
- 引用的论文必须是真实存在的
- 如果没有真实数据支撑某个论点，明确说明"需要进一步实验验证"
"""
    
    def build_paper_intro_prompt(
        self,
        title: str,
        authors: str,
        affiliation: str,
        abstract: str
    ) -> str:
        """构建论文开篇提示"""
        return f"""请撰写一篇关于"{title}"的学术论文。

作者信息:
- 作者: {authors}
- 单位: {affiliation}

论文摘要:
/begin abstract
{abstract}
/end abstract

请按以下结构撰写完整论文:

1. 摘要 (Abstract) - 200-300字，概括研究问题、方法、贡献和主要结果

2. 引言 (Introduction) - 包含:
   - 研究背景和动机
   - 研究问题定义
   - 主要贡献（3-5点）
   - 论文结构安排

3. 相关工作 (Related Work) - 涵盖:
   - 传统技术分析策略
   - 机器学习在量化交易中的应用
   - 信号处理方法在金融时间序列中的应用

4. 方法论 (Methodology) - 详细描述:
   - 特征工程方法
   - 策略设计原理
   - 风险控制机制

5. 实验设置 (Experimental Setup) - 包含:
   - 数据集描述（真实A股数据）
   - 评估指标定义
   - 对比基准策略

6. 实验结果 (Results) - 展示真实回测结果:
   - 使用实际的回测数据（如果提供）
   - 可视化分析图表
   - 统计显著性检验

7. 讨论 (Discussion) - 分析:
   - 结果的意义和局限性
   - 与现有方法的比较
   - 可能的改进方向

8. 结论 (Conclusion) - 总结:
   - 研究主要发现
   - 实践意义
   - 未来研究方向

9. 参考文献 (References) - 真实引用的论文列表

现在开始撰写论文，完成每个主要部分后输出 [PAUSE] 标记等待续写指令。"""
    
    def generate_with_resume(
        self,
        title: str,
        authors: str,
        affiliation: str,
        abstract: str,
        api_caller,  # 实际API调用函数
        resume_from_checkpoint: bool = True
    ) -> str:
        """
        带断点续生成功能的论文生成
        
        参数:
            resume_from_checkpoint: 是否从已有检查点恢复
        """
        task_id = f"fars_paper_{hashlib.md5(title.encode()).hexdigest()[:8]}"
        
        # 检查是否有可恢复的检查点
        if resume_from_checkpoint:
            checkpoints = self.chunk_manager.list_checkpoints()
            if checkpoints:
                last_cp = max(checkpoints, key=lambda x: x.chunk_index)
                if last_cp.state == ChunkState.PAUSED:
                    print(f"发现未完成的检查点: 块 #{last_cp.chunk_index + 1}")
                    print(f"已生成内容长度: {len(last_cp.content)} 字符")
                    print("将从检查点恢复生成...")
        
        # 构建提示词
        system_prompt = self.build_system_prompt()
        user_prompt = self.build_paper_intro_prompt(title, authors, affiliation, abstract)
        
        # 执行分块生成
        full_content = []
        
        for checkpoint in self.chunk_manager.generate_with_checkpoints(
            system_prompt=system_prompt,
            user_request=user_prompt,
            task_id=task_id,
            api_caller=api_caller
        ):
            yield checkpoint
    
    def save_final_paper(self, content: str, output_path: str, format: str = "markdown"):
        """保存最终论文"""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        if format == "markdown":
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
        elif format == "latex":
            # 转换为LaTeX格式
            latex_content = self._convert_to_latex(content)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(latex_content)
        
        print(f"论文已保存至: {output_path}")
    
    def _convert_to_latex(self, markdown_content: str) -> str:
        """将Markdown内容转换为LaTeX"""
        # 简化转换，实际应用中需要更完整的处理
        latex = r"""
\documentclass[12pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage{ctex}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{booktabs}

\title{FARS Generated Paper}
\author{Wei Hong}
\date{\today}

\begin{document}
\maketitle

"""
        latex += markdown_content
        latex += "\n\\end{document}\n"
        return latex


# ============================================================
# 使用示例
# ============================================================

def demo_with_mock_api():
    """演示（使用模拟API）"""
    
    print("=" * 70)
    print("FARS Paper Generator - 断点续生成演示")
    print("=" * 70)
    
    # 创建生成器
    generator = FARSPaperGenerator(workspace_dir="./demo_workspace")
    
    # 加载回测结果
    results = generator.load_backtest_results()
    if results:
        print(f"\n已加载回测数据: {results.get('stock', 'Unknown')}")
        print(f"数据范围: {results.get('data_range', 'Unknown')}")
        print(f"数据点数: {results.get('data_points', 0)}")
        
        # 提取关键指标
        strategies = results.get('strategies', {})
        for name, data in strategies.items():
            metrics = data.get('metrics', {})
            print(f"\n策略 {name}:")
            for k, v in metrics.items():
                print(f"  {k}: {v:.2f}")
    else:
        print("\n未找到回测数据，使用模拟数据演示")
    
    # 模拟API调用
    call_count = [0]
    
    def mock_api_caller(system: str, user: str) -> str:
        """模拟API调用"""
        call_count[0] += 1
        print(f"\n[API调用 #{call_count[0]}]")
        
        # 根据调用次数返回不同的内容块
        if call_count[0] == 1:
            return f"""
# 摘要

本文研究了中国A股市场中基于技术指标的量化交易策略。我们提出了三种改进的交易策略，并使用2019-2024年的真实历史数据进行了全面回测。实验结果表明，在考虑交易成本后，所有策略均未能超越买入持有基准，揭示了技术分析策略在实际应用中的局限性。

[PAUSE]
"""
        elif call_count[0] == 2:
            return f"""
## 1. 引言

### 1.1 研究背景

量化交易作为一种系统化的投资方法，在过去二十年间获得了广泛关注。与传统的主观判断交易不同，量化交易依赖于数学模型和计算机程序来识别交易机会、执行交易指令。技术分析作为量化交易的一个重要分支，通过分析历史价格和成交量数据来预测未来价格走势。

### 1.2 研究问题

尽管技术分析策略在实际交易中被广泛应用，但其有效性一直存在争议。本研究旨在回答以下问题：
1. 常见的技术分析策略在中国A股市场的表现如何？
2. 这些策略在扣除交易成本后是否仍能获得正收益？
3. 策略的表现是否在不同的市场环境下保持稳定？

### 1.3 主要贡献

本文的主要贡献包括：
1. 使用真实的历史数据对三种主流技术分析策略进行了全面的实证评估
2. 考虑了现实交易中的交易成本和滑点因素
3. 提供了策略表现的时间序列分析

[PAUSE]
"""
        elif call_count[0] == 3:
            return f"""
## 2. 相关工作

### 2.1 技术分析策略

技术分析策略基于历史价格数据进行交易决策。移动平均线交叉策略（MA Crossover）是最经典的技术分析策略之一，由George Lane于1950年代提出。该策略的核心思想是当短期移动平均线上穿长期移动平均线时产生买入信号，反之产生卖出信号。

相对强弱指数（RSI）策略由J. Welles Wilder Jr.于1978年提出，是一种动量振荡器，用于判断资产是否处于超买或超卖状态。RSI值在0-100之间波动，当RSI低于30时通常被视为超卖信号，当RSI高于70时被视为超买信号。

布林带策略由John Bollinger于1980年代提出，通过计算价格的标准差来构建价格波动区间。当价格触及布林带上轨时可能意味着超买，触及下轨时可能意味着超卖。

### 2.2 量化交易研究现状

近年来，机器学习技术在量化交易领域获得了广泛应用。Zhang等人（2020）使用深度学习模型预测股票走势取得了显著效果。Chen等人（2021）研究了集成学习在量化因子挖掘中的应用。

[PAUSE]
"""
        else:
            return """
## 3. 方法论

### 3.1 特征工程

我们使用三类技术指标作为策略的特征输入...

## 4. 实验设置

### 4.1 数据集

实验使用平安银行（000001）2019-2024年的日线数据...

## 5. 结论

本研究对三种主流技术分析策略进行了实证分析...

[END]
"""
    
    # 执行生成
    print("\n开始生成论文...")
    
    for checkpoint in generator.generate_with_resume(
        title="基于技术指标的A股量化交易策略实证研究",
        authors="魏宏",
        affiliation="FARS量化研究系统",
        abstract="本研究对中国A股市场的技术分析策略进行了全面评估...",
        api_caller=mock_api_caller,
        resume_from_checkpoint=False
    ):
        print(f"\n完成块 #{checkpoint.chunk_index + 1}，状态: {checkpoint.state.value}")
    
    print("\n" + "=" * 70)
    print("论文生成完成！")
    print("=" * 70)
    
    # 列出检查点
    print("\n已保存的检查点:")
    for cp in generator.chunk_manager.list_checkpoints():
        print(f"  块 #{cp.chunk_index + 1}: {len(cp.content)} 字符, {cp.state.value}")


if __name__ == "__main__":
    demo_with_mock_api()