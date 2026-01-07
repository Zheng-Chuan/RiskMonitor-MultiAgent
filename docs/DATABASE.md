# 数据库设计

## 核心表结构

### Positions 表

```sql
CREATE TABLE positions (
    position_id VARCHAR(50) PRIMARY KEY,
    trader_id VARCHAR(50) NOT NULL,
    desk VARCHAR(100) NOT NULL,
    security_id VARCHAR(100) NOT NULL,
    quantity DECIMAL(18, 4) NOT NULL,
    delta DECIMAL(18, 4),
    entry_date DATE NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Securities 表

```sql
CREATE TABLE securities (
    security_id VARCHAR(100) PRIMARY KEY,
    security_type VARCHAR(50) NOT NULL,  -- Stock, Option, Swap, Bond
    underlying VARCHAR(20),
    option_type VARCHAR(10),  -- Call / Put
    strike DECIMAL(18, 4),
    expiry_date DATE,
    currency VARCHAR(3) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Risk_Metrics 表

```sql
CREATE TABLE risk_metrics (
    metric_id INT AUTO_INCREMENT PRIMARY KEY,
    position_id VARCHAR(50) NOT NULL,
    calculation_date DATE NOT NULL,
    delta DECIMAL(18, 4),
    gamma DECIMAL(18, 4),
    vega DECIMAL(18, 4),
    theta DECIMAL(18, 4),
    rho DECIMAL(18, 4),
    cva DECIMAL(18, 2),
    usd_equivalent DECIMAL(18, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Risk_Limits 表

```sql
CREATE TABLE risk_limits (
    limit_id INT AUTO_INCREMENT PRIMARY KEY,
    scope VARCHAR(50) NOT NULL,  -- Trader / Desk / Firm
    scope_id VARCHAR(100) NOT NULL,
    limit_type VARCHAR(50) NOT NULL,  -- Delta / Gamma / Vega / CVA
    limit_value DECIMAL(18, 2) NOT NULL,
    effective_date DATE NOT NULL,
    expiry_date DATE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## 数据关系

```
positions (1) -----> (N) risk_metrics
    |
    | (N)
    ↓
securities (1)

risk_limits (N) -----> (1) scope (Trader/Desk/Firm)
```

## 索引策略

### Positions 表索引
```sql
CREATE INDEX idx_trader_id ON positions(trader_id);
CREATE INDEX idx_desk ON positions(desk);
CREATE INDEX idx_entry_date ON positions(entry_date);
CREATE INDEX idx_security_id ON positions(security_id);
```

### Risk_Metrics 表索引
```sql
CREATE INDEX idx_position_id ON risk_metrics(position_id);
CREATE INDEX idx_calculation_date ON risk_metrics(calculation_date);
CREATE INDEX idx_position_date ON risk_metrics(position_id, calculation_date);
```

### Risk_Limits 表索引
```sql
CREATE INDEX idx_scope ON risk_limits(scope, scope_id);
CREATE INDEX idx_effective_date ON risk_limits(effective_date);
```

## 数据生命周期管理

### 数据保留策略
- **Positions**: 永久保留
- **Risk_Metrics**: 保留3年，之后归档
- **Risk_Limits**: 保留历史版本，用于审计

### 数据归档
```sql
-- 归档3年前的风险指标数据
CREATE TABLE risk_metrics_archive LIKE risk_metrics;

INSERT INTO risk_metrics_archive
SELECT * FROM risk_metrics
WHERE calculation_date < DATE_SUB(CURDATE(), INTERVAL 3 YEAR);

DELETE FROM risk_metrics
WHERE calculation_date < DATE_SUB(CURDATE(), INTERVAL 3 YEAR);
```

## 备份策略

### 每日备份
```bash
# 全量备份
docker-compose exec -T mysql sh -lc 'mysqldump -u "$${MYSQL_USER}" -p"$${MYSQL_PASSWORD}" "$${MYSQL_DATABASE}"' > backup_$(date +%Y%m%d).sql

# 压缩备份
docker-compose exec -T mysql sh -lc 'mysqldump -u "$${MYSQL_USER}" -p"$${MYSQL_PASSWORD}" "$${MYSQL_DATABASE}"' | gzip > backup_$(date +%Y%m%d).sql.gz
```

### 恢复数据
```bash
# 从备份恢复
docker-compose exec -T mysql sh -lc 'mysql -u "$${MYSQL_USER}" -p"$${MYSQL_PASSWORD}" "$${MYSQL_DATABASE}"' < backup_20241031.sql

# 从压缩备份恢复
gunzip < backup_20241031.sql.gz | docker-compose exec -T mysql sh -lc 'mysql -u "$${MYSQL_USER}" -p"$${MYSQL_PASSWORD}" "$${MYSQL_DATABASE}"'
```
