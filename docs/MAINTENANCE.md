# 文档与注释维护约定

本仓库的复杂度会在 Week 6+ 随 CDC, Sentinel, 多智能体编排显著上升. 为了避免代码变了但文档没变 或 注释失真, 这里固化一套最低维护标准.

## 维护原则

- 文档与 tests 同级重要: 实现变更必须同步更新 docs 与关键 docstring
- 先写当前已落地, 再写规划或设想: 文档里所有未来内容必须显式标注为计划或未实现
- 以入口为中心维护: main.py, src/riskmonitor_multiagent/server.py, docs/QUICKSTART.md 保持一致

## 何时必须更新文档

出现以下变化之一, 就必须同步更新 docs:

- 新增或删除或重命名 MCP tool, Resource, Prompt
- 新增或删除环境变量, 默认值变化, 启动方式变化
- 传输模式变化 stdio, sse, streamable-http, 端点变化 /health, /ready, /metrics, /mcp
- 数据表或 schema 变化 positions, alerts 以及 CDC 相关 schema
- 新增基础设施组件 docker compose, Kafka, Debezium
- 新增或变更 schema 文件与注册脚本 例如 schemas 与 scripts/schema_registry
- Sentinel 或 Multi Agent 流水线的职责变化 例如阈值口径, 角色输出字段

## 何时必须更新注释与 docstring

- 函数职责变化: 更新函数或模块 docstring 的说明参数返回异常段落
- 参数语义变化: 更新参数名默认值可选项说明, 避免误导调用方
- 业务流程变化: 更新工具入口的流程描述 例如 monitor_desk_exposure 的分步说明

## 建议的维护检查清单(提交前)

- docs/ROADMAP.md 的当前完成状态与仓库一致
- docs/QUICKSTART.md 的环境变量与启动方式可复现
- docs/ARCHITECTURE.md 的当前实现与规划边界清晰
- grep 关键字确认无过期信息 例如旧的 tool 名 旧的 env 名
