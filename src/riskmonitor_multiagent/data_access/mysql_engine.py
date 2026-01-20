"""MySQL 数据访问.

基于 SQLAlchemy Engine 提供连接池与连接超时配置.

说明:
- 这里优先使用成熟框架 SQLAlchemy 来管理连接池.
- 业务层不直接依赖 pymysql.connect.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL

from riskmonitor_multiagent import config


def _build_mysql_url() -> URL:
    """
    构建 MySQL 连接 URL.
    使用环境变量中的配置 (host, port, user, password, db).
    """
    # 使用 SQLAlchemy URL.create 以正确处理用户名与密码的转义.
    return URL.create(
        drivername="mysql+pymysql",
        username=config.get_mysql_user(),
        password=config.get_mysql_password(),
        host=config.get_mysql_host(),
        port=config.get_mysql_port(),
        database=config.get_mysql_database(),
        query={"charset": "utf8mb4"},
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """
    获取 SQLAlchemy Engine 单例.
    Engine 内部维护了连接池.
    配置了 connect_timeout, read_timeout, write_timeout.
    """
    # 单例 engine, 由 SQLAlchemy 负责连接池.
    # pool_pre_ping: 避免陈旧连接.
    connect_args = {
        "connect_timeout": config.get_mysql_connect_timeout_s(),
        "read_timeout": config.get_mysql_read_timeout_s(),
        "write_timeout": config.get_mysql_write_timeout_s(),
    }

    return create_engine(
        _build_mysql_url(),
        pool_pre_ping=True,
        pool_recycle=config.get_mysql_pool_recycle_s(),
        pool_size=config.get_mysql_pool_size(),
        max_overflow=config.get_mysql_max_overflow(),
        connect_args=connect_args,
    )
