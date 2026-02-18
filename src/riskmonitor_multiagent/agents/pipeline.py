from __future__ import annotations

import logging
import uuid
from typing import Any

from riskmonitor_multiagent.agents.roles import ManagerAgent
from riskmonitor_multiagent.agents.roles import RiskAnalystAgent
from riskmonitor_multiagent.agents.roles import SystemEngineerAgent
from riskmonitor_multiagent.orchestration.tool_executor import execute_agent_command, new_agent_command

logger = logging.getLogger(__name__)


async def run_agent_pipeline(*, event: dict[str, Any]) -> dict[str, Any]:
    engineer = SystemEngineerAgent()
    run_id = str(uuid.uuid4())
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    source_meta = payload.get("source_payload_meta") if isinstance(payload.get("source_payload_meta"), dict) else {}
    message_ts_ms = source_meta.get("message_ts_ms")

    receipts = [
        execute_agent_command(
            new_agent_command(
                run_id=run_id,
                command_id=f"cmd_{uuid.uuid4().hex}",
                target_agent="system_engineer",
                action="collect_metrics",
                params={},
                timeout_ms=1000,
                expected_output_schema="tool_result.v1",
            )
        ),
        execute_agent_command(
            new_agent_command(
                run_id=run_id,
                command_id=f"cmd_{uuid.uuid4().hex}",
                target_agent="system_engineer",
                action="kafka_lag",
                params={"message_ts_ms": message_ts_ms},
                timeout_ms=1000,
                expected_output_schema="tool_result.v1",
            )
        ),
        execute_agent_command(
            new_agent_command(
                run_id=run_id,
                command_id=f"cmd_{uuid.uuid4().hex}",
                target_agent="system_engineer",
                action="mysql_health",
                params={},
                timeout_ms=1000,
                expected_output_schema="tool_result.v1",
            )
        ),
        execute_agent_command(
            new_agent_command(
                run_id=run_id,
                command_id=f"cmd_{uuid.uuid4().hex}",
                target_agent="system_engineer",
                action="chroma_health",
                params={},
                timeout_ms=1000,
                expected_output_schema="tool_result.v1",
            )
        ),
    ]

    engineer_result = await engineer.analyze(event=event, context={"receipts": receipts, "facts": {}, "observations": []})
    if not engineer_result.ok:
        logger.warning(f"SystemEngineer blocked: {engineer_result.output}")
        return {"blocked": True, "engineer": engineer_result.output}

    analyst = RiskAnalystAgent()
    analyst_result = await analyst.analyze(event=event)
    logger.info(f"RiskAnalyst result ok={analyst_result.ok}")

    manager = ManagerAgent()
    manager_result = await manager.decide(event=event, analyst_report=analyst_result.output)
    logger.info(f"Manager result ok={manager_result.ok}")

    return {
        "blocked": False,
        "engineer": engineer_result.output,
        "analyst": analyst_result.output,
        "manager": manager_result.output,
    }
