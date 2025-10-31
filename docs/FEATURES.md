# 核心功能

## 数据模拟层

**目的**: 模拟真实的交易头寸数据流入关系数据库

### 模拟数据结构

**Positions 表**:
```python
{
    "position_id": "POS-2024-001",
    "trader_id": "TRADER-001",
    "desk": "Equity Derivatives",
    "security_id": "AAPL-CALL-150-20251231",
    "quantity": 1000,
    "delta": 600.0,
    "entry_date": "2024-10-01",
    "currency": "USD"
}
```

### 模拟场景

1. **单一期权头寸** - 买入AAPL看涨期权，计算Greeks和CVA
2. **复合策略头寸** - 跨式期权(Straddle)、价差策略(Spread)
3. **多币种头寸** - EUR、JPY、GBP期权，需要Dollarization
4. **对手方风险** - 不同交易对手，CVA计算

## MCP工具集

### 1. 头寸查询工具
- `query_positions_by_trader` - 查询特定交易员的所有头寸
- `query_positions_by_desk` - 查询整个交易台的头寸
- `query_positions_by_security` - 查询特定证券的所有头寸

### 2. Greeks计算工具
- `calculate_portfolio_greeks` - Portfolio级别风险度量
- `calculate_greeks_by_underlying` - 按标的资产分组的Greeks
- `calculate_delta_hedge_requirement` - 对冲策略建议

### 3. CVA计算工具
- `calculate_cva_by_counterparty` - 对手方信用风险评估
- `calculate_cva_change` - CVA风险归因分析
- `simulate_cva_stress` - 压力测试

### 4. 风险聚合工具
- `aggregate_risk_by_desk` - 管理层风险报告
- `aggregate_risk_by_asset_class` - 资产配置分析
- `dollarize_multi_currency_positions` - 跨币种风险统一度量

### 5. 限额检查工具
- `check_greeks_limits` - 实时风险监控
- `check_concentration_limits` - 防止过度集中
- `generate_limit_breach_alert` - 自动告警

### 6. 报表生成工具
- `generate_daily_risk_report` - 每日风险报告
- `generate_pnl_attribution_report` - 绩效分析
- `generate_regulatory_report` - 合规报送

### 7. 压力测试工具
- `run_market_stress_test` - 极端情景分析
- `run_historical_scenario` - 历史情景回测

### 8. 场景分析工具
- `analyze_what_if_scenario` - 假设分析
- `optimize_portfolio_for_target_greeks` - Portfolio优化

## 典型工作流

### 场景1: Risk Manager早晨风险检查

**自然语言请求**:
> "给我看看昨天股票衍生品交易台的整体风险情况，特别关注Delta和Vega暴露，以及是否有超限的情况"

**MCP工具调用链**:
```
1. query_positions_by_desk(desk="Equity Derivatives", date="2024-10-30")
2. calculate_portfolio_greeks(desk="Equity Derivatives")
3. check_greeks_limits(desk="Equity Derivatives")
4. generate_daily_risk_report(date="2024-10-30", scope="desk")
```

**输出**: Excel报表，包含所有头寸、Greeks汇总、限额使用情况

### 场景2: CVA团队对手方风险分析

**自然语言请求**:
> "分析一下对手方XYZ Bank的信用风险，计算我们的CVA暴露，并模拟如果他们的信用评级从A降到BBB会怎样"

**MCP工具调用链**:
```
1. query_positions_by_counterparty(counterparty="XYZ Bank")
2. calculate_cva_by_counterparty(counterparty="XYZ Bank")
3. simulate_cva_stress(counterparty="XYZ Bank", rating_change="A_to_BBB")
4. generate_cva_report(counterparty="XYZ Bank")
```

**输出**:
- 当前CVA: $6,000
- 评级下降后CVA: $30,000
- CVA增加: $24,000
- 建议: 考虑买入CDS对冲
