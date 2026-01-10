#!/usr/bin/env python3
"""
RiskMonitor-MCP 服务端
用于金融衍生品风险管理的 MCP 服务
"""

import os
import logging
import uuid
import asyncio
import time
from typing import Optional, Any
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from mcp.server import FastMCP
from mcp.server.fastmcp import Context
import pymysql
import httpx

# 加载环境变量
# 从项目目录加载 .env, 不依赖当前工作目录
_repo_root = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=_repo_root / ".env")


class RequestIdFilter(logging.Filter):
    # 确保每条日志都有 request_id, 避免日志格式化失败
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    # request_id 通过 logger.extra 注入, 见 log_info 与 log_error
    format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
)

for _handler in logging.getLogger().handlers:
    _handler.addFilter(RequestIdFilter())

logger = logging.getLogger("riskmonitor")

# 初始化 MCP server
mcp = FastMCP("RiskMonitor")


def new_request_id() -> str:
    # 单次工具调用的关联 id
    return uuid.uuid4().hex


def log_info(message: str, request_id: str) -> None:
    # 通过 extra 传递 request_id, 保持结构化日志一致
    logger.info(message, extra={"request_id": request_id})


def log_error(message: str, request_id: str) -> None:
    # 通过 extra 传递 request_id, 保持结构化日志一致
    logger.error(message, extra={"request_id": request_id})


def error_payload(code: str, message: str, request_id: str) -> dict:
    # JSON 返回工具的标准错误结构
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }


# 任务注册表
# 用于长耗时操作先返回 task_id, 再通过轮询工具获取状态与结果
_tasks: dict[str, dict[str, Any]] = {}
_tasks_lock = asyncio.Lock()


_metrics_lock = asyncio.Lock()
_metrics: dict[str, Any] = {
    "monitor_desk_exposure": {
        "request_count": 0,
        "latency_ms": [],
        "max_samples": 200,
    }
}


def _new_task_id() -> str:
    # task_id 用于让客户端持有句柄, 后续通过轮询查询状态与获取结果
    return uuid.uuid4().hex


async def _set_task(task_id: str, patch: dict[str, Any]) -> None:
    # 任务状态写入需要加锁, 避免并发更新导致状态丢失
    # patch 采用增量更新, 便于不同阶段逐步写入 progress, message, result
    async with _tasks_lock:
        current = _tasks.get(task_id, {})
        current.update(patch)
        _tasks[task_id] = current


async def _get_task(task_id: str) -> Optional[dict[str, Any]]:
    # 返回副本, 避免调用方直接修改内部状态
    async with _tasks_lock:
        item = _tasks.get(task_id)
        return dict(item) if item is not None else None


async def _run_task_calculate_total_delta(task_id: str) -> None:
    # 任务执行函数在后台协程中运行
    # status: queued -> running -> succeeded | failed | canceled
    request_id = new_request_id()
    log_info(f"task=calculate_total_delta start task_id={task_id}", request_id)
    await _set_task(task_id, {"status": "running", "request_id": request_id, "progress": 0})

    try:
        # 让出一次事件循环, 给客户端机会先拿到 task_id
        await asyncio.sleep(0)
        await _set_task(task_id, {"progress": 10, "message": "开始查询数据库"})

        # 复用现有业务实现, 保持口径一致
        # 注意: 这里调用的是工具函数 calculate_total_delta, 其内部也会产生日志与 request_id
        result = await calculate_total_delta()

        # 任务完成后将 result 写回注册表, 轮询方即可取回
        await _set_task(task_id, {"progress": 100, "status": "succeeded", "result": result})
        log_info(f"task=calculate_total_delta ok task_id={task_id}", request_id)
    except asyncio.CancelledError:
        # background.cancel() 会触发 CancelledError
        # 这里将状态写为 canceled, 并返回统一错误结构
        await _set_task(task_id, {"status": "canceled", "progress": 0, "error": {"code": "CANCELED", "message": "任务已取消"}})
        log_error(f"task=calculate_total_delta canceled task_id={task_id}", request_id)
    except Exception as e:
        # 兜底异常会标记 failed, 便于客户端区分执行失败与主动取消
        await _set_task(task_id, {"status": "failed", "progress": 0, "error": {"code": "INTERNAL_ERROR", "message": f"任务执行出错: {str(e)}"}})
        log_error(f"task=calculate_total_delta error task_id={task_id} err={str(e)}", request_id)

