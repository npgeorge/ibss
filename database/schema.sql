-- IBSS Superstocks Dashboard - Database Schema
-- PostgreSQL Database Schema

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- Stocks master table
CREATE TABLE stocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) UNIQUE NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap BIGINT,
    float_shares BIGINT,
    outstanding_shares BIGINT,
    magic_line_period INTEGER DEFAULT 10,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stocks_symbol ON stocks(symbol);
CREATE INDEX idx_stocks_sector ON stocks(sector);
CREATE INDEX idx_stocks_market_cap ON stocks(market_cap);

-- ============================================================================
-- PRICE DATA
-- ============================================================================

-- Daily price data
CREATE TABLE price_data_daily (
    id BIGSERIAL PRIMARY KEY,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    adjusted_close DECIMAL(12, 4),
    UNIQUE(stock_id, date)
);

CREATE INDEX idx_price_daily_stock_date ON price_data_daily(stock_id, date DESC);
CREATE INDEX idx_price_daily_date ON price_data_daily(date DESC);

-- Weekly price data (aggregated)
CREATE TABLE price_data_weekly (
    id BIGSERIAL PRIMARY KEY,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    week_start_date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    UNIQUE(stock_id, week_start_date)
);

CREATE INDEX idx_price_weekly_stock_date ON price_data_weekly(stock_id, week_start_date DESC);

-- ============================================================================
-- TECHNICAL INDICATORS
-- ============================================================================

-- Technical indicators (calculated)
CREATE TABLE technical_indicators (
    id BIGSERIAL PRIMARY KEY,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    date DATE NOT NULL,

    -- Moving Averages (weekly periods converted to daily)
    sma_8w DECIMAL(12, 4),   -- 40 days
    sma_10w DECIMAL(12, 4),  -- 50 days (Magic Line default)
    sma_12w DECIMAL(12, 4),  -- 60 days
    sma_14w DECIMAL(12, 4),  -- 70 days
    sma_20d DECIMAL(12, 4),  -- 20 days
    sma_50d DECIMAL(12, 4),  -- 50 days
    sma_200d DECIMAL(12, 4), -- 200 days

    -- Volume indicators
    volume_avg_20d BIGINT,
    volume_avg_50d BIGINT,
    volume_ratio DECIMAL(6, 2),  -- current/average

    -- Momentum indicators
    rsi_14 DECIMAL(6, 2),
    macd DECIMAL(12, 4),
    macd_signal DECIMAL(12, 4),
    macd_histogram DECIMAL(12, 4),

    -- Relative strength
    relative_strength DECIMAL(8, 4),

    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_id, date)
);

CREATE INDEX idx_technical_stock_date ON technical_indicators(stock_id, date DESC);

-- ============================================================================
-- FUNDAMENTAL DATA
-- ============================================================================

-- Earnings data
CREATE TABLE earnings (
    id SERIAL PRIMARY KEY,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    report_date DATE NOT NULL,
    fiscal_quarter VARCHAR(10),
    fiscal_year INTEGER,

    -- Earnings metrics
    eps_actual DECIMAL(10, 4),
    eps_estimated DECIMAL(10, 4),
    eps_surprise_pct DECIMAL(6, 2),

    -- Revenue metrics
    revenue BIGINT,
    revenue_estimated BIGINT,
    revenue_surprise_pct DECIMAL(6, 2),

    -- Growth rates
    eps_growth_yoy DECIMAL(8, 2),
    eps_growth_qoq DECIMAL(8, 2),
    revenue_growth_yoy DECIMAL(8, 2),
    revenue_growth_qoq DECIMAL(8, 2),

    UNIQUE(stock_id, fiscal_quarter, fiscal_year)
);

CREATE INDEX idx_earnings_stock ON earnings(stock_id);
CREATE INDEX idx_earnings_date ON earnings(report_date DESC);

