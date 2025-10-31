"""
集成测试：MCP工具
测试MCP Server的工具函数
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from main import query_all_positions, query_positions_by_trader, query_positions_by_desk, calculate_total_delta


def test_query_all_positions():
    """测试查询所有头寸"""
    result = query_all_positions()
    assert result is not None
    assert "Found" in result or "No positions" in result
    assert "Error" not in result
    print(f"\n{result[:200]}...")  # 打印前200个字符


def test_query_positions_by_trader():
    """测试按交易员查询"""
    result = query_positions_by_trader("TRADER-001")
    assert result is not None
    assert "TRADER-001" in result
    assert "Error" not in result
    print(f"\n{result[:200]}...")


def test_query_positions_by_trader_not_found():
    """测试查询不存在的交易员"""
    result = query_positions_by_trader("TRADER-999")
    assert "No positions found" in result


def test_query_positions_by_desk():
    """测试按交易台查询"""
    result = query_positions_by_desk("Equity Derivatives")
    assert result is not None
    assert "Equity Derivatives" in result
    assert "Error" not in result
    print(f"\n{result[:200]}...")


def test_query_positions_by_desk_not_found():
    """测试查询不存在的交易台"""
    result = query_positions_by_desk("NonExistent Desk")
    assert "No positions found" in result


def test_calculate_total_delta():
    """测试计算总Delta"""
    result = calculate_total_delta()
    assert result is not None
    assert "Portfolio Total Delta" in result
    assert "Delta by Desk" in result
    assert "Error" not in result
    print(f"\n{result}")


def test_all_tools_return_string():
    """测试所有工具都返回字符串"""
    tools = [
        query_all_positions(),
        query_positions_by_trader("TRADER-001"),
        query_positions_by_desk("Equity Derivatives"),
        calculate_total_delta()
    ]
    
    for result in tools:
        assert isinstance(result, str)
        assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
