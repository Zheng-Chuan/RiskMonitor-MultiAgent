"""
LLM 辅助评估器.

用于评估需要主观判断的指标:
- 答案质量
- 推理有效性
- 逻辑一致性
- 风险评估准确度
"""

from __future__ import annotations

import json
import logging
from typing import Any

from riskmonitor_multiagent.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class LLMJudge:
    """
    LLM 辅助评估器.
    
    使用 LLM 对主观指标进行评估.
    """
    
    def __init__(self, model: str | None = None) -> None:
        """
        初始化 LLM 评估器.
        
        Args:
            model: 使用的模型名称
        """
        self._agent = BaseAgent(
            name="llm_judge",
            system_prompt=self._build_system_prompt(),
            model=model,
        )
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词."""
        return """You are an expert evaluator for multi-agent AI systems.

Your role is to objectively assess the quality of agent outputs based on specific criteria.

Evaluation Guidelines:
1. Be objective and consistent
2. Consider the context and constraints
3. Provide scores between 0 and 1
4. Base your judgment on evidence, not assumptions
5. Consider both what was done and how it was done

Always respond with valid JSON containing your evaluation scores and brief explanations.

Write Chinese text using only English punctuation."""
    
    async def evaluate_answer_quality(
        self,
        task: str,
        agent_output: str,
        ground_truth: str | None = None,
        criteria: list[str] | None = None,
    ) -> dict[str, float]:
        """
        评估答案质量.
        
        Args:
            task: 任务描述
            agent_output: Agent 输出
            ground_truth: 参考答案
            criteria: 评估标准
            
        Returns:
            评估结果字典
        """
        criteria = criteria or ["accuracy", "completeness", "relevance", "clarity"]
        
        prompt = f"""Please evaluate the following agent output.

Task: {task}

Agent Output:
{agent_output[:2000]}

Reference Answer (if available):
{ground_truth or "Not provided"}

Evaluation Criteria:
{json.dumps(criteria, indent=2)}

For each criterion, provide a score between 0 and 1:
- 0.0-0.3: Poor (major issues or incorrect)
- 0.4-0.6: Acceptable (some issues but usable)
- 0.7-0.9: Good (minor issues)
- 1.0: Excellent (no issues)

Return JSON format:
{{
    "accuracy": <score>,
    "completeness": <score>,
    "relevance": <score>,
    "clarity": <score>,
    "overall": <weighted_average>,
    "explanation": "<brief explanation in Chinese>"
}}"""

        try:
            result = await self._agent.ask_json(
                user_prompt=prompt,
                fallback={"accuracy": 0.5, "completeness": 0.5, "relevance": 0.5, "clarity": 0.5, "overall": 0.5},
                max_tokens=512,
            )
            
            output = result.output if isinstance(result.output, dict) else {}
            
            return {
                "accuracy": float(output.get("accuracy", 0.5)),
                "completeness": float(output.get("completeness", 0.5)),
                "relevance": float(output.get("relevance", 0.5)),
                "clarity": float(output.get("clarity", 0.5)),
                "overall": float(output.get("overall", 0.5)),
            }
        except Exception as e:
            logger.warning(f"LLM judge failed for answer quality: {e}")
            return {"accuracy": 0.5, "completeness": 0.5, "relevance": 0.5, "clarity": 0.5, "overall": 0.5}
    
    async def evaluate_reasoning_quality(
        self,
        reasoning_chain: list[dict[str, Any]],
        task: str,
    ) -> dict[str, float]:
        """
        评估推理质量.
        
        Args:
            reasoning_chain: 推理链 (thought -> reasoning -> evidence -> action)
            task: 任务描述
            
        Returns:
            评估结果字典
        """
        chain_text = "\n".join([
            f"Step {i+1}:\n"
            f"  Thought: {step.get('thought', 'N/A')}\n"
            f"  Reasoning: {step.get('reasoning', 'N/A')}\n"
            f"  Evidence: {step.get('evidence', 'N/A')}\n"
            f"  Action: {step.get('action_type', 'N/A')}"
            for i, step in enumerate(reasoning_chain[:5])
        ])
        
        prompt = f"""Please evaluate the reasoning quality of the following agent reasoning chain.

Task: {task}

Reasoning Chain:
{chain_text}

Evaluate on these dimensions:
1. thought_relevance: Are the thoughts relevant to the task? (0-1)
2. reasoning_validity: Is the reasoning logically valid? (0-1)
3. evidence_support: Does evidence support the reasoning? (0-1)
4. logical_consistency: Is the reasoning chain logically consistent? (0-1)
5. reasoning_depth: How deep is the reasoning? (0-1)

