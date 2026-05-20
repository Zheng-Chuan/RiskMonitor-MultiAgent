"""Pydantic Settings 配置管理(统一入口).

使用 pydantic-settings 统一管理配置, 提供类型安全、环境变量支持和 .env 文件加载.

兼容性:
- ``config.py`` 现在作为薄包装层, 委托到这里的 ``Settings``.
- 新代码可直接使用 ``settings`` 单例或 ``get_settings()`` 工厂.

使用示例:
```python
from riskmonitor_multiagent.config_pydantic import settings

print(settings.llm_model)
print(settings.mysql_host)
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_dotenv() -> Optional[str]:
    """向上查找 .env 文件.

    保持与原 ``config.py._try_load_repo_dotenv`` 一致的解析路径
    (仓库根目录 = ``Path(__file__).resolve().parents[2]``).
    """
    cur = Path(__file__).resolve()
    for parent in [cur] + list(cur.parents):
        dotenv = parent / ".env"
        if dotenv.is_file():
            return str(dotenv)
    return None


class Settings(BaseSettings):
    """统一配置类.

    配置来源优先级 (从高到低):
    1. 环境变量
    2. .env 文件 (启动时加载一次)
    3. 默认值
    """

    model_config = SettingsConfigDict(
        env_file=_find_dotenv(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM 配置 ----
    llm_api_key: str = Field(default="", description="LLM API Key")
    llm_base_url: str = Field(default="", description="LLM API 基础 URL")
    llm_model: str = Field(default="ark-code-latest", description="LLM 模型名称")
    llm_http_referer: str = Field(default="", description="LLM HTTP-Referer (可选)")
    llm_app_title: str = Field(default="", description="LLM X-Title (可选)")
    llm_resolve_ip: str = Field(default="", description="LLM API 固定 IP (可选)")

    # ---- MySQL 配置 ----
    mysql_host: str = Field(default="localhost", description="MySQL 主机")
    mysql_port: int = Field(default=3306, description="MySQL 端口")
    mysql_database: str = Field(default="riskmonitor", description="MySQL 数据库名")
    mysql_user: str = Field(default="admin", description="MySQL 用户")
    mysql_password: str = Field(default="", description="MySQL 密码")
    mysql_connect_timeout: float = Field(default=3.0, description="MySQL 连接超时(秒)")
    mysql_read_timeout: float = Field(default=5.0, description="MySQL 读取超时(秒)")
    mysql_write_timeout: float = Field(default=5.0, description="MySQL 写入超时(秒)")
    mysql_pool_size: int = Field(default=5, description="MySQL 连接池大小")
    mysql_pool_max_overflow: int = Field(default=10, description="MySQL 连接池最大溢出数")
    mysql_pool_recycle: int = Field(default=1800, description="MySQL 连接回收时间(秒)")

    # ---- Redis 配置 ----
    redis_host: str = Field(default="localhost", description="Redis 主机")
    redis_port: int = Field(default=6379, description="Redis 端口")
    redis_db: int = Field(default=0, description="Redis 数据库号")
    redis_password: Optional[str] = Field(default=None, description="Redis 密码")

    # ---- HITL 配置 ----
    hitl_redis_stream: str = Field(default="risk_monitor:approval", description="HITL Redis Stream 名称")
    hitl_auto_approve: bool = Field(default=False, description="是否自动审批")

    # ---- Chroma 配置 ----
    chroma_host: str = Field(default="localhost", description="Chroma 主机")
    chroma_port: int = Field(default=8001, description="Chroma 端口")
    chroma_collection: str = Field(default="riskmonitor-alerts", description="Chroma 默认集合名")
    chroma_memory_collection: str = Field(default="riskmonitor-memory", description="Chroma 记忆集合名")
    chroma_persist_dir: str = Field(default="", description="Chroma 持久化目录(为空则使用 HTTP 客户端)")

    # ---- Knowledge 配置 ----
    knowledge_db_path: str = Field(default="", description="知识库 SQLite 路径(为空使用默认)")

    # ---- 派生属性 ----
    @property
    def mysql_dsn(self) -> str:
        """MySQL DSN."""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        """Redis URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


# 兼容旧名称
Config = Settings


def get_settings() -> Settings:
    """获取一个新的 ``Settings`` 实例.

    每次调用都会重新读取环境变量, 便于测试场景下使用
    ``monkeypatch.setenv`` 动态修改配置.
    """
    return Settings()


# 全局单例 (新代码推荐使用)
settings: Settings = Settings()

# 历史别名: 旧版本曾导出 ``config``, 保留以避免破坏可能存在的引用
config = settings


def get_config() -> Settings:
    """旧版工厂函数别名, 等价于 ``get_settings()``."""
    return get_settings()
