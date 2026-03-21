# OpenRouter 配置指南

## 1. 获取 API Key

1. 访问 [OpenRouter](https://openrouter.ai/)
2. 点击右上角 "Sign In" 登录（支持 GitHub/Google 登录）
3. 登录后访问 [Keys](https://openrouter.ai/keys) 页面
4. 点击 "Create Key" 创建新的 API Key
5. 复制 Key 并保存到安全位置（例如 `.env` 文件）

## 2. 配置 .env 文件

在项目根目录的 `.env` 文件中配置：

```bash
# LLM（OpenRouter + GPT-4o-mini，支持严格 JSON Schema）
LLM_API_KEY=sk-or-v1-YOUR_OPENROUTER_API_KEY
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openai/gpt-4o-mini

# OpenRouter 可选配置（用于排行榜排名）
LLM_HTTP_REFERER=https://github.com/RiskMonitor-MultiAgent
LLM_APP_TITLE=RiskMonitor-MultiAgent

# 不使用固定 IP（OpenRouter 无需 DNS 绕过）
LLM_RESOLVE_IP=
```

## 3. 支持的模型

OpenRouter 提供 200+ 种模型，推荐使用以下支持**严格 JSON Schema**的模型：

### 推荐模型

| 模型 | 价格 (Input/Output) | 特点 |
|------|-------------------|------|
| `openai/gpt-4o-mini` | $0.15 / $0.60 per 1M tokens | ⭐ 性价比最高，推荐 |
| `openai/gpt-4o` | $2.50 / $10 per 1M tokens | 最新 GPT-4，最强性能 |
| `deepseek/deepseek-chat` | ¥1 / ¥2 per 1M tokens | 国产模型，便宜 |
| `google/gemini-2.0-flash` | $0.075 / $0.30 per 1M tokens | Google 原生支持 |

### 完整模型列表

访问 [OpenRouter Models](https://openrouter.ai/models) 查看所有可用模型。

## 4. 价格说明

OpenRouter 按实际使用的 tokens 计费：

- **Input tokens**: 发送给模型的文本（prompt）
- **Output tokens**: 模型生成的文本（response）
- **1M tokens** ≈ 750,000 英文单词 或 500,000 中文字符

### 示例成本

运行一次完整评估（42 个用例）：
- 约消耗 50,000 - 100,000 tokens
- GPT-4o-mini 成本：约 $0.03 - $0.06
- 每天运行 10 次，月成本约 $10 - $20

## 5. 充值

1. 访问 [Credits](https://openrouter.ai/credits) 页面
2. 最低充值 $5
3. 支持信用卡/PayPal

## 6. 监控用量

访问 [Activity](https://openrouter.ai/activity) 查看：
- 每日/每月用量
- 各模型消耗
- 成本统计

## 7. 故障排查

### 问题 1: 401 Unauthorized

**原因**: API Key 无效或过期

**解决**: 
- 检查 `.env` 中的 `LLM_API_KEY` 是否正确
- 重新创建 API Key

### 问题 2: 429 Too Many Requests

**原因**: 超出速率限制

**解决**:
- 等待几分钟后重试
- 升级账户提高限额

### 问题 3: JSON 输出仍有格式问题

**原因**: 某些模型不支持 JSON Mode

**解决**:
- 确保使用 `openai/gpt-4o-mini` 或 `openai/gpt-4o`
- 检查代码中 `use_json_mode=True` 参数

## 8. 参考资料

- [OpenRouter 官方文档](https://openrouter.ai/docs)
- [JSON Mode 支持](https://openrouter.ai/docs/features/json-mode)
- [模型列表](https://openrouter.ai/models)
- [价格对比](https://openrouter.ai/models?o=pricing_max_tokens)
