"""
最小 TaskGraph 执行器.

当前阶段只让 TaskGraph 真正接管 specialist 执行路径.
先支持:
- delegate
- finalize
- stop

其余节点类型先显式报错, 不再静默忽略.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any, Awaitable, Callable

from riskmonitor_multiagent.contracts.agent_messages import validate_agent_receipt
from riskmonitor_multiagent.contracts.approval import (
    build_approval_summary_text,
    normalize_approval_record,
    normalize_approval_request,
)
from riskmonitor_multiagent.contracts.task_graph import normalize_task_graph
from riskmonitor_multiagent.orchestration.tool_executor import execute_agent_command, new_agent_command
from riskmonitor_multiagent.orchestration.tool_registry import get_tool_meta
from riskmonitor_multiagent.proactive_agents import ProactiveAgentResult
from riskmonitor_multiagent.utils.ids import new_command_id, new_run_id

DelegateHandler = Callable[..., Awaitable[ProactiveAgentResult]]
NodeResultHandler = Callable[..., Awaitable[None]]


class TaskGraphExecutor:
    """执行最小 TaskGraph."""

    def __init__(
        self,
        *,
        delegate_handlers: dict[str, DelegateHandler],
        on_node_completed: NodeResultHandler | None = None,
    ) -> None:
        self._delegate_handlers = dict(delegate_handlers)
        self._on_node_completed = on_node_completed

    async def execute(
        self,
        *,
        task: dict[str, Any],
        task_graph: dict[str, Any],
        execution_state: dict[str, Any] | None = None,
        resume_from_step_id: str | None = None,
    ) -> dict[str, Any]:
        graph = normalize_task_graph(
            task_graph,
            plan_steps=task_graph.get("plan_steps") if isinstance(task_graph, dict) and isinstance(task_graph.get("plan_steps"), list) else [],
        )
        nodes = [dict(node) for node in graph.get("nodes", []) if isinstance(node, dict)]
        edges = [dict(edge) for edge in graph.get("edges", []) if isinstance(edge, dict)]
        prior_state = dict(execution_state) if isinstance(execution_state, dict) else {}
        completed = self._extract_completed_steps(prior_state)
        node_outputs = self._extract_node_outputs(prior_state)
        delegate_results = self._restore_delegate_results(prior_state)
        receipts = self._extract_receipts(prior_state)
        approval_records = self._extract_approval_records(prior_state)
        execution_trace = list(prior_state.get("trace", [])) if isinstance(prior_state.get("trace"), list) else []
        retry_records = list(prior_state.get("retry_records", [])) if isinstance(prior_state.get("retry_records"), list) else []
        errors = list(prior_state.get("errors", [])) if isinstance(prior_state.get("errors"), list) else []
        resume_history = list(prior_state.get("resume_history", [])) if isinstance(prior_state.get("resume_history"), list) else []
        if resume_from_step_id:
            # 最新一次恢复放在最前面 便于调用方直接读取当前恢复入口.
            resume_history.insert(
                0,
                {
                    "resume_from_step_id": resume_from_step_id,
                    "mode": "step_resume",
                }
            )

        dependency_map: dict[str, set[str]] = {str(node["step_id"]): set() for node in nodes}
        for node in nodes:
            step_id = str(node["step_id"])
            parent_id = node.get("parent_id")
            if isinstance(parent_id, str) and parent_id.strip():
                dependency_map[step_id].add(parent_id.strip())

        for edge in edges:
            from_step_id = edge.get("from_step_id")
            to_step_id = edge.get("to_step_id")
            if isinstance(from_step_id, str) and from_step_id.strip() and isinstance(to_step_id, str) and to_step_id.strip():
                dependency_map.setdefault(to_step_id.strip(), set()).add(from_step_id.strip())

        remaining = {str(node["step_id"]): node for node in nodes}
        final_output: dict[str, Any] = {}
        status = "completed"
        failed_step_id: str | None = None
        blocked_step_id: str | None = None

        for node in nodes:
            step_id = str(node["step_id"])
            if step_id in completed and not self._should_resume_node(step_id=step_id, resume_from_step_id=resume_from_step_id, dependency_map=dependency_map):
                node["status"] = "completed"
                remaining.pop(step_id, None)
            elif self._should_resume_node(step_id=step_id, resume_from_step_id=resume_from_step_id, dependency_map=dependency_map):
                node["status"] = "pending"
                completed.discard(step_id)
                node_outputs.pop(step_id, None)

        # 清理需要从失败点之后重新执行的派生节点状态
        if resume_from_step_id:
            for step_id in list(node_outputs.keys()):
                if self._should_resume_node(step_id=step_id, resume_from_step_id=resume_from_step_id, dependency_map=dependency_map):
                    node_outputs.pop(step_id, None)
                    completed.discard(step_id)

        while remaining:
            ready_nodes = [
                node
                for step_id, node in remaining.items()
                if dependency_map.get(step_id, set()).issubset(completed)
            ]
            if not ready_nodes:
                status = "failed"
                for node in remaining.values():
                    node["status"] = "blocked"
                errors.append("task_graph_stalled")
                break

            results = await asyncio.gather(
                *(
                    self._execute_node_with_retry(
                        task=task,
                        node=node,
                        node_outputs=node_outputs,
                    )
                    for node in ready_nodes
                )
            )

            should_stop = False
            for node, node_result in zip(ready_nodes, results):
                step_id = str(node["step_id"])
                node["status"] = node_result["status"]
                node["attempt_count"] = node_result.get("attempt_count", 1)
                if isinstance(node_result.get("evidence"), dict):
                    node["evidence"] = node_result["evidence"]
                if "output_ref" in node_result:
                    node["output_ref"] = node_result["output_ref"]
                if isinstance(node_result.get("command_id"), str) and node_result.get("command_id"):
                    node["command_id"] = node_result["command_id"]
                if isinstance(node_result.get("error"), str) and node_result.get("error"):
                    node["last_error"] = node_result["error"]
                if isinstance(node_result.get("failure_classification"), str) and node_result.get("failure_classification"):
                    node["failure_classification"] = node_result["failure_classification"]
                if isinstance(node_result.get("retry_records"), list):
                    retry_records.extend(node_result["retry_records"])
                if isinstance(node_result.get("receipt"), dict):
                    receipt = dict(node_result["receipt"])
                    receipts = [
                        existing
                        for existing in receipts
                        if not (
                            isinstance(existing, dict)
                            and (
                                str(existing.get("command_id") or "") == str(receipt.get("command_id") or "")
                                or str(existing.get("step_id") or "") == step_id
                            )
                        )
                    ]
                    receipt["step_id"] = step_id
                    receipts.append(receipt)
                if isinstance(node_result.get("approval_record"), dict):
                    approval_record = dict(node_result["approval_record"])
                    approval_records = [
                        existing
                        for existing in approval_records
                        if not (
                            isinstance(existing, dict)
                            and str(existing.get("approval_id") or "") == str(approval_record.get("approval_id") or "")
                        )
                    ]
                    approval_records.append(approval_record)

                execution_trace.append(
                    {
                        "step_id": step_id,
                        "kind": node.get("kind"),
                        "status": node_result["status"],
                        "target_agent": node.get("target_agent"),
                        "tool_name": node_result.get("tool_name") or node.get("tool_name"),
                        "command_id": node_result.get("command_id"),
                        "error": node_result.get("error"),
                        "attempt_count": node_result.get("attempt_count", 1),
                        "failure_classification": node_result.get("failure_classification"),
                        "started_at_ms": node_result.get("started_at_ms"),
                        "finished_at_ms": node_result.get("finished_at_ms"),
                        "latency_ms": node_result.get("latency_ms"),
                        "input_sources": node_result.get("input_sources", []),
                        "receipt_command_ids": node_result.get("receipt_command_ids", []),
                        "approval_record": node_result.get("approval_record"),
                    }
                )
                if self._on_node_completed is not None:
                    await self._on_node_completed(
                        node=dict(node),
                        trace_entry=dict(execution_trace[-1]),
                        node_result=dict(node_result),
                    )

                if node_result["status"] == "completed":
                    completed.add(step_id)
                    if isinstance(node_result.get("output"), dict):
                        node_outputs[step_id] = node_result["output"]
                    if isinstance(node_result.get("delegate_result"), ProactiveAgentResult):
                        delegate_results[node_result["delegate_result"].meta["agent_name"]] = node_result["delegate_result"]
                    if isinstance(node_result.get("final_output"), dict):
                        final_output = node_result["final_output"]
                elif node_result["status"] == "stopped":
                    completed.add(step_id)
                    should_stop = True
                    status = "stopped"
                    final_output = node_result.get("final_output") or {}
                elif node_result["status"] == "blocked":
                    should_stop = True
                    status = "blocked"
                    blocked_step_id = step_id
                    if isinstance(node_result.get("output"), dict):
                        node_outputs[step_id] = node_result["output"]
                    err = node_result.get("error")
                    if isinstance(err, str) and err:
                        errors.append(err)
                else:
                    status = "failed"
                    err = node_result.get("error")
                    if isinstance(err, str) and err:
                        errors.append(err)
                    failed_step_id = step_id

                remaining.pop(step_id, None)

            if should_stop or status == "failed":
                break

        if not final_output:
            final_output = self._build_fallback_final_output(task=task, delegate_results=delegate_results, receipts=receipts)

        return {
            "status": status,
            "task_graph": {
                "schema_version": graph.get("schema_version"),
                "nodes": nodes,
                "edges": edges,
            },
            "task_graph_execution": {
                "status": status,
                "completed_steps": sorted(completed),
                "failed_step_id": failed_step_id,
                "blocked_step_id": blocked_step_id,
                "errors": errors,
                "node_outputs": node_outputs,
                "delegate_outputs": {
                    agent_name: result.output
                    for agent_name, result in delegate_results.items()
                    if isinstance(result.output, dict)
                },
                "retry_records": retry_records,
                "resume_history": resume_history,
                "resume_ready": failed_step_id is not None,
                "receipts": receipts,
                "approval_records": approval_records,
                "trace": execution_trace,
            },
            "delegate_results": delegate_results,
            "receipts": receipts,
            "approval_records": approval_records,
            "final_output": final_output,
        }

    async def _execute_node_with_retry(
        self,
        *,
        task: dict[str, Any],
        node: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        retry_budget = self._resolve_retry_budget(task=task, node=node)
        retry_records: list[dict[str, Any]] = []
        last_result: dict[str, Any] | None = None

        for attempt in range(retry_budget + 1):
            result = await self._execute_node_once(
                task=task,
                node=node,
                node_outputs=node_outputs,
            )
            result["attempt_count"] = attempt + 1
            last_result = result
            if result["status"] in {"completed", "stopped"}:
                result["retry_records"] = retry_records
                return result

            failure_classification = str(result.get("failure_classification") or "")
            retryable = failure_classification in {"timeout", "dependency", "runtime"}
            retry_records.append(
                {
                    "step_id": str(node.get("step_id") or ""),
                    "attempt": attempt + 1,
                    "failure_classification": failure_classification or "runtime",
                    "error": result.get("error"),
                    "retry_scheduled": retryable and attempt < retry_budget,
                }
            )
            if not retryable or attempt >= retry_budget:
                result["retry_records"] = retry_records
                return result

        assert last_result is not None
        last_result["retry_records"] = retry_records
        return last_result

    async def _execute_node_once(
        self,
        *,
        task: dict[str, Any],
        node: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        timeout_seconds = self._resolve_timeout_seconds(task=task, node=node)
        started_at_ms = time.time() * 1000
        try:
            if timeout_seconds is not None:
                result = await asyncio.wait_for(
                    self._execute_node(task=task, node=node, node_outputs=node_outputs),
                    timeout=timeout_seconds,
                )
            else:
                result = await self._execute_node(task=task, node=node, node_outputs=node_outputs)
            finished_at_ms = time.time() * 1000
            result["started_at_ms"] = started_at_ms
            result["finished_at_ms"] = finished_at_ms
            result["latency_ms"] = finished_at_ms - started_at_ms
            return result
        except asyncio.TimeoutError:
            finished_at_ms = time.time() * 1000
            return {
                "status": "failed",
                "error": f"step_timeout:{str(node.get('step_id') or '')}",
                "failure_classification": "timeout",
                "started_at_ms": started_at_ms,
                "finished_at_ms": finished_at_ms,
                "latency_ms": finished_at_ms - started_at_ms,
            }
        except Exception as exc:  # pragma: no cover - 通过测试中的故障注入覆盖行为
            finished_at_ms = time.time() * 1000
            return {
                "status": "failed",
                "error": str(exc) or exc.__class__.__name__,
                "failure_classification": self._classify_exception(exc),
                "started_at_ms": started_at_ms,
                "finished_at_ms": finished_at_ms,
                "latency_ms": finished_at_ms - started_at_ms,
            }

    async def _execute_node(
        self,
        *,
        task: dict[str, Any],
        node: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        kind = str(node.get("kind") or "")
        step_id = str(node.get("step_id") or "")
        step_approval_result = self._check_step_approval(node=node)
        if step_approval_result is not None:
            return step_approval_result

        if kind == "delegate":
            target_agent = str(node.get("target_agent") or "").strip()
            handler = self._delegate_handlers.get(target_agent)
            if handler is None:
                return {"status": "failed", "error": f"unsupported_delegate_target:{target_agent or 'unknown'}"}

            result = await handler(
                task=task,
                context={
                    "task_graph_node": node,
                    "step_id": step_id,
                    "upstream_outputs": dict(node_outputs),
                    "resume_context": (
                        dict(task.get("resume_context", {}))
                        if isinstance(task.get("resume_context"), dict)
                        else {}
                    ),
                },
            )
            result.meta = dict(result.meta or {})
            result.meta["agent_name"] = target_agent
            return {
                "status": "completed" if result.ok else "failed",
                "output": result.output if isinstance(result.output, dict) else {},
                "delegate_result": result,
                "output_ref": target_agent,
                "evidence": {"task_graph_step_id": step_id, "delegate_agent": target_agent},
                "error": None if result.ok else f"delegate_failed:{target_agent}",
            }

        if kind == "tool_call":
            tool_name = str(node.get("tool_name") or "").strip()
            if not tool_name:
                return {
                    "status": "failed",
                    "error": "missing_tool_name",
                    "failure_classification": "validation",
                }

            meta = get_tool_meta(tool_name)
            if meta is None:
                return {
                    "status": "failed",
                    "error": f"unknown_tool:{tool_name}",
                    "failure_classification": "dependency",
                }

            params = dict(node.get("params")) if isinstance(node.get("params"), dict) else {}
            task_budget = task.get("tool_budget") if isinstance(task.get("tool_budget"), dict) else {}
            if task_budget and "_budget" not in params:
                params["_budget"] = dict(task_budget)
            target_agent = str(node.get("target_agent") or meta.owner or "").strip()
            if not target_agent:
                return {
                    "status": "failed",
                    "error": f"missing_target_agent_for_tool:{tool_name}",
                    "failure_classification": "validation",
                }

            command_id = str(node.get("command_id") or new_command_id())
            run_id = task.get("run_id") if isinstance(task.get("run_id"), str) and task.get("run_id") else None
            if not run_id:
                run_id = task.get("task_id") if isinstance(task.get("task_id"), str) and task.get("task_id") else new_run_id("task_graph")
            timeout_ms = node.get("timeout_ms") if isinstance(node.get("timeout_ms"), int) and node.get("timeout_ms") > 0 else meta.default_timeout_ms
            retry_budget = node.get("retry_budget") if isinstance(node.get("retry_budget"), int) and node.get("retry_budget") >= 0 else 0
            expected_output_schema = (
                str(node.get("expected_output_schema"))
                if isinstance(node.get("expected_output_schema"), str) and node.get("expected_output_schema")
                else "tool_result.v1"
            )
            command = new_agent_command(
                run_id=str(run_id),
                command_id=command_id,
                target_agent=target_agent,
                action=tool_name,
                params=params,
                timeout_ms=int(timeout_ms),
                expected_output_schema=expected_output_schema,
                retry_budget=int(retry_budget),
            )
            receipt = execute_agent_command(command)
            ok_receipt, receipt_errors = validate_agent_receipt(receipt)
            if not ok_receipt:
                return {
                    "status": "failed",
                    "error": "invalid_tool_receipt",
                    "failure_classification": "runtime",
                    "command_id": command_id,
                    "tool_name": tool_name,
                    "receipt": {
                        "schema_version": receipt.get("schema_version"),
                        "run_id": receipt.get("run_id"),
                        "command_id": receipt.get("command_id"),
                        "tool_name": tool_name,
                        "status": "failed",
                        "ok": False,
                        "latency_ms": float(receipt.get("latency_ms") or 0.0),
                        "error": "invalid_tool_receipt",
                        "inputs": params,
                        "outputs": None,
                        "output": None,
                        "evidence": {"receipt_errors": receipt_errors},
                        "artifacts": [],
                        "target_agent": target_agent,
                        "side_effect": bool(meta.capability == "side_effect"),
                        "approval_state": "unknown",
                        "approval_trace": {"required": bool(meta.capability == "side_effect"), "current_state": "unknown", "history": []},
                        "failure_classification": "runtime",
                        "retry_count": 0,
                        "retry_budget": int(retry_budget),
                        "timeout_ms": int(timeout_ms),
                    },
                }

            receipt_command_id = (
                str(receipt.get("command_id"))
                if isinstance(receipt.get("command_id"), str) and receipt.get("command_id")
                else command_id
            )
            output_payload = {
                "tool_name": tool_name,
                "command_id": receipt_command_id,
                "summary": f"tool {tool_name} completed cmd:{receipt_command_id}",
                "receipt_command_ids": [receipt_command_id],
                "result": receipt.get("outputs"),
                "approval_state": receipt.get("approval_state"),
                "approval_trace": receipt.get("approval_trace"),
            }
            error = receipt.get("error")
            status = "completed" if receipt.get("ok") is True else ("blocked" if receipt.get("status") == "blocked" else "failed")
            failure_classification = None if status == "completed" else self._classify_receipt_error(receipt)
            approval_record = self._build_command_approval_record(step_id=step_id, receipt=receipt)
            return {
                "status": status,
                "output": output_payload,
                "output_ref": command_id,
                "evidence": {
                    "task_graph_step_id": step_id,
                    "receipt_command_ids": [receipt_command_id],
                    "tool_name": tool_name,
                    "approval_state": receipt.get("approval_state"),
                },
                "error": error,
                "failure_classification": failure_classification,
                "command_id": receipt_command_id,
                "tool_name": tool_name,
                "receipt": receipt,
                "approval_record": approval_record,
                "receipt_command_ids": [receipt_command_id],
            }

        if kind == "finalize":
            final_output = self._build_finalize_output(task=task, node=node, node_outputs=node_outputs)
            return {
                "status": "completed",
                "output": final_output,
                "final_output": final_output,
                "output_ref": "final_output",
                "evidence": {"task_graph_step_id": step_id, "fields": ["delegate_outputs"]},
                "input_sources": list(final_output.get("sources") or []),
            }

        if kind == "replan":
            return {
                "status": "completed",
                "output": {
                    "replan": True,
                    "reason": node.get("reason"),
                    "replan_from_step_id": node.get("replan_from_step_id"),
                },
                "output_ref": "replan",
                "evidence": {"task_graph_step_id": step_id, "fields": ["critic_plan.issues"]},
            }

        if kind == "stop":
            final_output = {
                "summary": str(node.get("instruction") or "任务已停止"),
                "stopped": True,
                "stop_step_id": step_id,
            }
            return {
                "status": "stopped",
                "output": final_output,
                "final_output": final_output,
                "output_ref": "stop_output",
                "evidence": {"task_graph_step_id": step_id},
            }

        return {"status": "failed", "error": f"unknown_step_kind:{kind or 'unknown'}"}

    def _resolve_retry_budget(self, *, task: dict[str, Any], node: dict[str, Any]) -> int:
        retry_budget = node.get("retry_budget")
        if isinstance(retry_budget, int) and retry_budget >= 0:
            return retry_budget

        policy = task.get("execution_policy") if isinstance(task.get("execution_policy"), dict) else {}
        default_retry_budget = policy.get("default_retry_budget")
        if isinstance(default_retry_budget, int) and default_retry_budget >= 0:
            return default_retry_budget
        return 0

    def _resolve_timeout_seconds(self, *, task: dict[str, Any], node: dict[str, Any]) -> float | None:
        timeout_ms = node.get("timeout_ms")
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            policy = task.get("execution_policy") if isinstance(task.get("execution_policy"), dict) else {}
            timeout_ms = policy.get("default_timeout_ms")
        if isinstance(timeout_ms, int) and timeout_ms > 0:
            return timeout_ms / 1000.0
        return None

    def _classify_exception(self, exc: Exception) -> str:
        if isinstance(exc, (ValueError, TypeError)):
            return "validation"
        if isinstance(exc, (ImportError, LookupError, ConnectionError, OSError)):
            return "dependency"

        msg = str(exc).lower()
        if any(token in msg for token in ("invalid", "validation", "missing param", "bad param", "参数")):
            return "validation"
        if any(token in msg for token in ("dependency", "service unavailable", "connection", "unreachable")):
            return "dependency"
        return "runtime"

    def _extract_completed_steps(self, state: dict[str, Any]) -> set[str]:
        raw = state.get("completed_steps")
        if not isinstance(raw, list):
            return set()
        return {str(step_id) for step_id in raw if isinstance(step_id, str) and step_id.strip()}

    def _extract_node_outputs(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw = state.get("node_outputs")
        if not isinstance(raw, Mapping):
            return {}
        return {
            str(step_id): dict(payload)
            for step_id, payload in raw.items()
            if isinstance(step_id, str) and isinstance(payload, dict)
        }

    def _extract_receipts(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        raw = state.get("receipts")
        if not isinstance(raw, list):
            return []
        return [dict(receipt) for receipt in raw if isinstance(receipt, dict)]

    def _extract_approval_records(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        raw = state.get("approval_records")
        if not isinstance(raw, list):
            return []
        return [dict(record) for record in raw if isinstance(record, dict)]

    def _restore_delegate_results(self, state: dict[str, Any]) -> dict[str, ProactiveAgentResult]:
        raw = state.get("delegate_outputs")
        if not isinstance(raw, Mapping):
            return {}
        restored: dict[str, ProactiveAgentResult] = {}
        for agent_name, payload in raw.items():
            if isinstance(agent_name, str) and isinstance(payload, dict):
                restored[agent_name] = ProactiveAgentResult(
                    ok=True,
                    output=dict(payload),
                    meta={"agent_name": agent_name, "resumed": True},
                )
        return restored

    def _should_resume_node(
        self,
        *,
        step_id: str,
        resume_from_step_id: str | None,
        dependency_map: dict[str, set[str]],
    ) -> bool:
        if not isinstance(resume_from_step_id, str) or not resume_from_step_id.strip():
            return False
        target = resume_from_step_id.strip()
        if step_id == target:
            return True
        return self._depends_on(step_id=step_id, target_step_id=target, dependency_map=dependency_map)

    def _depends_on(
        self,
        *,
        step_id: str,
        target_step_id: str,
        dependency_map: dict[str, set[str]],
    ) -> bool:
        stack = list(dependency_map.get(step_id, set()))
        visited: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            if current == target_step_id:
                return True
            stack.extend(dependency_map.get(current, set()))
        return False

    def _build_finalize_output(
        self,
        *,
        task: dict[str, Any],
        node: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        sections: list[str] = []
        sources: list[str] = []
        receipt_command_ids: list[str] = []

        for output_ref, payload in node_outputs.items():
            if not isinstance(payload, dict):
                continue
            summary = payload.get("summary")
            report = payload.get("report")
            ids = payload.get("receipt_command_ids")
            if isinstance(ids, list):
                for receipt_id in ids:
                    if isinstance(receipt_id, str) and receipt_id and receipt_id not in receipt_command_ids:
                        receipt_command_ids.append(receipt_id)
            if isinstance(summary, str) and summary.strip():
                sections.append(summary.strip())
                sources.append(output_ref)
            elif isinstance(report, str) and report.strip():
                sections.append(report.strip())
                sources.append(output_ref)

        if not sections:
            payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
            default_summary = payload.get("content") if isinstance(payload.get("content"), str) else "任务已执行"
            sections.append(default_summary)

        return {
            "summary": "\n".join(sections),
            "sources": sources,
            "receipt_command_ids": receipt_command_ids,
            "finalize_reason": node.get("reason"),
            "task_graph_completed": True,
        }

    def _build_fallback_final_output(
        self,
        *,
        task: dict[str, Any],
        delegate_results: dict[str, ProactiveAgentResult],
        receipts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        node_outputs = {
            name: result.output
            for name, result in delegate_results.items()
            if isinstance(result.output, dict)
        }
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            command_id = receipt.get("command_id")
            if isinstance(command_id, str) and command_id:
                node_outputs[command_id] = {
                    "summary": f"tool {receipt.get('tool_name')} completed cmd:{command_id}",
                    "receipt_command_ids": [command_id],
                }
        return self._build_finalize_output(
            task=task,
            node={"reason": "自动生成最终结论"},
            node_outputs=node_outputs,
        )

    def _classify_receipt_error(self, receipt: dict[str, Any]) -> str:
        classification = receipt.get("failure_classification")
        if isinstance(classification, str) and classification:
            return classification
        error = str(receipt.get("error") or "")
        if error in {"approval_required", "approval_reason_required", "rbac_denied", "policy_denied"}:
            return "permission"
        if error in {"approval_rejected", "approval_expired"}:
            return "permission"
        if error == "invalid_command":
            return "validation"
        if error in {"unknown_action", "handler_missing"}:
            return "dependency"
        if error == "tool_timeout":
            return "timeout"
        return "runtime"

    def _check_step_approval(self, *, node: dict[str, Any]) -> dict[str, Any] | None:
        approval = node.get("approval")
        if not isinstance(approval, dict) or approval.get("required") is not True:
            return None

        request = normalize_approval_request(
            {
                "level": "step",
                "approval_id": approval.get("approval_id") or f"step:{node.get('step_id')}",
                "step_id": node.get("step_id"),
                "reason": approval.get("reason") or node.get("reason"),
                "risk_level": approval.get("risk_level") or "HIGH",
                "impact_scope": approval.get("impact_scope") or [str(node.get("target_agent") or node.get("kind") or "system")],
                "recommended_action": approval.get("recommended_action") or "review_and_resume_step",
            }
        )
        explicit_state = str(approval.get("state") or "pending").strip().lower()
        actor = approval.get("actor") if isinstance(approval.get("actor"), str) and approval.get("actor") else None
        note = approval.get("note") if isinstance(approval.get("note"), str) and approval.get("note") else None

        if explicit_state in {"approved", "resumed"}:
            return None

        if explicit_state == "rejected":
            record = normalize_approval_record(
                {
                    "request": request,
                    "state": "rejected",
                    "actor": actor,
                    "note": note,
                    "error": "approval_rejected",
                }
            )
            return {
                "status": "blocked",
                "output": {
                    "summary": build_approval_summary_text(record),
                    "approval_request": request,
                },
                "approval_record": record,
                "error": "approval_rejected",
                "failure_classification": "permission",
            }

        if explicit_state == "expired":
            record = normalize_approval_record(
                {
                    "request": request,
                    "state": "expired",
                    "actor": actor,
                    "note": note,
                    "error": "approval_expired",
                }
            )
            return {
                "status": "blocked",
                "output": {
                    "summary": build_approval_summary_text(record),
                    "approval_request": request,
                },
                "approval_record": record,
                "error": "approval_expired",
                "failure_classification": "permission",
            }

        record = normalize_approval_record(
            {
                "request": request,
                "state": "pending",
                "actor": actor,
                "note": note,
                "error": "approval_required",
            }
        )
        return {
            "status": "blocked",
            "output": {
                "summary": build_approval_summary_text(record),
                "approval_request": request,
            },
            "approval_record": record,
            "error": "approval_required",
            "failure_classification": "permission",
        }

    def _build_command_approval_record(self, *, step_id: str, receipt: dict[str, Any]) -> dict[str, Any] | None:
        approval_trace = receipt.get("approval_trace")
        if not isinstance(approval_trace, dict) or not approval_trace.get("required"):
            return None
        request = receipt.get("approval_request")
        if not isinstance(request, dict):
            request = {
                "level": "command",
                "approval_id": f"command:{receipt.get('command_id')}",
                "step_id": step_id,
                "command_id": receipt.get("command_id"),
                "tool_name": receipt.get("tool_name"),
                "reason": ((receipt.get("evidence") or {}).get("reason") if isinstance(receipt.get("evidence"), dict) else None) or "approval_required",
                "risk_level": (
                    (((receipt.get("inputs") or {}).get("_event") or {}).get("severity"))
                    if isinstance((receipt.get("inputs") or {}).get("_event"), dict)
                    else None
                ) or "HIGH",
                "impact_scope": ["system"],
                "recommended_action": "review_and_confirm_command_execution",
            }
        record = normalize_approval_record(
            {
                "request": request,
                "state": receipt.get("approval_state") or approval_trace.get("current_state") or "pending",
                "actor": ((receipt.get("inputs") or {}).get("approval") or {}).get("actor") if isinstance((receipt.get("inputs") or {}).get("approval"), dict) else None,
                "note": ((receipt.get("inputs") or {}).get("approval") or {}).get("note") if isinstance((receipt.get("inputs") or {}).get("approval"), dict) else None,
                "error": receipt.get("error"),
            }
        )
        record["step_id"] = step_id
        record["command_id"] = receipt.get("command_id")
        record["tool_name"] = receipt.get("tool_name")
        return record


__all__ = ["TaskGraphExecutor"]
