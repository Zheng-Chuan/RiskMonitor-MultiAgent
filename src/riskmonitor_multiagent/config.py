"""配置层.

集中管理环境变量读取与默认值.
"""

from __future__ import annotations

import os


def get_mysql_host() -> str:
    """获取 MySQL 主机地址, 默认为 localhost."""
    return os.getenv("MYSQL_HOST", "localhost").strip() or "localhost"


def get_mysql_port() -> int:
    """获取 MySQL 端口, 默认为 3306."""
    return int(os.getenv("MYSQL_PORT", "3306"))


def get_mysql_database() -> str:
    """获取 MySQL 数据库名, 默认为 riskmonitor."""
    return os.getenv("MYSQL_DATABASE", "riskmonitor").strip() or "riskmonitor"


def get_mysql_user() -> str:
    """获取 MySQL 用户名, 默认为 admin."""
    return os.getenv("MYSQL_USER", "admin").strip() or "admin"


def get_mysql_password() -> str:
    """
    获取 MySQL 密码.
    必须设置 MYSQL_PASSWORD 环境变量.

    异常:
        ValueError: 如果未设置 MYSQL_PASSWORD.
    """
    password = os.getenv("MYSQL_PASSWORD")
    if password is None or not password.strip():
        raise ValueError("MYSQL_PASSWORD is not set")
    return password.strip()


def get_mysql_connect_timeout_s() -> float:
    """获取数据库连接超时时间(秒), 默认为 3秒."""
    return float(os.getenv("MYSQL_CONNECT_TIMEOUT", "3"))


def get_mysql_read_timeout_s() -> float:
    """获取数据库读取超时时间(秒), 默认为 5秒."""
    return float(os.getenv("MYSQL_READ_TIMEOUT", "5"))


def get_mysql_write_timeout_s() -> float:
    """获取数据库写入超时时间(秒), 默认为 5秒."""
    return float(os.getenv("MYSQL_WRITE_TIMEOUT", "5"))


def get_mysql_pool_size() -> int:
    """获取数据库连接池大小, 默认为 5."""
    return int(os.getenv("MYSQL_POOL_SIZE", "5"))


def get_mysql_max_overflow() -> int:
    """获取数据库连接池最大溢出数, 默认为 10."""
    return int(os.getenv("MYSQL_POOL_MAX_OVERFLOW", "10"))


def get_mysql_pool_recycle_s() -> int:
    """获取数据库连接回收时间(秒), 默认为 1800秒 (30分钟)."""
    return int(os.getenv("MYSQL_POOL_RECYCLE", "1800"))
