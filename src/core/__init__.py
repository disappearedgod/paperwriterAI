"""
FARS Core Module
核心配置和数据库
"""

from .config import (
    CONFIG,
    Workspace,
    PROJECT_ROOT,
    WORKSPACE_DIR,
    PAPERS_DIR,
    REPORTS_DIR,
    DATABASE_SCHEMA
)

from .database import (
    get_connection,
    init_database
)

__all__ = [
    "CONFIG",
    "Workspace",
    "PROJECT_ROOT",
    "WORKSPACE_DIR",
    "PAPERS_DIR",
    "REPORTS_DIR",
    "DATABASE_SCHEMA",
    "get_connection",
    "init_database"
]