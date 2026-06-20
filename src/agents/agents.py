"""
FARS - 四个核心Agent实现
Ideation Agent, Planning Agent, Experiment Agent, Writing Agent
"""

import json
import re
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

from ..tools.fetchers import PaperFetcher, MarketDataFetcher, LLMCaller, CodeExecutor
from ..tools.backtest import BacktestEngine, MomentumStrategy, BacktestResult
from ..core.config import Workspace, CONFIG
from ..prompts.templates import (
    IDEA_GENERATION_PROMPT, PAPER_ANALYSIS_PROMPT,
    EXPERIMENT_PLANNING_PROMPT, CODE_GENERATION_PROMPT,
    DEBUG_ASSISTANCE_PROMPT, PAPER_WRITING_PROMPT, STRATEGY_EVALUATION_PROMPT,
    fill_idea_prompt, fill_code_gen_prompt, fill_debug_prompt,SCIENTIFIC_AGENT_SYSTEM_PROMPT
)


class IdeationAgent:
    """
    Ideation Agent - 论文阅读与假设生成

    职责：
    1. 从arXiv/Semantic Scholar获取最新论文
    2. 深度分析论文的方法论和贡献
    3. 从论文中提取可量化的交易逻辑和因子假设
    4. 生成结构化的假设JSON
    """

    def __init__(self, llm_caller: LLMCaller = None, workspace: Workspace = None):
        self.paper_fetcher = PaperFetcher()
        self.llm = llm_caller or LLMCaller(
            provider=CONFIG["llm"]["provider"],
            model=CONFIG["llm"]["model"]
        )
        self.workspace = workspace or Workspace()

    def search_papers(self, query: str, max_results: int = 20,
                     sources: List[str] = None) -> List[Dict]:
        """
        搜索论文

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            sources: 数据源列表 ["arxiv", "semantic_scholar"]

        Returns:
            论文列表
        """
        if sources is None:
            sources = ["arxiv", "semantic_scholar"]

        all_papers = []

        if "arxiv" in sources:
            papers = self.paper_fetcher.fetch_from_arxiv(
                query=query,
                max_results=max_results,
                categories=["q-fin.PM", "q-fin.TR", "cs.LG", "cs.AI"]
            )
            all_papers.extend(papers)

        if "semantic_scholar" in sources:
            papers = self.paper_fetcher.fetch_from_semantic_scholar(
                query=query,
                max_results=max_results,
                fields=["title", "authors", "abstract", "year", "openAccessPdf", "citationCount"]
            )
            all_papers.extend(papers)

        # 去重（基于arxiv_id或title）
        seen = set()
        unique_papers = []
        for paper in all_papers:
            paper_id = paper.get("arxiv_id") or paper.get("title", "")[:50]
            if paper_id not in seen:
                seen.add(paper_id)
                unique_papers.append(paper)

        return unique_papers

    def analyze_paper(self, paper_info: Dict) -> Dict:
        """
        深度分析单篇论文

        Args:
            paper_info: 论文基本信息

        Returns:
            分析结果
        """
        prompt = PAPER_ANALYSIS_PROMPT.format(
            title=paper_info.get("title", ""),
            abstract=paper_info.get("abstract", "")
        )

        response = self.llm.call(
            prompt=prompt,
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT
        )

        if response:
            try:
                # 提取JSON
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return {"error": "Failed to parse analysis result"}

    def generate_ideas(self, paper_info: Dict, analysis_result: Dict = None) -> Dict:
        """
        从论文生成交易假设

        Args:
            paper_info: 论文基本信息
            analysis_result: 可选的已有分析结果

        Returns:
            生成的假设JSON
        """
        # 如果没有分析结果，先进行分析
        if analysis_result is None:
            analysis_result = self.analyze_paper(paper_info)

        # 使用分析结果填充提示模板
        prompt = fill_idea_prompt(paper_info)

        # 如果有分析结果，追加到提示中
        if analysis_result and "analysis" in analysis_result:
            analysis_json = json.dumps(analysis_result["analysis"], ensure_ascii=False)
            prompt += f"\n\n深度分析结果：\n{analysis_json}"

        response = self.llm.call(
            prompt=prompt,
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT
        )

        if response:
            try:
                # 提取JSON
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    ideas = json.loads(json_match.group())
                    # 保存到workspace
                    self.workspace.save_artifact(
                        "ideas",
                        f"ideas_{paper_info.get('arxiv_id', 'paper')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        ideas
                    )
                    return ideas
            except json.JSONDecodeError as e:
                return {"error": f"Failed to parse ideas: {e}"}

        return {"error": "Failed to generate ideas"}

    def run_full_pipeline(self, query: str, max_papers: int = 5) -> List[Dict]:
        """
        运行完整的论文到假设流程

        Args:
            query: 搜索关键词
            max_papers: 处理的最大论文数

        Returns:
            生成的假设列表
        """
        # 1. 搜索论文
        print(f"[Ideation Agent] Searching papers with query: {query}")
        papers = self.search_papers(query, max_results=max_papers)

        if not papers:
            print("[Ideation Agent] No papers found")
            return []

        # 2. 对每篇论文生成假设
        all_ideas = []
        for i, paper in enumerate(papers[:max_papers]):
            print(f"[Ideation Agent] Processing paper {i+1}/{min(max_papers, len(papers))}: {paper.get('title', '')[:50]}...")

            # 生成假设
            ideas = self.generate_ideas(paper)
            if "ideas" in ideas:
                ideas["paper_info"] = paper
                all_ideas.append(ideas)

        return all_ideas


