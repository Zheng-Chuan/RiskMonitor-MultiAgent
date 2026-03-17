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
SET @exists := (
    SELECT COUNT(1)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'positions'
      AND index_name = 'idx_positions_trader'
);
SET @sql := IF(@exists = 0, 'CREATE INDEX idx_positions_trader ON positions(trader_id)', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @exists := (
    SELECT COUNT(1)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'positions'
      AND index_name = 'idx_positions_desk'
);
SET @sql := IF(@exists = 0, 'CREATE INDEX idx_positions_desk ON positions(desk)', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @exists := (
    SELECT COUNT(1)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'positions'
      AND index_name = 'idx_positions_security'
);
SET @sql := IF(@exists = 0, 'CREATE INDEX idx_positions_security ON positions(security_id)', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @exists := (
    SELECT COUNT(1)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'positions'
      AND index_name = 'idx_positions_date'
);
SET @sql := IF(@exists = 0, 'CREATE INDEX idx_positions_date ON positions(entry_date)', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

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

CREATE TABLE IF NOT EXISTS audit_events (
    audit_id VARCHAR(36) PRIMARY KEY,
    ts_ms BIGINT NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    correlation_id VARCHAR(128) DEFAULT NULL,
    run_id VARCHAR(128) NOT NULL,
    command_id VARCHAR(128) DEFAULT NULL,
    target_agent VARCHAR(64) NOT NULL,
    action VARCHAR(128) NOT NULL,
    actor VARCHAR(128) NOT NULL,
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by VARCHAR(128) DEFAULT NULL,
    approval_reason VARCHAR(128) DEFAULT NULL,
    ok BOOLEAN NOT NULL DEFAULT FALSE,
    error TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_event_id (event_id),
    INDEX idx_audit_correlation_id (correlation_id),
    INDEX idx_audit_run_id (run_id),
    INDEX idx_audit_ts_ms (ts_ms)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS processed_cdc_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    topic VARCHAR(128) NOT NULL,
    partition_id INT NOT NULL,
    offset_id BIGINT NOT NULL,
    event_id VARCHAR(256) NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    last_error TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_processed_cdc (topic, partition_id, offset_id),
    INDEX idx_processed_event_id (event_id),
    INDEX idx_processed_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS dlq_events (
    dlq_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    topic VARCHAR(128) NOT NULL,
    partition_id INT NOT NULL,
    offset_id BIGINT NOT NULL,
    event_id VARCHAR(256) DEFAULT NULL,
    error_code VARCHAR(64) DEFAULT NULL,
    error_message TEXT DEFAULT NULL,
    payload_json JSON DEFAULT NULL,
    attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_dlq (topic, partition_id, offset_id),
    INDEX idx_dlq_event_id (event_id),
    INDEX idx_dlq_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 插入测试用演示数据(符合金融领域常识的简化样例)
INSERT IGNORE INTO positions (position_id, trader_id, desk, security_id, quantity, delta, entry_date, currency) VALUES
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
('POS-2024-015', 'TRADER-008', 'Credit Trading', 'JPM-CDS-20250630', 10000000, 50000.0, '2024-10-31', 'USD'),
-- Equities desk (for test cases)
('POS-2025-001', 'TRADER-001', 'Equities', 'AAPL-CALL-175-20250331', 1500, 950.0, '2025-01-15', 'USD'),
('POS-2025-002', 'TRADER-001', 'Equities', 'GOOGL-PUT-140-20250630', -800, -480.0, '2025-01-16', 'USD'),
('POS-2025-003', 'TRADER-002', 'Equities', 'MSFT-CALL-420-20250331', 1200, 720.0, '2025-01-17', 'USD'),
('POS-2025-004', 'TRADER-002', 'Equities', 'TSLA-PUT-250-20250228', -1500, -900.0, '2025-01-18', 'USD'),
-- Rates desk (for test cases)
('POS-2025-010', 'TRADER-004', 'Rates', 'EURUSD-FWD-20250331', 12000000, 60000.0, '2025-01-20', 'EUR'),
('POS-2025-011', 'TRADER-004', 'Rates', 'GBPUSD-CALL-1.30-20250228', 6000000, 150000.0, '2025-01-21', 'GBP'),
('POS-2025-012', 'TRADER-005', 'Rates', 'USDJPY-PUT-150-20250331', -10000000, -50000.0, '2025-01-22', 'JPY'),
-- Credit desk (for test cases)
('POS-2025-020', 'TRADER-008', 'Credit', 'JPM-CDS-20250630', 12000000, 60000.0, '2025-01-25', 'USD'),
('POS-2025-021', 'TRADER-008', 'Credit', 'GS-CDS-20250331', 8000000, 40000.0, '2025-01-26', 'USD');

-- 插入告警历史数据（用于测试用例）
INSERT IGNORE INTO alerts (alert_id, request_id, alert_type, severity, desk, trader_id, metric_name, metric_value, threshold_value, breach_amount, message, acknowledged, created_at) VALUES
('ALERT-2025-001', 'REQ-001', 'delta_breach', 'HIGH', 'Equities', 'TRADER-001', 'delta_exposure', 950.0, 800.0, 150.0, 'Equities desk delta exposure exceeds threshold', FALSE, '2025-03-10 09:00:00'),
('ALERT-2025-002', 'REQ-002', 'delta_breach', 'MEDIUM', 'Equities', 'TRADER-002', 'delta_exposure', 720.0, 600.0, 120.0, 'Equities desk delta exposure approaches threshold', FALSE, '2025-03-11 10:30:00'),
('ALERT-2025-003', 'REQ-003', 'delta_breach', 'LOW', 'Rates', 'TRADER-004', 'delta_exposure', 60000.0, 75000.0, -15000.0, 'Rates desk delta within limit', FALSE, '2025-03-12 14:00:00'),
('ALERT-2025-004', 'REQ-004', 'delta_breach', 'HIGH', 'Equities', 'TRADER-001', 'delta_exposure', 900.0, 800.0, 100.0, 'Equities desk delta breach again', FALSE, '2025-03-13 08:45:00'),
('ALERT-2025-005', 'REQ-005', 'delta_breach', 'HIGH', 'Equities', 'TRADER-002', 'delta_exposure', 850.0, 600.0, 250.0, 'Equities desk delta breach continues', FALSE, '2025-03-14 11:20:00'),
('ALERT-2025-006', 'REQ-006', 'delta_breach', 'MEDIUM', 'Credit', 'TRADER-008', 'delta_exposure', 60000.0, 70000.0, -10000.0, 'Credit desk delta within limit', FALSE, '2025-03-15 16:30:00'),
('ALERT-2025-007', 'REQ-007', 'delta_breach', 'HIGH', 'Equities', 'TRADER-001', 'delta_exposure', 980.0, 800.0, 180.0, 'Equities desk delta breach persists', FALSE, '2025-03-16 09:15:00');


GRANT SELECT, RELOAD, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'admin'@'%';
FLUSH PRIVILEGES;
