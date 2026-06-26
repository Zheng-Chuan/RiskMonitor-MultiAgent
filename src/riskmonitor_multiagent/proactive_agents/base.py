"""
主动 Agent 基类 - 具备 BDI 模型、ReAct 循环和后台监控能力.

核心特性:
1. BDI 模型:信念(Belief)、愿望(Desire)、意图(Intention)
2. ReAct 循环:Thought → Reasoning → Action → Observation
3. CoT 思维链:每个步骤都有动态生成的 reason 和 evidence
4. 后台监控:主动感知环境变化并发起行为
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from riskmonitor_multiagent.agents.base import AgentResult, BaseAgent
from riskmonitor_multiagent.contracts.event import EventType, new_event
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms

# 向前兼容: TYPE_CHECKING 下导入 TieredPromptBuilder, 避免循环导入
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from riskmonitor_multiagent.prompts.tiered_prompt_builder import (
        PromptTier,
        TieredPromptBuilder,
    )

logger = logging.getLogger(__name__)


@dataclass
class Belief:
    """Agent 的信念:Agent 认为世界的状态."""
    
    content: Any
    source: str
    confidence: float = 1.0
    belief_id: str = field(default_factory=lambda: f"belief_{uuid.uuid4().hex[:8]}")
    timestamp_ms: int = field(default_factory=lambda: time.time_ns() // 1000000)


@dataclass
class Desire:
    """Agent 的愿望:Agent 想要达到的状态."""
    
    description: str
    priority: int = 0
    active: bool = True
    desire_id: str = field(default_factory=lambda: f"desire_{uuid.uuid4().hex[:8]}")


@dataclass
class Intention:
    """Agent 的意图:Agent 承诺要执行的行动."""
    
    description: str
    target_agent: Optional[str] = None
    tool_name: Optional[str] = None
    tool_params: Optional[dict[str, Any]] = None
    status: str = "pending"
    intention_id: str = field(default_factory=lambda: f"intention_{uuid.uuid4().hex[:8]}")
    created_timestamp_ms: int = field(default_factory=lambda: time.time_ns() // 1000000)


@dataclass
class ReActStep:
    """ReAct 循环的单个步骤(动态生成,非硬编码)."""
    
    step_id: str
    thought: str
    reasoning: str
    evidence: dict[str, Any]
    action_type: str
    action: dict[str, Any]
    observation: Optional[dict[str, Any]] = None
    timestamp_ms: int = field(default_factory=lambda: time.time_ns() // 1000000)


@dataclass
class ProactiveAgentResult:
    """主动 Agent 执行结果."""
    
    ok: bool
    output: dict[str, Any]
    usage: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    react_steps: list[ReActStep] = field(default_factory=list)
    bdi_state: dict[str, Any] = field(default_factory=dict)
    llm_interactions: list[dict[str, Any]] = field(default_factory=list)


class BaseProactiveAgent:
    """
    主动 Agent 基类.
    
    具备:
    1. BDI 模型:信念、愿望、意图
    2. ReAct 循环:动态生成 thought/reasoning/evidence
    3. 后台监控:主动感知环境
    4. CoT 思维链:每个步骤都有推理过程
    """
    
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        prompt_version: str | None = None,
        policy_version: str | None = None,
        model: str | None = None,
        enable_background_monitor: bool = True,
        monitor_interval_seconds: int = 60,
        enable_context_compression: bool = False,
        context_compressor: Any | None = None,
    ) -> None:
        """
        初始化主动 Agent.
        
        Args:
            name: Agent 名称
            system_prompt: 系统提示词
            prompt_version: 提示词版本
            policy_version: 策略版本
            model: 模型名称
            enable_background_monitor: 是否启用后台监控
            monitor_interval_seconds: 后台监控间隔(秒)
            enable_context_compression: 是否启用上下文压缩
            context_compressor: 自定义 ContextCompressor 实例
        """
        self._name = name
        self._system_prompt = system_prompt
        self._prompt_version = prompt_version
        self._policy_version = policy_version
        self._model = model
        self._enable_monitor = enable_background_monitor
        self._monitor_interval = monitor_interval_seconds

        # 上下文压缩器
        if context_compressor is not None:
            self._context_compressor = context_compressor
        elif enable_context_compression:
            from riskmonitor_multiagent.memory.context_compressor import ContextCompressor
            self._context_compressor = ContextCompressor(enable_llm_summary=False)
        else:
            self._context_compressor = None
        
        self._base_agent = BaseAgent(
            name=name,
            system_prompt=system_prompt,
            model=model,
            prompt_version=prompt_version,
            policy_version=policy_version,
        )
        
        self._beliefs: list[Belief] = []
        self._desires: list[Desire] = []
        self._intentions: list[Intention] = []
        
        self._llm_interactions: list[dict[str, Any]] = []
        
        self._monitor_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        self._last_task_result: Optional[ProactiveAgentResult] = None

        # 三层 prompt 构建器 (可选增强, 默认 None)
        self._prompt_builder: TieredPromptBuilder | None = None

        if self._enable_monitor:
            self._init_desires()
    
    def _init_desires(self) -> None:
        """初始化 Agent 的愿望(子类可重写)."""
        pass
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    def add_belief(self, content: Any, source: str, confidence: float = 1.0) -> Belief:
        """添加信念."""
        belief = Belief(content=content, source=source, confidence=confidence)
        self._beliefs.append(belief)
        logger.debug(f"[{self._name}] Added belief: {belief.belief_id}")
        return belief
    
    def get_beliefs(self, source: Optional[str] = None) -> list[Belief]:
        """获取信念."""
        if source:
            return [b for b in self._beliefs if b.source == source]
        return list(self._beliefs)
    
    def clear_beliefs(self) -> None:
        """清空信念."""
        self._beliefs.clear()
    
    def add_desire(self, description: str, priority: int = 0) -> Desire:
        """添加愿望."""
        desire = Desire(description=description, priority=priority)
        self._desires.append(desire)
        logger.debug(f"[{self._name}] Added desire: {desire.desire_id}")
        return desire
    
    def get_active_desires(self) -> list[Desire]:
        """获取活跃愿望(按优先级排序)."""
        active = [d for d in self._desires if d.active]
        return sorted(active, key=lambda x: -x.priority)
    
    def add_intention(
        self,
        description: str,
        target_agent: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_params: Optional[dict[str, Any]] = None,
    ) -> Intention:
        """添加意图."""
        intention = Intention(
            description=description,
            target_agent=target_agent,
            tool_name=tool_name,
            tool_params=tool_params,
            status="pending",
        )
        self._intentions.append(intention)
        logger.debug(f"[{self._name}] Added intention: {intention.intention_id}")
        return intention
    
    def get_pending_intentions(self) -> list[Intention]:
        """获取待处理意图."""
        return [i for i in self._intentions if i.status == "pending"]
    
    def update_intention_status(self, intention_id: str, status: str) -> bool:
        """更新意图状态."""
        for intention in self._intentions:
            if intention.intention_id == intention_id:
                intention.status = status
                return True
        return False
    
    def get_bdi_state(self) -> dict[str, Any]:
        """获取 BDI 状态摘要."""
        return {
            "agent_name": self._name,
            "beliefs": [
                {"belief_id": b.belief_id, "source": b.source, "confidence": b.confidence}
                for b in self._beliefs
            ],
            "desires": [
                {"desire_id": d.desire_id, "description": d.description, "priority": d.priority, "active": d.active}
                for d in self._desires
            ],
            "intentions": [
                {"intention_id": i.intention_id, "description": i.description, "status": i.status}
                for i in self._intentions
            ],
        }
    
    def record_llm_interaction(
        self,
        interaction_type: str,
        system_prompt: str,
        user_prompt: str,
        raw_response: str,
        parsed_output: dict[str, Any],
        latency_ms: int,
        tokens_used: int = 0,
        model: str = "",
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """记录 LLM 交互."""
        interaction = {
            "timestamp_ms": int(time.time() * 1000),
            "agent_name": self._name,
            "interaction_type": interaction_type,
            "system_prompt": system_prompt[:500] if system_prompt else "",
            "user_prompt": user_prompt[:1000] if user_prompt else "",
            "raw_response": raw_response[:2000] if raw_response else "",
            "parsed_output": parsed_output,
            "latency_ms": latency_ms,
            "tokens_used": tokens_used,
            "model": model,
            "success": success,
            "error": error,
        }
        self._llm_interactions.append(interaction)
    
    def get_llm_interactions(self) -> list[dict[str, Any]]:
        """获取 LLM 交互记录."""
        return list(self._llm_interactions)
    
    def clear_llm_interactions(self) -> None:
        """清空 LLM 交互记录."""
        self._llm_interactions.clear()

    async def _maybe_compress_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        task_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """在 LLM 调用前检查并压缩上下文.

        如果压缩器已配置且消息超过阈值, 自动压缩.
        压缩失败时返回原始消息, 不中断主流程.

        Args:
            messages: 原始消息列表
            task_context: 可选的任务上下文

        Returns:
            压缩后或原始的消息列表
        """
        if not self._context_compressor:
            return messages

        try:
            if self._context_compressor.should_compress(messages):
                result = await self._context_compressor.compress(
                    messages, task_context=task_context,
                )
                if result.compressed:
                    logger.info(
                        "[%s] Context compressed: %d -> %d tokens (%.1f%% ratio, %d messages summarized)",
                        self._name,
                        result.original_tokens,
                        result.compressed_tokens,
                        result.compression_ratio * 100,
                        result.summarized_count,
                    )
                    return result.compressed_messages
        except Exception as e:
            logger.warning("[%s] Context compression failed, using original: %s", self._name, e)

        return messages
    
    async def start_background_monitor(self) -> None:
        """启动后台监控(真正的主动性)."""
        if self._monitor_task is not None:
            logger.warning(f"[{self._name}] Monitor already running")
            return
        
        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"[{self._name}] Background monitor started")
    
    async def stop_background_monitor(self) -> None:
        """停止后台监控."""
        if self._monitor_task is None:
            return
        
        self._is_running = False
        self._monitor_task.cancel()
        try:
            await self._monitor_task
        except asyncio.CancelledError:
            pass
        self._monitor_task = None
        logger.info(f"[{self._name}] Background monitor stopped")
    
    async def _monitor_loop(self) -> None:
        """后台监控循环 - 主动感知环境."""
        logger.info(f"[{self._name}] Monitor loop started")
        
        while self._is_running:
            try:
                await self._perceive_environment()
                
                await self._deliberate()
                
                await self._act()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"[{self._name}] Monitor loop error: {e}")
            
            await asyncio.sleep(self._monitor_interval)
        
        logger.info(f"[{self._name}] Monitor loop exited")
    
    async def _perceive_environment(self) -> None:
        """感知环境 - 更新信念(子类可重写)."""
        pass
    
    async def _deliberate(self) -> None:
        """思考 - 根据信念和愿望形成意图."""
        # 获取最新的信念
        recent_beliefs = self.get_beliefs()[-5:]  # 最近 5 个信念
        
        # 获取活跃的愿望
        active_desires = self.get_active_desires()
        
        # 检查是否有需要主动处理的情况
        for belief in recent_beliefs:
            # 如果信念来自系统监控,检查是否需要主动告警
            if belief.source == "system_metrics":
                if belief.content.get("metric") == "error_rate":
                    error_rate = belief.content.get("value", 0)
                    if error_rate > 0.1:  # 错误率超过 10%
                        # 形成主动告警的意图
                        self.add_intention(
                            description=f"主动告警:系统错误率异常 ({error_rate*100:.1f}%)",
                            target_agent="orchestrator",
                            tool_name="submit_alerts",
                            tool_params={
                                "alert_type": "system_error",
                                "severity": "high" if error_rate > 0.2 else "medium",
                                "message": f"系统错误率 {error_rate*100:.1f}% 超过阈值 (10%)",
                                "metric_name": "error_rate",
                                "metric_value": error_rate,
                            },
                        )
                        logger.info(f"[{self._name}] Created proactive alert intention for error rate {error_rate*100:.1f}%")
    
    async def _act(self) -> None:
        """行动 - 执行意图."""
        pending_intentions = self.get_pending_intentions()
        
        for intention in pending_intentions:
            # 更新状态为 executing
            self.update_intention_status(intention.intention_id, "executing")
            
            try:
                # 如果有目标 Agent,发送消息
                if intention.target_agent:
                    from riskmonitor_multiagent.orchestration.proactive_workflow import get_proactive_workflow

                    proactive_event = self._build_proactive_event(intention=intention)

                    workflow = get_proactive_workflow()
                    candidate_agents = list(
                        dict.fromkeys(
                            [
                                intention.target_agent,
                                "critic",
                                "orchestrator",
                            ]
                        )
                    )
                    await workflow.start_from_event(
                        event=proactive_event,
                        candidate_agents=candidate_agents,
                    )

                    logger.info(
                        f"[{self._name}] Sent proactive event to unified workflow via {intention.target_agent}"
                    )
                
                # 更新状态为 completed
                self.update_intention_status(intention.intention_id, "completed")
                
            except Exception as e:
                logger.exception(f"[{self._name}] Failed to execute intention: {e}")
                self.update_intention_status(intention.intention_id, "failed")

    def _build_proactive_event(self, *, intention: Intention) -> dict[str, Any]:
        """把主动意图转换为统一系统事件."""
        tool_params = dict(intention.tool_params or {})
        event_type = EventType.TASK_CREATED
        if tool_params.get("metric_name") == "error_rate":
            event_type = EventType.RISK_BREACH_DETECTED

        task_payload = {
            "task_id": f"proactive_{intention.intention_id}",
            "session_id": f"proactive_{self._name}",
            "content": intention.description,
            "task": {
                "task_id": f"proactive_{intention.intention_id}",
                "session_id": f"proactive_{self._name}",
                "source": "system_event",
                "payload": {
                    "content": intention.description,
                    "proactive_intention_id": intention.intention_id,
                    "tool_name": intention.tool_name,
                    "tool_params": tool_params,
                },
            },
            "trigger_reason": intention.description,
            "trigger_evidence": {
                "source_agent": self._name,
                "tool_name": intention.tool_name,
                "tool_params": tool_params,
            },
            "target_agent": intention.target_agent,
        }
        return new_event(
            event_type=event_type,
            source_agent=self._name,
            target_agent=intention.target_agent,
            payload=task_payload,
            priority="high" if event_type == EventType.RISK_BREACH_DETECTED else "normal",
        )
    
    async def run_with_react(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
        max_tokens: int = 512,
        max_steps: int = 5,
    ) -> ProactiveAgentResult:
        """
        使用 ReAct 循环执行任务.
        
        这是核心方法,每个任务都会走:
        1. Thought: 生成思考
        2. Reasoning: 生成推理理由
        3. Evidence: 生成证据
        4. Action: 执行行动
        5. Observation: 观察结果
        
        Args:
            task: 任务定义
            context: 上下文
            max_tokens: 最大 Token 数
            max_steps: 最大步骤数
            
        Returns:
            ProactiveAgentResult 包含执行结果和 ReAct 步骤
        """
        start_time = time.time()
        inc_counter(f"proactive_agent_{self._name}_runs_total")
        
        react_steps: list[ReActStep] = []
        
        try:
            for step_idx in range(max_steps):
                step_id = f"step_{step_idx + 1}"
                logger.debug(f"[{self._name}] ReAct {step_id}/{max_steps}")
                
                thought = await self._generate_thought(task, react_steps, context)
                
                reasoning = await self._generate_reasoning(task, react_steps, thought, context)
                
                evidence = await self._generate_evidence(task, react_steps, thought, reasoning, context)
                
                action_type, action = await self._decide_action(task, react_steps, thought, context)
                
                observation = await self._execute_action(action_type, action)
                
                step = ReActStep(
                    step_id=step_id,
                    thought=thought,
                    reasoning=reasoning,
                    evidence=evidence,
                    action_type=action_type,
                    action=action,
                    observation=observation,
                )
                react_steps.append(step)
                
                if await self._should_terminate(task, react_steps):
                    logger.debug(f"[{self._name}] ReAct terminated at {step_id}")
                    break
            
            final_output = await self._generate_final_answer(task, react_steps)
            
            result = ProactiveAgentResult(
                ok=True,
                output=final_output,
                react_steps=react_steps,
                bdi_state=self.get_bdi_state(),
                llm_interactions=self.get_llm_interactions(),
            )
            
            self._last_task_result = result
            inc_counter(f"proactive_agent_{self._name}_runs_success")
            
            latency_ms = (time.time() - start_time) * 1000
            observe_ms(f"proactive_agent_{self._name}_latency_ms", latency_ms)
            
            return result
            
        except Exception as e:
            logger.exception(f"[{self._name}] ReAct execution failed: {e}")
            inc_counter(f"proactive_agent_{self._name}_runs_error")
            
            return ProactiveAgentResult(
                ok=False,
                output={"error": str(e)},
                react_steps=react_steps,
                bdi_state=self.get_bdi_state(),
                llm_interactions=self.get_llm_interactions(),
            )
    
    async def _generate_thought(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
        context: dict[str, Any] | None,
    ) -> str:
        """生成思考 - 动态生成,非硬编码."""
        history_text = self._format_history(history)
        context_text = self._format_context(context)
        
        prompt = f"""You are {self._name}. Generate your next thought about the task.