# 数据库连接
def get_db_connection():
    """获取数据库连接"""
    mysql_password = os.getenv('MYSQL_PASSWORD')
    if not mysql_password:
        # 快速失败, 避免默认密码兜底带来安全问题
        raise ValueError("MYSQL_PASSWORD is not set")

    connect_timeout = float(os.getenv("MYSQL_CONNECT_TIMEOUT", "3"))
    read_timeout = float(os.getenv("MYSQL_READ_TIMEOUT", "5"))
    write_timeout = float(os.getenv("MYSQL_WRITE_TIMEOUT", "5"))

    return pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        database=os.getenv('MYSQL_DATABASE', 'riskmonitor'),
        user=os.getenv('MYSQL_USER', 'admin'),
        password=mysql_password,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=write_timeout,
    )


async def _record_latency(tool_name: str, latency_ms: float) -> None:
    async with _metrics_lock:
        item = _metrics.get(tool_name)
        if item is None:
            return
        item["request_count"] = int(item.get("request_count", 0)) + 1
        samples = list(item.get("latency_ms", []))
        samples.append(float(latency_ms))
        max_samples = int(item.get("max_samples", 200))
        if len(samples) > max_samples:
            samples = samples[-max_samples:]
        item["latency_ms"] = samples


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = int(round(0.95 * (len(sorted_values) - 1)))
    idx = max(0, min(idx, len(sorted_values) - 1))
    return float(sorted_values[idx])


async def _fetch_market_snapshot(url: str, request_id: str) -> dict:
    timeout_s = float(os.getenv("MARKET_SNAPSHOT_TIMEOUT", "2"))
    retries = int(os.getenv("MARKET_SNAPSHOT_RETRIES", "2"))

    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    raise ValueError("market snapshot response must be a JSON object")
                return data
        except Exception as e:
            last_error = e
            log_error(f"market_snapshot_fetch_failed attempt={attempt} err={str(e)}", request_id)
            await asyncio.sleep(min(0.2 * (attempt + 1), 1.0))

    raise RuntimeError(f"market snapshot fetch failed: {str(last_error)}")


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _compute_position_pv_usd(position: dict, snapshot: dict) -> float:
    security_id = position.get("security_id")
    currency = position.get("currency") or "USD"
    quantity = _to_float(position.get("quantity")) or 0.0

    prices = snapshot.get("prices") if isinstance(snapshot.get("prices"), dict) else {}
    fx_rates = snapshot.get("fx_rates") if isinstance(snapshot.get("fx_rates"), dict) else {}

    price = _to_float(prices.get(security_id))
    if price is None:
        price = 0.0

    fx = _to_float(fx_rates.get(currency))
    if fx is None:
        fx = 1.0

    return float(quantity * price * fx)