-- Fundamental metrics
CREATE TABLE fundamentals (
    id SERIAL PRIMARY KEY,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    date DATE NOT NULL,

    -- Valuation
    pe_ratio DECIMAL(10, 2),
    peg_ratio DECIMAL(10, 2),
    price_to_sales DECIMAL(10, 2),
    price_to_book DECIMAL(10, 2),

    -- Profitability
    gross_margin DECIMAL(6, 2),
    operating_margin DECIMAL(6, 2),
    net_margin DECIMAL(6, 2),
    roe DECIMAL(6, 2),
    roa DECIMAL(6, 2),

    -- Financial health
    debt_to_equity DECIMAL(10, 2),
    current_ratio DECIMAL(6, 2),
    quick_ratio DECIMAL(6, 2),

    -- Cash flow
    free_cash_flow BIGINT,
    operating_cash_flow BIGINT,

    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_id, date)
);

CREATE INDEX idx_fundamentals_stock ON fundamentals(stock_id);

-- ============================================================================
-- INSIDER TRADING
-- ============================================================================

-- Insider transactions
CREATE TABLE insider_transactions (
    id SERIAL PRIMARY KEY,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,

    -- Filing information
    filing_date DATE NOT NULL,
    transaction_date DATE NOT NULL,

    -- Insider information
    insider_name VARCHAR(255) NOT NULL,
    insider_title VARCHAR(255),
    insider_relationship VARCHAR(100),

    -- Transaction details
    transaction_type VARCHAR(50) NOT NULL,  -- 'purchase', 'sale', 'option_exercise'
    shares INTEGER NOT NULL,
    price_per_share DECIMAL(10, 4),
    total_value DECIMAL(15, 2),

    -- Ownership
    shares_owned_after BIGINT,
    ownership_percent DECIMAL(6, 3),

    -- SEC filing details
    form_type VARCHAR(20),  -- Form 4, Form 3, etc.
    sec_filing_url TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(stock_id, transaction_date, insider_name)
);

CREATE INDEX idx_insider_stock ON insider_transactions(stock_id);
CREATE INDEX idx_insider_date ON insider_transactions(transaction_date DESC);
CREATE INDEX idx_insider_type ON insider_transactions(transaction_type);

-- ============================================================================
-- PATTERN RECOGNITION
-- ============================================================================

-- Detected patterns
CREATE TABLE patterns (
    id SERIAL PRIMARY KEY,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,

    pattern_type VARCHAR(50) NOT NULL,  -- 'staircase', 'cup_handle', 'flat_base', etc.
    detected_date DATE NOT NULL,

    -- Pattern metrics
    strength_score DECIMAL(5, 2),  -- 0-100
    confidence DECIMAL(5, 2),      -- 0-100

    -- Trading levels
    entry_price DECIMAL(10, 4),
    stop_loss DECIMAL(10, 4),
    target_price DECIMAL(10, 4),

    -- Pattern details
    pattern_start_date DATE,
    pattern_end_date DATE,
    consolidation_days INTEGER,

    -- Status
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'triggered', 'failed', 'completed'
    triggered_date DATE,

    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_patterns_stock ON patterns(stock_id);
CREATE INDEX idx_patterns_type ON patterns(pattern_type);
CREATE INDEX idx_patterns_status ON patterns(status);

-- ============================================================================
-- SCREENING & SCORING
-- ============================================================================

-- Screening results (daily cache)
CREATE TABLE screening_results (
    id SERIAL PRIMARY KEY,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    screen_date DATE DEFAULT CURRENT_DATE,

    -- Component scores
    technical_score DECIMAL(5, 2),      -- 0-100
    fundamental_score DECIMAL(5, 2),    -- 0-100
    insider_score DECIMAL(5, 2),        -- 0-100
    pattern_score DECIMAL(5, 2),        -- 0-100

    -- Total score
    total_score DECIMAL(5, 2),          -- 0-100

    -- Ranking
    rank INTEGER,

    -- Details (JSON)
    score_breakdown JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_id, screen_date)
);

CREATE INDEX idx_screening_date ON screening_results(screen_date DESC);
CREATE INDEX idx_screening_score ON screening_results(total_score DESC);

-- ============================================================================
-- USER MANAGEMENT
-- ============================================================================

-- Users
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);

-- Watchlists
CREATE TABLE watchlists (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Alert settings (JSON)
    alert_settings JSONB,

    -- Notes
    notes TEXT,
    entry_target DECIMAL(10, 4),
    stop_loss DECIMAL(10, 4),

    UNIQUE(user_id, stock_id)
);

CREATE INDEX idx_watchlist_user ON watchlists(user_id);

