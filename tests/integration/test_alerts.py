"""
告警闭环端到端测试

Week4: 可观测与告警闭环
测试告警规则评估、持久化和查询功能
"""



import sys
from pathlib import Path

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


@pytest.mark.asyncio
async def test_alert_rules_evaluation():
    """测试告警规则评估"""
    from riskmonitor_mcp.services import alert_rules_service

    # 测试超限场景
    alerts = alert_rules_service.evaluate_desk_delta_breach(
        desk="Equity Derivatives",
        abs_delta=1500000.0,
        threshold=1000000.0,
        request_id="test-request-001"
    )
    
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["alert_type"] == "DESK_DELTA_BREACH"
    assert alert["desk"] == "Equity Derivatives"
    assert alert["metric_value"] == 1500000.0
    assert alert["threshold_value"] == 1000000.0
    assert alert["breach_amount"] == 500000.0
    assert alert["severity"] in ["INFO", "WARNING", "CRITICAL"]
    
    # 测试未超限场景
    alerts_no_breach = alert_rules_service.evaluate_desk_delta_breach(
        desk="Fixed Income",
        abs_delta=800000.0,
        threshold=1000000.0,
        request_id="test-request-002"
    )
    
    assert len(alerts_no_breach) == 0


@pytest.mark.asyncio
async def test_alert_severity_determination():
    """测试告警级别判定"""
    from riskmonitor_mcp.services import alert_rules_service

    # CRITICAL: 超限 50% 以上
    alerts_critical = alert_rules_service.evaluate_desk_delta_breach(
        desk="Test Desk",
        abs_delta=1600000.0,
        threshold=1000000.0,
        request_id="test-critical"
    )
    assert alerts_critical[0]["severity"] == "CRITICAL"
    
    # WARNING: 超限 20%-50%
    alerts_warning = alert_rules_service.evaluate_desk_delta_breach(
        desk="Test Desk",
        abs_delta=1300000.0,
        threshold=1000000.0,
        request_id="test-warning"
    )
    assert alerts_warning[0]["severity"] == "WARNING"
    
    # INFO: 超限 20% 以下
    alerts_info = alert_rules_service.evaluate_desk_delta_breach(
        desk="Test Desk",
        abs_delta=1100000.0,
        threshold=1000000.0,
        request_id="test-info"
    )
    assert alerts_info[0]["severity"] == "INFO"


@pytest.mark.asyncio
async def test_alert_persistence_and_retrieval():
    """测试告警持久化和查询"""
    from riskmonitor_mcp.data_access import alerts_repository
    from riskmonitor_mcp.services import alert_rules_service

    # 生成测试告警
    test_request_id = f"test-persist-{pytest.__version__}"
    alerts = alert_rules_service.evaluate_desk_delta_breach(
        desk="Test Persistence Desk",
        abs_delta=1200000.0,
        threshold=1000000.0,
        request_id=test_request_id
    )
    
    assert len(alerts) == 1
    
    # 保存到数据库
    alerts_repository.save_alerts_batch(alerts)
    
    # 根据 request_id 查询
    retrieved_alerts = alerts_repository.get_alerts_by_request_id(test_request_id)
    assert len(retrieved_alerts) >= 1
    
    retrieved_alert = retrieved_alerts[0]
    assert retrieved_alert["request_id"] == test_request_id
    assert retrieved_alert["desk"] == "Test Persistence Desk"
    assert retrieved_alert["alert_type"] == "DESK_DELTA_BREACH"
    assert float(retrieved_alert["metric_value"]) == 1200000.0
    assert float(retrieved_alert["threshold_value"]) == 1000000.0
    
    # 根据 alert_id 查询
    alert_id = retrieved_alert["alert_id"]
    single_alert = alerts_repository.get_alert_by_id(alert_id)
    assert single_alert is not None
    assert single_alert["alert_id"] == alert_id


@pytest.mark.asyncio
async def test_get_recent_alerts():
    """测试查询最近告警"""
    from riskmonitor_mcp.data_access import alerts_repository

    # 查询所有最近告警
    recent_alerts = alerts_repository.get_recent_alerts(limit=10)
    assert isinstance(recent_alerts, list)
    
    # 按 severity 过滤
    critical_alerts = alerts_repository.get_recent_alerts(limit=10, severity="CRITICAL")
    assert isinstance(critical_alerts, list)
    for alert in critical_alerts:
        assert alert["severity"] == "CRITICAL"
    
    # 按 desk 过滤
    desk_alerts = alerts_repository.get_recent_alerts(limit=10, desk="Equity Derivatives")
    assert isinstance(desk_alerts, list)
    for alert in desk_alerts:
        assert alert["desk"] == "Equity Derivatives"


@pytest.mark.asyncio
async def test_alert_format_for_response():
    """测试告警格式化"""
    from riskmonitor_mcp.services import alert_rules_service

    alerts = alert_rules_service.evaluate_desk_delta_breach(
        desk="Format Test Desk",
        abs_delta=1500000.0,
        threshold=1000000.0,
        request_id="test-format"
    )
    
    formatted = alert_rules_service.format_alerts_for_response(alerts)
    
    assert len(formatted) == 1
    formatted_alert = formatted[0]
    
    # 验证格式化后的字段
    assert "alert_id" in formatted_alert
    assert "alert_type" in formatted_alert
    assert "severity" in formatted_alert
    assert "desk" in formatted_alert
    assert "metric_name" in formatted_alert
    assert "metric_value" in formatted_alert
    assert "threshold_value" in formatted_alert
    assert "breach_amount" in formatted_alert
    assert "message" in formatted_alert
    
    # 验证不包含内部字段
    assert "acknowledged" not in formatted_alert
    assert "acknowledged_at" not in formatted_alert
    assert "created_at" not in formatted_alert
