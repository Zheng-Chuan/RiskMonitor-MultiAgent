import os
import sys
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
    monkeypatch.setenv("DISABLE_LLM", "1")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("MEMORY_SQLITE_PATH", str(tmp_path / "memory.sqlite"))
    monkeypatch.delenv("WORKING_MEMORY_BACKEND", raising=False)

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
    assert isinstance(result.get("engineer"), dict)
    assert isinstance(result.get("analyst"), dict)
    assert isinstance(result.get("orchestrator_final"), dict)
    assert isinstance(result.get("critic_final"), dict)

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

