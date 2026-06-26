"""
记忆写入操作模块.

包含高级记忆写入编排方法(record_working_memory, persist_run_artifacts 等).
通过 Mixin 模式集成到 MemoryStore.
"""

from __future__ import annotations

import asyncio
from typing import Any

from riskmonitor_multiagent.contracts.approval import build_approval_summary_text
from riskmonitor_multiagent.memory.memory_helpers import (
    _DEFAULT_PRIVATE_AGENT_IDS,
    agent_perspective,
    build_experience_policy,
    build_long_term_experience_content,
    build_private_task_snapshot,
    canonical_agent_id,
    derive_lesson_text,
    derive_summary_text,
    extract_confidence,
    extract_content_text,
    make_json_safe,
)


class MemoryWriteOperationsMixin:
    """记忆写入操作 Mixin,提供高级写入编排方法."""

    async def record_working_memory(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        trace_entry: dict[str, Any],
        node: dict[str, Any] | None = None,
        node_result: dict[str, Any] | None = None,
        private_memory_enabled: bool = True,
    ) -> dict[str, Any]:
        """记录 step 级 working memory."""
        step_id = str(trace_entry.get("step_id") or "unknown")
        kind = str(trace_entry.get("kind") or "unknown")
        status = str(trace_entry.get("status") or "unknown")
        tool_name = trace_entry.get("tool_name")
        target_agent = canonical_agent_id(
            trace_entry.get("target_agent") or (node or {}).get("target_agent"),
        )
        error = trace_entry.get("error")
        content = extract_content_text(task)
        task_phase = "execution"
        confidence = extract_confidence(node_result)

        text_parts = [f"step {step_id}", f"kind={kind}", f"status={status}"]
        if isinstance(target_agent, str) and target_agent:
            text_parts.append(f"agent={target_agent}")
        if isinstance(tool_name, str) and tool_name:
            text_parts.append(f"tool={tool_name}")
        if isinstance(error, str) and error:
            text_parts.append(f"error={error}")
        if content:
            text_parts.append(f"task={content[:80]}")

        shared_entry = await self.append(
            {
                "agent_id": target_agent or "orchestrator",
                "scope": "shared",
                "kind": "working_memory",
                "memory_type": "episodic",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "task_graph_execution",
                "created_by": target_agent or "task_graph_executor",
                "agent_role": target_agent or "orchestrator",
                "agent_perspective": agent_perspective(target_agent or "orchestrator"),
                "task_phase": task_phase,
                "confidence": confidence,
                "trace_ref": {
                    "run_id": run_id,
                    "step_id": step_id,
                    "command_id": trace_entry.get("command_id"),
                },
                "content": {
                    "text": " ".join(text_parts),
                    "task_id": task.get("task_id"),
                    "payload": make_json_safe(task.get("payload")),
                    "trace_entry": make_json_safe(trace_entry),
                    "node_result": make_json_safe(node_result if isinstance(node_result, dict) else {}),
                },
                "tags": [kind, status, task_phase],
            }
        )

        if private_memory_enabled and isinstance(target_agent, str) and target_agent in _DEFAULT_PRIVATE_AGENT_IDS:
            private_snapshot = build_private_task_snapshot(
                agent_id=target_agent, task=task,
                trace_entry=trace_entry, node_result=node_result or {},
            )
            await self.append(
                {
                    "agent_id": target_agent,
                    "scope": "private",
                    "kind": "private_task_state",
                    "memory_type": "episodic",
                    "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                    "run_id": run_id,
                    "source": "task_graph_execution",
                    "created_by": target_agent,
                    "agent_role": target_agent,
                    "agent_perspective": agent_perspective(target_agent),
                    "task_phase": task_phase,
                    "confidence": confidence,
                    "trace_ref": {
                        "run_id": run_id,
                        "step_id": step_id,
                        "command_id": trace_entry.get("command_id"),
                    },
                    "content": private_snapshot,
                    "tags": ["private_task_memory", status],
                },
                agent_id=target_agent,
                scope="private",
            )

        return shared_entry

    async def persist_run_artifacts(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        final_output: dict[str, Any],
        critic_final: dict[str, Any],
    ) -> dict[str, Any]:
        """保存 run summary 和 procedural lesson."""
        run_summary = critic_final.get("run_summary") if isinstance(critic_final, dict) else {}
        if not isinstance(run_summary, dict):
            run_summary = {}
        summary_text = run_summary.get("text")
        if not isinstance(summary_text, str) or not summary_text.strip():
            summary_text = derive_summary_text(final_output=final_output)
        key_points = run_summary.get("key_points")
        if not isinstance(key_points, list):
            key_points = []

        summary_payload = {
            "text": summary_text,
            "key_points": key_points,
            "receipt_command_ids": list(final_output.get("receipt_command_ids") or []),
            "task_id": task.get("task_id"),
            "session_id": task.get("session_id"),
        }
        await self.upsert_run_summary(run_id=run_id, summary=summary_payload)
        summary_entry = await self.append(
            {
                "agent_id": "critic",
                "scope": "shared",
                "kind": "final",
                "memory_type": "episodic",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "critic_final_review",
                "created_by": "critic",
                "trace_ref": {"run_id": run_id},
                "content": summary_payload,
                "tags": ["summary"],
            }
        )

        lesson_text = derive_lesson_text(final_output=final_output, run_summary=summary_payload)
        lesson_entry = await self.append(
            {
                "agent_id": "critic",
                "scope": "shared",
                "kind": "lesson",
                "memory_type": "procedural",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "critic_final_review",
                "created_by": "critic",
                "trace_ref": {"run_id": run_id},
                "content": {
                    "text": lesson_text,
                    "task_id": task.get("task_id"),
                    "key_points": key_points,
                    "receipt_command_ids": summary_payload["receipt_command_ids"],
                },
                "tags": ["lesson", "procedure"],
            }
        )
        # lesson 是关键数据, 立即同步落盘 (仅在 should_persist 时触发)
        if self._ttl_engine.should_persist(lesson_entry):
            asyncio.ensure_future(self.persistence.persist_memory_entry(lesson_entry))
        experience_entry = await self._persist_long_term_experience(
            run_id=run_id, task=task, final_output=final_output, critic_final=critic_final,
        )
        return {
            "run_summary": summary_payload,
            "summary_entry": summary_entry,
            "lesson_entry": lesson_entry,
            "long_term_experience": experience_entry.get("experience_entry"),
            "rejected_experience": experience_entry.get("rejected_entry"),
            "memory_policy": experience_entry.get("policy", {}),
        }

    async def persist_approval_memory(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        approval_records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """保存审批摘要."""
        saved_entries: list[dict[str, Any]] = []
        for record in approval_records:
            if not isinstance(record, dict):
                continue
            saved_entries.append(
                await self.append(
                    {
                        "agent_id": "orchestrator",
                        "scope": "shared",
                        "kind": "approval",
                        "memory_type": "episodic",
                        "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                        "run_id": run_id,
                        "source": "approval_trace",
                        "created_by": "workflow",
                        "trace_ref": {
                            "run_id": run_id,
                            "step_id": record.get("step_id"),
                            "command_id": record.get("command_id"),
                            "approval_id": record.get("approval_id"),
                        },
                        "content": {
                            "text": build_approval_summary_text(record),
                            "task_id": task.get("task_id"),
                            "approval_record": record,
                        },
                        "tags": ["approval", str(record.get("state") or "pending")],
                    }
                )
            )
        return saved_entries

    async def _persist_long_term_experience(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        final_output: dict[str, Any],
        critic_final: dict[str, Any],
    ) -> dict[str, Any]:
        """保存长期经验."""
        policy = build_experience_policy(
            run_id=run_id, critic_final=critic_final, final_output=final_output,
        )
        if not policy["accepted"]:
            rejected_entry = await self.append(
                {
                    "agent_id": "critic",
                    "scope": "shared",
                    "kind": "experience_rejection",
                    "memory_type": "episodic",
                    "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                    "run_id": run_id,
                    "source": "critic_confidence_policy",
                    "created_by": "critic",
                    "agent_role": "critic",
                    "agent_perspective": agent_perspective("critic"),
                    "task_phase": "final_review",
                    "confidence": float(policy["confidence"]),
                    "trace_ref": {"run_id": run_id},
                    "content": {
                        "text": f"experience rejected because {policy['reasons'][0]}",
                        "policy": policy,
                    },
                    "tags": ["experience", "rejected"],
                }
            )
            return {"experience_entry": None, "rejected_entry": rejected_entry, "policy": policy}

        content = build_long_term_experience_content(
            task=task, final_output=final_output, critic_final=critic_final, policy=policy,
        )
        experience_entry = await self.append(
            {
                "agent_id": "critic",
                "scope": "shared",
                "kind": "semantic_case",
                "memory_type": "semantic",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "critic_confidence_policy",
                "created_by": "critic",
                "agent_role": "critic",
                "agent_perspective": content.get("agent_perspective"),
                "task_phase": "final_review",
                "confidence": float(policy["confidence"]),
                "trace_ref": {"run_id": run_id},
                "content": content,
                "tags": ["experience", "few_shot", "critic"],
            }
        )
        # long_term_experience 是关键数据, 立即同步落盘 (仅在 should_persist 时触发)
        if self._ttl_engine.should_persist(experience_entry):
            asyncio.ensure_future(self.persistence.persist_memory_entry(experience_entry))
        return {"experience_entry": experience_entry, "rejected_entry": None, "policy": policy}
