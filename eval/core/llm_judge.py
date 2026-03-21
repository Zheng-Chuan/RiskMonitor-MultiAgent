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

    async def evaluate_intent_match(
        self,
        expected_intent: str,
        actual_intent: str,
        context: str,
    ) -> dict[str, Any]:
        """
        评估意图匹配度.

        Args:
            expected_intent: 期望的意图
            actual_intent: 实际的意图
            context: 任务上下文

        Returns:
            包含 score (0-1) 和 explanation 的字典
        """
        prompt = f"""Please evaluate whether the actual intent matches the expected intent.

Task Context:
{context}

Expected Intent:
{expected_intent}

Actual Intent:
{actual_intent}

Evaluate the intent match on these criteria:
1. semantic_alignment: Are the intents semantically aligned even if not identical?
2. completeness: Does the actual intent cover all key aspects of the expected intent?
3. specificity: Is the actual intent appropriately specific?

Return JSON format:
{{
    "score": <overall_score_0_to_1>,
    "semantic_alignment": <score_0_to_1>,
    "completeness": <score_0_to_1>,
    "specificity": <score_0_to_1>,
    "explanation": "<brief explanation in Chinese>"
}}"""

        try:
            result = await self._agent.ask_json(
                user_prompt=prompt,
                fallback={
                    "score": 0.5,
                    "semantic_alignment": 0.5,
                    "completeness": 0.5,
                    "specificity": 0.5,
                    "explanation": "Intent match evaluation failed",
                },
                max_tokens=512,
            )

            output = result.output if isinstance(result.output, dict) else {}
            return {
                "score": float(output.get("score", 0.5)),
                "semantic_alignment": float(output.get("semantic_alignment", 0.5)),
                "completeness": float(output.get("completeness", 0.5)),
                "specificity": float(output.get("specificity", 0.5)),
                "explanation": output.get("explanation", ""),
            }
        except Exception as e:
            logger.warning(f"LLM judge failed for intent match: {e}")
            return {
                "score": 0.5,
                "semantic_alignment": 0.5,
                "completeness": 0.5,
                "specificity": 0.5,
                "explanation": f"Error: {str(e)}",
            }

    async def evaluate_ambiguity_resolution(
        self,
        task: str,
        intent_output: dict[str, Any],
    ) -> dict[str, Any]:
        """
        评估歧义消解能力.

        Args:
            task: 任务描述
            intent_output: 意图识别输出

        Returns:
            包含 score (0-1) 和 explanation 的字典
        """
        intent_text = json.dumps(intent_output, ensure_ascii=False, indent=2)

        prompt = f"""Please evaluate how well the agent resolved ambiguities in the task.

Task:
{task}

Intent Output:
{intent_text[:1000]}

Evaluate the ambiguity resolution:
1. ambiguity_identified: Did the agent identify ambiguities in the task?
2. clarification_quality: Were the clarifications appropriate?
3. assumption_transparency: Are the agent's assumptions clearly stated?

Return JSON format:
{{
    "score": <overall_score_0_to_1>,
    "ambiguity_identified": <score_0_to_1>,
    "clarification_quality": <score_0_to_1>,
    "assumption_transparency": <score_0_to_1>,
    "explanation": "<brief explanation in Chinese>"
}}"""

        try:
            result = await self._agent.ask_json(
                user_prompt=prompt,
                fallback={
                    "score": 0.7,
                    "ambiguity_identified": 0.7,
                    "clarification_quality": 0.7,
                    "assumption_transparency": 0.7,
                    "explanation": "Ambiguity resolution evaluation failed",
                },
                max_tokens=512,
            )

            output = result.output if isinstance(result.output, dict) else {}
            return {
                "score": float(output.get("score", 0.7)),
                "ambiguity_identified": float(output.get("ambiguity_identified", 0.7)),
                "clarification_quality": float(output.get("clarification_quality", 0.7)),
                "assumption_transparency": float(output.get("assumption_transparency", 0.7)),
                "explanation": output.get("explanation", ""),
            }
        except Exception as e:
            logger.warning(f"LLM judge failed for ambiguity resolution: {e}")
            return {
                "score": 0.7,
                "ambiguity_identified": 0.7,
                "clarification_quality": 0.7,
                "assumption_transparency": 0.7,
                "explanation": f"Error: {str(e)}",
            }

    async def evaluate_context_understanding(
        self,
        task: str,
        agent_output: str,
    ) -> dict[str, Any]:
        """
        评估上下文理解能力.

        Args:
            task: 任务描述
            agent_output: Agent 输出

        Returns:
            包含 score (0-1) 和 explanation 的字典
        """
        prompt = f"""Please evaluate how well the agent understood the context of the task.

Task:
{task}

Agent Output:
{agent_output[:1500]}

Evaluate context understanding:
1. key_context_used: Did the agent correctly identify and use key context from the task?
2. irrelevant_info_avoided: Did the agent avoid being distracted by irrelevant information?
3. context_integration: Was the relevant context properly integrated into the response?

Return JSON format:
{{
    "score": <overall_score_0_to_1>,
    "key_context_used": <score_0_to_1>,
    "irrelevant_info_avoided": <score_0_to_1>,
    "context_integration": <score_0_to_1>,
    "explanation": "<brief explanation in Chinese>"
}}"""

        try:
            result = await self._agent.ask_json(
                user_prompt=prompt,
                fallback={
                    "score": 0.7,
                    "key_context_used": 0.7,
                    "irrelevant_info_avoided": 0.7,
                    "context_integration": 0.7,
                    "explanation": "Context understanding evaluation failed",
                },
                max_tokens=512,
            )

            output = result.output if isinstance(result.output, dict) else {}
            return {
                "score": float(output.get("score", 0.7)),
                "key_context_used": float(output.get("key_context_used", 0.7)),
                "irrelevant_info_avoided": float(output.get("irrelevant_info_avoided", 0.7)),
                "context_integration": float(output.get("context_integration", 0.7)),
                "explanation": output.get("explanation", ""),
            }
        except Exception as e:
            logger.warning(f"LLM judge failed for context understanding: {e}")
            return {
                "score": 0.7,
                "key_context_used": 0.7,
                "irrelevant_info_avoided": 0.7,
                "context_integration": 0.7,
                "explanation": f"Error: {str(e)}",
            }

    async def evaluate_conflict_resolution(
        self,
        messages: list[dict[str, Any]],
        task: str,
    ) -> dict[str, Any]:
        """
        评估冲突解决能力.

        Args:
            messages: 消息列表
            task: 任务描述

        Returns:
            包含 score (0-1) 和 explanation 的字典
        """
        messages_text = "\n".join([
            f"[{msg.get('from', 'unknown')} -> {msg.get('to', 'unknown')}]: {msg.get('content', '')[:200]}"
            for msg in messages[:10]
        ])

        prompt = f"""Please evaluate how well conflicts between agents were resolved.

Task:
{task}

Messages:
{messages_text}

Evaluate conflict resolution:
1. conflict_identified: Were conflicts properly identified?
2. resolution_quality: Were conflicts resolved effectively?
3. consensus_achieved: Was consensus or agreement reached?

Return JSON format:
{{
    "score": <overall_score_0_to_1>,
    "conflict_identified": <score_0_to_1>,
    "resolution_quality": <score_0_to_1>,
    "consensus_achieved": <score_0_to_1>,
    "explanation": "<brief explanation in Chinese>"
}}"""

        try:
            result = await self._agent.ask_json(
                user_prompt=prompt,
                fallback={
                    "score": 0.7,
                    "conflict_identified": 0.7,
                    "resolution_quality": 0.7,
                    "consensus_achieved": 0.7,
                    "explanation": "Conflict resolution evaluation failed",
                },
                max_tokens=512,
            )

            output = result.output if isinstance(result.output, dict) else {}
            return {
                "score": float(output.get("score", 0.7)),
                "conflict_identified": float(output.get("conflict_identified", 0.7)),
                "resolution_quality": float(output.get("resolution_quality", 0.7)),
                "consensus_achieved": float(output.get("consensus_achieved", 0.7)),
                "explanation": output.get("explanation", ""),
            }
        except Exception as e:
            logger.warning(f"LLM judge failed for conflict resolution: {e}")
            return {
                "score": 0.7,
                "conflict_identified": 0.7,
                "resolution_quality": 0.7,
                "consensus_achieved": 0.7,
                "explanation": f"Error: {str(e)}",
            }


__all__ = ["LLMJudge"]
