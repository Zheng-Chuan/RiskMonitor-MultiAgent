"""
TaskGraph 契约定义与归一化.

用于将线性 plan_steps 升级为显式任务图产物, 为 7.1 的任务图调度器做准备.
"""

from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.utils import is_non_empty_str

TASK_GRAPH_SCHEMA_VERSION = "task_graph.v1"

_ALLOWED_NODE_KINDS = {
    "tool_call",
    "delegate",
    "ask_human",
    "analyze",
    "finalize",
    "stop",
    "replan",
}

_ALLOWED_NODE_STATUSES = {
    "pending",
    "ready",
    "running",
    "completed",
    "failed",
    "blocked",
    "skipped",
}


def validate_task_graph(graph: dict[str, Any]) -> tuple[bool, list[str]]:
    """验证 TaskGraph."""
    if not isinstance(graph, dict):
        return False, ["task_graph must be dict"]

    errors: list[str] = []

    version = graph.get("schema_version")
    if version is not None and not is_non_empty_str(version):
        errors.append("bad_task_graph_schema_version")

    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append("bad_task_graph_nodes")
        return False, errors

    step_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("bad_task_graph_node")
            continue

        step_id = node.get("step_id")
        if not is_non_empty_str(step_id):
            errors.append("bad_task_graph_step_id")
        else:
            sid = str(step_id)
            if sid in step_ids:
                errors.append("duplicate_task_graph_step_id")
            step_ids.add(sid)

        kind = node.get("kind")
        if not is_non_empty_str(kind) or str(kind) not in _ALLOWED_NODE_KINDS:
            errors.append("bad_task_graph_kind")

        status = node.get("status")
        if status is not None and (not is_non_empty_str(status) or str(status) not in _ALLOWED_NODE_STATUSES):
            errors.append("bad_task_graph_status")

        parent_id = node.get("parent_id")
        if parent_id is not None and not is_non_empty_str(parent_id):
            errors.append("bad_task_graph_parent_id")

        if not is_non_empty_str(node.get("reason")):
            errors.append("bad_task_graph_reason")

        evidence = node.get("evidence")
        if evidence is not None and not isinstance(evidence, dict):
            errors.append("bad_task_graph_evidence")

        if str(kind) == "delegate" and not is_non_empty_str(node.get("target_agent")):
            errors.append("bad_task_graph_delegate_target_agent")

    edges = graph.get("edges", [])
    if not isinstance(edges, list):
        errors.append("bad_task_graph_edges")
    else:
        for edge in edges:
            if not isinstance(edge, dict):
                errors.append("bad_task_graph_edge")
                continue
            from_step_id = edge.get("from_step_id")
            to_step_id = edge.get("to_step_id")
            if not is_non_empty_str(from_step_id) or not is_non_empty_str(to_step_id):
                errors.append("bad_task_graph_edge_ref")
                continue
            if str(from_step_id) not in step_ids or str(to_step_id) not in step_ids:
                errors.append("unknown_task_graph_edge_ref")

    return len(errors) == 0, errors


def build_task_graph_from_plan_steps(plan_steps: list[dict[str, Any]]) -> dict[str, Any]:
    """从线性 plan_steps 构建最小 TaskGraph."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    previous_step_id: str | None = None

    for index, raw_step in enumerate(plan_steps):
        step = dict(raw_step) if isinstance(raw_step, dict) else {}
        step_id = str(step.get("step_id") or f"s{index + 1}")
        parent_id = step.get("parent_id")
        if parent_id is None and previous_step_id is not None:
            parent_id = previous_step_id

        node = {
            "step_id": step_id,
            "parent_id": parent_id,
            "kind": step.get("kind") or "analyze",
            "status": step.get("status") or "pending",
            "reason": step.get("reason") or "缺少原因说明 已自动回填",
            "evidence": step.get("evidence") if isinstance(step.get("evidence"), dict) else {"fields": ["plan_steps"]},
        }

        for key in ("target_agent", "instruction", "tool_name", "params", "condition", "replan_from_step_id"):
            if key in step:
                node[key] = step.get(key)

        nodes.append(node)

        if previous_step_id is not None:
            edges.append(
                {
                    "from_step_id": previous_step_id,
                    "to_step_id": step_id,
                    "condition": "always",
                }
            )
        previous_step_id = step_id

    return {
        "schema_version": TASK_GRAPH_SCHEMA_VERSION,
        "nodes": nodes,
        "edges": edges,
    }


def normalize_task_graph(graph: dict[str, Any], *, plan_steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """归一化 TaskGraph. 如果缺失则从 plan_steps 自动生成."""
    source = dict(graph) if isinstance(graph, dict) else {}

    if not isinstance(source.get("nodes"), list) or not source.get("nodes"):
        return build_task_graph_from_plan_steps(plan_steps or [])

    normalized = {
        "schema_version": source.get("schema_version") or TASK_GRAPH_SCHEMA_VERSION,
        "nodes": [],
        "edges": source.get("edges") if isinstance(source.get("edges"), list) else [],
    }

    for index, raw_node in enumerate(source.get("nodes", [])):
        node = dict(raw_node) if isinstance(raw_node, dict) else {}
        step_id = str(node.get("step_id") or f"s{index + 1}")
        normalized_node = {
            "step_id": step_id,
            "parent_id": node.get("parent_id"),
            "kind": node.get("kind") or "analyze",
            "status": node.get("status") or "pending",
            "reason": node.get("reason") or "缺少原因说明 已自动回填",
            "evidence": node.get("evidence") if isinstance(node.get("evidence"), dict) else {"fields": ["task_graph"]},
        }
        for key in ("target_agent", "instruction", "tool_name", "params", "condition", "replan_from_step_id"):
            if key in node:
                normalized_node[key] = node.get(key)
        normalized["nodes"].append(normalized_node)

    if not normalized["edges"]:
        prev_step_id: str | None = None
        for node in normalized["nodes"]:
            step_id = str(node["step_id"])
            if prev_step_id is not None:
                normalized["edges"].append(
                    {
                        "from_step_id": prev_step_id,
                        "to_step_id": step_id,
                        "condition": "always",
                    }
                )
            prev_step_id = step_id

    return normalized


__all__ = [
    "TASK_GRAPH_SCHEMA_VERSION",
    "build_task_graph_from_plan_steps",
    "normalize_task_graph",
    "validate_task_graph",
]
