"""配置层.

集中管理环境变量读取与默认值.
"""

from __future__ import annotations

import os
from pathlib import Path


def _try_load_repo_dotenv() -> None:
    """
    尝试从仓库根目录加载 .env.
    用于在非 server.py 入口场景下也能读取到本地 .env 配置.
    """
    try:
        from dotenv import load_dotenv  # pylint: disable=import-outside-toplevel
    except Exception:  # pylint: disable=broad-except
        return
    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(dotenv_path=repo_root / ".env")


def get_mysql_host() -> str:
    """获取 MySQL 主机地址, 默认为 localhost."""
    value = os.getenv("MYSQL_HOST")
    if value is None or not value.strip():
        _try_load_repo_dotenv()
        value = os.getenv("MYSQL_HOST")
    return (value or "localhost").strip() or "localhost"


def get_mysql_port() -> int:
    """获取 MySQL 端口, 默认为 3306."""
    value = os.getenv("MYSQL_PORT")
    if value is None or not value.strip():
        _try_load_repo_dotenv()
        value = os.getenv("MYSQL_PORT")
    return int((value or "3306").strip() or "3306")


def get_mysql_database() -> str:
    """获取 MySQL 数据库名, 默认为 riskmonitor."""
    value = os.getenv("MYSQL_DATABASE")
    if value is None or not value.strip():
        _try_load_repo_dotenv()
        value = os.getenv("MYSQL_DATABASE")
    return (value or "riskmonitor").strip() or "riskmonitor"


def get_mysql_user() -> str:
    """获取 MySQL 用户名, 默认为 admin."""
    value = os.getenv("MYSQL_USER")
    if value is None or not value.strip():
        _try_load_repo_dotenv()
        value = os.getenv("MYSQL_USER")
    return (value or "admin").strip() or "admin"


def get_mysql_password() -> str:
    """
    获取 MySQL 密码.
    必须设置 MYSQL_PASSWORD 环境变量.

    异常:
        ValueError: 如果未设置 MYSQL_PASSWORD.
    """
    password = os.getenv("MYSQL_PASSWORD")
    if password is None or not password.strip():
        _try_load_repo_dotenv()
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


def get_llm_api_key() -> str:
    """
    获取 LLM API Key.
    必须设置 LLM_API_KEY 环境变量.
    当前项目默认使用火山引擎 Coding API 的 Key.

    异常:
        ValueError: 如果未设置 LLM_API_KEY.
    """
    api_key = os.getenv("LLM_API_KEY")
    if api_key is None or not api_key.strip():
        _try_load_repo_dotenv()
        api_key = os.getenv("LLM_API_KEY")
    if api_key is None or not api_key.strip():
        raise ValueError("LLM_API_KEY is not set")
    return api_key.strip()


def get_llm_base_url() -> str:
    """获取 LLM 主机 Base URL. 当前项目默认使用火山引擎 Coding API."""
    value = os.getenv("LLM_BASE_URL")
    if value is None or not value.strip():
        _try_load_repo_dotenv()
        value = os.getenv("LLM_BASE_URL")
    value = (value or "").strip().rstrip("/")
    if not value:
        raise ValueError("LLM_BASE_URL is not set")
    return value


def get_llm_model() -> str:
    """获取 LLM 模型 ID;优先读 LLM_MODEL,默认 ark-code-latest."""
    value = os.getenv("LLM_MODEL")
    if value is None or not value.strip():
        _try_load_repo_dotenv()
        value = os.getenv("LLM_MODEL")
    if value and value.strip():
        return value.strip()
    return "ark-code-latest"


def get_llm_http_referer() -> str:
    """获取 LLM HTTP-Referer(可选)."""
    value = os.getenv("LLM_HTTP_REFERER")
    if value is None:
        _try_load_repo_dotenv()
        value = os.getenv("LLM_HTTP_REFERER")
    return (value or "").strip()


def get_llm_app_title() -> str:
    """获取 LLM X-Title(可选)."""
    value = os.getenv("LLM_APP_TITLE")
    if value is None:
        _try_load_repo_dotenv()
        value = os.getenv("LLM_APP_TITLE")
    return (value or "").strip()


def get_llm_resolve_ip() -> str:
    """
    获取 LLM API 的固定 IP 地址(可选).

    用于绕过 DNS 解析问题(如 Cloudflare 某些节点故障时).
    格式: IP 地址,例如 "104.26.9.9"
    """
    value = os.getenv("LLM_RESOLVE_IP")
    if value is None:
        _try_load_repo_dotenv()
        value = os.getenv("LLM_RESOLVE_IP")
    return (value or "").strip()


def get_knowledge_db_path() -> str:
    """获取知识库 SQLite 文件路径, 默认为 repo_root/data/knowledge.sqlite."""
    value = os.getenv("KNOWLEDGE_DB_PATH")
    if value is None or not value.strip():
        _try_load_repo_dotenv()
        value = os.getenv("KNOWLEDGE_DB_PATH")
    if value is not None and value.strip():
        return value.strip()
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "data" / "knowledge.sqlite")


def get_chroma_host() -> str:
    value = os.getenv("CHROMA_HOST")
    if value is None:
        _try_load_repo_dotenv()
        value = os.getenv("CHROMA_HOST")
    return (value or "localhost").strip() or "localhost"


def get_chroma_port() -> int:
    value = os.getenv("CHROMA_PORT")
    if value is None:
        _try_load_repo_dotenv()
        value = os.getenv("CHROMA_PORT")
    return int((value or "8001").strip() or "8001")


def get_chroma_collection() -> str:
    value = os.getenv("CHROMA_COLLECTION")
    if value is None:
        _try_load_repo_dotenv()
        value = os.getenv("CHROMA_COLLECTION")
    return (value or "riskmonitor-alerts").strip() or "riskmonitor-alerts"


def get_chroma_memory_collection() -> str:
    value = os.getenv("CHROMA_MEMORY_COLLECTION")
    if value is None:
        _try_load_repo_dotenv()
        value = os.getenv("CHROMA_MEMORY_COLLECTION")
    return (value or "riskmonitor-memory").strip() or "riskmonitor-memory"


def get_chroma_persist_dir() -> str:
    value = os.getenv("CHROMA_PERSIST_DIR")
    if value is None:
        _try_load_repo_dotenv()
        value = os.getenv("CHROMA_PERSIST_DIR")
    return (value or "").strip()