Task: {task}
Context: {context_text}
History: {history_text}

Generate a thought about what you should consider or do next. Be specific and relevant to the task.

Only return the thought text, no JSON format."""

        try:
            from riskmonitor_multiagent.llm import LlmClient
            
            start_time = time.time()
            client = LlmClient()
            messages = await self._maybe_compress_messages(
                [
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt},
                ],
                task_context=task,
            )
            resp = await client.chat_completions(
                messages=messages,
                model=self._model,
                temperature=0.7,
                max_tokens=128,
                use_cache=False,
            )
            latency_ms = int((time.time() - start_time) * 1000)
            
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            thought = content.strip() if content.strip() else "继续执行任务"
            
            self.record_llm_interaction(
                interaction_type="thought",
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                raw_response=content,
                parsed_output={"thought": thought},
                latency_ms=latency_ms,
                model=self._model or "",
                success=True,
            )
            
            return thought
        except Exception as e:
            self.record_llm_interaction(
                interaction_type="thought",
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                raw_response="",
                parsed_output={},
                latency_ms=0,
                model=self._model or "",
                success=False,
                error=str(e),
            )
            return "继续执行任务"
    
    async def _generate_reasoning(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
        thought: str,
        context: dict[str, Any] | None,
    ) -> str:
        """生成推理理由 - CoT 核心."""
        history_text = self._format_history(history)
        
        prompt = f"""You are {self._name}. Generate reasoning for your thought.