class PlanningAgent:
    """
    Planning Agent - 实验计划制定

    职责：
    1. 将假设转化为详细的实验计划
    2. 设计对照实验
    3. 设定评估指标和成功标准
    4. 规划实验步骤和数据需求
    """

    def __init__(self, llm_caller: LLMCaller = None, workspace: Workspace = None):
        self.llm = llm_caller or LLMCaller(
            provider=CONFIG["llm"]["provider"],
            model=CONFIG["llm"]["model"]
        )
        self.workspace = workspace or Workspace()

    def create_experiment_plan(self, idea: Dict, existing_plan: Dict = None) -> Dict:
        """
        创建实验计划

        Args:
            idea: 假设JSON
            existing_plan: 可选的已有计划

        Returns:
            实验计划JSON
        """
        # 提取关键信息
        idea_summary = idea.get("ideas", [{}])[0].get("title", "") if idea.get("ideas") else ""
        idea_details = json.dumps(idea.get("ideas", [])[0] if idea.get("ideas") else {}, ensure_ascii=False)

        prompt = EXPERIMENT_PLANNING_PROMPT.format(
            idea_summary=idea_summary,
            idea_details=idea_details
        )

        response = self.llm.call(
            prompt=prompt,
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT
        )

        if response:
            try:
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    plan = json.loads(json_match.group())
                    # 保存到workspace
                    self.workspace.save_artifact(
                        "plans",
                        f"plan_{plan.get('experiment_id', 'exp')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        plan
                    )
                    return plan
            except json.JSONDecodeError:
                pass

        return {"error": "Failed to create experiment plan"}

    def refine_plan(self, current_plan: Dict, feedback: Dict) -> Dict:
        """
        根据反馈优化实验计划

        Args:
            current_plan: 当前计划
            feedback: 反馈信息（如之前的实验结果）

        Returns:
            优化后的计划
        """
        refined_plan = current_plan.copy()
        refined_plan["refinement_history"] = refined_plan.get("refinement_history", [])
        refined_plan["refinement_history"].append({
            "timestamp": datetime.now().isoformat(),
            "feedback": feedback
        })

        # 这里可以添加更复杂的优化逻辑
        return refined_plan


