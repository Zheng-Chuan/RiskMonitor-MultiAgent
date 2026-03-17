"""协作增强模块.

提供 Agent 间协作增强功能：
1. Agent 上下文共享
2. 主动消息通知
3. 协作提示词模板
4. 协作状态追踪
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from riskmonitor_multiagent.orchestration.message_bus import (
    MessageBus,
    MessageType,
    AgentMessage,
    get_message_bus,
)

logger = logging.getLogger(__name__)


@dataclass
class CollaborationContext:
    """协作上下文."""
    run_id: str
    current_phase: str = "init"
    shared_facts: dict[str, Any] = field(default_factory=dict)
    pending_questions: list[dict[str, Any]] = field(default_factory=list)
    agent_status: dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "current_phase": self.current_phase,
            "shared_facts": self.shared_facts,
            "pending_questions": self.pending_questions,
            "agent_status": self.agent_status,
        }


class CollaborationEnhancer:
    """协作增强器."""
    
    def __init__(self, run_id: str, message_bus: Optional[MessageBus] = None) -> None:
        self.run_id = run_id
        self.message_bus = message_bus or get_message_bus()
        self.context = CollaborationContext(run_id=run_id)
    
    async def share_fact(self, key: str, value: Any, source_agent: str) -> None:
        """分享一个事实到共享上下文."""
        self.context.shared_facts[key] = {
            "value": value,
            "source": source_agent,
        }
        
        # 发布事实消息
        await self.message_bus.publish(
            from_agent=source_agent,
            message_type=MessageType.OBSERVATION,
            content={"fact_key": key, "fact_value": value},
        )
        logger.debug(f"Fact shared: {key} from {source_agent}")
    
    async def ask_question(
        self,
        question: str,
        from_agent: str,
        to_agent: Optional[str] = None,
    ) -> str:
        """一个 Agent 向另一个 Agent 提问."""
        msg = await self.message_bus.publish(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=MessageType.QUESTION,
            content={"question": question},
        )
        
        question_entry = {
            "message_id": msg.message_id,
            "question": question,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "answered": False,
        }
        self.context.pending_questions.append(question_entry)
        
        logger.debug(f"Question asked: {question} from {from_agent}")
        return msg.message_id
    
    async def answer_question(
        self,
        question_message_id: str,
        answer: str,
        from_agent: str,
    ) -> None:
        """回答问题."""
        await self.message_bus.publish(
            from_agent=from_agent,
            message_type=MessageType.ANSWER,
            content={"answer": answer},
            in_reply_to=question_message_id,
        )
        
        # 更新待办问题
        for q in self.context.pending_questions:
            if q.get("message_id") == question_message_id:
                q["answered"] = True
                q["answer"] = answer
        
        logger.debug(f"Question answered: {question_message_id}")
    
    def get_collaboration_prompt(self, agent_name: str) -> str:
        """获取协作提示词模板."""
        facts_str = json.dumps(self.context.shared_facts, ensure_ascii=False, indent=2)
        questions_str = json.dumps(self.context.pending_questions, ensure_ascii=False, indent=2)
        
        return f"""
## Collaboration Context (Shared Between Agents

### Shared Facts:
{facts_str}

### Pending Questions:
{questions_str}

### Your Role: {agent_name}

Instructions for Collaboration:
1. Use shared_facts for common knowledge (do not repeat what others have already established
2. Answer pending_questions if they are directed to you
3. Ask questions when you need clarification from other agents
4. Build on others' work, don't work in isolation
5. Reference message threads for conversation history

Remember: This is a team effort, not individual work!
"""
    
    def update_agent_status(self, agent_name: str, status: str) -> None:
        """更新 Agent 状态."""
        self.context.agent_status[agent_name] = status
    
    def get_context(self) -> CollaborationContext:
        """获取协作上下文."""
        return self.context


# 协作提示词增强模板
COLLABORATION_PROMPT_TEMPLATE = """
## Collaboration Enhancement

You are part of a multi-agent team. Your response should:

1. Acknowledge what other agents have contributed
2. Build on their work instead of repeating
3. Ask clarifying questions when needed
4. Reference evidence from receipts and artifacts
5. Coordinate with the orchestrator

Remember: This is a team effort!

When you see output from other agents:
- Use their findings as facts
- Ask them for clarification if needed
- Coordinate your response with theirs

"""


def build_collaborative_system_prompt(base_prompt: str, enhancer: CollaborationEnhancer) -> str:
    """构建带有协作增强的系统提示词."""
    collab_context = enhancer.get_collaboration_prompt("")
    return f"""{base_prompt}

{COLLABORATION_PROMPT_TEMPLATE}

{collab_context}
"""