Task: {task}
Your thought: {thought}
History: {history_text}

Generate a reasoning that explains why you chose this thought. Consider:
- What information do you have?
- What do you need to verify?
- What are the risks or uncertainties?

Only return the reasoning text, no JSON format."""

        try:
            from riskmonitor_multiagent.llm import LlmClient
            
            start_time = time.time()
            client = LlmClient()
            messages = await self._maybe_compress_messages(
                [
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt},
                ],
                task_context=task,
            )
            resp = await client.chat_completions(
                messages=messages,
                model=self._model,
                temperature=0.7,
                max_tokens=256,
                use_cache=False,
            )
            latency_ms = int((time.time() - start_time) * 1000)
            
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            reasoning = content.strip() if content.strip() else "基于任务要求执行"
            
            self.record_llm_interaction(
                interaction_type="reasoning",
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                raw_response=content,
                parsed_output={"reasoning": reasoning},
                latency_ms=latency_ms,
                model=self._model or "",
                success=True,
            )
            
            return reasoning
        except Exception as e:
            self.record_llm_interaction(
                interaction_type="reasoning",
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                raw_response="",
                parsed_output={},
                latency_ms=0,
                model=self._model or "",
                success=False,
                error=str(e),
            )
            return "基于任务要求执行"
    
    async def _generate_evidence(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
        thought: str,
        reasoning: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """生成证据 - CoT 核心."""
        beliefs = self.get_beliefs()
        beliefs_text = "\n".join([
            f"- {b.source}: {b.content}" 
            for b in beliefs[-5:]
        ]) if beliefs else "No beliefs yet"
        
        prompt = f"""You are {self._name}. Generate evidence for your reasoning.