class ExperimentAgent:
    """
    Experiment Agent - 实验执行与回测

    职责：
    1. 根据实验计划生成可执行代码
    2. 在沙箱环境中执行回测
    3. 评估策略性能
    4. 错误自愈和代码调试
    """

    def __init__(self, llm_caller: LLMCaller = None, workspace: Workspace = None):
        self.llm = llm_caller or LLMCaller(
            provider=CONFIG["llm"]["provider"],
            model=CONFIG["llm"]["model"]
        )
        self.workspace = workspace or Workspace()
        self.code_executor = CodeExecutor()
        self.backtest_engine = BacktestEngine(
            initial_cash=CONFIG["backtest"].get("initial_cash", 1000000),
            commission=CONFIG["backtest"].get("commission", 0.001)
        )

    def generate_code(self, experiment_plan: Dict) -> str:
        """
        生成回测代码

        Args:
            experiment_plan: 实验计划

        Returns:
            生成的Python代码
        """
        prompt = fill_code_gen_prompt(experiment_plan)

        response = self.llm.call(
            prompt=prompt,
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT
        )

        if response:
            # 提取Python代码
            code_match = re.search(r'```python\n([\s\S]*?)\n```', response)
            if code_match:
                code = code_match.group(1)
                # 保存代码
                exp_id = experiment_plan.get("experiment_id", "exp")
                self.workspace.save_artifact(
                    "experiments",
                    f"code_{exp_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py",
                    code
                )
                return code

            # 也可能没有markdown标记
            code_start = response.find("import")
            if code_start != -1:
                code = response[code_start:]
                exp_id = experiment_plan.get("experiment_id", "exp")
                self.workspace.save_artifact(
                    "experiments",
                    f"code_{exp_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py",
                    code
                )
                return code

        return ""

    def execute_experiment(self, code: str, experiment_plan: Dict) -> Dict:
        """
        执行实验

        Args:
            code: Python代码
            experiment_plan: 实验计划

        Returns:
            执行结果
        """
        print(f"[Experiment Agent] Executing experiment: {experiment_plan.get('experiment_id')}")

        # 准备全局和局部变量
        globals_dict = {
            "config": CONFIG,
            "workspace": self.workspace,
            "experiment_plan": experiment_plan
        }

        # 执行代码
        success, output, result_dict = self.code_executor.execute(code, globals_dict)

        if success:
            print(f"[Experiment Agent] Experiment completed successfully")
            return {
                "status": "completed",
                "output": output,
                "result": result_dict,
                "experiment_id": experiment_plan.get("experiment_id")
            }
        else:
            print(f"[Experiment Agent] Experiment failed: {output[:200]}")
            return {
                "status": "failed",
                "error": output,
                "experiment_id": experiment_plan.get("experiment_id")
            }

    def debug_and_fix(self, error: str, code: str, experiment_plan: Dict) -> str:
        """
        Debug并修复代码

        Args:
            error: 错误信息
            code: 原始代码
            experiment_plan: 实验计划

        Returns:
            修复后的代码
        """
        prompt = fill_debug_prompt(
            error_traceback=error,
            original_code=code,
            experiment_id=experiment_plan.get("experiment_id", ""),
            hypothesis=experiment_plan.get("hypothesis", "")
        )

        response = self.llm.call(
            prompt=prompt,
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT
        )

        if response:
            try:
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    result = json.loads(json_match.group())
                    if "fixed_code" in result:
                        # 保存修复后的代码
                        exp_id = experiment_plan.get("experiment_id", "exp")
                        self.workspace.save_artifact(
                            "experiments",
                            f"code_fixed_{exp_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py",
                            result["fixed_code"]
                        )
                        return result["fixed_code"]
            except json.JSONDecodeError:
                pass

        return code  # 返回原始代码作为后备

    def run_experiment_with_retry(self, experiment_plan: Dict, max_retries: int = 3) -> Dict:
        """
        运行实验（带重试机制）

        Args:
            experiment_plan: 实验计划
            max_retries: 最大重试次数

        Returns:
            实验结果
        """
        for attempt in range(max_retries):
            # 生成代码
            code = self.generate_code(experiment_plan)
            if not code:
                return {"status": "failed", "error": "Failed to generate code"}

            # 执行实验
            result = self.execute_experiment(code, experiment_plan)

            if result["status"] == "completed":
                # 评估结果
                eval_result = self.evaluate_result(result)
                return eval_result
            else:
                # 尝试Debug和修复
                if attempt < max_retries - 1:
                    print(f"[Experiment Agent] Attempt {attempt + 1} failed, attempting to fix...")
                    code = self.debug_and_fix(result["error"], code, experiment_plan)
                    experiment_plan["retry_code"] = code
                else:
                    return result

        return {"status": "failed", "error": "Max retries exceeded"}

    def evaluate_result(self, result: Dict) -> Dict:
        """
        评估实验结果

        Args:
            result: 实验执行结果

        Returns:
            评估结果
        """
        result_metrics = result.get("result", {}).get("result_metrics", {}) if result.get("result") else {}

        # 检查是否满足阈值
        min_sharpe = CONFIG["evaluation"]["min_sharpe_ratio"]
        max_dd = CONFIG["evaluation"]["max_drawdown_threshold"]
        min_ic = CONFIG["evaluation"]["min_ic"]

        sharpe = result_metrics.get("sharpe_ratio", 0)
        max_drawdown = result_metrics.get("max_drawdown", 0)

        passed = (sharpe >= min_sharpe and max_drawdown >= max_dd)

        return {
            "status": "completed" if passed else "below_threshold",
            "passed": passed,
            "result_metrics": result_metrics,
            "thresholds": {
                "min_sharpe_ratio": min_sharpe,
                "max_drawdown_threshold": max_dd,
                "min_ic": min_ic
            },
            "experiment_id": result.get("experiment_id")
        }


