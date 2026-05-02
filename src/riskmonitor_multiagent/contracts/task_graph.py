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
    dependency_map: dict[str, set[str]] = {}
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
            dependency_map.setdefault(sid, set())

        kind = node.get("kind")
        if not is_non_empty_str(kind) or str(kind) not in _ALLOWED_NODE_KINDS:
            errors.append("bad_task_graph_kind")

        status = node.get("status")
        if status is not None and (not is_non_empty_str(status) or str(status) not in _ALLOWED_NODE_STATUSES):
            errors.append("bad_task_graph_status")

        parent_id = node.get("parent_id")
        if parent_id is not None and not is_non_empty_str(parent_id):
            errors.append("bad_task_graph_parent_id")
        elif is_non_empty_str(parent_id) and is_non_empty_str(step_id):
            dependency_map.setdefault(str(step_id), set()).add(str(parent_id))

        if not is_non_empty_str(node.get("reason")):
            errors.append("bad_task_graph_reason")

        evidence = node.get("evidence")
        if evidence is not None and not isinstance(evidence, dict):
            errors.append("bad_task_graph_evidence")

        if str(kind) == "delegate" and not is_non_empty_str(node.get("target_agent")):
            errors.append("bad_task_graph_delegate_target_agent")
        if str(kind) == "tool_call" and not is_non_empty_str(node.get("tool_name")):
            errors.append("bad_task_graph_tool_name")

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
                continue
            dependency_map.setdefault(str(to_step_id), set()).add(str(from_step_id))

    for node in nodes:
        if not isinstance(node, dict):
            continue
        step_id = node.get("step_id")
        parent_id = node.get("parent_id")
        if is_non_empty_str(step_id) and is_non_empty_str(parent_id) and str(parent_id) not in step_ids:
            errors.append("unknown_task_graph_parent_id")

    if not any(error in {"bad_task_graph_nodes", "bad_task_graph_node"} for error in errors):
        if _has_cycle(step_ids=step_ids, dependency_map=dependency_map):
            errors.append("cyclic_task_graph")

    return len(errors) == 0, errors


