import asyncio
import gc
import os

import pytest
import pytest_asyncio


@pytest.fixture(autouse=True, scope="function")
def reset_memory_store():
    """在每个测试前清理 MemoryStore 的 Redis 数据."""
    # 设置测试环境变量
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

    # 清理全局 MemoryStore 实例,强制重新创建
    try:
        from riskmonitor_multiagent.memory.memory_store import _MEMORY_STORE, MemoryStore
        import riskmonitor_multiagent.memory.memory_store as ms_module

        if _MEMORY_STORE is not None:
            # 尝试关闭现有连接
            try:
                import asyncio

                loop = asyncio.new_event_loop()
                loop.run_until_complete(_MEMORY_STORE.close())
                loop.close()
            except Exception:
                pass
            # 重置全局变量
            ms_module._MEMORY_STORE = None
    except Exception:
        pass

    yield

    # 测试结束后清理 Redis
    try:
        from riskmonitor_multiagent.memory.memory_store import _MEMORY_STORE

        if _MEMORY_STORE is not None:
            import asyncio

            async def _clear():
                try:
                    r = await _MEMORY_STORE._ensure_connected()
                    await r.flushdb()
                except Exception:
                    pass

            loop = asyncio.new_event_loop()
            loop.run_until_complete(_clear())
            loop.close()
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus):
    try:
        from riskmonitor_multiagent.data_access.mysql_engine import dispose_engine

        dispose_engine()
    except Exception:
        pass

    try:
        from riskmonitor_multiagent.memory.stores import dispose_all_sql_memory_engines

        dispose_all_sql_memory_engines()
    except Exception:
        pass

    try:
        for obj in gc.get_objects():
            try:
                if isinstance(obj, asyncio.AbstractEventLoop) and not obj.is_closed():
                    obj.close()
            except Exception:
                pass
    except Exception:
        pass
