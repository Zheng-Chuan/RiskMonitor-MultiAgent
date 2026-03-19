"""
ReAct Adapter 测试.
"""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.orchestration.react_adapter import (
    RiskMonitorReActAdapter,
    get_react_adapter,
    reset_react_adapter,
)


class TestRiskMonitorReActAdapter:
    """RiskMonitorReActAdapter 测试."""

    def setup_method(self) -> None:
        """测试前重置."""
        reset_react_adapter()
    
    def test_initialization(self) -> None:
        """测试初始化."""
        adapter = RiskMonitorReActAdapter()
        
        assert adapter._intent_agent is not None
        assert adapter._orchestrator_agent is not None
        assert adapter._critic_agent is not None
        assert adapter._system_engineer_agent is not None
        assert adapter._risk_analyst_agent is not None
    
    def test_global_singleton(self) -> None:
        """测试全局单例."""
        adapter1 = get_react_adapter()
        adapter2 = get_react_adapter()
        
        assert adapter1 is adapter2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