class WritingAgent:
    """
    Writing Agent - 论文撰写

    职责：
    1. 根据实验结果撰写完整论文
    2. 生成LaTeX格式的学术论文
    3. 自动生成图表和表格
    4. 输出可提交的论文草稿
    """

    def __init__(self, llm_caller: LLMCaller = None, workspace: Workspace = None):
        self.llm = llm_caller or LLMCaller(
            provider=CONFIG["llm"]["provider"],
            model=CONFIG["llm"]["model"]
        )
        self.workspace = workspace or Workspace()

    def write_paper(self, experiment_result: Dict, original_idea: Dict,
                   original_paper: Dict = None) -> Dict:
        """
        撰写论文

        Args:
            experiment_result: 实验结果
            original_idea: 原始假设
            original_paper: 原始论文（参考）

        Returns:
            论文JSON
        """
        prompt = PAPER_WRITING_PROMPT.format(
            experiment_id=experiment_result.get("experiment_id", ""),
            hypothesis=original_idea.get("ideas", [{}])[0].get("title", "") if original_idea.get("ideas") else "",
            experiment_plan=json.dumps(original_idea, ensure_ascii=False),
            experiment_results=json.dumps(experiment_result, ensure_ascii=False),
            original_title=original_paper.get("title", "") if original_paper else "",
            original_authors=", ".join(original_paper.get("authors", [])) if original_paper else "",
            original_year=original_paper.get("year", ""),
            original_methodology=original_paper.get("methodology", "") if original_paper else ""
        )

        response = self.llm.call(
            prompt=prompt,
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT
        )

        if response:
            try:
                # 尝试提取JSON
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    paper_data = json.loads(json_match.group())

                    # 保存论文
                    paper_title = paper_data.get("paper_title", "Untitled")
                    safe_title = re.sub(r'[^\w\s-]', '', paper_title)[:50]

                    self.workspace.save_artifact(
                        "papers",
                        f"paper_{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tex",
                        paper_data.get("tex_content", "")
                    )

                    # 保存元数据
                    self.workspace.save_artifact(
                        "papers",
                        f"paper_meta_{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        {
                            "title": paper_title,
                            "references": paper_data.get("references", []),
                            "charts_needed": paper_data.get("charts_needed", []),
                            "word_count": paper_data.get("word_count", ""),
                            "created_at": datetime.now().isoformat()
                        }
                    )

                    return paper_data
            except json.JSONDecodeError:
                pass

        return {"error": "Failed to write paper"}

    def generate_charts(self, experiment_result: Dict) -> List[str]:
        """
        生成图表代码

        Args:
            experiment_result: 实验结果

        Returns:
            图表文件路径列表
        """
        # 使用matplotlib生成图表
        chart_code = '''
import matplotlib.pyplot as plt
import json
import os

# 确保charts目录存在
os.makedirs("charts", exist_ok=True)

# 模拟数据（实际使用时从experiment_result获取）
equity_curve = {equity_curve}
result_metrics = {result_metrics}

# 1. 权益曲线图
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# 权益曲线
dates = [e["date"] for e in equity_curve]
values = [e["equity"] for e in equity_curve]
axes[0, 0].plot(dates, values, 'b-', linewidth=1.5)
axes[0, 0].set_title('Equity Curve')
axes[0, 0].set_xlabel('Date')
axes[0, 0].set_ylabel('Portfolio Value')
axes[0, 0].grid(True, alpha=0.3)

# 回撤图
returns = [e["equity"] for e in equity_curve]
drawdown = [1 - v / max(values[:i+1]) if i > 0 else 0 for i, v in enumerate(values)]
axes[0, 1].fill_between(dates, drawdown, 0, alpha=0.3, color='red')
axes[0, 1].set_title('Drawdown')
axes[0, 1].set_xlabel('Date')
axes[0, 1].set_ylabel('Drawdown')
axes[0, 1].grid(True, alpha=0.3)

# 收益分布
axes[1, 0].bar(["Total Return", "Sharpe", "Max DD"], 
               [result_metrics.get("total_return", 0), 
                result_metrics.get("sharpe_ratio", 0) / 10,
                result_metrics.get("max_drawdown", 0)])
axes[1, 0].set_title('Key Metrics')
axes[1, 0].grid(True, alpha=0.3)

# 保存图表
plt.tight_layout()
plt.savefig("charts/backtest_results.png", dpi=150, bbox_inches='tight')
print("Charts saved to charts/backtest_results.png")
'''.format(
            equity_curve=json.dumps(experiment_result.get("equity_curve", [])),
            result_metrics=json.dumps(experiment_result.get("result_metrics", {}))
        )

        # 保存图表代码
        self.workspace.save_artifact(
            "experiments",
            f"chart_generator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py",
            chart_code
        )

        return ["charts/backtest_results.png"]


