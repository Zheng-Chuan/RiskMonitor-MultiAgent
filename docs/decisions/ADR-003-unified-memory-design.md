# ADR-003: 统一记忆架构设计（Private + Shared + Long-term）

**状态**：Decided, Implemented
**日期**：2026-06-26
**作者**：RiskMonitor-MultiAgent 项目组

## Context / 问题背景

多 Agent 系统面临"协作与隔离"的矛盾：

1. **协作需求**：Agent 之间需要共享任务进展、工具执行结果、冲突仲裁结论
2. **隔离需求**：不同角色的推理中间产物不应互相干扰，避免记忆污染导致角色漂移
3. **学习需求**：高置信的成功经验需要沉淀为长期知识，供后续任务复用
4. **恢复需求**：中断后恢复执行需要读取完整的任务状态快照

早期系统只有 shared memory 一层，所有 Agent 读写同一个空间。这带来了以下问题：
- 角色边界模糊：Analyst 的分析中间态被 Engineer 误读为确定结论
- 记忆污染：一个 Agent 的错误推理扩散到其他 Agent 的决策
- 恢复困难：缺乏结构化的任务状态快照，恢复时需要重新推理全部历史

## Decision / 决策

**采用三层记忆 + 四条主链的统一记忆架构。**

### 三层记忆模型

#### 第一层：Private Task Memory（私有任务记忆）

每个 Agent 在每次任务中拥有仅本角色可读可写的私有记忆空间。

模板结构：
```
PrivateTaskMemory {
  role: str               # Agent 角色标识
  task_goal: str          # 当前任务目标
  current_progress: str   # 执行进度
  open_questions: str[]   # 待解决问题
  recent_observations: str[]  # 最近观测
  next_intended_action: str   # 下一步计划
}
```

隔离规则：
- 默认只能由对应 Agent 读写
- 其他 Agent 只能通过 Shared Board 间接获取摘要
- `memory_cross_talk_rate` 指标监控越界访问

#### 第二层：Shared Memory Board（公共记忆看板）

多 Agent 协作的公共信息空间，每条记忆必须带来源和视角标识。

每条记忆包含：
- `agent_role`：写入角色
- `agent_perspective`：角色视角（分析/执行/审查）
- `task_phase`：写入时的任务阶段
- `confidence`：置信度
- `trace_ref`：关联的 trace entry

用途：跨角色信息共享、冲突检测、协作协调。

#### 第三层：Long-term Experience（长期经验）

由 CriticAgent 基于 confidence policy 沉淀的高置信结论。

每条经验包含：
- `agent_perspective`：产出视角
- `decision_pattern`：决策模式
- `applicable_conditions`：适用条件
- `failure_boundary`：失败边界
- `evidence_refs`：证据引用

只有满足置信门槛的经验被沉淀。低置信 summary 不进入长期经验库。

### 四条主链

#### Planning Chain（规划链）

OrchestratorAgent 规划前必须：
1. 读取 Shared Board 中的最新协作状态
2. 检索 Long-term Experience 中的相关历史决策
3. 将命中的经验以 few-shot 形式注入规划 prompt
4. 输出计划时标注 `memory_hits` 引用

#### Execution Chain（执行链）

TaskGraphExecutor 在关键 step 执行前后：
1. 前：读取 Private Memory 获取当前进度和上下文
2. 执行：调用工具/委托 Agent
3. 后：更新 Private Memory（progress, observations）
4. 后：向 Shared Board 写入关键结果摘要

#### Finalize Chain（收尾链）

CriticAgent 在最终审查时：
1. 评估本次执行质量
2. 若 quality_score >= confidence_threshold，提取可复用模式
3. 沉淀为 Long-term Experience
4. 若不满足阈值，记录但标记为 rejected（不沉淀）

#### Resume Chain（恢复链）

恢复执行时必须：
1. 加载 Private Memory 快照
2. 加载 Shared Board 快照
3. 加载 receipt state（工具执行回执）
4. 加载 run_summary（任务摘要）
5. 合并为 resume context 注入执行链路

### Few-shot 经验复用

`search_semantic()` 不只返回相似文本，还返回可复用的结构化经验片段。规划时能显式引用历史案例中的 `decision_pattern` 或 `failure_boundary`。

支持 `memory_on` / `memory_off` / `private_disabled` 三组对照实验验证记忆价值。

## Rationale / 理由

### 隔离防止记忆污染

Private Memory 确保 Analyst 的风险判断中间态不会被 Engineer 误读为确定指令。角色漂移可通过 `role_drift_rate` 指标检测。

### 共享支持协作

Shared Board 让多 Agent 在保持隔离的前提下交换必要信息。每条信息带来源标识，冲突可检测可仲裁。

### 经验沉淀支持学习

高置信经验沉淀为 Long-term Experience 后，后续类似任务可直接复用。A/B 实验证实 `memory_on` 相比 `memory_off` 的 `few_shot_reuse_rate` 从 0.0 提升到 1.0。

### 恢复有完整快照

三层记忆的快照组合（Private + Shared + Receipt State + Run Summary）提供了恢复执行所需的全部上下文。

## Consequences / 后果

| 后果 | 程度 | 说明 |
|------|------|------|
| 存储复杂度增加 | 中 | 需要维护三层独立存储和快照机制 |
| 隔离性提升 | 高 | 角色间记忆不互相污染 |
| 可恢复性提升 | 高 | 完整状态快照支持任意断点恢复 |
| 学习能力提升 | 高 | 高置信经验可跨任务复用 |
| 可度量性提升 | 高 | memory_hit_rate, memory_usefulness 等指标可追踪 |
| 维护成本增加 | 中 | TTL 策略、清理策略、一致性保障 |

## Considered Options / 考虑的其他方案

### 方案A: 纯 Shared Memory（现状）

**Pros**:
- 实现简单
- 所有 Agent 共享信息无障碍

**Cons**:
- 记忆污染风险高
- 无法区分来源和视角
- 恢复执行缺乏结构化快照

**为什么没选**：多 Agent 场景下，无隔离的共享记忆会导致角色漂移和错误传播。

### 方案B: 纯 Private Memory（完全隔离）

**Pros**:
- 隔离彻底
- 无污染风险

**Cons**:
- Agent 间无法高效协作
- 信息孤岛
- 汇总时缺乏共享上下文

**为什么没选**：多 Agent 协作的核心价值在于信息共享和多视角融合，完全隔离违背协作初衷。

## Update Log

- 2026-06-26: 创建本 ADR，确立三层统一记忆架构设计
