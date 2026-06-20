"""
FARS - 主程序入口
增强版：支持研究方向、文件上传、日志备份、Ollama备选

使用方式:
    python src/main.py --direction quant_finance --topic "your research topic"
    python src/main.py --mode generate --upload path/to/paper.pdf
    python src/main.py --test-llm  # 测试LLM连接
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import (
    PROJECT_ROOT, Workspace, ResearchDirection, RESEARCH_DIRECTION_DESCRIPTIONS, LLMProvider, LLM_PROVIDER_CONFIG,
    setup_logging, BackupManager, load_config, save_config
)
from src.tools.fetchers import LLMCaller, PaperFetcher, MarketDataFetcher
from src.prompts.templates import (
    PAPER_WRITING_PROMPT, SCIENTIFIC_AGENT_SYSTEM_PROMPT,
    IDEA_GENERATION_PROMPT, PAPER_ANALYSIS_PROMPT, CODE_GENERATION_PROMPT
)


# ============== 主程序类 ==============

class FARS:
    """FARS - Fully Automated Research System - 主控制器"""

    def __init__(self, research_direction: ResearchDirection = ResearchDirection.QUANT_FINANCE,
                 workspace_dir: str = None):
        """
        初始化FARS

        Args:
            research_direction: 研究方向
            workspace_dir: 自定义工作区目录
        """
        self.research_direction = research_direction
        self.workspace = Workspace(research_direction=research_direction)
        self.config = load_config()

        # 初始化LLM
        llm_config = self.config.get("llm", {})
        self._init_llm(llm_config)

        # 初始化工具
        self.paper_fetcher = PaperFetcher()
        self.market_fetcher = MarketDataFetcher()

        self.workspace.logger.info(f"FARS初始化完成")
        self.workspace.logger.info(f"研究方向: {research_direction.value}")

    def _init_llm(self, llm_config: dict):
        """初始化LLM调用器"""
        provider = llm_config.get("provider", "minimax")
        model = llm_config.get("model", "MiniMax-M2.7-highspeed")
        api_key = llm_config.get("api_key")
        base_url = llm_config.get("base_url")

        # 配置Ollama作为备选
        fallback_providers = [
            {
                "provider": "ollama",
                "model": "gemma4",
                "base_url": "http://localhost:11434/v1"
            }
        ]

        self.llm = LLMCaller(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            fallback_providers=fallback_providers
        )

        self.workspace.logger.info(f"LLM初始化: {provider}/{model}")

    def test_llm_connection(self) -> Dict:
        """测试LLM连接"""
        self.workspace.logger.info("测试LLM连接...")

        # 测试主provider
        result = self.llm.test_connection()

        if result["success"]:
            self.workspace.logger.info(f"LLM连接成功: {result['provider']}/{result['model']}")
        else:
            self.workspace.logger.warning(f"主LLM连接失败: {result.get('error')}")

        return result

    def upload_paper(self, file_path: str) -> Dict:
        """
        上传论文文件到工作区

        Args:
            file_path: 论文文件路径

        Returns:
            上传结果
        """
        self.workspace.logger.info(f"上传论文: {file_path}")

        try:
            source = Path(file_path)
            if not source.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            # 根据扩展名处理
            ext = source.suffix.lower()
            if ext == ".pdf":
                # PDF文件 - 暂不支持直接解析，保存引用
                dest = self.workspace.upload_file(source, upload_name=f"paper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
                return {
                    "status": "success",
                    "file_path": str(dest),
                    "type": "pdf",
                    "message": "PDF已上传，请通过Overleaf或其他工具手动处理"
                }
            elif ext == ".tex":
                # LaTeX文件 - 直接保存
                dest = self.workspace.upload_file(source)
                return {
                    "status": "success",
                    "file_path": str(dest),
                    "type": "tex",
                    "message": "LaTeX文件已上传"
                }
            elif ext == ".json":
                # JSON文件 - 可能是论文元数据
                dest = self.workspace.upload_file(source)
                return {
                    "status": "success",
                    "file_path": str(dest),
                    "type": "json",
                    "message": "JSON元数据已上传"
                }
            elif ext in [".txt", ".md"]:
                # 文本文件
                dest = self.workspace.upload_file(source)
                return {
                    "status": "success",
                    "file_path": str(dest),
                    "type": "text",
                    "message": "文本文件已上传"
                }
            else:
                return {
                    "status": "error",
                    "message": f"不支持的文件类型: {ext}"
                }

        except Exception as e:
            self.workspace.logger.error(f"上传失败: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    def search_papers(self, query: str, max_results: int = 10,
                      categories: List[str] = None) -> List[Dict]:
        """
        搜索学术论文

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            categories: arXiv分类列表

        Returns:
            论文列表
        """
        self.workspace.logger.info(f"搜索论文: query={query}, max_results={max_results}")

        # 根据研究方向调整默认分类
        if self.research_direction == ResearchDirection.QUANT_FINANCE:
            categories = categories or ["q-fin.PM", "q-fin.ST", "q-fin.TR", "cs.LG", "stat.ML"]
        elif self.research_direction == ResearchDirection.COMPUTER_VISION:
            categories = categories or ["cs.CV"]
        elif self.research_direction == ResearchDirection.REINFORCEMENT_LEARNING:
            categories = categories or ["cs.LG", "cs.AI", "stat.ML"]

        results = self.paper_fetcher.fetch_from_arxiv(query, max_results, categories)
        self.workspace.logger.info(f"找到 {len(results)} 篇论文")

        return results

    def analyze_paper(self, paper_info: Dict) -> Dict:
        """
        分析论文并提取信息

        Args:
            paper_info: 论文信息字典

        Returns:
            分析结果
        """
        self.workspace.logger.info(f"分析论文: {paper_info.get('title', 'Unknown')[:50]}...")

        prompt = PAPER_ANALYSIS_PROMPT.format(
            paper_id=paper_info.get("arxiv_id", ""),
            title=paper_info.get("title", ""),
            abstract=paper_info.get("abstract", "")
        )

        response = self.llm.call(
            prompt=prompt,
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT,
            max_tokens=8192
        )

        if response:
            try:
                # 提取JSON
                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    analysis = json.loads(json_match.group())
                    # 保存分析结果
                    self.workspace.save_artifact("ideas", f"analysis_{paper_info.get('arxiv_id', 'unknown')}.json", analysis)
                    return analysis
            except Exception as e:
                self.workspace.logger.error(f"解析分析结果失败: {e}")

        return {"status": "error", "message": "分析失败"}

    def generate_hypothesis(self, paper_info: Dict) -> Dict:
        """
        从论文生成交易假设

        Args:
            paper_info: 论文信息

        Returns:
            生成的假设
        """
        self.workspace.logger.info(f"从论文生成假设: {paper_info.get('title', 'Unknown')[:50]}...")

        prompt = IDEA_GENERATION_PROMPT.format(
            paper_id=paper_info.get("arxiv_id", ""),
            title=paper_info.get("title", ""),
            authors=", ".join(paper_info.get("authors", [])),
            year=paper_info.get("year", ""),
            abstract=paper_info.get("abstract", ""),
            methodology=paper_info.get("methodology", "N/A"),
            key_contributions="\n".join([f"- {c}" for c in paper_info.get("key_contributions", [])])
        )

        response = self.llm.call(
            prompt=prompt,
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT,
            max_tokens=8192
        )

        if response:
            try:
                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    hypothesis = json.loads(json_match.group())
                    # 保存
                    self.workspace.save_artifact("ideas", f"hypothesis_{paper_info.get('arxiv_id', 'unknown')}.json", hypothesis)
                    return hypothesis
            except Exception as e:
                self.workspace.logger.error(f"解析假设失败: {e}")

        return {"status": "error", "message": "假设生成失败"}

    def generate_paper(self, experiment_result: dict, topic: str = None) -> Dict:
        """
        生成研究论文

        Args:
            experiment_result: 实验结果
            topic: 论文主题

        Returns:
            生成的论文
        """
        self.workspace.logger.info(f"生成论文: {topic or experiment_result.get('experiment_id', 'unknown')}")

        topic = topic or self.research_direction.value
        original_paper = {}

        prompt = PAPER_WRITING_PROMPT.format(
            experiment_id=experiment_result.get("experiment_id", "exp_001"),
            hypothesis=topic,
            experiment_results=json.dumps(experiment_result, ensure_ascii=False),
            original_title=original_paper.get("title", "N/A") if original_paper else "N/A",
            original_authors=", ".join(original_paper.get("authors", [])) if original_paper else "N/A",
            original_year=original_paper.get("year", "")
        )

        self.workspace.logger.info(f"Prompt长度: {len(prompt)} 字符")

        response = self.llm.call(
            prompt=prompt,
            system_prompt=SCIENTIFIC_AGENT_SYSTEM_PROMPT,
            max_tokens=16000  # 降低到16K以避免context window溢出
        )

        if response:
            try:
                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    paper_data = json.loads(json_match.group())

                    # 保存论文
                    paper_title = paper_data.get("paper_title", "Untitled")
                    safe_title = re.sub(r'[^\w\s-]', '', paper_title)[:50]
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    tex_filename = f"paper_{safe_title}_{timestamp}.tex"
                    tex_path = self.workspace.project_dir / "papers" / tex_filename

                    with open(tex_path, 'w', encoding='utf-8') as f:
                        f.write(paper_data.get("tex_content", ""))

                    self.workspace.logger.info(f"论文已保存: {tex_path}")

                    return {
                        "status": "success",
                        "tex_path": str(tex_path),
                        "paper_title": paper_title,
                        "tex_content": paper_data.get("tex_content", ""),
                        "references": paper_data.get("references", []),
                        "charts_needed": paper_data.get("charts_needed", [])
                    }
            except Exception as e:
                self.workspace.logger.error(f"解析论文失败: {e}")
                # 保存原始响应用于调试
                debug_path = self.workspace.project_dir / "papers" / f"debug_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(response or "No response")
                return {
                    "status": "partial",
                    "debug_path": str(debug_path),
                    "raw_response": response[:500] + "..." if response and len(response) > 500 else response
                }

        return {"status": "error", "message": "论文生成失败"}

    def run_workflow(self, topic: str, mode: str = "all") -> Dict:
        """
        运行完整工作流

        Args:
            topic: 研究主题
            mode: 运行模式 (all|search|analyze|generate)

        Returns:
            工作流结果
        """
        self.workspace.logger.info(f"开始工作流: topic={topic}, mode={mode}")
        self.workspace.log_step("workflow_start", "started", {"topic": topic, "mode": mode})

        results = {
            "topic": topic,
            "mode": mode,
            "research_direction": self.research_direction.value,
            "steps": {}
        }

        try:
            if mode in ["all", "search"]:
                # Step 1: 搜索论文
                self.workspace.log_step("search_papers", "started")
                papers = self.search_papers(topic, max_results=5)
                results["steps"]["search"] = {
                    "status": "completed",
                    "count": len(papers),
                    "papers": [{"title": p.get("title"), "arxiv_id": p.get("arxiv_id")} for p in papers[:3]]
                }
                self.workspace.logger.info(f"搜索完成: 找到 {len(papers)} 篇论文")

            if mode in ["all", "analyze"] and papers:
                # Step 2: 分析论文
                self.workspace.log_step("analyze_papers", "started")
                for i, paper in enumerate(papers[:2]):  # 只分析前2篇
                    analysis = self.analyze_paper(paper)
                    results["steps"][f"analysis_{i}"] = analysis
                self.workspace.logger.info(f"分析完成")

            if mode in ["all", "generate"]:
                # Step 3: 生成论文
                self.workspace.log_step("generate_paper", "started")

                # 模拟实验结果
                simulated_results = {
                    "experiment_id": f"exp_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "execution_time": datetime.now().isoformat(),
                    "result_metrics": {
                        "total_return": 0.08,
                        "sharpe_ratio": 1.2,
                        "max_drawdown": -0.15,
                        "annual_return": 0.10,
                        "win_rate": 0.52,
                        "total_trades": 45
                    },
                    "status": "completed"
                }

                paper_result = self.generate_paper(simulated_results, topic)
                results["steps"]["generation"] = paper_result

                self.workspace.logger.info(f"生成完成: {paper_result.get('status')}")

            self.workspace.log_step("workflow_complete", "completed", results)
            results["status"] = "success"

        except Exception as e:
            self.workspace.logger.error(f"工作流失败: {e}")
            results["status"] = "error"
            results["error"] = str(e)
            self.workspace.log_step("workflow_failed", "failed", {"error": str(e)})

        return results

    def get_status(self) -> Dict:
        """获取系统状态"""
        return {
            "research_direction": self.research_direction.value,
            "project_id": self.workspace.project_id,
            "project_dir": str(self.workspace.project_dir),
            "config": self.config,
            "llm_status": self.test_llm_connection(),
            "backup_count": len(self.workspace.backup_manager.list_backups())
        }


# ============== CLI入口 ==============

def main():
    parser = argparse.ArgumentParser(
        description="FARS - Fully Automated Research System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
研究方向选项:
  quant_finance    量化金融 (默认，主方向)
  computer_vision  计算机视觉
  rl               强化学习

示例:
  # 生成量化交易论文
  python src/main.py --direction quant_finance --topic "Transformer-based momentum trading"

  # 上传论文文件
  python src/main.py --upload path/to/paper.pdf

  # 测试LLM连接
  python src/main.py --test-llm

  # 搜索论文
  python src/main.py --search --topic "deep learning stock prediction"

  # 查看状态
  python src/main.py --status
        """
    )

    parser.add_argument("--direction", "-d", choices=["quant_finance", "computer_vision", "rl"],
                       default="quant_finance", help="研究方向")
    parser.add_argument("--topic", "-t", type=str, help="研究主题/关键词")
    parser.add_argument("--mode", "-m", choices=["all", "search", "analyze", "generate"],
                       default="all", help="运行模式")
    parser.add_argument("--upload", "-u", type=str, help="上传论文文件路径")
    parser.add_argument("--test-llm", action="store_true", help="测试LLM连接")
    parser.add_argument("--search", action="store_true", help="搜索论文模式")
    parser.add_argument("--status", action="store_true", help="查看系统状态")
    parser.add_argument("--workspace", type=str, help="自定义工作区目录")

    args = parser.parse_args()

    # 解析研究方向
    direction_map = {
        "quant_finance": ResearchDirection.QUANT_FINANCE,
        "computer_vision": ResearchDirection.COMPUTER_VISION,
        "rl": ResearchDirection.REINFORCEMENT_LEARNING
    }
    direction = direction_map.get(args.direction, ResearchDirection.QUANT_FINANCE)

    # 初始化FARS
    fars = FARS(research_direction=direction, workspace_dir=args.workspace)

    # 处理命令
    if args.test_llm:
        result = fars.test_llm_connection()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.status:
        status = fars.get_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))

    elif args.upload:
        result = fars.upload_paper(args.upload)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.search and args.topic:
        papers = fars.search_papers(args.topic, max_results=10)
        print(json.dumps(papers, ensure_ascii=False, indent=2))

    elif args.topic:
        result = fars.run_workflow(args.topic, mode=args.mode)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()