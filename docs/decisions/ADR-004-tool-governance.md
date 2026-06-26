# ADR-004: 零信任工具治理体系（5道关卡）

**状态**：Decided, Implemented
**日期**：2026-06-26
**作者**：RiskMonitor-MultiAgent 项目组

## Context / 问题背景

金融风控场景中，Agent 调用的工具可能产生真实的业务副作用：

- `write_alert`：创建风控告警，可能触发交易限制
- `submit_alerts`：提交告警到下游系统，影响合规状态
- `adjust_limit`：调整风控限额，直接影响交易能力

这些副作用动作如果被 AI 静默执行，将带来以下风险：
1. **合规风险**：未经审批的告警提交可能违反金融监管要求
2. **操作风险**：错误的限额调整可能导致风险暴露
3. **审计风险**：无法证明"谁在什么时候基于什么理由执行了什么操作"
4. **可逆性风险**：已提交的告警或限额变更可能无法撤回

系统需要一套完整的工具治理体系，确保每个副作用动作都**可审计、可拒绝、可回放**。

## Decision / 决策

**所有工具执行必须经过 RBAC → 预算 → 审批 → 超时重试 → 收据 五道关卡。**

### 关卡一：RBAC 权限检查

每个工具在 `tool_registry` 中注册时声明所需权限。每个 Agent 角色有独立的权限集。调用前先验证角色是否有权执行该工具。

```
ToolRegistration {
  tool_name: str
  required_permissions: str[]
  side_effect: bool
  risk_level: low | medium | high | critical
}
```

### 关卡二：预算检查

工具调用受以下预算约束：
- `max_tool_calls_per_run`：单次 run 的工具调用上限
- `max_retries_per_tool`：单工具最大重试次数
- `token_budget_per_run`：单次 run 的 token 预算
- `timeout_ms`：单次工具调用的超时限制

超出预算的调用直接拒绝，不进入执行阶段。

### 关卡三：审批门控

所有 `side_effect=true` 的工具自动受审批控制：

审批状态机：
```
pending → approved → executed
pending → rejected → blocked
pending → expired → blocked
approved → resumed（从阻断点恢复）
```

审批请求必须包含：
- `reason`：执行理由
- `risk_level`：风险等级
- `impact_scope`：影响范围
- `suggested_action`：建议动作
- `evidence_refs`：决策证据

### 关卡四：超时重试

工具执行带超时和重试策略：
- 超时后自动记录 `timeout` 失败分类
- 根据重试预算决定是否重试
- 重试时携带前次失败上下文

### 关卡五：标准化收据

每次工具执行（无论成功或失败）都产出标准化 Receipt：

```
Receipt (agent_receipt.v1) {
  command_id: str        # 关联的 Command ID
  tool_name: str         # 工具名
  inputs: dict           # 输入参数
  outputs: dict          # 输出结果
  status: ok | error     # 执行状态
  error: str | null      # 错误信息
  latency_ms: int        # 执行耗时
  side_effect: bool      # 是否有副作用
  approval_state: str    # 审批状态
  failure_classification: str | null  # 失败分类
  retry_count: int       # 重试次数
}
```

### 关键数据结构：Command

所有工具调用通过统一的 Command 结构发起：

```
Command (agent_command.v1) {
  command_id: str
  agent_role: str
  tool_name: str
  inputs: dict
  timeout_ms: int
  retry_budget: int
  require_approval: bool
  risk_level: str
  evidence_refs: str[]
}
```

### 失败分类体系

| 分类 | 说明 | 处理策略 |
|------|------|---------|
| `permission` | 权限不足 | 拒绝，不重试 |
| `validation` | 参数校验失败 | 拒绝，修正后可重试 |
| `runtime` | 运行时异常 | 可重试，按退避策略 |
| `dependency` | 依赖服务不可用 | 可重试，等待依赖恢复 |
| `timeout` | 执行超时 | 可重试，增大超时 |

### 统一执行入口

所有工具调用只能通过 `tool_registry.py` 和 `tool_executor.py` 执行。不存在绕过五道关卡的旁路。

## Rationale / 理由

### 金融合规要求

金融监管要求所有影响业务状态的操作必须可追溯、可审计。五道关卡确保每个副作用动作都有完整的证据链。

### 防止 AI 静默修改

LLM 可能产生幻觉或错误判断。审批门控确保高风险操作必须经过人工确认，不会被 AI 静默执行。

### 故障隔离

失败分类体系让系统知道"为什么失败"以及"是否可以重试"。permission 和 validation 失败不重试（避免死循环），runtime 和 dependency 失败可有策略地重试。

### 全链路可追踪

Receipt 作为工具执行的"收据"，是后续 Agent 决策和最终审计的关键证据。最终输出必须引用至少 1 个 receipt，确保结论有据可查。

## Consequences / 后果

| 后果 | 程度 | 说明 |
|------|------|------|
| 工具执行延迟增加 | 低 | 五道关卡主要是逻辑检查，非网络调用 |
| 审批导致任务阻塞 | 中 | 副作用工具需等待审批，但支持超时和恢复 |
| 审计能力极大提升 | 高 | 每个操作有完整 Receipt 和审批链 |
| 安全性极大提升 | 高 | 未授权操作 100% 被阻断 |
| 开发约束增加 | 中 | 新增工具必须按规范注册，声明权限和副作用 |
| 可回放性提升 | 高 | Command + Receipt 对构成完整的操作证据链 |

## Considered Options / 考虑的其他方案

### 方案A: 事后审计（先执行后审查）

**Pros**:
- 执行不阻塞
- 实现简单

**Cons**:
- 副作用已产生，无法撤回
- 不满足金融合规"事前审批"要求

**为什么没选**：金融场景中，错误的告警提交或限额调整可能造成不可逆后果。必须事前拦截。

### 方案B: 白名单模式（只允许特定组合）

**Pros**:
- 安全性高
- 规则简单明确

**Cons**:
- 灵活性差
- 新场景需要频繁修改白名单
- 无法支持 LLM 动态决策

**为什么没选**：金融风控任务的工具组合是动态的，白名单无法覆盖所有合法场景。

## Update Log

- 2026-06-26: 创建本 ADR，确立零信任工具治理五道关卡体系
