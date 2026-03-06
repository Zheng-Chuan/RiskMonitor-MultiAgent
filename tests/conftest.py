import asyncio
import gc


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
