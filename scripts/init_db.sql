-- RiskMonitor Database Initialization Script (MySQL)
-- This script creates the initial database schema

-- Create Positions table (simplified version for Phase 1)
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

-- Create index for common queries
CREATE INDEX idx_positions_trader ON positions(trader_id);
CREATE INDEX idx_positions_desk ON positions(desk);
CREATE INDEX idx_positions_security ON positions(security_id);
CREATE INDEX idx_positions_date ON positions(entry_date);

-- Insert sample data for testing
INSERT INTO positions (position_id, trader_id, desk, security_id, quantity, delta, entry_date, currency) VALUES
('POS-2024-001', 'TRADER-001', 'Equity Derivatives', 'AAPL-CALL-150-20251231', 1000, 600.0, '2024-10-01', 'USD'),
('POS-2024-002', 'TRADER-001', 'Equity Derivatives', 'GOOGL-PUT-140-20251231', -500, -300.0, '2024-10-05', 'USD'),
('POS-2024-003', 'TRADER-002', 'Fixed Income', 'TSLA-CALL-200-20251231', 800, 480.0, '2024-10-10', 'USD'),
('POS-2024-004', 'TRADER-002', 'Equity Derivatives', 'MSFT-CALL-350-20251231', 1200, 720.0, '2024-10-15', 'USD'),
('POS-2024-005', 'TRADER-003', 'FX Derivatives', 'EUR-USD-FWD-20251231', 5000, 250.0, '2024-10-20', 'EUR');
