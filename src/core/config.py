"""
FARS - Fully Automated Research System
Core Configuration - Enhanced with Research Directions
"""

import os
import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Union
from enum import Enum
import logging

# ============== 研究方向定义 ==============

class ResearchDirection(Enum):
    """FARS 支持的研究方向"""
    QUANT_FINANCE = "quant_finance"           # 量化金融（核心方向）
    COMPUTER_VISION = "computer_vision"         # 计算机视觉
    REINFORCEMENT_LEARNING = "rl"               # 强化学习

# 研究方向优先级配置
RESEARCH_DIRECTION_PRIORITY = {
    ResearchDirection.QUANT_FINANCE: 1,        # 主方向，优先级最高
    ResearchDirection.COMPUTER_VISION: 2,       # 次方向
    ResearchDirection.REINFORCEMENT_LEARNING: 2 # 次方向
}

# 方向描述
RESEARCH_DIRECTION_DESCRIPTIONS = {
    ResearchDirection.QUANT_FINANCE: {
        "name": "Quantitative Finance",
        "name_cn": "量化金融",
        "keywords": ["quantitative trading", "factor model", "portfolio optimization", "risk management", "market microstructure"],
        "applicable_venues": ["ICML", "NeurIPS", "ICLR", "JPF", "RFS"],
        "paper_format": "elsarticle",
        "main_metrics": ["Sharpe ratio", "Information Coefficient", "Max Drawdown", "Alpha"]
    },
    ResearchDirection.COMPUTER_VISION: {
        "name": "Computer Vision",
        "name_cn": "计算机视觉",
        "keywords": ["object detection", "image segmentation", "visual recognition", "CNN", "vision transformer"],
        "applicable_venues": ["CVPR", "ICCV", "ECCV", "NeurIPS", "ICML"],
        "paper_format": "cvpr",
        "main_metrics": ["mIoU", "mAP", "Accuracy", "F1-score"]
    },
    ResearchDirection.REINFORCEMENT_LEARNING: {
        "name": "Reinforcement Learning",
        "name_cn": "强化学习",
        "keywords": ["RL", "policy gradient", "Q-learning", "MDP", "reward design", "multi-agent"],
        "applicable_venues": ["NeurIPS", "ICML", "ICLR", "AAAI", "IJCAI"],
        "paper_format": "neurips",
        "main_metrics": ["Cumulative Reward", "Success Rate", "Sample Efficiency"]
    }
}


# ============== 日志系统 ==============

