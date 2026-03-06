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