-- Portfolios (positions)
CREATE TABLE portfolios (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,

    -- Position details
    shares INTEGER NOT NULL,
    avg_cost DECIMAL(10, 4) NOT NULL,
    entry_date DATE NOT NULL,

    -- Risk management
    stop_loss DECIMAL(10, 4),
    target_price DECIMAL(10, 4),

    -- Position status
    is_open BOOLEAN DEFAULT TRUE,
    exit_date DATE,
    exit_price DECIMAL(10, 4),

    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_portfolio_user ON portfolios(user_id);
CREATE INDEX idx_portfolio_stock ON portfolios(stock_id);

-- ============================================================================
-- ALERTS
-- ============================================================================

-- Alert rules
CREATE TABLE alert_rules (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,

    alert_type VARCHAR(50) NOT NULL,  -- 'magic_line_touch', 'breakout', 'volume_surge', etc.
    condition VARCHAR(255) NOT NULL,
    threshold DECIMAL(12, 4),

    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alert_rules_user ON alert_rules(user_id);
CREATE INDEX idx_alert_rules_stock ON alert_rules(stock_id);

-- Triggered alerts
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    alert_rule_id INTEGER REFERENCES alert_rules(id) ON DELETE SET NULL,

    alert_type VARCHAR(50) NOT NULL,
    priority VARCHAR(20) NOT NULL,  -- 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    message TEXT NOT NULL,

    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP,

    -- Alert data (JSON)
    alert_data JSONB
);

CREATE INDEX idx_alerts_user ON alerts(user_id);
CREATE INDEX idx_alerts_triggered ON alerts(triggered_at DESC);
CREATE INDEX idx_alerts_priority ON alerts(priority);

-- ============================================================================
-- DATA PIPELINE & JOBS
-- ============================================================================

-- Data update log
CREATE TABLE data_updates (
    id SERIAL PRIMARY KEY,
    update_type VARCHAR(50) NOT NULL,  -- 'price_daily', 'insider', 'earnings', etc.
    status VARCHAR(20) NOT NULL,        -- 'running', 'completed', 'failed'
    records_processed INTEGER,
    records_failed INTEGER,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

CREATE INDEX idx_data_updates_type ON data_updates(update_type);
CREATE INDEX idx_data_updates_started ON data_updates(started_at DESC);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- View: Latest screening results with stock details
CREATE VIEW v_latest_screening AS
SELECT
    s.symbol,
    s.company_name,
    s.sector,
    s.industry,
    sr.technical_score,
    sr.fundamental_score,
    sr.insider_score,
    sr.total_score,
    sr.rank,
    sr.screen_date
FROM screening_results sr
JOIN stocks s ON sr.stock_id = s.id
WHERE sr.screen_date = (SELECT MAX(screen_date) FROM screening_results)
ORDER BY sr.total_score DESC;

-- View: Active patterns with stock details
CREATE VIEW v_active_patterns AS
SELECT
    s.symbol,
    s.company_name,
    p.pattern_type,
    p.strength_score,
    p.entry_price,
    p.stop_loss,
    p.target_price,
    p.detected_date,
    p.status
FROM patterns p
JOIN stocks s ON p.stock_id = s.id
WHERE p.status = 'active'
ORDER BY p.detected_date DESC;

-- View: Recent insider buying
CREATE VIEW v_recent_insider_buying AS
SELECT
    s.symbol,
    s.company_name,
    it.insider_name,
    it.insider_title,
    it.transaction_date,
    it.shares,
    it.price_per_share,
    it.total_value
FROM insider_transactions it
JOIN stocks s ON it.stock_id = s.id
WHERE it.transaction_type = 'purchase'
  AND it.transaction_date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY it.transaction_date DESC;

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function: Update timestamp (for tables with an updated_at column)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function: Update timestamp (for tables with a last_updated column)
CREATE OR REPLACE FUNCTION update_last_updated_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Update portfolios updated_at
CREATE TRIGGER update_portfolios_updated_at
    BEFORE UPDATE ON portfolios
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger: Update stocks last_updated
CREATE TRIGGER update_stocks_last_updated
    BEFORE UPDATE ON stocks
    FOR EACH ROW
    EXECUTE FUNCTION update_last_updated_column();
