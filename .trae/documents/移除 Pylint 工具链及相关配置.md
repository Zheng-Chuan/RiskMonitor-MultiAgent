# 移除 Pylint 及其相关配置的计划

我们将从项目中彻底移除 pylint，包括配置文件、依赖、构建脚本、Docker 服务以及代码中的相关注释。

## 1. 删除配置文件
- 删除 [`.pylintrc`](file:///Users/zhengchuan/Documents/TECH/Repo/RiskMonitor-MCP/.pylintrc)

## 2. 移除依赖与环境配置
- **requirements.txt**: 移除 `pylint` 依赖。
- **docker-compose.yml**: 移除 `lint-runner` 服务定义。

## 3. 清理构建脚本 (Makefile)
- 移除 `make pylint` 和 `make lint` 命令目标。
- 移除 `help` 命令中关于 lint 的说明。

## 4. 更新文档
- **docs/QUICKSTART.md**: 删除 "运行 pylint 作为交付前检查" 章节。
- **docs/ROADMAP.md**: 更新相关任务状态，移除关于 pylint 的规划。

## 5. 清理代码中的 Pylint 注释
- 批量移除代码文件（如 `main.py`, `src/...`, `tests/...`）中出现的 `# pylint: disable=...` 注释，保持代码整洁。

## 6. 提交与推送
- 运行 `git add` 和 `git commit` 提交更改。
- 运行 `git push` 推送到远程仓库。
