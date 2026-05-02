from __future__ import annotations


class RiskMonitorReActAdapter:
    """旧 ReAct Adapter 测试兼容层."""

    def __init__(self) -> None:
        self._intent_agent = object()
        self._orchestrator_agent = object()
        self._critic_agent = object()
        self._system_engineer_agent = object()
        self._risk_analyst_agent = object()


_REACT_ADAPTER: RiskMonitorReActAdapter | None = None


def get_react_adapter() -> RiskMonitorReActAdapter:
    global _REACT_ADAPTER
    if _REACT_ADAPTER is None:
        _REACT_ADAPTER = RiskMonitorReActAdapter()
    return _REACT_ADAPTER


def reset_react_adapter() -> None:
    global _REACT_ADAPTER
    _REACT_ADAPTER = None


__all__ = [
    "RiskMonitorReActAdapter",
    "get_react_adapter",
    "reset_react_adapter",
]
