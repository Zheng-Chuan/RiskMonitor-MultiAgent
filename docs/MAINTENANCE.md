# 文档与注释维护约定

本仓库的复杂度会在 Week 6+ 随 CDC/流处理/多智能体编排显著上升。为了避免“代码变了但文档没变 / 注释失真”，这里固化一套最低维护标准。

## 维护原则

- 文档与 tests 同级重要：实现变更必须同步更新 docs 与关键 docstring。
- 先写“当前已落地”，再写“规划/设想”：文档里所有未来内容必须显式标注为“计划/未实现”。
- 以入口为中心维护：`main.py`、`src/riskmonitor_multiagent/server.py`、`docs/QUICKSTART.md` 保持一致。

## 何时必须更新文档

出现以下变化之一，就必须同步更新 docs：

- 新增/删除/重命名 MCP tool、Resource、Prompt
- 新增/删除环境变量、默认值变化、启动方式变化
- 传输模式变化(stdio/sse/streamable-http)、端点变化(/health /ready /metrics /mcp)
- 数据表或 schema 变化(positions/alerts 及后续 CDC 相关表)
- 新增基础设施组件(docker-compose, Kafka, Debezium 等)

## 何时必须更新注释与 docstring

- 函数职责变化：更新函数/模块 docstring 的“说明/参数/返回/异常”段落。
- 参数语义变化：更新参数名、默认值、可选项说明，避免误导调用方。
- 业务流程变化：更新工具入口的流程描述(例如 monitor_desk_exposure 的分步说明)。

## 建议的维护检查清单(提交前)

- docs/ROADMAP.md 的当前完成状态与仓库一致
- docs/QUICKSTART.md 的环境变量与启动方式可复现
- docs/ARCHITECTURE.md 的“当前实现”与“规划”边界清晰
- grep 关键字确认无过期信息(例如旧的 tool 名、旧的 env 名)
