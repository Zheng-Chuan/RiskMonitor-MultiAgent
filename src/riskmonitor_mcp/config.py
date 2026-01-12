"""配置层.

集中管理环境变量读取与默认值.
"""

from __future__ import annotations

import os


def get_mysql_host() -> str:
    return os.getenv("MYSQL_HOST", "localhost").strip() or "localhost"


def get_mysql_port() -> int:
    return int(os.getenv("MYSQL_PORT", "3306"))


def get_mysql_database() -> str:
    return os.getenv("MYSQL_DATABASE", "riskmonitor").strip() or "riskmonitor"


def get_mysql_user() -> str:
    return os.getenv("MYSQL_USER", "admin").strip() or "admin"


def get_mysql_password() -> str:
    password = os.getenv("MYSQL_PASSWORD")
    if password is None or not password.strip():
        raise ValueError("MYSQL_PASSWORD is not set")
    return password.strip()


def get_mysql_connect_timeout_s() -> float:
    return float(os.getenv("MYSQL_CONNECT_TIMEOUT", "3"))


def get_mysql_read_timeout_s() -> float:
    return float(os.getenv("MYSQL_READ_TIMEOUT", "5"))


def get_mysql_write_timeout_s() -> float:
    return float(os.getenv("MYSQL_WRITE_TIMEOUT", "5"))


def get_mysql_pool_size() -> int:
    return int(os.getenv("MYSQL_POOL_SIZE", "5"))


def get_mysql_max_overflow() -> int:
    return int(os.getenv("MYSQL_POOL_MAX_OVERFLOW", "10"))


def get_mysql_pool_recycle_s() -> int:
    return int(os.getenv("MYSQL_POOL_RECYCLE", "1800"))