@mcp.tool()
def query_all_positions() -> dict:
    """查询所有头寸数据

    用途:
        读取并展示 positions 表中的全部头寸记录, 用于快速概览当前持仓

    数据访问:
        只读, MySQL 表: positions

    安全与授权:
        该工具会读取交易与风险数据, 请确保你有权限访问相关数据

    返回:
        dict: 结构化 JSON 对象, 包含头寸明细与汇总信息
    """
    try:
        request_id = new_request_id()
        log_info("tool=query_all_positions start", request_id)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT position_id, trader_id, desk, security_id, 
                   quantity, delta, entry_date, currency
            FROM positions
            ORDER BY entry_date DESC
        """)
        
        positions = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not positions:
            log_info("tool=query_all_positions empty", request_id)
            return {
                "position_count": 0,
                "positions": [],
                "message": "未找到任何头寸记录.",
                "request_id": request_id,
            }

        normalized_positions = []
        for pos in positions:
            entry_date = pos.get('entry_date')
            normalized_positions.append({
                "position_id": pos.get('position_id'),
                "trader_id": pos.get('trader_id'),
                "desk": pos.get('desk'),
                "security_id": pos.get('security_id'),
                "quantity": float(pos['quantity']) if pos.get('quantity') is not None else None,
                "delta": float(pos['delta']) if pos.get('delta') is not None else None,
                "entry_date": entry_date.isoformat() if hasattr(entry_date, 'isoformat') else entry_date,
                "currency": pos.get('currency')
            })

        log_info(f"tool=query_all_positions ok count={len(positions)}", request_id)
        return {
            "position_count": len(positions),
            "positions": normalized_positions,
            "request_id": request_id,
        }
        
    except Exception as e:
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=query_all_positions error={str(e)}", request_id)
        return {
            "request_id": request_id,
            **error_payload("INTERNAL_ERROR", f"查询所有头寸出错: {str(e)}", request_id),
        }


@mcp.tool()
def query_positions_by_trader(
    trader_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    """查询特定交易员的所有头寸

    用途:
        按 trader_id 过滤查询 positions, 并汇总该交易员的 total delta

    数据访问:
        只读, MySQL 表: positions

    安全与授权:
        该工具会读取交易与风险数据, 请确保你有权限访问相关数据

    参数:
        trader_id: 交易员ID, 例如 'TRADER-001'
        start_date: 可选, 开始日期, 格式 YYYY-MM-DD
        end_date: 可选, 结束日期, 格式 YYYY-MM-DD
        limit: 可选, 返回记录条数上限, 默认 100, 最大 1000
        offset: 可选, 分页偏移, 默认 0

    返回:
        str: 该交易员头寸与汇总的格式化文本
    """
    try:
        request_id = new_request_id()
        log_info(f"tool=query_positions_by_trader start trader_id={trader_id}", request_id)
        if limit is None:
            limit = 100
        limit = max(1, min(int(limit), 1000))
        if offset is None:
            offset = 0
        offset = max(0, int(offset))

        if start_date is not None:
            datetime.strptime(start_date, "%Y-%m-%d")
        if end_date is not None:
            datetime.strptime(end_date, "%Y-%m-%d")

        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT position_id, trader_id, desk, security_id,
                   quantity, delta, entry_date, currency
            FROM positions
            WHERE trader_id = %s
        """
        params = [trader_id]

        if start_date is not None:
            query += " AND entry_date >= %s"
            params.append(start_date)
        if end_date is not None:
            query += " AND entry_date <= %s"
            params.append(end_date)

        query += " ORDER BY entry_date DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, tuple(params))

        positions = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not positions:
            log_info("tool=query_positions_by_trader empty", request_id)
            return f"未找到交易员 {trader_id} 的头寸记录."
        
        # 汇总计算
        total_delta = sum(float(pos['delta']) for pos in positions)
        
        # 格式化输出
        result = f"交易员 {trader_id} - {len(positions)} 个头寸:\n"
        result += f"总 Delta: {total_delta:,.2f}\n\n"
        
        for pos in positions:
            result += f"头寸 ID: {pos['position_id']}\n"
            result += f"  交易台: {pos['desk']}\n"
            result += f"  证券: {pos['security_id']}\n"
            result += f"  数量: {pos['quantity']:,.0f}\n"
            result += f"  Delta: {pos['delta']:,.2f}\n"
            result += f"  入场日期: {pos['entry_date']}\n"
            result += f"  货币: {pos['currency']}\n"
            result += "\n"
        
        log_info(f"tool=query_positions_by_trader ok count={len(positions)}", request_id)
        return result
        
    except ValueError as e:
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=query_positions_by_trader invalid_input={str(e)}", request_id)
        return f"无效输入 request_id={request_id}: {str(e)}"
    except Exception as e:
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=query_positions_by_trader error={str(e)}", request_id)
        return f"查询交易员 {trader_id} 头寸出错 request_id={request_id}: {str(e)}"


