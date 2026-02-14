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