Return JSON format:
{{
    "thought_relevance": <score>,
    "reasoning_validity": <score>,
    "evidence_support": <score>,
    "logical_consistency": <score>,
    "reasoning_depth": <score>,
    "overall": <average>,
    "explanation": "<brief explanation in Chinese>"
}}"""

        try:
            result = await self._agent.ask_json(
                user_prompt=prompt,
                fallback={
                    "thought_relevance": 0.5,
                    "reasoning_validity": 0.5,
                    "evidence_support": 0.5,
                    "logical_consistency": 0.5,
                    "reasoning_depth": 0.5,
                    "overall": 0.5,
                },
                max_tokens=512,
            )
            
            output = result.output if isinstance(result.output, dict) else {}
            
            return {
                "thought_relevance": float(output.get("thought_relevance", 0.5)),
                "reasoning_validity": float(output.get("reasoning_validity", 0.5)),
                "evidence_support": float(output.get("evidence_support", 0.5)),
                "logical_consistency": float(output.get("logical_consistency", 0.5)),
                "reasoning_depth": float(output.get("reasoning_depth", 0.5)),
                "overall": float(output.get("overall", 0.5)),
            }
        except Exception as e:
            logger.warning(f"LLM judge failed for reasoning quality: {e}")
            return {
                "thought_relevance": 0.5,
                "reasoning_validity": 0.5,
                "evidence_support": 0.5,
                "logical_consistency": 0.5,
                "reasoning_depth": 0.5,
                "overall": 0.5,
            }
    
    async def evaluate_collaboration_quality(
        self,
        agent_outputs: dict[str, Any],
        task: str,
    ) -> dict[str, float]:
        """
        评估协作质量.
        
        Args:
            agent_outputs: 各 Agent 的输出
            task: 任务描述
            
        Returns:
            评估结果字典
        """
        outputs_text = "\n".join([
            f"Agent: {name}\nOutput: {json.dumps(output, ensure_ascii=False)[:500]}"
            for name, output in agent_outputs.items()
        ])
        
        prompt = f"""Please evaluate the collaboration quality among multiple agents.

Task: {task}

Agent Outputs:
{outputs_text}

Evaluate on these dimensions:
1. role_specialization: Did each agent focus on their specialty? (0-1)
2. information_complementarity: Did agents provide complementary information? (0-1)
3. collaboration_efficiency: Was the collaboration efficient without redundancy? (0-1)
4. conflict_resolution: Were conflicts resolved properly? (0-1)

Return JSON format:
{{
    "role_specialization": <score>,
    "information_complementarity": <score>,
    "collaboration_efficiency": <score>,
    "conflict_resolution": <score>,
    "overall": <average>,
    "explanation": "<brief explanation in Chinese>"
}}"""

        try:
            result = await self._agent.ask_json(
                user_prompt=prompt,
                fallback={
                    "role_specialization": 0.5,
                    "information_complementarity": 0.5,
                    "collaboration_efficiency": 0.5,
                    "conflict_resolution": 0.5,
                    "overall": 0.5,
                },
                max_tokens=512,
            )
            
            output = result.output if isinstance(result.output, dict) else {}
            
            return {
                "role_specialization": float(output.get("role_specialization", 0.5)),
                "information_complementarity": float(output.get("information_complementarity", 0.5)),
                "collaboration_efficiency": float(output.get("collaboration_efficiency", 0.5)),
                "conflict_resolution": float(output.get("conflict_resolution", 0.5)),
                "overall": float(output.get("overall", 0.5)),
            }
        except Exception as e:
            logger.warning(f"LLM judge failed for collaboration quality: {e}")
            return {
                "role_specialization": 0.5,
                "information_complementarity": 0.5,
                "collaboration_efficiency": 0.5,
                "conflict_resolution": 0.5,
                "overall": 0.5,
            }
    
    async def evaluate_risk_assessment(
        self,
        task: str,
        agent_actions: list[dict[str, Any]],
        risk_context: dict[str, Any],
    ) -> dict[str, float]:
        """
        评估风险评估准确度.
        
        Args:
            task: 任务描述
            agent_actions: Agent 的行动列表
            risk_context: 风险上下文
            
        Returns:
            评估结果字典
        """
        actions_text = "\n".join([
            f"- {action.get('type', 'unknown')}: {action.get('description', 'N/A')}"
            for action in agent_actions[:10]
        ])
        
        prompt = f"""Please evaluate the risk assessment quality of the agent's actions.

Task: {task}

Agent Actions:
{actions_text}

Risk Context:
{json.dumps(risk_context, ensure_ascii=False, indent=2)}

Evaluate on these dimensions:
1. risk_identification: Were risks properly identified? (0-1)
2. risk_severity_assessment: Was risk severity correctly assessed? (0-1)
3. mitigation_proposed: Were appropriate mitigations proposed? (0-1)
4. approval_compliance: Did the agent follow approval requirements? (0-1)

Return JSON format:
{{
    "risk_identification": <score>,
    "risk_severity_assessment": <score>,
    "mitigation_proposed": <score>,
    "approval_compliance": <score>,
    "overall": <average>,
    "explanation": "<brief explanation in Chinese>"
}}"""

        try:
            result = await self._agent.ask_json(
                user_prompt=prompt,
                fallback={
                    "risk_identification": 0.5,
                    "risk_severity_assessment": 0.5,
                    "mitigation_proposed": 0.5,
                    "approval_compliance": 0.5,
                    "overall": 0.5,
                },
                max_tokens=512,
            )
            
            output = result.output if isinstance(result.output, dict) else {}
            
            return {
                "risk_identification": float(output.get("risk_identification", 0.5)),
                "risk_severity_assessment": float(output.get("risk_severity_assessment", 0.5)),
                "mitigation_proposed": float(output.get("mitigation_proposed", 0.5)),
                "approval_compliance": float(output.get("approval_compliance", 0.5)),
                "overall": float(output.get("overall", 0.5)),
            }
        except Exception as e:
            logger.warning(f"LLM judge failed for risk assessment: {e}")
            return {
                "risk_identification": 0.5,
                "risk_severity_assessment": 0.5,
                "mitigation_proposed": 0.5,
                "approval_compliance": 0.5,
                "overall": 0.5,
            }


__all__ = ["LLMJudge"]