Your thought: {thought}
Your reasoning: {reasoning}
Current beliefs: {beliefs_text}

Generate evidence that supports your reasoning. Cite specific sources or data.

Evidence (as JSON with keys like "sources", "data", "references"):"""

        start_time = time.time()
        result = await self._base_agent.ask_json(
            user_prompt=prompt,
            fallback={"sources": [], "data": {}},
            max_tokens=256,
        )
        latency_ms = int((time.time() - start_time) * 1000)
        
        self.record_llm_interaction(
            interaction_type="evidence",
            system_prompt=self._system_prompt,
            user_prompt=prompt,
            raw_response=str(result.output),
            parsed_output=result.output,
            latency_ms=latency_ms,
            model=self._model or "",
            success=result.ok,
        )
        
        return result.output
    
    async def _decide_action(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
        thought: str,
        context: dict[str, Any] | None,
    ) -> tuple[str, dict[str, Any]]:
        """决定行动."""
        prompt = f"""You are {self._name}. Decide your next action.

Task: {task}
Your thought: {thought}
History: {self._format_history(history)}

Choose an action type and parameters:
- "llm_call": Make another LLM call to gather more information
- "tool_call": Execute a tool (specify tool_name and params)
- "finalize": Task is complete, generate final answer

Return as JSON with "action_type" and "action" (dict with params)."""

        start_time = time.time()
        result = await self._base_agent.ask_json(
            user_prompt=prompt,
            fallback={"action_type": "finalize", "action": {"answer": "任务已完成"}},
            max_tokens=256,
        )
        latency_ms = int((time.time() - start_time) * 1000)
        
        output = result.output
        action_type = output.get("action_type", "finalize")
        action = output.get("action", {})
        
        self.record_llm_interaction(
            interaction_type="action",
            system_prompt=self._system_prompt,
            user_prompt=prompt,
            raw_response=str(output),
            parsed_output=output,
            latency_ms=latency_ms,
            model=self._model or "",
            success=result.ok,
        )
        
        return action_type, action
    
    async def _execute_action(self, action_type: str, action: dict[str, Any]) -> dict[str, Any]:
        """执行行动."""
        if action_type == "llm_call":
            return {"status": "llm_call_executed", "action": action}
        elif action_type == "tool_call":
            return await self._execute_tool_call(action)
        elif action_type == "finalize":
            return {"status": "finalized", "result": action}
        elif action_type == "ask_human":
            # 真正的 ask_human 实现 - 等待用户回答
            question = action.get("question", "需要您的帮助")
            context = action.get("context", {})
            timeout = action.get("timeout", 300)  # 默认 5 分钟
            
            from riskmonitor_multiagent.proactive_agents.question_manager import get_question_manager
            
            manager = get_question_manager()
            answer = await manager.ask_user(
                agent_name=self._name,
                question=question,
                context=context,
                timeout_seconds=timeout,
            )
            
            return {
                "status": "human_answered",
                "question": question,
                "answer": answer,
                "timeout": answer.startswith("[超时]"),
            }
        else:
            return {"status": "unknown_action", "action": action}
    
    async def _execute_tool_call(self, action: dict[str, Any]) -> dict[str, Any]:
        """执行工具调用(子类可重写)."""
        return {"status": "tool_call_not_implemented", "action": action}
    
    async def _should_terminate(self, task: dict[str, Any], history: list[ReActStep]) -> bool:
        """检查是否应该终止."""
        if not history:
            return False
        
        last_step = history[-1]
        
        # 如果是 finalize,终止
        if last_step.action_type == "finalize":
            return True
        
        # 如果是 ask_human 但已超时,终止
        if last_step.action_type == "ask_human":
            observation = last_step.observation
            if observation and observation.get("timeout"):
                return True  # 超时后终止
        
        return False
    
    async def _generate_final_answer(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
    ) -> dict[str, Any]:
        """生成最终答案."""
        steps_summary = "\n".join([
            f"Step {s.step_id}: {s.thought} -> {s.action_type}"
            for s in history
        ])
        
        prompt = f"""You are {self._name}. Generate final answer based on your reasoning chain.

