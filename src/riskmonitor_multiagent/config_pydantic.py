"""Pydantic Settings 配置管理（新）.

使用 pydantic-settings 统一管理配置，提供类型安全、环境变量支持和验证。

兼容性：
- 保留原有的 config.py 中的函数作为兼容层
- 新代码可以直接使用 Config 类

使用示例：
```python
from riskmonitor_multiagent.config_pydantic import config

# 访问配置
print(config.llm_model)
print(config.mysql_host)
```
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_dotenv() -> Optional[str]:
    """向上查找 .env 文件."""
    cur = Path(__file__).resolve()
    for parent in [cur] + list(cur.parents):
        dotenv = parent / ".env"
        if dotenv.is_file():
            return str(dotenv)
    return None


class Config(BaseSettings):
    """统一配置类.

    配置来源优先级（从高到低）：
    1. 环境变量
    2. .env 文件
    3. 默认值
    """

    model_config = SettingsConfigDict(
        env_file=_find_dotenv(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM 配置
    llm_model: str = Field(default="qwen3-8b", description="LLM 模型名称")
    llm_base_url: str = Field(default="https://api.openai.com/v1", description="LLM API 基础 URL")
    llm_api_key: str = Field(default="", description="LLM API Key")
    llm_resolve_ip: Optional[str] = Field(default=None, description="LLM API 固定 IP")
    llm_http_referer: Optional[str] = Field(default=None, description="LLM HTTP Referer")
    llm_app_title: Optional[str] = Field(default=None, description="LLM App Title")

    # MySQL 配置
    mysql_host: str = Field(default="localhost", description="MySQL 主机")
    mysql_port: int = Field(default=3306, description="MySQL 端口")
    mysql_user: str = Field(default="root", description="MySQL 用户")
    mysql_password: str = Field(default="", description="MySQL 密码")
    mysql_db: str = Field(default="risk_monitor", description="MySQL 数据库名")

    # Redis 配置
    redis_host: str = Field(default="localhost", description="Redis 主机")
    redis_port: int = Field(default=6379, description="Redis 端口")
    redis_db: int = Field(default=0, description="Redis 数据库号")
    redis_password: Optional[str] = Field(default=None, description="Redis 密码")

    # HITL 配置
    hitl_redis_stream: str = Field(default="risk_monitor:approval", description="HITL Redis Stream 名称")
    hitl_auto_approve: bool = Field(default=False, description="是否自动审批")

    @property
    def mysql_dsn(self) -> str:
        """MySQL DSN."""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}"
            "?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        """Redis URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


# 全局配置单例
_config: Optional[Config] = None


def get_config() -> Config:
    """获取全局配置单例."""
    global _config
    if _config is None:
        _config = Config()
    return _config


# 便捷访问
config = get_config()