class CritiqueAgent:
    """
    Critique Agent - 评估与反思

    职责：
    1. 评估策略性能
    2. 进行自我反思
    3. 提供改进建议
    """

    def __init__(self, llm_caller: LLMCaller = None):
        self.llm = llm_caller or LLMCaller(
            provider=CONFIG["llm"]["provider"],
            model=CONFIG["llm"]["model"]
        )

    def evaluate_strategy(self, backtest_result: Dict, experiment_config: Dict) -> Dict:
        """
        评估策略

        Args:
            backtest_result: 回测结果
            experiment_config: 实验配置

        Returns:
            评估结果
        """
        prompt = STRATEGY_EVALUATION_PROMPT.format(
            backtest_results=json.dumps(backtest_result, ensure_ascii=False),
            data_range=experiment_config.get("data_config", {}).get("start_date", "") + " to " +
                      experiment_config.get("data_config", {}).get("end_date", ""),
            rebalance_frequency=experiment_config.get("backtest_config", {}).get("rebalance_frequency", ""),
            benchmark=CONFIG["backtest"].get("benchmark", "")
        )

        response = self.llm.call(
            prompt=prompt,
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT
        )

        if response:
            try:
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return {"error": "Failed to evaluate strategy"}

    def generate_reflection(self, evaluation: Dict, idea: Dict) -> Dict:
        """
        生成反思

        Args:
            evaluation: 评估结果
            idea: 原始假设

        Returns:
            反思结果
        """
        reflection_prompt = """
基于以下评估结果和原始假设，生成反思和改进建议：

评估结果：
{evaluation}

原始假设：
{idea}

请分析：
1. 为什么策略表现好/差？
2. 假设是否正确？
3. 有哪些改进空间？
4. 是否值得进一步研究？
"""

        response = self.llm.call(
            prompt=reflection_prompt.format(
                evaluation=json.dumps(evaluation, ensure_ascii=False),
                idea=json.dumps(idea, ensure_ascii=False)
            ),
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT
        )

        return {"reflection": response, "evaluation": evaluation}