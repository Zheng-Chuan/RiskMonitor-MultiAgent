from __future__ import annotations

import os


def get_policy_version() -> str:
    return os.getenv("POLICY_VERSION", "policy.v1").strip() or "policy.v1"


PROMPT_VERSION_SYSTEM_ENGINEER = "system_engineer_prompt.v1"
PROMPT_VERSION_RISK_ANALYST = "risk_analyst_prompt.v1"
PROMPT_VERSION_MANAGER = "manager_prompt.v1"

