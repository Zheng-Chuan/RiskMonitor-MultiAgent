-- 创建 alerts 表用于存储告警记录
-- Week4: 可观测与告警闭环

CREATE TABLE IF NOT EXISTS alerts (
    alert_id VARCHAR(36) PRIMARY KEY COMMENT '告警唯一ID, UUID格式',
    request_id VARCHAR(36) NOT NULL COMMENT '关联的请求ID, 用于追踪',
    alert_type VARCHAR(50) NOT NULL COMMENT '告警类型, 例如: DESK_DELTA_BREACH',
    severity VARCHAR(20) NOT NULL COMMENT '告警级别: INFO, WARNING, CRITICAL',
    desk VARCHAR(100) NOT NULL COMMENT '交易台名称',
    trader_id VARCHAR(50) DEFAULT NULL COMMENT '交易员ID, 可选',
    metric_name VARCHAR(50) NOT NULL COMMENT '指标名称, 例如: abs_delta',
    metric_value DECIMAL(20, 2) NOT NULL COMMENT '指标当前值',
    threshold_value DECIMAL(20, 2) NOT NULL COMMENT '阈值',
    breach_amount DECIMAL(20, 2) NOT NULL COMMENT '超限金额 = metric_value - threshold_value',
    message TEXT NOT NULL COMMENT '告警消息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '告警创建时间',
    acknowledged BOOLEAN DEFAULT FALSE COMMENT '是否已确认',
    acknowledged_at TIMESTAMP NULL COMMENT '确认时间',
    acknowledged_by VARCHAR(50) DEFAULT NULL COMMENT '确认人',
    INDEX idx_request_id (request_id),
    INDEX idx_alert_type (alert_type),
    INDEX idx_desk (desk),
    INDEX idx_created_at (created_at),
    INDEX idx_severity (severity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警记录表';
