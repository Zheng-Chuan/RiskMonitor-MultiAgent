from __future__ import annotations

from typing import Any


_SIDE_EFFECT_PATTERNS = [
    "删除",
    "drop",
    "truncate",
    "写入",
    "更新",
    "修改",
    "执行",
    "重启",
    "kill",
    "发布",
    "deploy",
    "回滚",
    "rollback",
    "发邮件",
    "发送",
]


def guess_side_effects(*, text: str) -> bool:
    q = (text or "").strip().lower()
    if not q:
        return False
    return any(p.lower() in q for p in _SIDE_EFFECT_PATTERNS)


def guess_risk_level(*, text: str, side_effects: bool) -> str:
    q = (text or "").strip().lower()
    if side_effects:
        return "HIGH"
    if any(k in q for k in ["转账", "交易", "资金", "支付", "production", "prod", "权限", "密钥", "secret", "key"]):
        return "HIGH"
    if any(k in q for k in ["故障", "报错", "延迟", "timeout", "不可用", "lag"]):
        return "MEDIUM"
    return "LOW"


def build_intent_metadata(*, task: dict[str, Any], policy_version: str, prompt_version: str) -> dict[str, Any]:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    content = payload.get("content") if isinstance(payload.get("content"), str) else ""
    return {
        "task_id": task.get("task_id"),
        "session_id": task.get("session_id"),
        "source": task.get("source"),
        "user_id": task.get("user_id"),
        "policy_version": policy_version,
        "prompt_version": prompt_version,
        "content_len": len(content),
    }