def setup_logging(project_dir: Path, log_level: int = logging.INFO) -> logging.Logger:
    """配置项目日志系统"""
    logger = logging.getLogger(f"FARS_{project_dir.name}")
    logger.setLevel(log_level)

    # 清除已有的handlers
    logger.handlers.clear()

    # 控制台handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_format = logging.Formatter(
        '[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # 文件handler
    log_dir = project_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(
        log_dir / f"fars_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_format = logging.Formatter(
        '[%(asctime)s] %(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger


class BackupManager:
    """文件和配置备份管理器"""

    def __init__(self, project_dir: Path, logger: logging.Logger):
        self.project_dir = project_dir
        self.logger = logger
        self.backup_dir = project_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_file(self, file_path: Path, backup_name: str = None) -> Optional[Path]:
        """备份单个文件

        Args:
            file_path: 要备份的文件路径
            backup_name: 自定义备份文件名（不含扩展名）

        Returns:
            备份文件路径，失败返回None
        """
        if not file_path.exists():
            self.logger.warning(f"备份失败：文件不存在 {file_path}")
            return None

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = backup_name or file_path.stem
        backup_filename = f"{backup_name}_{timestamp}{file_path.suffix}"
        backup_path = self.backup_dir / backup_filename

        try:
            shutil.copy2(file_path, backup_path)
            self.logger.info(f"已备份: {file_path} -> {backup_path}")
            return backup_path
        except Exception as e:
            self.logger.error(f"备份失败: {e}")
            return None

    def backup_config(self, config_data: dict, config_name: str = "config") -> Optional[Path]:
        """备份配置数据为JSON

        Args:
            config_data: 配置字典
            config_name: 配置名称

        Returns:
            备份文件路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"{config_name}_{timestamp}.json"
        backup_path = self.backup_dir / backup_filename

        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"已备份配置: {backup_path}")
            return backup_path
        except Exception as e:
            self.logger.error(f"配置备份失败: {e}")
            return None

    def list_backups(self) -> List[Dict]:
        """列出所有备份文件"""
        backups = []
        for f in self.backup_dir.iterdir():
            if f.is_file():
                backups.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
                })
        return sorted(backups, key=lambda x: x["created"], reverse=True)

    def restore_backup(self, backup_path: Path, target_path: Path) -> bool:
        """恢复备份文件

        Args:
            backup_path: 备份文件路径
            target_path: 目标恢复路径

        Returns:
            是否成功
        """
        try:
            shutil.copy2(backup_path, target_path)
            self.logger.info(f"已恢复: {backup_path} -> {target_path}")
            return True
        except Exception as e:
            self.logger.error(f"恢复失败: {e}")
            return False


# ============== 项目根目录 ==============

PROJECT_ROOT = Path(__file__).parent.parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
PAPERS_DIR = PROJECT_ROOT / "papers"
REPORTS_DIR = PROJECT_ROOT / "reports"
UPLOAD_DIR = PROJECT_ROOT / "uploads"

# 确保目录存在
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
PAPERS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ============== LLM Provider 定义 ==============

class LLMProvider(Enum):
    """支持的LLM Provider"""
    MINIMAX = "minimax"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"  # 本地模型


LLM_PROVIDER_CONFIG = {
    LLMProvider.MINIMAX: {
        "name": "MiniMax",
        "models": ["MiniMax-M2.7-highspeed", "MiniMax-M2.8-32K"],
        "base_url": "https://token.juda.dev/v1",
        "context_window": 196608,
        "supports_streaming": True
    },
    LLMProvider.OPENAI: {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "base_url": "https://api.openai.com/v1",
        "context_window": 128000,
        "supports_streaming": True
    },
    LLMProvider.ANTHROPIC: {
        "name": "Anthropic",
        "models": ["claude-3-5-sonnet", "claude-3-opus"],
        "base_url": "https://api.anthropic.com",
        "context_window": 200000,
        "supports_streaming": True
    },
    LLMProvider.DEEPSEEK: {
        "name": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-coder"],
        "base_url": "https://api.deepseek.com",
        "context_window": 128000,
        "supports_streaming": True
    },
    LLMProvider.OLLAMA: {
        "name": "Ollama (Local)",
        "models": ["gemma4", "qwen3.6:35b-a3b-coding-mxfp8", "qwen3-coder:30b-a3b-q4_K_M", "llama3.1:8b"],
        "base_url": "http://localhost:11434/v1",
        "context_window": 32768,  # 取决于模型
        "supports_streaming": True
    }
}


# ============== Workspace 类 ==============

class Workspace:
    """共享工作空间 - 四个Agent之间的协作中介"""

    def __init__(self, project_id: Optional[str] = None, research_direction: ResearchDirection = ResearchDirection.QUANT_FINANCE):
        if project_id is None:
            project_id = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.project_id = project_id
        self.research_direction = research_direction
        self.project_dir = WORKSPACE_DIR / "projects" / project_id
        self._init_project_dirs()

        # 初始化日志和备份
        self.logger = setup_logging(self.project_dir)
        self.backup_manager = BackupManager(self.project_dir, self.logger)

        self.logger.info(f"项目已初始化: {self.project_id}")
        self.logger.info(f"研究方向: {research_direction.value} - {RESEARCH_DIRECTION_DESCRIPTIONS.get(research_direction, {}).get('name_cn', 'Unknown')}")

    def _init_project_dirs(self):
        """初始化项目目录结构"""
        subdirs = ["ideas", "plans", "experiments", "papers", "data", "charts", "logs", "backups", "uploads"]
        for subdir in subdirs:
            (self.project_dir / subdir).mkdir(parents=True, exist_ok=True)

    def save_artifact(self, stage: str, filename: str, content: Union[str, dict],
                      backup: bool = True) -> Path:
        """保存工件到指定阶段目录

        Args:
            stage: 阶段名称 (ideas|plans|experiments|papers|data|charts|logs)
            filename: 文件名
            content: 内容（str或dict）
            backup: 是否备份之前版本

        Returns:
            保存的文件路径
        """
        stage_dir = self.project_dir / stage
        file_path = stage_dir / filename

        # 备份已存在的同名文件
        if backup and file_path.exists():
            self.backup_manager.backup_file(file_path)

        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False, indent=2)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        self.logger.info(f"已保存工件: {stage}/{filename}")
        return file_path

    def read_artifact(self, stage: str, filename: str) -> Optional[str]:
        """读取工件"""
        file_path = self.project_dir / stage / filename
        if not file_path.exists():
            self.logger.warning(f"工件不存在: {stage}/{filename}")
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def list_artifacts(self, stage: str) -> List[str]:
        """列出指定阶段的所有工件"""
        stage_dir = self.project_dir / stage
        if not stage_dir.exists():
            return []
        return [f.name for f in stage_dir.iterdir() if f.is_file()]

    def upload_file(self, source_path: Path, upload_name: str = None) -> Path:
        """上传/导入文件到项目

        Args:
            source_path: 源文件路径（可以是绝对路径或相对路径）
            upload_name: 上传后的文件名（默认使用原文件名）

        Returns:
            上传后的文件路径
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"源文件不存在: {source_path}")

        upload_dir = self.project_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        final_name = upload_name or source.name
        dest_path = upload_dir / final_name

        # 如果目标已存在，先备份
        if dest_path.exists():
            self.backup_manager.backup_file(dest_path)

        shutil.copy2(source, dest_path)
        self.logger.info(f"已上传文件: {source} -> {dest_path}")

        return dest_path

    def get_project_summary(self) -> Dict:
        """获取项目状态摘要"""
        return {
            "project_id": self.project_id,
            "research_direction": self.research_direction.value,
            "research_direction_name": RESEARCH_DIRECTION_DESCRIPTIONS.get(self.research_direction, {}).get("name", "Unknown"),
            "project_dir": str(self.project_dir),
            "stages": {
                stage: self.list_artifacts(stage)
                for stage in ["ideas", "plans", "experiments", "papers"]
            },
            "backup_count": len(self.backup_manager.list_backups()),
            "created_at": datetime.now().isoformat()
        }

    def log_step(self, step_name: str, status: str, details: Dict = None):
        """记录工作流步骤

        Args:
            step_name: 步骤名称
            status: 状态 (started|completed|failed)
            details: 详细信息
        """
        log_entry = {
            "step": step_name,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.save_artifact("logs", f"step_{step_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", log_entry)
        self.logger.info(f"步骤 {step_name} [{status}]")


# ============== 全局配置 ==============

CONFIG = {
    "llm": {
        "provider": "minimax",
        "model": "MiniMax-M2.7-highspeed",
        "temperature": 0.7,
        "max_tokens": 4096,
        "api_key": None,
        "base_url": None
    },
    "data": {
        "yfinance_enabled": True,
        "akshare_enabled": True,
        "mongodb_uri": "mongodb://localhost:27017",
        "mongodb_db": "quant_db"
    },
    "backtest": {
        "framework": "backtrader",
        "default_frequency": "1d",
        "benchmark": "000300.SS"
    },
    "evaluation": {
        "min_sharpe_ratio": 1.5,
        "max_drawdown_threshold": -0.25,
        "min_ic": 0.02
    },
    "research_direction": {
        "primary": "quant_finance",
        "secondary": ["computer_vision", "rl"]
    }
}


def save_config():
    """保存配置到文件"""
    config_path = PROJECT_ROOT / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=2)