@mcp.tool()
async def query_positions_by_desk(
    desk_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    ctx: Context = None,
) -> dict:
    """查询特定交易台的所有头寸

    用途:
        按 desk 过滤查询 positions, 并汇总该交易台的 total delta 与 trader 数量

    数据访问:
        只读, MySQL 表: positions

    安全与授权:
        该工具会读取交易与风险数据, 请确保你有权限访问相关数据

    参数:
        desk_name: 交易台名称, 例如 'Equity Derivatives'
        start_date: 可选, 开始日期, 格式 YYYY-MM-DD
        end_date: 可选, 结束日期, 格式 YYYY-MM-DD
        limit: 可选, 返回记录条数上限, 默认 100, 最大 1000
        offset: 可选, 分页偏移, 默认 0

    返回:
        dict: 结构化 JSON 对象, 包含该交易台头寸明细与汇总指标
    """
    try:
        request_id = new_request_id()
        log_info(f"tool=query_positions_by_desk start desk={desk_name}", request_id)

        if ctx is not None:
            await ctx.report_progress(0, 100, "开始处理请求")

        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))

        if start_date is not None:
            datetime.strptime(start_date, "%Y-%m-%d")
        if end_date is not None:
            datetime.strptime(end_date, "%Y-%m-%d")

        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT position_id, trader_id, desk, security_id,
                   quantity, delta, entry_date, currency
            FROM positions
            WHERE desk = %s
        """
        params = [desk_name]

        if start_date is not None:
            query += " AND entry_date >= %s"
            params.append(start_date)
        if end_date is not None:
            query += " AND entry_date <= %s"
            params.append(end_date)

        query += " ORDER BY entry_date DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, tuple(params))

        positions = cursor.fetchall()
        cursor.close()
        conn.close()

        if not positions:
            log_info("tool=query_positions_by_desk empty", request_id)
            return {
                "desk": desk_name,
                "position_count": 0,
                "trader_count": 0,
                "total_delta": 0.0,
                "positions": [],
                "message": f"未找到交易台 {desk_name} 的头寸记录.",
                "request_id": request_id,
            }

        # 汇总计算
        total_delta = sum(float(pos['delta']) for pos in positions)
        traders = set(pos['trader_id'] for pos in positions)

        normalized_positions = []
        for pos in positions:
            entry_date = pos.get('entry_date')
            normalized_positions.append({
                "position_id": pos.get('position_id'),
                "trader_id": pos.get('trader_id'),
                "desk": pos.get('desk'),
                "security_id": pos.get('security_id'),
                "quantity": float(pos['quantity']) if pos.get('quantity') is not None else None,
                "delta": float(pos['delta']) if pos.get('delta') is not None else None,
                "entry_date": entry_date.isoformat() if hasattr(entry_date, 'isoformat') else entry_date,
                "currency": pos.get('currency')
            })

        if ctx is not None:
            await ctx.report_progress(90, 100, "结果整理完成")

        log_info(f"tool=query_positions_by_desk ok count={len(positions)}", request_id)
        return {
            "desk": desk_name,
            "position_count": len(positions),
            "trader_count": len(traders),
            "total_delta": float(total_delta),
            "positions": normalized_positions,
            "request_id": request_id,
        }

    except asyncio.CancelledError:
        request_id = locals().get("request_id") or new_request_id()
        log_error("tool=query_positions_by_desk canceled", request_id)
        return {
            "desk": desk_name,
            "request_id": request_id,
            **error_payload("CANCELED", "请求已取消", request_id),
        }

    except ValueError as e:
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=query_positions_by_desk invalid_input={str(e)}", request_id)
        return {
            "desk": desk_name,
            "request_id": request_id,
            **error_payload("INVALID_INPUT", str(e), request_id),
        }
    except Exception as e:
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=query_positions_by_desk error={str(e)}", request_id)
        return {
            "desk": desk_name,
            "request_id": request_id,
            **error_payload("INTERNAL_ERROR", f"查询交易台 {desk_name} 头寸出错: {str(e)}", request_id),
        }


@mcp.tool()
async def calculate_total_delta(ctx: Context = None) -> dict:
    """计算所有头寸的总 Delta

    用途:
        计算全组合总 delta, 并按 desk 聚合展示 delta 与头寸数量

    数据访问:
        只读, MySQL 表: positions

    安全与授权:
        该工具会读取交易与风险数据, 请确保你有权限访问相关数据

    返回:
        dict: 结构化 JSON 对象, 包含组合总 delta 与按 desk 分组汇总
    """
    try:
        request_id = new_request_id()
        log_info("tool=calculate_total_delta start", request_id)

        if ctx is not None:
            await ctx.report_progress(0, 100, "开始处理请求")

        conn = get_db_connection()
        cursor = conn.cursor()

        if ctx is not None:
            await ctx.report_progress(20, 100, "开始计算组合总 delta")

        # 组合总 delta
        cursor.execute("SELECT SUM(delta) as total_delta FROM positions")
        total_result = cursor.fetchone()
        total_delta = float(total_result['total_delta']) if total_result['total_delta'] else 0

        if ctx is not None:
            await ctx.report_progress(50, 100, "开始按 desk 汇总")

        # 按 desk 汇总 delta
        cursor.execute("""
            SELECT desk, SUM(delta) as desk_delta, COUNT(*) as position_count
            FROM positions
            GROUP BY desk
            ORDER BY ABS(SUM(delta)) DESC
        """)
        
        desk_deltas = cursor.fetchall()
        cursor.close()
        conn.close()

        normalized_desks = []
        for desk in desk_deltas:
            normalized_desks.append({
                "desk": desk.get('desk'),
                "desk_delta": float(desk['desk_delta']) if desk.get('desk_delta') is not None else 0.0,
                "position_count": int(desk['position_count']) if desk.get('position_count') is not None else 0
            })

        if ctx is not None:
            await ctx.report_progress(95, 100, "结果整理完成")

        log_info(f"tool=calculate_total_delta ok desk_count={len(normalized_desks)}", request_id)
        return {
            "total_delta": float(total_delta),
            "by_desk": normalized_desks,
            "request_id": request_id,
        }

    except asyncio.CancelledError:
        request_id = locals().get("request_id") or new_request_id()
        log_error("tool=calculate_total_delta canceled", request_id)
        return {
            "request_id": request_id,
            **error_payload("CANCELED", "请求已取消", request_id),
        }

    except Exception as e:
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=calculate_total_delta error={str(e)}", request_id)
        return {
            "request_id": request_id,
            **error_payload("INTERNAL_ERROR", f"计算总 delta 出错: {str(e)}", request_id),
        }


@mcp.tool()
async def monitor_desk_exposure(
    desk: str,
    as_of: Optional[str] = None,
    market_snapshot_url: Optional[str] = None,
    abs_delta_limit: float = 1000000.0,
    ctx: Context = None,
) -> dict:
    """Intraday desk exposure monitoring

    用途:
        基于 positions 与 market snapshot 计算 desk 级别 exposure, 并进行限额判断与告警输出.

    数据访问:
        只读, MySQL 表: positions

    参数:
        desk: 交易台名称
        as_of: 可选, 估值时间, ISO8601 或 YYYY-MM-DD
        market_snapshot_url: 可选, market snapshot 的 HTTP URL
        abs_delta_limit: desk delta 绝对值限额

    返回:
        dict: 结构化 JSON, 包含 exposure, breaches, alerts, request_id
    """
    request_id = new_request_id()
    start = time.monotonic()

    try:
        if as_of is None or not as_of.strip():
            as_of = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        else:
            as_of = as_of.strip()

        if market_snapshot_url is None or not market_snapshot_url.strip():
            market_snapshot_url = os.getenv("MARKET_SNAPSHOT_URL", "http://127.0.0.1:9010/snapshot")
        else:
            market_snapshot_url = market_snapshot_url.strip()

        if ctx is not None:
            await ctx.report_progress(0, 100, "开始处理请求")

        log_info(f"tool=monitor_desk_exposure start desk={desk} as_of={as_of}", request_id)

        snapshot = await _fetch_market_snapshot(market_snapshot_url, request_id)
        if ctx is not None:
            await ctx.report_progress(20, 100, "market snapshot 已获取")

        db_retries = int(os.getenv("MYSQL_RETRIES", "1"))
        last_db_error: Optional[Exception] = None
        positions = []
        for attempt in range(db_retries + 1):
            conn = None
            cursor = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT position_id, trader_id, desk, security_id,
                           quantity, delta, entry_date, currency
                    FROM positions
                    WHERE desk = %s
                    """,
                    (desk,),
                )
                positions = cursor.fetchall()
                last_db_error = None
                break
            except pymysql.MySQLError as e:
                last_db_error = e
                log_error(f"db_query_failed tool=monitor_desk_exposure attempt={attempt} err={str(e)}", request_id)
                if attempt >= db_retries:
                    break
                await asyncio.sleep(min(0.2 * (attempt + 1), 1.0))
            finally:
                try:
                    if cursor is not None:
                        cursor.close()
                finally:
                    if conn is not None:
                        conn.close()

        if last_db_error is not None:
            raise RuntimeError(f"db query failed: {str(last_db_error)}")

        if ctx is not None:
            await ctx.report_progress(60, 100, "positions 已获取")

        total_delta = 0.0
        total_pv_usd = 0.0
        by_currency: dict[str, dict[str, float]] = {}

        for pos in positions:
            delta = _to_float(pos.get("delta")) or 0.0
            currency = (pos.get("currency") or "USD").strip()
            pv_usd = _compute_position_pv_usd(pos, snapshot)
            total_delta += delta
            total_pv_usd += pv_usd

            cur_item = by_currency.get(currency)
            if cur_item is None:
                cur_item = {"delta": 0.0, "pv_usd": 0.0}
                by_currency[currency] = cur_item
            cur_item["delta"] += float(delta)
            cur_item["pv_usd"] += float(pv_usd)

        breaches = []
        if abs(float(total_delta)) > float(abs_delta_limit):
            breaches.append(
                {
                    "type": "ABS_DELTA_LIMIT",
                    "metric": "total_delta",
                    "value": float(total_delta),
                    "threshold": float(abs_delta_limit),
                    "message": "desk total_delta breached abs_delta_limit",
                }
            )

        alerts = []
        if breaches:
            alerts.append(
                {
                    "alert_id": uuid.uuid4().hex,
                    "severity": "high",
                    "desk": desk,
                    "as_of": as_of,
                    "breach_count": len(breaches),
                    "message": "desk exposure breach detected",
                }
            )

        if ctx is not None:
            await ctx.report_progress(95, 100, "结果整理完成")

        latency_ms = (time.monotonic() - start) * 1000.0
        await _record_latency("monitor_desk_exposure", latency_ms)
        log_info(f"tool=monitor_desk_exposure ok desk={desk} latency_ms={latency_ms:.2f}", request_id)

        return {
            "as_of": as_of,
            "desk": desk,
            "exposure": {
                "pv_usd": float(total_pv_usd),
                "total_delta": float(total_delta),
                "total_vega": 0.0,
                "by_currency": by_currency,
                "position_count": len(positions),
            },
            "limits": {"abs_delta_limit": float(abs_delta_limit)},
            "breaches": breaches,
            "alerts": alerts,
            "market_snapshot": {
                "source_url": market_snapshot_url,
                "as_of": snapshot.get("as_of"),
            },
            "latency_ms": float(latency_ms),
            "request_id": request_id,
        }

    except asyncio.CancelledError:
        latency_ms = (time.monotonic() - start) * 1000.0
        await _record_latency("monitor_desk_exposure", latency_ms)
        log_error(f"tool=monitor_desk_exposure canceled latency_ms={latency_ms:.2f}", request_id)
        return {
            "desk": desk,
            "as_of": as_of,
            "latency_ms": float(latency_ms),
            "request_id": request_id,
            **error_payload("CANCELED", "请求已取消", request_id),
        }
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000.0
        await _record_latency("monitor_desk_exposure", latency_ms)
        log_error(f"tool=monitor_desk_exposure error={str(e)} latency_ms={latency_ms:.2f}", request_id)
        return {
            "desk": desk,
            "as_of": as_of,
            "latency_ms": float(latency_ms),
            "request_id": request_id,
            **error_payload("INTERNAL_ERROR", f"monitor desk exposure 出错: {str(e)}", request_id),
        }


