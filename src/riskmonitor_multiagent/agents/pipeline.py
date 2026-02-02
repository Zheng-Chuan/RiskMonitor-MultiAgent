from __future__ import annotations

import logging
from typing import Any

from riskmonitor_multiagent.agents.roles import JuniorAnalystAgent
from riskmonitor_multiagent.agents.roles import RiskManagerAgent
from riskmonitor_multiagent.agents.roles import SystemEngineerAgent

logger = logging.getLogger(__name__)


async def run_agent_pipeline(*, event: dict[str, Any]) -> dict[str, Any]:
    engineer = SystemEngineerAgent()
    engineer_result = engineer.analyze(event=event)
    if not engineer_result.ok:
        logger.warning(f"SystemEngineer blocked: {engineer_result.output}")
        return {"blocked": True, "engineer": engineer_result.output}

    analyst = JuniorAnalystAgent()
    analyst_result = await analyst.analyze(event=event)
    logger.info(f"JuniorAnalyst result ok={analyst_result.ok}")

    manager = RiskManagerAgent()
    manager_result = await manager.decide(event=event, analyst_report=analyst_result.output)
    logger.info(f"RiskManager result ok={manager_result.ok}")

    return {
        "blocked": False,
        "engineer": engineer_result.output,
        "analyst": analyst_result.output,
        "manager": manager_result.output,
    }

