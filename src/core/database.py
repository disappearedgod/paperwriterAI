"""
FARS 数据库初始化脚本
初始化SQLite数据库和表结构
"""

import sqlite3
import os
from pathlib import Path

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "workspace" / "fars.db"


def get_connection():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    """创建所有表"""
    conn = get_connection()
    cursor = conn.cursor()

    # ========== 论文表 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            paper_id TEXT PRIMARY KEY,
            source VARCHAR(20) NOT NULL,
            external_id VARCHAR(100),
            title TEXT NOT NULL,
            authors TEXT,
            abstract TEXT,
            year INTEGER,
            categories TEXT,
            keywords TEXT,
            pdf_url TEXT,
            pdf_path TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            reading_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ========== Paper Status 枚举表 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_status (
            status VARCHAR(20) PRIMARY KEY,
            description TEXT
        )
    """)

    # 插入枚举值
    cursor.executemany(
        "INSERT OR IGNORE INTO paper_status VALUES (?, ?)",
        [
            ('pending', '待处理'),
            ('downloaded', '已下载'),
            ('analyzed', '已分析'),
            ('cited', '已引用'),
        ]
    )

    # ========== Alpha因子表 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alpha_factors (
            factor_id TEXT PRIMARY KEY,
            source_paper_id TEXT,
            factor_name TEXT NOT NULL,
            description TEXT,
            trading_logic TEXT NOT NULL,
            parameters TEXT,
            expected_direction VARCHAR(20),
            risk_factors TEXT,
            market_universe VARCHAR(50),
            time_horizon VARCHAR(20),
            related_factors TEXT,
            status VARCHAR(20) DEFAULT 'generated',
            validation_results TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ========== 实验表 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            experiment_id TEXT PRIMARY KEY,
            hypothesis_id TEXT NOT NULL,
            experiment_name TEXT NOT NULL,
            description TEXT,
            plan TEXT NOT NULL,
            status VARCHAR(20) DEFAULT 'planned',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ========== 实验运行记录表 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiment_runs (
            run_id TEXT PRIMARY KEY,
            experiment_id TEXT NOT NULL,
            run_number INTEGER NOT NULL,
            parameters TEXT,
            generated_code TEXT,
            execution_log TEXT,
            result TEXT,
            judgment TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            healing_attempts INTEGER DEFAULT 0,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT
        )
    """)

    # ========== 研究报告表 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY,
            run_id TEXT,
            report_type VARCHAR(20) DEFAULT 'paper',
            title TEXT,
            abstract TEXT,
            content TEXT,
            figures TEXT,
            tables_data TEXT,
            references_bib TEXT,
            status VARCHAR(20) DEFAULT 'draft',
            feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ========== 系统配置表 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ========== 操作日志表 ==========
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name VARCHAR(50),
            operation VARCHAR(100),
            input_data TEXT,
            output_data TEXT,
            status VARCHAR(20),
            error_message TEXT,
            duration_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ========== 创建索引 ==========
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source)",
        "CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year)",
        "CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status)",
        "CREATE INDEX IF NOT EXISTS idx_factors_status ON alpha_factors(status)",
        "CREATE INDEX IF NOT EXISTS idx_factors_universe ON alpha_factors(market_universe)",
        "CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status)",
        "CREATE INDEX IF NOT EXISTS idx_experiments_hypothesis ON experiments(hypothesis_id)",
        "CREATE INDEX IF NOT EXISTS idx_runs_experiment ON experiment_runs(experiment_id)",
        "CREATE INDEX IF NOT EXISTS idx_runs_status ON experiment_runs(status)",
        "CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)",
        "CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type)",
        "CREATE INDEX IF NOT EXISTS idx_logs_agent ON operation_logs(agent_name)",
        "CREATE INDEX IF NOT EXISTS idx_logs_created ON operation_logs(created_at)",
    ]

    for index_sql in indexes:
        cursor.execute(index_sql)

    conn.commit()
    conn.close()

    print(f"✓ 数据库初始化完成: {DB_PATH}")
    return DB_PATH


def seed_sample_data():
    """插入示例数据（可选）"""
    conn = get_connection()
    cursor = conn.cursor()

    # 检查是否已有数据
    cursor.execute("SELECT COUNT(*) FROM papers")
    if cursor.fetchone()[0] > 0:
        print("✓ 示例数据已存在，跳过播种")
        conn.close()
        return

    # 插入示例论文
    sample_papers = [
        {
            "paper_id": "arxiv_2409.06289",
            "source": "arxiv",
            "external_id": "2409.06289",
            "title": "Automate Strategy Finding with LLM in Quant Investment",
            "authors": '["Zhou, Tao", "Wang, Wei", "Chen, Yi"]',
            "abstract": "We present a novel framework that uses Large Language Models to automate the quantitative investment strategy discovery process...",
            "year": 2024,
            "categories": '["q-fin.TR", "cs.AI"]',
            "keywords": '["quantitative trading", "LLM", "strategy discovery"]',
            "status": "analyzed"
        },
        {
            "paper_id": "arxiv_2503.24047",
            "source": "arxiv",
            "external_id": "2503.24047",
            "title": "Towards Scientific Intelligence: A Survey of LLM-based Scientific Agents",
            "authors": '["Zhang, San", "Li, Si", "Wang, Wu"]',
            "abstract": "This survey provides a comprehensive review of LLM-based scientific agents...",
            "year": 2025,
            "categories": '["cs.AI", "cs.CL"]',
            "keywords": '["LLM agents", "scientific discovery", "automation"]',
            "status": "pending"
        },
    ]

    cursor.executemany("""
        INSERT INTO papers (paper_id, source, external_id, title, authors,
                           abstract, year, categories, keywords, status)
        VALUES (:paper_id, :source, :external_id, :title, :authors,
                :abstract, :year, :categories, :keywords, :status)
    """, sample_papers)

    # 插入系统配置
    configs = [
        ("default_llm_provider", "openai", "默认LLM提供商"),
        ("default_llm_model", "gpt-4o", "默认LLM模型"),
        ("max_retries", "3", "代码执行最大重试次数"),
        ("backtest_initial_cash", "1000000", "回测初始资金"),
        ("evaluation_sharpe_threshold", "1.5", "夏普比率阈值"),
        ("evaluation_ic_threshold", "0.02", "IC阈值"),
    ]

    cursor.executemany(
        "INSERT OR IGNORE INTO system_config VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
        configs
    )

    conn.commit()
    conn.close()
    print("✓ 示例数据播种完成")


def init_database(seed: bool = True):
    """初始化数据库"""
    print("=" * 50)
    print("FARS 数据库初始化")
    print("=" * 50)

    db_path = create_tables()

    if seed:
        seed_sample_data()

    print("=" * 50)
    print(f"数据库路径: {db_path}")
    print("=" * 50)

    return db_path


if __name__ == "__main__":
    init_database(seed=True)