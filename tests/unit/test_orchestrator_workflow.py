import os
import sys
import json
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


@pytest.mark.asyncio
async def test_orchestrator_workflow_runs_and_writes_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path / "ctx"))
    monkeypatch.setenv("ENABLE_LANGGRAPH", "1")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT", "1000000")
    monkeypatch.setenv("LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT", "1000000")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("MEMORY_SQLITE_PATH", str(tmp_path / "memory.sqlite"))
    monkeypatch.delenv("WORKING_MEMORY_BACKEND", raising=False)

    from riskmonitor_multiagent.llm import llm_client

    async def _fake_chat(self, *, messages, model=None, temperature=0.2, max_tokens=None):
        sys_prompt = (messages[0] or {}).get("content") if isinstance(messages, list) and messages else ""
        user_prompt = (messages[1] or {}).get("content") if isinstance(messages, list) and len(messages) > 1 else ""
        if isinstance(sys_prompt, str) and "intent extraction agent" in sys_prompt:
            obj = {
                "schema_version": "intent_output.v2",
                "primary_intent_type": "check_system",
                "intents": [{"intent_type": "check_system", "slots": {}, "confidence": 0.8}],
                "disambiguation": {"has_multiple": False, "explanation": "", "notes": []},
                "risk_level": "LOW",
                "permission_requirements": {"side_effects": False, "requires_human_approval": False, "allowed_tools": None},
                "evidence": {"fields": ["task.payload.content"]},
                "degraded": False,
            }
        elif isinstance(sys_prompt, str) and "orchestrator agent" in sys_prompt:
            phase = "plan"
            if isinstance(user_prompt, str) and "phase': 'finalize" in user_prompt:
                phase = "finalize"
            if phase == "plan":
                obj = {
                    "schema_version": "orchestrator_output.v1",
                    "intent": {"type": "check_system", "confidence": 0.8, "slots": {}},
                    "plan_steps": [
                        {"kind": "delegate", "step_id": "s1", "reason": "先确认系统侧是否存在可观测异常", "target_agent": "system_engineer", "instruction": "分析系统层面可能原因并给出证据"},
                        {"kind": "delegate", "step_id": "s2", "reason": "再评估业务影响避免只看技术视角", "target_agent": "risk_analyst", "instruction": "分析业务层面影响范围并给出证据"},
                        {"kind": "finalize", "step_id": "s3", "reason": "综合双视角输出可执行结论", "instruction": "基于两份分析做最终结论与下一步建议"},
                    ],
                    "commands": None,
                    "evidence": {"fields": ["task.payload.content"]},
                    "degraded": False,
                }
            else:
                obj = {
                    "schema_version": "orchestrator_output.v1",
                    "intent": {"type": "check_system", "confidence": 0.8, "slots": {}},
                    "plan_steps": [{"kind": "finalize", "step_id": "s1", "reason": "收敛并输出最终结论", "instruction": "输出"}],
                    "commands": None,
                    "evidence": {"fields": ["task.payload.content"]},
                    "degraded": False,
                }
        elif isinstance(sys_prompt, str) and "critic agent" in sys_prompt:
            obj = {
                "schema_version": "critic_review.v1",
                "ok": True,
                "risk_level": "LOW",
                "issues": [],
                "require_human_approval": True,
                "suggested_fixes": [],
                "evidence": {"fields": ["task.payload.content"]},
                "run_summary": {"text": "评审通过", "key_points": ["证据引用齐全"], "receipt_command_ids": []},
            }
        elif isinstance(sys_prompt, str) and "system engineer agent" in sys_prompt:
            obj = {
                "schema_version": "system_engineer_output.v1",
                "system_issue": False,
                "reason": "ok",
                "latency_ms": None,
                "summary": "系统侧未发现明显异常 建议补充更多指标用于深入排查",
                "evidence": {"fields": ["task.payload.content"]},
                "findings": {},
                "recommendations": ["补充时间范围 指标与日志", "如涉及副作用动作先走审批"],
            }
        else:
            obj = {
                "schema_version": "risk_analyst_output.v1",
                "report": "业务侧影响初步可控 建议关注关键敞口指标变化",
                "key_facts": {},
                "confidence": 0.6,
                "evidence": {"fields": ["task.payload.content"]},
            }
        return {
            "choices": [{"message": {"content": json.dumps(obj, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    monkeypatch.setattr(llm_client.LlmClient, "chat_completions", _fake_chat, raising=True)

    from riskmonitor_multiagent.orchestration.orchestrator_workflow import run_orchestrator_workflow
    from riskmonitor_multiagent.memory.unified_memory import UnifiedMemory

    task = {
        "task_id": "task_demo_1",
        "session_id": "session_demo",
        "source": "human",
        "payload": {"content": "检查系统延迟与可能原因 并给出下一步建议"},
    }

    out = await run_orchestrator_workflow(task=task)
    assert out.get("ok") is True

    result = out.get("result")
    assert isinstance(result, dict)
    assert result.get("schema_version") == "orchestrator_run.v1"
    assert isinstance(result.get("run_id"), str) and result.get("run_id")
    assert isinstance(result.get("orchestrator_plan"), dict)
    assert isinstance(result.get("critic_plan"), dict)
    assert isinstance(result.get("approval"), dict)
    assert isinstance(result.get("engineer"), dict)
    assert isinstance(result.get("analyst"), dict)
    assert isinstance(result.get("orchestrator_final"), dict)
    assert isinstance(result.get("critic_final"), dict)
    quality = result.get("quality")
    assert isinstance(quality, dict)
    assert isinstance(quality.get("step_reason_coverage"), float)
    assert isinstance(quality.get("evidence_missing_rate"), float)
    assert isinstance(quality.get("receipt_binding_rate"), float)

    approval = result.get("approval") or {}
    assert approval.get("required") in {True, False}
    if approval.get("required") is True:
        assert approval.get("approved") is True

    mem = UnifiedMemory()
    recent = await mem.list_recent(
        agent_id="orchestrator",
        scope="shared",
        session_id="session_demo",
        run_id=str(result.get("run_id")),
        limit=20,
    )
    kinds = [x.get("kind") for x in recent if isinstance(x, dict)]
    assert "plan" in kinds
    assert "final" in kinds
    run_summary = await mem.get_run_summary(run_id=str(result.get("run_id")))
    assert isinstance(run_summary, dict)
    assert isinstance(run_summary.get("text"), str)
    assert isinstance(run_summary.get("receipt_command_ids"), list)


@pytest.mark.asyncio
async def test_orchestrator_workflow_requires_human_when_not_auto_approved(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path / "ctx"))
    monkeypatch.setenv("ENABLE_LANGGRAPH", "1")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT", "1000000")
    monkeypatch.setenv("LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT", "1000000")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("MEMORY_SQLITE_PATH", str(tmp_path / "memory.sqlite"))
    monkeypatch.setenv("HITL_AUTO_APPROVE", "0")
    monkeypatch.delenv("WORKING_MEMORY_BACKEND", raising=False)

    from riskmonitor_multiagent.llm import llm_client

    async def _fake_chat(self, *, messages, model=None, temperature=0.2, max_tokens=None):
        sys_prompt = (messages[0] or {}).get("content") if isinstance(messages, list) and messages else ""
        user_prompt = (messages[1] or {}).get("content") if isinstance(messages, list) and len(messages) > 1 else ""
        if isinstance(sys_prompt, str) and "intent extraction agent" in sys_prompt:
            obj = {
                "schema_version": "intent_output.v2",
                "primary_intent_type": "needs_approval",
                "intents": [{"intent_type": "needs_approval", "slots": {}, "confidence": 0.8}],
                "disambiguation": {"has_multiple": False, "explanation": "", "notes": []},
                "risk_level": "MEDIUM",
                "permission_requirements": {"side_effects": False, "requires_human_approval": True, "allowed_tools": None},
                "evidence": {"fields": ["task.payload.content"]},
                "degraded": False,
            }
        elif isinstance(sys_prompt, str) and "orchestrator agent" in sys_prompt and isinstance(user_prompt, str) and "phase': 'plan" in user_prompt:
            obj = {
                "schema_version": "orchestrator_output.v1",
                "intent": {"type": "needs_approval", "confidence": 0.8, "slots": {}},
                "plan_steps": [{"kind": "finalize", "step_id": "s1", "reason": "先走审批避免风险扩大", "instruction": "输出"}],
                "commands": None,
                "evidence": {"fields": ["task.payload.content"]},
                "degraded": False,
            }
        else:
            obj = {
                "schema_version": "critic_review.v1",
                "ok": True,
                "risk_level": "MEDIUM",
                "issues": [],
                "require_human_approval": True,
                "suggested_fixes": ["请人工确认风险操作范围"],
                "evidence": {"fields": ["task.payload.content"]},
                "run_summary": {"text": "需要人工审批", "key_points": [], "receipt_command_ids": []},
            }
        return {
            "choices": [{"message": {"content": json.dumps(obj, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    monkeypatch.setattr(llm_client.LlmClient, "chat_completions", _fake_chat, raising=True)

    from riskmonitor_multiagent.orchestration.orchestrator_workflow import run_orchestrator_workflow
    from riskmonitor_multiagent.memory.unified_memory import UnifiedMemory

    task = {
        "task_id": "task_demo_2",
        "session_id": "session_demo",
        "source": "human",
        "payload": {"content": "对系统执行可能有副作用的操作前先人工确认"},
    }

    out = await run_orchestrator_workflow(task=task)
    assert out.get("ok") is True

    result = out.get("result")
    assert isinstance(result, dict)
    approval = result.get("approval") or {}
    assert approval.get("required") is True
    assert approval.get("approved") is False
    quality = result.get("quality")
    assert isinstance(quality, dict)

    mem = UnifiedMemory()
    recent = await mem.list_recent(
        agent_id="orchestrator",
        scope="shared",
        session_id="session_demo",
        run_id=str(result.get("run_id")),
        limit=20,
    )
    kinds = [x.get("kind") for x in recent if isinstance(x, dict)]
    assert "plan" in kinds
    assert "final" not in kinds


@pytest.mark.asyncio
async def test_orchestrator_commands_generate_receipts_and_critic_can_see(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path / "ctx"))
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("MEMORY_SQLITE_PATH", str(tmp_path / "memory.sqlite"))
    monkeypatch.delenv("MONGO_URL", raising=False)

    from riskmonitor_multiagent.agents.base import AgentResult
    from riskmonitor_multiagent.orchestration.tool_executor import new_agent_command
    from riskmonitor_multiagent.orchestration.orchestrator_workflow import run_orchestrator_workflow

    seen = {"receipts": None}

    async def _fake_orchestrate(self, *, task, context=None, max_tokens=None):
        phase = context.get("phase") if isinstance(context, dict) else ""
        if phase == "plan":
            cmd = new_agent_command(
                run_id="run_case_cmd",
                command_id="cmd_write_alert_1",
                target_agent="manager",
                action="write_alert",
                params={"alert": {"alert_id": "a-1", "desk": "eq", "severity": "WARNING"}},
                timeout_ms=1000,
                expected_output_schema="tool_result.v1",
            )
            return AgentResult(
                ok=True,
                output={
                    "schema_version": "orchestrator_output.v1",
                    "intent": {"type": "write_alert", "confidence": 0.9, "slots": {}},
                    "plan_steps": [
                        {"kind": "tool_call", "step_id": "s1", "reason": "先采集只读指标", "tool_name": "collect_metrics", "params": {}},
                        {"kind": "finalize", "step_id": "s2", "reason": "汇总输出结果", "instruction": "输出结论"},
                    ],
                    "commands": [cmd],
                    "evidence": {"fields": ["task.payload.content"]},
                    "degraded": False,
                },
            )
        return AgentResult(
            ok=True,
            output={
                "schema_version": "orchestrator_output.v1",
                "intent": {"type": "write_alert", "confidence": 0.9, "slots": {}},
                "plan_steps": [{"kind": "finalize", "step_id": "s1", "reason": "完成收敛", "instruction": "输出"}],
                "commands": None,
                "evidence": {"fields": ["task.payload.content"], "receipt_command_ids": ["cmd_write_alert_1"]},
                "degraded": False,
            },
        )

    async def _fake_critic_review(self, *, task, orchestrator, engineer=None, analyst=None, receipts=None, max_tokens=None):
        seen["receipts"] = receipts
        rc = [x.get("command_id") for x in receipts if isinstance(x, dict) and isinstance(x.get("command_id"), str)] if isinstance(receipts, list) else []
        return AgentResult(
            ok=True,
            output={
                "schema_version": "critic_review.v1",
                "ok": True,
                "risk_level": "LOW",
                "issues": [],
                "require_human_approval": False,
                "suggested_fixes": [],
                "evidence": {"fields": ["task.payload.content"], "receipt_command_ids": rc},
                "run_summary": {"text": "命令执行完成", "key_points": ["有收据"], "receipt_command_ids": rc},
            },
        )

    monkeypatch.setattr("riskmonitor_multiagent.agents.roles.OrchestratorAgent.orchestrate", _fake_orchestrate)
    monkeypatch.setattr("riskmonitor_multiagent.agents.roles.CriticAgent.review", _fake_critic_review)
    async def _fake_intent(self, *, task, metadata=None, max_tokens=None):
        return AgentResult(
            ok=True,
            output={
                "schema_version": "intent_output.v2",
                "primary_intent_type": "write_alert",
                "intents": [{"intent_type": "write_alert", "slots": {}, "confidence": 0.9}],
                "disambiguation": {"has_multiple": False, "explanation": "", "notes": []},
                "risk_level": "HIGH",
                "permission_requirements": {"side_effects": True, "requires_human_approval": True, "allowed_tools": None},
                "evidence": {"fields": ["task.payload.content"]},
                "degraded": False,
            },
        )

    monkeypatch.setattr("riskmonitor_multiagent.agents.roles.IntentAgent.recognize", _fake_intent)

    out = await run_orchestrator_workflow(
        task={"task_id": "task_cmd", "session_id": "s_cmd", "source": "human", "payload": {"content": "写入告警并检查指标"}}
    )
    assert out.get("ok") is True
    result = out.get("result") if isinstance(out.get("result"), dict) else {}
    assert "router" not in result
    assert result.get("status") in {"completed", "pending_approval"}
    receipts = result.get("receipts")
    assert isinstance(receipts, list) and len(receipts) >= 1
    assert isinstance(seen.get("receipts"), list) and len(seen.get("receipts")) >= 1


@pytest.mark.asyncio
async def test_orchestrator_unknown_step_kind_is_not_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path / "ctx"))
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("MEMORY_SQLITE_PATH", str(tmp_path / "memory.sqlite"))

    from riskmonitor_multiagent.agents.base import AgentResult
    from riskmonitor_multiagent.orchestration.orchestrator_workflow import run_orchestrator_workflow

    async def _fake_orchestrate(self, *, task, context=None, max_tokens=None):
        phase = context.get("phase") if isinstance(context, dict) else ""
        if phase == "plan":
            return AgentResult(
                ok=True,
                output={
                    "schema_version": "orchestrator_output.v1",
                    "intent": {"type": "unknown", "confidence": 0.2, "slots": {}},
                    "plan_steps": [{"kind": "mystery_kind", "step_id": "s1", "reason": "测试未知分支"}],
                    "commands": None,
                    "evidence": {"fields": ["task.payload.content"]},
                    "degraded": False,
                },
            )
        return AgentResult(
            ok=True,
            output={
                "schema_version": "orchestrator_output.v1",
                "intent": {"type": "unknown", "confidence": 0.2, "slots": {}},
                "plan_steps": [{"kind": "finalize", "step_id": "s1", "reason": "结束", "instruction": "输出"}],
                "commands": None,
                "evidence": {"fields": ["task.payload.content"]},
                "degraded": False,
            },
        )

    async def _fake_critic_review(self, *, task, orchestrator, engineer=None, analyst=None, receipts=None, max_tokens=None):
        return AgentResult(
            ok=True,
            output={
                "schema_version": "critic_review.v1",
                "ok": True,
                "risk_level": "LOW",
                "issues": [],
                "require_human_approval": False,
                "suggested_fixes": [],
                "evidence": {"fields": ["task.payload.content"]},
                "run_summary": {"text": "ok", "key_points": [], "receipt_command_ids": []},
            },
        )

    monkeypatch.setattr("riskmonitor_multiagent.agents.roles.OrchestratorAgent.orchestrate", _fake_orchestrate)
    monkeypatch.setattr("riskmonitor_multiagent.agents.roles.CriticAgent.review", _fake_critic_review)
    async def _fake_intent(self, *, task, metadata=None, max_tokens=None):
        return AgentResult(
            ok=True,
            output={
                "schema_version": "intent_output.v2",
                "primary_intent_type": "unknown",
                "intents": [{"intent_type": "unknown", "slots": {}, "confidence": 0.4}],
                "disambiguation": {"has_multiple": False, "explanation": "", "notes": []},
                "risk_level": "LOW",
                "permission_requirements": {"side_effects": False, "requires_human_approval": False, "allowed_tools": None},
                "evidence": {"fields": ["task.payload.content"]},
                "degraded": False,
            },
        )

    monkeypatch.setattr("riskmonitor_multiagent.agents.roles.IntentAgent.recognize", _fake_intent)
    out = await run_orchestrator_workflow(task={"task_id": "task_unknown", "session_id": "s_u", "source": "human", "payload": {"content": "测试未知step"}})
    result = out.get("result") if isinstance(out.get("result"), dict) else {}
    errors = result.get("errors") if isinstance(result.get("errors"), list) else []
    assert any(str(x).startswith("unknown_step_kind:") for x in errors)


@pytest.mark.asyncio
async def test_multi_intent_disambiguation_written_to_shared_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path / "ctx"))
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT", "1000000")
    monkeypatch.setenv("LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT", "1000000")
    monkeypatch.setenv("MEMORY_SQLITE_PATH", str(tmp_path / "memory.sqlite"))

    from riskmonitor_multiagent.agents.base import AgentResult
    from riskmonitor_multiagent.memory.unified_memory import UnifiedMemory
    from riskmonitor_multiagent.orchestration.orchestrator_workflow import run_orchestrator_workflow
    from riskmonitor_multiagent.llm import llm_client

    async def _fake_chat(self, *, messages, model=None, temperature=0.2, max_tokens=None):
        sys_prompt = (messages[0] or {}).get("content") if isinstance(messages, list) and messages else ""
        user_prompt = (messages[1] or {}).get("content") if isinstance(messages, list) and len(messages) > 1 else ""
        if isinstance(sys_prompt, str) and "orchestrator agent" in sys_prompt:
            phase = "plan"
            if isinstance(user_prompt, str) and "phase': 'finalize" in user_prompt:
                phase = "finalize"
            if phase == "plan":
                obj = {
                    "schema_version": "orchestrator_output.v1",
                    "intent": {"type": "query_positions", "confidence": 0.7, "slots": {}},
                    "plan_steps": [{"kind": "finalize", "step_id": "s1", "reason": "先收敛输出避免误操作", "instruction": "输出"}],
                    "commands": None,
                    "evidence": {"fields": ["task.payload.content"]},
                    "degraded": False,
                }
            else:
                obj = {
                    "schema_version": "orchestrator_output.v1",
                    "intent": {"type": "query_positions", "confidence": 0.7, "slots": {}},
                    "plan_steps": [{"kind": "finalize", "step_id": "s1", "reason": "输出最终结果", "instruction": "输出"}],
                    "commands": None,
                    "evidence": {"fields": ["task.payload.content"]},
                    "degraded": False,
                }
        else:
            obj = {
                "schema_version": "critic_review.v1",
                "ok": True,
                "risk_level": "LOW",
                "issues": [],
                "require_human_approval": False,
                "suggested_fixes": [],
                "evidence": {"fields": ["task.payload.content"]},
                "run_summary": {"text": "ok", "key_points": [], "receipt_command_ids": []},
            }
        return {
            "choices": [{"message": {"content": json.dumps(obj, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    monkeypatch.setattr(llm_client.LlmClient, "chat_completions", _fake_chat, raising=True)

    async def _fake_intent(self, *, task, metadata=None, max_tokens=None):
        return AgentResult(
            ok=True,
            output={
                "schema_version": "intent_output.v2",
                "primary_intent_type": "query_positions",
                "intents": [
                    {"intent_type": "write_alert", "slots": {}, "confidence": 0.2},
                    {"intent_type": "query_positions", "slots": {"desk": "EQ"}, "confidence": 0.8},
                ],
                "disambiguation": {"has_multiple": True, "explanation": "同一句同时包含查询和写入倾向", "notes": []},
                "risk_level": "MEDIUM",
                "permission_requirements": {"side_effects": True, "requires_human_approval": True, "allowed_tools": None},
                "evidence": {"fields": ["task.payload.content"]},
                "degraded": False,
            },
        )

    monkeypatch.setattr("riskmonitor_multiagent.agents.roles.IntentAgent.recognize", _fake_intent)
    out1 = await run_orchestrator_workflow(task={"task_id": "task_m1", "session_id": "s_m", "source": "human", "payload": {"content": "查头寸并可能写告警"}})
    out2 = await run_orchestrator_workflow(task={"task_id": "task_m2", "session_id": "s_m", "source": "human", "payload": {"content": "查头寸并可能写告警"}})
    i1 = ((out1.get("result") or {}).get("intent") or {}).get("intents")
    i2 = ((out2.get("result") or {}).get("intent") or {}).get("intents")
    assert i1 == i2

    mem = UnifiedMemory()
    recent = await mem.list_recent(agent_id="intent", scope="shared", session_id="s_m", limit=20)
    kinds = [x.get("kind") for x in recent if isinstance(x, dict)]
    assert "intent_disambiguation" in kinds
