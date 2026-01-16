"""
Prometheus 指标服务

Week4: 可观测与告警闭环
提供 Prometheus 格式的指标暴露
"""

from typing import Any, Dict, List
import time


# 进程内指标存储
_request_count: Dict[str, int] = {}
_request_latency_sum: Dict[str, float] = {}
_request_latency_count: Dict[str, int] = {}
_error_count: Dict[str, int] = {}
_start_time = time.time()


def record_request(tool_name: str, latency_ms: float, is_error: bool = False) -> None:
    """
    记录请求指标

    Args:
        tool_name: 工具名称
        latency_ms: 延迟(毫秒)
        is_error: 是否错误
    """
    # 请求计数
    _request_count[tool_name] = _request_count.get(tool_name, 0) + 1

    # 延迟统计
    _request_latency_sum[tool_name] = _request_latency_sum.get(tool_name, 0.0) + latency_ms
    _request_latency_count[tool_name] = _request_latency_count.get(tool_name, 0) + 1

    # 错误计数
    if is_error:
        _error_count[tool_name] = _error_count.get(tool_name, 0) + 1


def generate_prometheus_metrics() -> str:
    """
    生成 Prometheus 格式的指标

    Returns:
        Prometheus 文本格式的指标
    """
    lines: List[str] = []

    # 进程启动时间
    lines.append("# HELP process_start_time_seconds Process start time in unix timestamp")
    lines.append("# TYPE process_start_time_seconds gauge")
    lines.append(f"process_start_time_seconds {_start_time}")
    lines.append("")

    # 进程运行时间
    uptime = time.time() - _start_time
    lines.append("# HELP process_uptime_seconds Process uptime in seconds")
    lines.append("# TYPE process_uptime_seconds gauge")
    lines.append(f"process_uptime_seconds {uptime:.2f}")
    lines.append("")

    # 请求总数
    lines.append("# HELP mcp_requests_total Total number of MCP tool requests")
    lines.append("# TYPE mcp_requests_total counter")
    for tool_name, count in _request_count.items():
        lines.append(f'mcp_requests_total{{tool="{tool_name}"}} {count}')
    lines.append("")

    # 请求延迟(平均值)
    lines.append("# HELP mcp_request_latency_ms_avg Average request latency in milliseconds")
    lines.append("# TYPE mcp_request_latency_ms_avg gauge")
    for tool_name, latency_sum in _request_latency_sum.items():
        latency_count = _request_latency_count.get(tool_name, 0)
        if latency_count > 0:
            avg_latency = latency_sum / latency_count
            lines.append(f'mcp_request_latency_ms_avg{{tool="{tool_name}"}} {avg_latency:.2f}')
    lines.append("")

    # 错误总数
    lines.append("# HELP mcp_errors_total Total number of errors")
    lines.append("# TYPE mcp_errors_total counter")
    for tool_name, count in _error_count.items():
        lines.append(f'mcp_errors_total{{tool="{tool_name}"}} {count}')
    lines.append("")

    # 错误率
    lines.append("# HELP mcp_error_rate Error rate (errors / requests)")
    lines.append("# TYPE mcp_error_rate gauge")
    for tool_name, request_count in _request_count.items():
        error_count = _error_count.get(tool_name, 0)
        if request_count > 0:
            error_rate = error_count / request_count
            lines.append(f'mcp_error_rate{{tool="{tool_name}"}} {error_rate:.4f}')
    lines.append("")

    return "\n".join(lines)


def get_metrics_summary() -> Dict[str, Any]:
    """
    获取指标摘要(用于内部监控)

    Returns:
        指标摘要字典
    """
    summary = {
        "uptime_seconds": time.time() - _start_time,
        "tools": {}
    }

    for tool_name, request_count in _request_count.items():
        error_count = _error_count.get(tool_name, 0)
        latency_sum = _request_latency_sum.get(tool_name, 0.0)
        latency_count = _request_latency_count.get(tool_name, 0)

        avg_latency = latency_sum / latency_count if latency_count > 0 else 0.0
        error_rate = error_count / request_count if request_count > 0 else 0.0

        summary["tools"][tool_name] = {
            "request_count": request_count,
            "error_count": error_count,
            "error_rate": error_rate,
            "avg_latency_ms": avg_latency
        }

    return summary


def reset_metrics() -> None:
    """重置所有指标(用于测试)"""
    global _start_time  
    _request_count.clear()
    _request_latency_sum.clear()
    _request_latency_count.clear()
    _error_count.clear()
    _start_time = time.time()