def load_config() -> Dict:
    """从文件加载配置"""
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return CONFIG


# ============== 数据Schema定义 ==============

DATABASE_SCHEMA = {
    "papers": {
        "paper_id": "str - 唯一标识",
        "title": "str - 论文标题",
        "authors": "list[str] - 作者列表",
        "year": "int - 发表年份",
        "arxiv_id": "str - arXiv ID",
        "url": "str - 原始链接",
        "abstract": "str - 摘要",
        "methodology": "str - 方法论摘要",
        "key_contributions": "list[str] - 核心贡献",
        "status": "str - read|reading|unread",
        "notes": "str - 阅读笔记",
        "created_at": "datetime - 创建时间"
    },
    "alpha_factors": {
        "factor_id": "str - 唯一标识",
        "name": "str - 因子名称",
        "category": "str - Momentum|MeanReversion|Volatility|Fundamental|Growth",
        "formula_latex": "str - LaTeX公式",
        "code_expression": "str - Python代码表达式",
        "source_paper": "str - 来源论文ID",
        "backtest_result": {
            "sharpe_ratio": "float - 夏普比率",
            "max_drawdown": "float - 最大回撤",
            "ic": "float - 信息系数"
        },
        "status": "str - generated|evaluated|selected|rejected",
        "created_at": "datetime - 创建时间"
    },
    "experiments": {
        "exp_id": "str - 唯一标识",
        "hypothesis": "str - 研究假设",
        "code_path": "str - 代码文件路径",
        "result_metrics": {
            "sharpe_ratio": "float",
            "max_drawdown": "float",
            "returns": "float",
            "ir": "float - 信息比率"
        },
        "status": "str - running|completed|failed",
        "error_message": "str - 错误信息(如有)",
        "created_at": "datetime - 创建时间"
    }
}