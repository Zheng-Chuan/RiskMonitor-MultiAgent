"""向后兼容的配置 getter 包装层.

此模块保留历史 ``get_*`` 函数签名, 并将所有读取委托到
``riskmonitor_multiagent.config_pydantic.Settings``.

注意:
- 不再直接读取 ``os.getenv``, 也不再每次调用都加载 ``.env``.
- ``.env`` 的解析与加载由 Pydantic Settings 在实例化时完成.
- 每个 getter 通过 ``get_settings()`` 创建新的 ``Settings`` 实例,
  保证测试中使用 ``monkeypatch.setenv`` 修改环境变量后也能立即生效.
- 历史上若 getter 含有额外校验或派生逻辑 (例如校验必填、剥离尾部斜杠、
  根据仓库目录推导默认路径), 这些逻辑保留在本兼容层内.
"""

from __future__ import annotations

from pathlib import Path

from riskmonitor_multiagent.config_pydantic import Settings, get_settings, settings


# ---- MySQL ----
def get_mysql_host() -> str:
    """获取 MySQL 主机地址, 默认为 localhost."""
    return get_settings().mysql_host or "localhost"


def get_mysql_port() -> int:
    """获取 MySQL 端口, 默认为 3306."""
    return int(get_settings().mysql_port or 3306)


def get_mysql_database() -> str:
    """获取 MySQL 数据库名, 默认为 riskmonitor."""
    return get_settings().mysql_database or "riskmonitor"


def get_mysql_user() -> str:
    """获取 MySQL 用户名, 默认为 admin."""
    return get_settings().mysql_user or "admin"


def get_mysql_password() -> str:
    """
    获取 MySQL 密码.
    必须设置 MYSQL_PASSWORD 环境变量.

    异常:
        ValueError: 如果未设置 MYSQL_PASSWORD.
    """
    password = (get_settings().mysql_password or "").strip()
    if not password:
        raise ValueError("MYSQL_PASSWORD is not set")
    return password


def get_mysql_connect_timeout_s() -> float:
    """获取数据库连接超时时间(秒), 默认为 3秒."""
    return float(get_settings().mysql_connect_timeout)


def get_mysql_read_timeout_s() -> float:
    """获取数据库读取超时时间(秒), 默认为 5秒."""
    return float(get_settings().mysql_read_timeout)


def get_mysql_write_timeout_s() -> float:
    """获取数据库写入超时时间(秒), 默认为 5秒."""
    return float(get_settings().mysql_write_timeout)


def get_mysql_pool_size() -> int:
    """获取数据库连接池大小, 默认为 5."""
    return int(get_settings().mysql_pool_size)


def get_mysql_max_overflow() -> int:
    """获取数据库连接池最大溢出数, 默认为 10."""
    return int(get_settings().mysql_pool_max_overflow)


def get_mysql_pool_recycle_s() -> int:
    """获取数据库连接回收时间(秒), 默认为 1800秒 (30分钟)."""
    return int(get_settings().mysql_pool_recycle)


# ---- LLM ----
def get_llm_api_key() -> str:
    """
    获取 LLM API Key.
    必须设置 LLM_API_KEY 环境变量.
    当前项目默认使用火山引擎 Coding API 的 Key.

    异常:
        ValueError: 如果未设置 LLM_API_KEY.
    """
    api_key = (get_settings().llm_api_key or "").strip()
    if not api_key:
        raise ValueError("LLM_API_KEY is not set")
    return api_key


def get_llm_base_url() -> str:
    """获取 LLM 主机 Base URL. 当前项目默认使用火山引擎 Coding API."""
    value = (get_settings().llm_base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("LLM_BASE_URL is not set")
    return value


def get_llm_model() -> str:
    """获取 LLM 模型 ID;优先读 LLM_MODEL,默认 ark-code-latest."""
    value = (get_settings().llm_model or "").strip()
    return value or "ark-code-latest"


def get_llm_http_referer() -> str:
    """获取 LLM HTTP-Referer(可选)."""
    return (get_settings().llm_http_referer or "").strip()


def get_llm_app_title() -> str:
    """获取 LLM X-Title(可选)."""
    return (get_settings().llm_app_title or "").strip()


def get_llm_resolve_ip() -> str:
    """
    获取 LLM API 的固定 IP 地址(可选).

    用于绕过 DNS 解析问题(如 Cloudflare 某些节点故障时).
    格式: IP 地址,例如 "104.26.9.9"
    """
    return (get_settings().llm_resolve_ip or "").strip()


# ---- Knowledge ----
def get_knowledge_db_path() -> str:
    """获取知识库 SQLite 文件路径, 默认为 repo_root/data/knowledge.sqlite."""
    value = (get_settings().knowledge_db_path or "").strip()
    if value:
        return value
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "data" / "knowledge.sqlite")


# ---- Chroma ----
def get_chroma_host() -> str:
    return (get_settings().chroma_host or "").strip() or "localhost"


def get_chroma_port() -> int:
    return int(get_settings().chroma_port or 8001)


def get_chroma_collection() -> str:
    return (get_settings().chroma_collection or "").strip() or "riskmonitor-alerts"


def get_chroma_memory_collection() -> str:
    return (get_settings().chroma_memory_collection or "").strip() or "riskmonitor-memory"


def get_chroma_persist_dir() -> str:
    return (get_settings().chroma_persist_dir or "").strip()


__all__ = [
    "Settings",
    "get_settings",
    "settings",
    "get_mysql_host",
    "get_mysql_port",
    "get_mysql_database",
    "get_mysql_user",
    "get_mysql_password",
    "get_mysql_connect_timeout_s",
    "get_mysql_read_timeout_s",
    "get_mysql_write_timeout_s",
    "get_mysql_pool_size",
    "get_mysql_max_overflow",
    "get_mysql_pool_recycle_s",
    "get_llm_api_key",
    "get_llm_base_url",
    "get_llm_model",
    "get_llm_http_referer",
    "get_llm_app_title",
    "get_llm_resolve_ip",
    "get_knowledge_db_path",
    "get_chroma_host",
    "get_chroma_port",
    "get_chroma_collection",
    "get_chroma_memory_collection",
    "get_chroma_persist_dir",
]
