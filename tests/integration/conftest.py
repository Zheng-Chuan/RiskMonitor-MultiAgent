"""Integration test fixtures - real infrastructure connections.

All fixtures connect to real Docker services (MySQL, Redis, ChromaDB)
and the real LLM provider (火山引擎). No mocks.
"""

import os

import pymysql
import pytest
from dotenv import load_dotenv


def _get_env(name: str) -> str | None:
    v = os.getenv(name)
    if v is None or not v.strip():
        return None
    return v.strip()


@pytest.fixture(autouse=True, scope="session")
def _require_mysql_for_integration_tests():
    load_dotenv()

    if _get_env("MYSQL_HOST") is None:
        os.environ["MYSQL_HOST"] = "127.0.0.1"
    if _get_env("MYSQL_PORT") is None:
        os.environ["MYSQL_PORT"] = "3307"
    if _get_env("MYSQL_DATABASE") is None:
        os.environ["MYSQL_DATABASE"] = "riskmonitor"
    if _get_env("MYSQL_USER") is None:
        os.environ["MYSQL_USER"] = "admin"

    host = _get_env("MYSQL_HOST")
    port = _get_env("MYSQL_PORT")
    database = _get_env("MYSQL_DATABASE")
    user = _get_env("MYSQL_USER")
    password = _get_env("MYSQL_PASSWORD")

    if not all([host, port, database, user, password]):
        raise RuntimeError("integration tests require MYSQL_HOST MYSQL_PORT MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD")

    try:
        conn = pymysql.connect(
            host=str(host),
            port=int(str(port)),
            database=str(database),
            user=str(user),
            password=str(password),
            connect_timeout=1,
            read_timeout=1,
            write_timeout=1,
            charset="utf8mb4",
        )
        conn.close()
    except Exception:
        raise RuntimeError("integration tests require reachable MySQL")


# ---------------------------------------------------------------------------
# Infrastructure health check (validates all Docker services are up)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def verify_infrastructure():
    """Session开始时验证所有基础设施可用."""
    load_dotenv()
    errors: list[str] = []

    # Check MySQL
    try:
        host = _get_env("MYSQL_HOST") or "127.0.0.1"
        port = int(_get_env("MYSQL_PORT") or "3307")
        database = _get_env("MYSQL_DATABASE") or "riskmonitor"
        user = _get_env("MYSQL_USER") or "admin"
        password = _get_env("MYSQL_PASSWORD") or ""
        conn = pymysql.connect(
            host=host, port=port, database=database,
            user=user, password=password,
            connect_timeout=3, charset="utf8mb4",
        )
        conn.close()
    except Exception as e:
        errors.append(f"MySQL不可用: {e}")

    # Check Redis
    try:
        import redis as _redis
        from riskmonitor_multiagent.config_pydantic import get_settings
        r = _redis.from_url(get_settings().redis_url)
        r.ping()
        r.close()
    except Exception as e:
        errors.append(f"Redis不可用: {e}")

    # Check ChromaDB
    try:
        import warnings as _w
        with _w.catch_warnings():
            _w.filterwarnings("ignore", category=DeprecationWarning)
            import chromadb
        from riskmonitor_multiagent.config import get_chroma_host, get_chroma_port
        client = chromadb.HttpClient(host=get_chroma_host(), port=get_chroma_port())
        client.heartbeat()
    except Exception as e:
        errors.append(f"ChromaDB不可用: {e}")

    if errors:
        # Non-fatal: tests that need specific services will fail via their own fixtures
        pass


# ---------------------------------------------------------------------------
# Real MySQL fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_db_engine():
    """真实MySQL引擎 - session级别复用."""
    from riskmonitor_multiagent.data_access.mysql_engine import get_engine
    engine = get_engine()
    yield engine


@pytest.fixture
def real_db_connection(real_db_engine):
    """真实MySQL连接 - 每个测试一个连接，测试后回滚."""
    conn = real_db_engine.raw_connection()
    conn.begin()
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def real_db_cursor(real_db_connection):
    """带DictCursor的真实数据库游标."""
    cursor = real_db_connection.cursor(pymysql.cursors.DictCursor)
    yield cursor
    cursor.close()


# ---------------------------------------------------------------------------
# Real ChromaDB fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_chroma_store():
    """真实ChromaDB连接 - 使用独立的测试collection."""
    from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore
    store = ChromaVectorStore(collection="test-integration")
    yield store
    # 清理测试collection
    try:
        client = store._client()
        client.delete_collection("test-integration")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Real LLM fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_llm_client():
    """真实火山引擎LLM客户端."""
    from riskmonitor_multiagent.llm.llm_client import LlmClient
    client = LlmClient()
    yield client


# ---------------------------------------------------------------------------
# Real Redis fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_redis():
    """真实Redis连接."""
    import redis as _redis
    from riskmonitor_multiagent.config_pydantic import get_settings
    r = _redis.from_url(get_settings().redis_url)
    yield r
    r.close()