@mcp.tool()
async def get_service_metrics() -> dict:
    """返回服务内指标快照

    用途:
        为性能与稳定性提供最小可观测指标, 便于在 demo 中展示.

    返回:
        dict: request_count 与 p95_latency_ms 等指标
    """
    async with _metrics_lock:
        monitor = dict(_metrics.get("monitor_desk_exposure", {}))
        latencies = list(monitor.get("latency_ms", []))
        return {
            "monitor_desk_exposure": {
                "request_count": int(monitor.get("request_count", 0)),
                "p95_latency_ms": _p95(latencies),
                "sample_size": len(latencies),
            }
        }


@mcp.tool()
async def start_calculate_total_delta_task() -> dict:
    """启动后台任务计算总 delta

    用途:
        对可能耗时的计算先返回 task_id, 客户端可轮询任务状态与结果

    返回:
        dict: 结构化 JSON 对象, 包含 task_id 与初始状态
    """
    # 创建任务并写入 queued 状态
    task_id = _new_task_id()
    await _set_task(task_id, {"status": "queued", "progress": 0, "created_at": datetime.utcnow().isoformat()})

    # 创建后台协程执行, 立刻返回 task_id
    background = asyncio.create_task(_run_task_calculate_total_delta(task_id))

    # 内部保存 asyncio task, 仅用于 cancel, 对外返回会过滤该字段
    await _set_task(task_id, {"_asyncio_task": background})
    return {
        "task_id": task_id,
        "status": "queued",
        "progress": 0,
    }


