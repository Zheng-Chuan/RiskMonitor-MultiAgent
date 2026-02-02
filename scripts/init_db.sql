-- RiskMonitor 数据库初始化脚本 (MySQL)
-- 用于创建最小可运行的数据库 schema 与演示数据

-- 创建 positions 表(Phase 1 简化版)
CREATE TABLE IF NOT EXISTS positions (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 为常用查询创建索引
CREATE INDEX idx_positions_trader ON positions(trader_id);
CREATE INDEX idx_positions_desk ON positions(desk);
CREATE INDEX idx_positions_security ON positions(security_id);
CREATE INDEX idx_positions_date ON positions(entry_date);

-- 创建 alerts 表(Week 4: 告警闭环)
CREATE TABLE IF NOT EXISTS alerts (
    alert_id VARCHAR(36) PRIMARY KEY,
    request_id VARCHAR(36) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    desk VARCHAR(100) NOT NULL,
    trader_id VARCHAR(50) DEFAULT NULL,
    metric_name VARCHAR(50) NOT NULL,
    metric_value DECIMAL(20, 2) NOT NULL,
    threshold_value DECIMAL(20, 2) NOT NULL,
    breach_amount DECIMAL(20, 2) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP NULL,
    acknowledged_by VARCHAR(50) DEFAULT NULL,
    INDEX idx_request_id (request_id),
    INDEX idx_alert_type (alert_type),
    INDEX idx_desk (desk),
    INDEX idx_created_at (created_at),
    INDEX idx_severity (severity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 插入测试用演示数据(符合金融领域常识的简化样例)
INSERT INTO positions (position_id, trader_id, desk, security_id, quantity, delta, entry_date, currency) VALUES
-- Equity Derivatives (股票衍生品)
('POS-2024-001', 'TRADER-001', 'Equity Derivatives', 'AAPL-CALL-175-20250331', 1000, 600.0, '2024-10-01', 'USD'),
('POS-2024-002', 'TRADER-001', 'Equity Derivatives', 'GOOGL-PUT-140-20250630', -500, -300.0, '2024-10-05', 'USD'),
('POS-2024-003', 'TRADER-001', 'Equity Derivatives', 'MSFT-CALL-420-20250331', 800, 480.0, '2024-10-08', 'USD'),
('POS-2024-004', 'TRADER-002', 'Equity Derivatives', 'TSLA-PUT-250-20250228', -1200, -720.0, '2024-10-10', 'USD'),
('POS-2024-005', 'TRADER-002', 'Equity Derivatives', 'NVDA-CALL-900-20250630', 500, 450.0, '2024-10-12', 'USD'),
('POS-2024-006', 'TRADER-003', 'Equity Derivatives', 'META-CALL-520-20250331', 600, 360.0, '2024-10-15', 'USD'),
('POS-2024-007', 'TRADER-003', 'Equity Derivatives', 'AMZN-PUT-160-20250430', -400, -240.0, '2024-10-18', 'USD'),

-- FX Derivatives (外汇衍生品)
('POS-2024-008', 'TRADER-004', 'FX Derivatives', 'EURUSD-FWD-20250331', 10000000, 50000.0, '2024-10-20', 'EUR'),
('POS-2024-009', 'TRADER-004', 'FX Derivatives', 'GBPUSD-CALL-1.30-20250228', 5000000, 125000.0, '2024-10-22', 'GBP'),
('POS-2024-010', 'TRADER-005', 'FX Derivatives', 'USDJPY-PUT-150-20250331', -8000000, -40000.0, '2024-10-25', 'JPY'),

-- Fixed Income (固定收益)
('POS-2024-011', 'TRADER-006', 'Fixed Income', 'US10Y-IRS-20250331', 50000000, 250000.0, '2024-10-28', 'USD'),
('POS-2024-012', 'TRADER-006', 'Fixed Income', 'EUR5Y-IRS-20250630', 30000000, 150000.0, '2024-10-29', 'EUR'),
('POS-2024-013', 'TRADER-007', 'Commodities', 'WTI-FUT-20250228', 1000, 50000.0, '2024-10-30', 'USD'),
('POS-2024-014', 'TRADER-007', 'Commodities', 'GOLD-FUT-20250331', 500, 100000.0, '2024-10-31', 'USD'),
('POS-2024-015', 'TRADER-008', 'Credit Trading', 'JPM-CDS-20250630', 10000000, 50000.0, '2024-10-31', 'USD')
;

GRANT SELECT, RELOAD, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'admin'@'%';
FLUSH PRIVILEGES;
