"""
FARS - 完全自动化研究系统
Fully Automated Research System

基于第一性原理的科研自动化系统：
- 所有研究尝试（成功/失败）都有价值
- 拓扑结构：思想分叉，实验验证/证伪
- 最小知识单元：假设 + 验证
- 核心目标：收益率（真实发现）+ 易用性

作者: 魏宏 (Wei Hong)
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class ResearchStatus(Enum):
    """研究状态"""
    HYPOTHESIS = "hypothesis"           # 假设阶段
    PLANNING = "planning"               # 规划阶段
    EXPERIMENTING = "experimenting"     # 实验阶段
    WRITING = "writing"                 # 写作阶段
    SUCCESS = "success"                # 成功完成
    FAILED = "failed"                  # 失败/被证伪
    ABANDONED = "abandoned"            # 被放弃


class PaperStatus(Enum):
    """论文状态"""
    DRAFT = "draft"                     # 草稿
    REVIEWING = "reviewing"             # 审核中
    PUBLISHED = "published"             # 已发表
    REJECTED = "rejected"               # 被拒绝
    ARCHIVED = "archived"               # 归档（失败研究）


@dataclass
class Hypothesis:
    """研究假设"""
    id: str
    title: str
    description: str
    created_at: str
    status: str = ResearchStatus.HYPOTHESIS.value
    source_paper: str = ""              # 来源论文
    tags: List[str] = field(default_factory=list)
    expected_outcome: str = ""          # 预期结果
    actual_outcome: str = ""            # 实际结果
    experiments: List[str] = field(default_factory=list)  # 实验ID列表


@dataclass
class Experiment:
    """实验"""
    id: str
    hypothesis_id: str
    title: str
    method: str                         # 实验方法
    data_source: str = ""               # 数据来源
    code_path: str = ""
    results: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)  # IC, Sharpe, etc.
    status: str = ResearchStatus.HYPOTHESIS.value
    started_at: str = ""
    completed_at: str = ""
    error: str = ""
    logs: List[str] = field(default_factory=list)


@dataclass
class Paper:
    """论文"""
    id: str
    title: str
    hypothesis_id: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    content: str = ""                   # LaTeX 或 Markdown
    status: str = PaperStatus.DRAFT.value
    quality_score: float = 0.0          # 质量评分
    arxiv_id: str = ""
    submitted_to: str = ""              # 投稿会议/期刊
    submitted_at: str = ""
    published_at: str = ""
    files: Dict[str, str] = field(default_factory=dict)  # file_type -> path
    feedback: str = ""                  # 审稿意见
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ResearchTopology:
    """研究拓扑结构 - 记录假设、实验、论文的关联"""
    nodes: List[Dict] = field(default_factory=list)  # 假设和论文作为节点
    edges: List[Dict] = field(default_factory=list)  # 关系作为边
    statistics: Dict[str, Any] = field(default_factory=dict)


class FARSDatabase:
    """FARS 研究数据库"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "workspace" / "fars_research.json"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> Dict:
        """加载数据库"""
        if self.db_path.exists():
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return self._init_db()

    def _init_db(self) -> Dict:
        """初始化数据库"""
        db = {
            "version": "2.0",
            "created_at": datetime.now().isoformat(),
            "hypotheses": [],
            "experiments": [],
            "papers": [],
            "topology": {"nodes": [], "edges": [], "statistics": {}}
        }
        self._save(db)
        return db

    def _save(self, data: Dict = None):
        """保存数据库"""
        if data is None:
            data = self.data
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ========== 假设操作 ==========

    def add_hypothesis(self, hypothesis: Hypothesis) -> str:
        """添加假设"""
        self.data["hypotheses"].append(asdict(hypothesis))
        self._save()
        return hypothesis.id

    def get_hypothesis(self, hyp_id: str) -> Optional[Hypothesis]:
        """获取假设"""
        for h in self.data["hypotheses"]:
            if h["id"] == hyp_id:
                return Hypothesis(**h)
        return None

    def update_hypothesis(self, hyp_id: str, updates: Dict):
        """更新假设"""
        for i, h in enumerate(self.data["hypotheses"]):
            if h["id"] == hyp_id:
                self.data["hypotheses"][i].update(updates)
                self._save()
                return True
        return False

    # ========== 实验操作 ==========

    def add_experiment(self, experiment: Experiment) -> str:
        """添加实验"""
        self.data["experiments"].append(asdict(experiment))
        # 更新假设的实验列表
        for h in self.data["hypotheses"]:
            if h["id"] == experiment.hypothesis_id:
                if "experiments" not in h:
                    h["experiments"] = []
                h["experiments"].append(experiment.id)
                break
        self._save()
        return experiment.id

    def get_experiment(self, exp_id: str) -> Optional[Experiment]:
        """获取实验"""
        for e in self.data["experiments"]:
            if e["id"] == exp_id:
                return Experiment(**e)
        return None

    def update_experiment(self, exp_id: str, updates: Dict):
        """更新实验"""
        for i, e in enumerate(self.data["experiments"]):
            if e["id"] == exp_id:
                self.data["experiments"][i].update(updates)
                self._save()
                return True
        return False

    # ========== 论文操作 ==========

    def add_paper(self, paper: Paper) -> str:
        """添加论文"""
        self.data["papers"].append(asdict(paper))
        self._save()
        return paper.id

    def get_paper(self, paper_id: str) -> Optional[Paper]:
        """获取论文"""
        for p in self.data["papers"]:
            if p["id"] == paper_id:
                return Paper(**p)
        return None

    def update_paper(self, paper_id: str, updates: Dict):
        """更新论文"""
        for i, p in enumerate(self.data["papers"]):
            if p["id"] == paper_id:
                p["updated_at"] = datetime.now().isoformat()
                self.data["papers"][i].update(updates)
                self._save()
                return True
        return False

    # ========== 拓扑操作 ==========

    def rebuild_topology(self) -> ResearchTopology:
        """重建研究拓扑"""
        nodes = []
        edges = []

        # 添加假设节点
        for h in self.data["hypotheses"]:
            nodes.append({
                "id": h["id"],
                "type": "hypothesis",
                "label": h["title"],
                "status": h["status"],
                "created_at": h["created_at"]
            })

            # 假设 -> 实验 边
            for exp_id in h.get("experiments", []):
                edges.append({
                    "source": h["id"],
                    "target": exp_id,
                    "type": "hypothesis_to_experiment"
                })

        # 添加实验节点
        for e in self.data["experiments"]:
            nodes.append({
                "id": e["id"],
                "type": "experiment",
                "label": e["title"],
                "status": e["status"],
                "metrics": e.get("metrics", {})
            })

            # 实验 -> 论文 边
            if e.get("hypothesis_id"):
                edges.append({
                    "source": e["id"],
                    "target": e["hypothesis_id"],
                    "type": "experiment_to_hypothesis"
                })

        # 添加论文节点
        for p in self.data["papers"]:
            nodes.append({
                "id": p["id"],
                "type": "paper",
                "label": p["title"],
                "status": p["status"],
                "quality_score": p.get("quality_score", 0)
            })

        # 统计
        stats = {
            "total_hypotheses": len(self.data["hypotheses"]),
            "total_experiments": len(self.data["experiments"]),
            "total_papers": len(self.data["papers"]),
            "success_rate": self._calc_success_rate(),
            "avg_quality_score": self._calc_avg_quality(),
            "status_distribution": self._calc_status_distribution()
        }

        topology = ResearchTopology(nodes=nodes, edges=edges, statistics=stats)
        self.data["topology"] = asdict(topology)
        self._save()
        return topology

    def _calc_success_rate(self) -> float:
        """计算成功率"""
        if not self.data["hypotheses"]:
            return 0.0
        success = sum(1 for h in self.data["hypotheses"]
                      if h["status"] in [ResearchStatus.SUCCESS.value, ResearchStatus.WRITING.value])
        return success / len(self.data["hypotheses"])

    def _calc_avg_quality(self) -> float:
        """计算平均质量分"""
        papers_with_score = [p for p in self.data["papers"] if p.get("quality_score", 0) > 0]
        if not papers_with_score:
            return 0.0
        return sum(p["quality_score"] for p in papers_with_score) / len(papers_with_score)

    def _calc_status_distribution(self) -> Dict:
        """计算状态分布"""
        dist = {}
        for h in self.data["hypotheses"]:
            status = h["status"]
            dist[status] = dist.get(status, 0) + 1
        return dist

    def get_all_papers(self, status: str = None) -> List[Paper]:
        """获取所有论文（可按状态筛选）"""
        papers = []
        for p in self.data["papers"]:
            if status is None or p["status"] == status:
                papers.append(Paper(**p))
        return papers

    def get_all_hypotheses(self, status: str = None) -> List[Hypothesis]:
        """获取所有假设（可按状态筛选）"""
        hyps = []
        for h in self.data["hypotheses"]:
            if status is None or h["status"] == status:
                hyps.append(Hypothesis(**h))
        return hyps