@mcp.tool()
async def get_task_status(task_id: str) -> dict:
    """查询任务状态

    用途:
        轮询后台任务的状态, 进度, 结果或错误

    参数:
        task_id: 任务 id

    返回:
        dict: 结构化 JSON 对象
    """
    # 轮询接口只返回公共字段, 不暴露内部协程对象
    item = await _get_task(task_id)
    if item is None:
        return {
            "task_id": task_id,
            **error_payload("NOT_FOUND", "未找到任务", new_request_id()),
        }

    public_item = {k: v for k, v in item.items() if not k.startswith("_")}
    public_item["task_id"] = task_id
    return public_item


@mcp.tool()
async def cancel_task(task_id: str) -> dict:
    """取消任务

    用途:
        尝试取消后台任务

    参数:
        task_id: 任务 id

    返回:
        dict: 结构化 JSON 对象
    """
    item = await _get_task(task_id)
    if item is None:
        return {
            "task_id": task_id,
            **error_payload("NOT_FOUND", "未找到任务", new_request_id()),
        }

    background = item.get("_asyncio_task")
    if background is not None and hasattr(background, "cancel"):
        # 触发后台协程取消
        background.cancel()
        await asyncio.sleep(0)

    # 先标记 cancel_requested, 最终状态会由后台执行函数写入 canceled
    await _set_task(task_id, {"status": "cancel_requested"})
    return {
        "task_id": task_id,
        "status": "cancel_requested",
    }


if __name__ == "__main__":
    # 启动 MCP server
    transport = os.getenv("MCP_TRANSPORT")
    if transport is None or not transport.strip():
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        if app_env == "production":
            transport = "streamable-http"
        else:
            transport = "stdio"
    transport = transport.strip().lower()
    mount_path = os.getenv("MCP_MOUNT_PATH")
    if mount_path is not None:
        mount_path = mount_path.strip() or None

    if transport == "sse":
        # SSE 为旧版 HTTP 传输, 仅用于兼容旧客户端
        mcp.run(transport="sse", mount_path=mount_path)
    elif transport in {"streamable-http", "http"}:
        # Streamable HTTP 为推荐传输, 用于无状态部署与水平扩展
        mcp.run(transport="streamable-http")
    else:
        # 默认使用 stdio, 适用于 Claude Desktop 与本地集成
        mcp.run(transport="stdio")