Task: {task}
Reasoning chain:
{steps_summary}

Generate a comprehensive final answer as JSON."""

        result = await self._base_agent.ask_json(
            user_prompt=prompt,
            fallback={"summary": "任务已完成", "conclusion": "基于推理链完成"},
            max_tokens=512,
        )
        
        return result.output
    
    def _format_history(self, history: list[ReActStep]) -> str:
        """格式化历史步骤."""
        if not history:
            return "No previous steps"
        
        lines = []
        for step in history[-3:]:
            thought_str = str(step.thought) if step.thought else ""
            reasoning_str = str(step.reasoning) if step.reasoning else ""
            lines.append(f"- {step.step_id}: Thought={thought_str[:50]}... Reason={reasoning_str[:50]}... Action={step.action_type}")
        
        return "\n".join(lines)
    
    def _format_context(self, context: dict[str, Any] | None) -> str:
        """格式化上下文."""
        if not context:
            return "No context"
        
        return str(context)[:500]

    # ------------------------------------------------------------------ #
    # 三层 prompt 构建器集成 (可选增强)
    # ------------------------------------------------------------------ #
    def set_prompt_builder(self, builder: TieredPromptBuilder) -> None:
        """设置三层 prompt 构建器.

        设置后, 构建 LLM messages 时将使用三层分离策略;
        未设置时使用现有逻辑.

        Args:
            builder: TieredPromptBuilder 实例
        """
        self._prompt_builder = builder
        logger.info(f"[{self._name}] TieredPromptBuilder enabled")

    def build_tiered_messages(
        self,
        *, 
        agent_role: str | None = None,
        tools_index: list[dict] | None = None,
        behavior_rules: list[str] | None = None,
        skills: list[dict] | None = None,
        project_rules: list[str] | None = None,
        memory_summary: dict[str, Any] | None = None,
        current_event: dict[str, Any] | None = None,
        task: dict[str, Any] | None = None,
        react_history: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        """使用三层 prompt 构建器组装 messages.

        如果未设置 prompt_builder, 回退到现有的单 system_prompt 方式.

        Returns:
            messages 列表
        """
        if self._prompt_builder is None:
            # 回退: 使用现有的单 system_prompt 方式
            return [{"role": "system", "content": self._system_prompt}]

        builder = self._prompt_builder
        stable = builder.build_stable_tier(
            agent_role=agent_role or self._system_prompt,
            tools_index=tools_index or [],
            behavior_rules=behavior_rules or [],
        )
        context = builder.build_context_tier(
            skills=skills or [],
            project_rules=project_rules or [],
            memory_summary=memory_summary,
        )
        volatile = builder.build_volatile_tier(
            current_event=current_event,
            task=task or {},
            react_history=react_history,
        )
        return builder.assemble_messages(stable, context, volatile)


__all__ = [
    "Belief",
    "Desire",
    "Intention",
    "ReActStep",
    "ProactiveAgentResult",
    "BaseProactiveAgent",
]
