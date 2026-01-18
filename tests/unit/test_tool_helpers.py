"""单元测试 tools helper

说明
- 覆盖输入归一化与轻量校验
- 不依赖数据库
"""

from __future__ import annotations



import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest  

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.tools import tool_helpers as helpers  

def test_normalize_limit_offset_defaults() -> None:
    limit, offset = helpers.normalize_limit_offset(None, None)
    assert limit == 100
    assert offset == 0


def test_normalize_limit_offset_bounds() -> None:
    limit, offset = helpers.normalize_limit_offset(0, -5)
    assert limit == 1
    assert offset == 0

    limit, offset = helpers.normalize_limit_offset(999999, 3)
    assert limit == 1000
    assert offset == 3


def test_validate_optional_yyyy_mm_dd_ok() -> None:
    helpers.validate_optional_yyyy_mm_dd(None, "start_date")
    helpers.validate_optional_yyyy_mm_dd("2026-01-14", "start_date")


def test_validate_optional_yyyy_mm_dd_invalid() -> None:
    with pytest.raises(ValueError) as exc:
        helpers.validate_optional_yyyy_mm_dd("2026/01/14", "start_date")
    assert "start_date" in str(exc.value)


def test_normalize_as_of_default_format() -> None:
    as_of = helpers.normalize_as_of(None)
    assert as_of.endswith("Z")


def test_normalize_str_default() -> None:
    assert helpers.normalize_str(None, "x") == "x"
    assert helpers.normalize_str("  ", "x") == "x"
    assert helpers.normalize_str(" y ", "x") == "y"


def test_normalize_positions() -> None:
    rows = [
        {
            "position_id": "POS-2026-001",
            "trader_id": "TRADER-001",
            "desk": "Equity Derivatives",
            "security_id": "AAPL-CALL-175-20250331",
            "quantity": Decimal("100"),
            "delta": Decimal("600"),
            "entry_date": datetime(2026, 1, 14),
            "currency": "USD",
        }
    ]
    result = helpers.normalize_positions(rows)
    assert result[0]["position_id"] == "POS-2026-001"
    assert isinstance(result[0]["quantity"], float)
    assert isinstance(result[0]["delta"], float)
    assert isinstance(result[0]["entry_date"], str)
