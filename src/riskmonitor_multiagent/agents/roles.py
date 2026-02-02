from __future__ import annotations

import time
from typing import Any

from riskmonitor_multiagent.agents.base import AgentResult
from riskmonitor_multiagent.agents.base import BaseAgent


class SystemEngineerAgent:
    def __init__(self, *, max_event_latency_ms: int = 60000) -> None:
        self._max_event_latency_ms = int(max_event_latency_ms)

    def analyze(self, *, event: dict[str, Any]) -> AgentResult:
        now_ms = int(time.time() * 1000)
        ts_ms = event.get("__ts_ms") or event.get("ts_ms") or event.get("event_ts_ms")
        latency_ms = None
        if isinstance(ts_ms, int):
            latency_ms = max(0, now_ms - ts_ms)
        elif isinstance(ts_ms, str) and ts_ms.isdigit():
            latency_ms = max(0, now_ms - int(ts_ms))

        desk = event.get("desk")
        exposure = event.get("exposure")

        if not isinstance(desk, str) or not desk.strip():
            return AgentResult(ok=False, output={"system_issue": True, "reason": "missing desk", "latency_ms": latency_ms})

        if exposure is None or not isinstance(exposure, (int, float)):
            return AgentResult(ok=False, output={"system_issue": True, "reason": "bad exposure", "latency_ms": latency_ms})

        if latency_ms is not None and latency_ms > self._max_event_latency_ms:
            return AgentResult(
                ok=False,
                output={
                    "system_issue": True,
                    "reason": f"event latency too high: {latency_ms}ms",
                    "latency_ms": latency_ms,
                },
            )

        return AgentResult(ok=True, output={"system_issue": False, "reason": "ok", "latency_ms": latency_ms})


class JuniorAnalystAgent:
    def __init__(self) -> None:
        self._agent = BaseAgent(
            name="junior_analyst",
            system_prompt=(
                "You are a junior risk analyst.\n"
                "Return only valid JSON.\n"
                "Keys: report, key_facts.\n"
                "report must be a short Chinese paragraph using only English punctuation.\n"
                "key_facts must be an object.\n"
            ),
        )

    async def analyze(self, *, event: dict[str, Any]) -> AgentResult:
        desk = event.get("desk")
        exposure = event.get("exposure")
        fallback = {
            "report": f"检测到 desk={desk} 的敞口变化值为 {exposure} 已触发阈值 需要进一步确认来源与影响范围",
            "key_facts": {"desk": desk, "exposure": exposure},
        }
        return await self._agent.ask_json(
            user_prompt=(
                "Input event:\n"
                f"{event}\n\n"
                "Summarize key facts and write a short report."
            ),
            fallback=fallback,
        )


class RiskManagerAgent:
    def __init__(self) -> None:
        self._agent = BaseAgent(
            name="risk_manager",
            system_prompt=(
                "You are a senior risk manager.\n"
                "Return only valid JSON.\n"
                "Keys: decision, action, rationale.\n"
                "decision must be one of WATCH or CRITICAL.\n"
                "action and rationale must be Chinese text using only English punctuation.\n"
            ),
        )

    async def decide(self, *, event: dict[str, Any], analyst_report: dict[str, Any]) -> AgentResult:
        exposure = event.get("exposure")
        level = "CRITICAL" if isinstance(exposure, (int, float)) and abs(exposure) >= 100000 else "WATCH"
        fallback = {
            "decision": level,
            "action": "建议立刻通知值班人员 并要求 desk 提供敞口变化原因",
            "rationale": "基于当前敞口变化幅度触发预警 需要人工确认是否为真实交易导致",
        }
        return await self._agent.ask_json(
            user_prompt=(
                "Input event:\n"
                f"{event}\n\n"
                "Analyst report:\n"
                f"{analyst_report}\n\n"
                "Make a decision and propose an action."
            ),
            fallback=fallback,
        )