class FARSResearch:
    """FARS 研究控制器"""

    def __init__(self, db_path: str = None):
        self.db = FARSDatabase(db_path)

    def create_hypothesis(
        self,
        title: str,
        description: str,
        source_paper: str = "",
        tags: List[str] = None,
        expected_outcome: str = ""
    ) -> Hypothesis:
        """创建新假设"""
        import uuid
        hyp = Hypothesis(
            id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            created_at=datetime.now().isoformat(),
            source_paper=source_paper,
            tags=tags or [],
            expected_outcome=expected_outcome
        )
        self.db.add_hypothesis(hyp)
        return hyp

    def create_experiment(
        self,
        hypothesis_id: str,
        title: str,
        method: str,
        data_source: str = ""
    ) -> Experiment:
        """创建实验"""
        import uuid
        exp = Experiment(
            id=str(uuid.uuid4())[:8],
            hypothesis_id=hypothesis_id,
            title=title,
            method=method,
            data_source=data_source,
            started_at=datetime.now().isoformat()
        )
        self.db.add_experiment(exp)
        # 更新假设状态
        self.db.update_hypothesis(hypothesis_id, {"status": ResearchStatus.EXPERIMENTING.value})
        return exp

    def create_paper(
        self,
        title: str,
        hypothesis_id: str = "",
        authors: List[str] = None,
        content: str = ""
    ) -> Paper:
        """创建论文"""
        import uuid
        paper = Paper(
            id=str(uuid.uuid4())[:8],
            title=title,
            hypothesis_id=hypothesis_id,
            authors=authors or [],
            content=content,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        self.db.add_paper(paper)
        return paper

    def run_workflow(self, hypothesis_id: str = None) -> Dict:
        """运行研究工作流"""
        if hypothesis_id:
            hyps = [self.db.get_hypothesis(hypothesis_id)]
        else:
            hyps = self.db.get_all_hypotheses(status=ResearchStatus.HYPOTHESIS.value)

        results = []
        for hyp in hyps:
            if hyp:
                result = self._process_hypothesis(hyp)
                results.append(result)

        return {
            "processed": len(results),
            "results": results
        }

    def _process_hypothesis(self, hyp: Hypothesis) -> Dict:
        """处理单个假设"""
        result = {"hypothesis_id": hyp.id, "title": hyp.title, "stages": {}}

        # Stage 1: Planning
        self.db.update_hypothesis(hyp.id, {"status": ResearchStatus.PLANNING.value})
        result["stages"]["planning"] = "completed"

        # Stage 2: Experiment
        exp = self.create_experiment(
            hypothesis_id=hyp.id,
            title=f"实验: {hyp.title}",
            method="量化回测"
        )
        result["stages"]["experiment"] = exp.id

        # Stage 3: 根据结果决定
        # 模拟实验结果
        success = len(hyp.description) > 50  # 简单模拟

        if success:
            # Stage 4: Writing
            paper = self.create_paper(
                title=f"基于{hyp.title}的研究",
                hypothesis_id=hyp.id
            )
            self.db.update_hypothesis(hyp.id, {"status": ResearchStatus.SUCCESS.value})
            self.db.update_experiment(exp.id, {
                "status": ResearchStatus.SUCCESS.value,
                "completed_at": datetime.now().isoformat()
            })
            result["stages"]["writing"] = paper.id
            result["outcome"] = "success"
        else:
            self.db.update_hypothesis(hyp.id, {"status": ResearchStatus.FAILED.value})
            self.db.update_experiment(exp.id, {
                "status": ResearchStatus.FAILED.value,
                "completed_at": datetime.now().isoformat(),
                "error": "实验未达到预期结果"
            })
            result["outcome"] = "failed"

        return result

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        self.db.rebuild_topology()
        return self.db.data["topology"]["statistics"]

    def get_topology_data(self) -> ResearchTopology:
        """获取拓扑数据"""
        return self.db.rebuild_topology()

    def export_to_json(self, output_path: str = None) -> str:
        """导出数据到JSON"""
        if output_path is None:
            output_path = Path(__file__).parent.parent.parent / "workspace" / "fars_export.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.db.data, f, ensure_ascii=False, indent=2)
        return str(output_path)


# ============================================================
# 演示
# ============================================================

def demo_fars_research():
    """演示 FARS 研究系统"""
    print("=" * 60)
    print("FARS - 完全自动化研究系统 演示")
    print("=" * 60)
    print()

    fars = FARSResearch()

    # 创建假设
    print("1. 创建研究假设...")
    hyp1 = fars.create_hypothesis(
        title="MA交叉策略在A股市场的有效性",
        description="移动平均线交叉策略（MA5/MA20）在中国A股市场能够获取超额收益",
        source_paper="AlphaPortfolio (2023)",
        tags=["技术分析", "动量策略", "A股"],
        expected_outcome="年化超额收益 > 2%"
    )
    print(f"   假设创建: {hyp1.id} - {hyp1.title}")

    hyp2 = fars.create_hypothesis(
        title="RSI均值回归策略的有效性",
        description="RSI指标在超买超卖区域具有均值回归特性",
        source_paper="Wilder (1978)",
        tags=["技术分析", "均值回归", "RSI"],
        expected_outcome="胜率 > 55%"
    )
    print(f"   假设创建: {hyp2.id} - {hyp2.title}")

    hyp3 = fars.create_hypothesis(
        title="布林带策略的盈利性",
        description="价格触及布林带下轨时买入，上轨时卖出能够获利",
        tags=["技术分析", "布林带", "趋势跟踪"],
        expected_outcome="夏普比率 > 1.0"
    )
    print(f"   假设创建: {hyp3.id} - {hyp3.title}")

    hyp4 = fars.create_hypothesis(
        title="成交量加权的动量效应",
        description="高成交量时期的动量效应更强",
        tags=["动量策略", "成交量", "因子投资"],
        expected_outcome="IC > 0.05"
    )
    print(f"   假设创建: {hyp4.id} - {hyp4.title}")

    print()
    print("2. 运行研究工作流...")
    results = fars.run_workflow()
    print(f"   处理了 {results['processed']} 个假设")

    print()
    print("3. 获取统计信息...")
    stats = fars.get_statistics()
    print(f"   总假设数: {stats['total_hypotheses']}")
    print(f"   总实验数: {stats['total_experiments']}")
    print(f"   总论文数: {stats['total_papers']}")
    print(f"   成功率: {stats['success_rate']*100:.1f}%")
    print(f"   平均质量分: {stats['avg_quality_score']:.2f}")

    print()
    print("4. 获取拓扑数据...")
    topology = fars.get_topology_data()
    print(f"   节点数: {len(topology.nodes)}")
    print(f"   边数: {len(topology.edges)}")

    print()
    print("5. 导出数据...")
    export_path = fars.export_to_json()
    print(f"   导出到: {export_path}")

    print()
    print("=" * 60)
    print("演示完成")
    print("=" * 60)

    return fars


if __name__ == "__main__":
    demo_fars_research()