def _has_cycle(*, step_ids: set[str], dependency_map: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def _visit(step_id: str) -> bool:
        if step_id in visited:
            return False
        if step_id in visiting:
            return True
        visiting.add(step_id)
        for parent_id in dependency_map.get(step_id, set()):
            if parent_id in step_ids and _visit(parent_id):
                return True
        visiting.remove(step_id)
        visited.add(step_id)
        return False

    for step_id in step_ids:
        if _visit(step_id):
            return True
    return False


def build_task_graph_from_plan_steps(plan_steps: list[dict[str, Any]]) -> dict[str, Any]:
    """从线性 plan_steps 构建最小 TaskGraph."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    prior_step_ids: list[str] = []

    for index, raw_step in enumerate(plan_steps):
        step = dict(raw_step) if isinstance(raw_step, dict) else {}
        step_id = str(step.get("step_id") or f"s{index + 1}")
        parent_id = step.get("parent_id")

        node = {
            "step_id": step_id,
            "parent_id": parent_id,
            "kind": step.get("kind") or "analyze",
            "status": step.get("status") or "pending",
            "reason": step.get("reason") or "缺少原因说明 已自动回填",
            "evidence": step.get("evidence") if isinstance(step.get("evidence"), dict) else {"fields": ["plan_steps"]},
        }

        for key in (
            "target_agent",
            "instruction",
            "tool_name",
            "command_id",
            "expected_output_schema",
            "params",
            "approval",
            "condition",
            "replan_from_step_id",
            "timeout_ms",
            "retry_budget",
            "output_ref",
            "attempt_count",
            "last_error",
            "failure_classification",
        ):
            if key in step:
                node[key] = step.get(key)

        nodes.append(node)

        if is_non_empty_str(parent_id):
            edges.append(
                {
                    "from_step_id": str(parent_id),
                    "to_step_id": step_id,
                    "condition": "always",
                }
            )
        elif str(node["kind"]) == "finalize":
            for prior_step_id in prior_step_ids:
                edges.append(
                    {
                        "from_step_id": prior_step_id,
                        "to_step_id": step_id,
                        "condition": "always",
                    }
                )
        elif str(node["kind"]) == "stop" and prior_step_ids:
            edges.append(
                {
                    "from_step_id": prior_step_ids[-1],
                    "to_step_id": step_id,
                    "condition": "always",
                }
            )

        prior_step_ids.append(step_id)

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
        for key in (
            "target_agent",
            "instruction",
            "tool_name",
            "command_id",
            "expected_output_schema",
            "params",
            "approval",
            "condition",
            "replan_from_step_id",
            "timeout_ms",
            "retry_budget",
            "output_ref",
            "attempt_count",
            "last_error",
            "failure_classification",
        ):
            if key in node:
                normalized_node[key] = node.get(key)
        normalized["nodes"].append(normalized_node)

    if not normalized["edges"]:
        prior_step_ids: list[str] = []
        for node in normalized["nodes"]:
            step_id = str(node["step_id"])
            parent_id = node.get("parent_id")
            kind = str(node.get("kind") or "analyze")
            if is_non_empty_str(parent_id):
                normalized["edges"].append(
                    {
                        "from_step_id": str(parent_id),
                        "to_step_id": step_id,
                        "condition": "always",
                    }
                )
            elif kind == "finalize":
                for prior_step_id in prior_step_ids:
                    normalized["edges"].append(
                        {
                            "from_step_id": prior_step_id,
                            "to_step_id": step_id,
                            "condition": "always",
                        }
                    )
            elif kind == "stop" and prior_step_ids:
                normalized["edges"].append(
                    {
                        "from_step_id": prior_step_ids[-1],
                        "to_step_id": step_id,
                        "condition": "always",
                    }
                )
            prior_step_ids.append(step_id)

    return normalized


def append_replan_subgraph(
    base_graph: dict[str, Any],
    replan_graph: dict[str, Any],
    *,
    reason: str,
    replan_index: int = 1,
) -> dict[str, Any]:
    """把新的重规划子图接到原任务图后面."""
    base = normalize_task_graph(
        base_graph,
        plan_steps=base_graph.get("plan_steps") if isinstance(base_graph, dict) and isinstance(base_graph.get("plan_steps"), list) else [],
    )
    new = normalize_task_graph(
        replan_graph,
        plan_steps=replan_graph.get("plan_steps") if isinstance(replan_graph, dict) and isinstance(replan_graph.get("plan_steps"), list) else [],
    )

    existing_nodes = [dict(node) for node in base.get("nodes", []) if isinstance(node, dict)]
    existing_edges = [dict(edge) for edge in base.get("edges", []) if isinstance(edge, dict)]

    replan_step_id = f"rp{replan_index}"
    existing_step_ids = {str(node.get("step_id")) for node in existing_nodes if is_non_empty_str(node.get("step_id"))}
    while replan_step_id in existing_step_ids:
        replan_index += 1
        replan_step_id = f"rp{replan_index}"

    outgoing_counts: dict[str, int] = {}
    incoming_counts: dict[str, int] = {}
    for edge in existing_edges:
        from_step_id = edge.get("from_step_id")
        to_step_id = edge.get("to_step_id")
        if is_non_empty_str(from_step_id):
            outgoing_counts[str(from_step_id)] = outgoing_counts.get(str(from_step_id), 0) + 1
        if is_non_empty_str(to_step_id):
            incoming_counts[str(to_step_id)] = incoming_counts.get(str(to_step_id), 0) + 1

    terminal_step_ids = [
        str(node["step_id"])
        for node in existing_nodes
        if is_non_empty_str(node.get("step_id")) and outgoing_counts.get(str(node["step_id"]), 0) == 0
    ]

    replan_node = {
        "step_id": replan_step_id,
        "parent_id": terminal_step_ids[-1] if terminal_step_ids else None,
        "kind": "replan",
        "status": "pending",
        "reason": reason or "critic rejected previous plan",
        "evidence": {"fields": ["critic_plan.issues", "critic_plan.suggested_fixes"]},
    }
    existing_nodes.append(replan_node)
    for terminal_step_id in terminal_step_ids:
        existing_edges.append(
            {
                "from_step_id": terminal_step_id,
                "to_step_id": replan_step_id,
                "condition": "critic_rejected",
            }
        )

    renamed_nodes: list[dict[str, Any]] = []
    step_id_map: dict[str, str] = {}
    for index, raw_node in enumerate(new.get("nodes", []), start=1):
        node = dict(raw_node)
        old_step_id = str(node.get("step_id") or f"s{index}")
        new_step_id = f"{replan_step_id}_{old_step_id}"
        step_id_map[old_step_id] = new_step_id
        node["step_id"] = new_step_id
        parent_id = node.get("parent_id")
        if is_non_empty_str(parent_id):
            node["parent_id"] = step_id_map.get(str(parent_id), f"{replan_step_id}_{parent_id}")
        else:
            node["parent_id"] = replan_step_id
        node["replan_from_step_id"] = replan_step_id
        renamed_nodes.append(node)

    existing_nodes.extend(renamed_nodes)

    new_edges = [dict(edge) for edge in new.get("edges", []) if isinstance(edge, dict)]
    incoming_new_counts: dict[str, int] = {}
    for edge in new_edges:
        to_step_id = edge.get("to_step_id")
        if is_non_empty_str(to_step_id):
            incoming_new_counts[str(to_step_id)] = incoming_new_counts.get(str(to_step_id), 0) + 1
        from_step_id = edge.get("from_step_id")
        to_step_id = edge.get("to_step_id")
        if is_non_empty_str(from_step_id) and is_non_empty_str(to_step_id):
            existing_edges.append(
                {
                    "from_step_id": step_id_map[str(from_step_id)],
                    "to_step_id": step_id_map[str(to_step_id)],
                    "condition": edge.get("condition") or "always",
                }
            )

    entry_step_ids: list[str] = []
    for node in renamed_nodes:
        step_id = str(node.get("step_id") or "")
        old_step_id = step_id.replace(f"{replan_step_id}_", "", 1)
        if incoming_new_counts.get(old_step_id, 0) == 0:
            entry_step_ids.append(step_id)
    if not entry_step_ids and renamed_nodes:
        entry_step_ids = [str(renamed_nodes[0]["step_id"])]

    for entry_step_id in entry_step_ids:
        existing_edges.append(
            {
                "from_step_id": replan_step_id,
                "to_step_id": entry_step_id,
                "condition": "always",
            }
        )

    return {
        "schema_version": TASK_GRAPH_SCHEMA_VERSION,
        "nodes": existing_nodes,
        "edges": existing_edges,
    }


__all__ = [
    "TASK_GRAPH_SCHEMA_VERSION",
    "build_task_graph_from_plan_steps",
    "append_replan_subgraph",
    "normalize_task_graph",
    "validate_task_graph",
]
