/**
 * TypeScript type definitions for IBSS API
 */

// Stock Types
export interface Stock {
  id: number;
  symbol: string;
  company_name: string;
  sector: string;
  industry?: string;
  market_cap?: number;
  current_price?: number;
  magic_line_period?: number;
  is_active: boolean;
}

// Price Data
export interface PriceData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  adjusted_close: number;
}

// Magic Line Analysis
export interface MagicLineResult {
  period: number;
  current_price: number;
  magic_line_value: number;
  distance_percent: number;
  is_above: boolean;
  respect_rate: number;
  bounce_count: number;
  total_tests: number;
  violation_detected: boolean;
  recommendation: string;
}

// Pattern Detection
export interface PatternResult {
  pattern_type: string;
  strength: number;
  start_date: string;
  end_date: string;
  entry_price?: number;
  stop_loss?: number;
  target_price?: number;
  description: string;
}

// Technical Indicators
export interface TechnicalIndicators {
  rsi_14?: number;
  macd?: number;
  macd_signal?: number;
  macd_histogram?: number;
  volume_ratio?: number;
  avg_volume_20d?: number;
  relative_strength?: number;
  ma_8_week?: number;
  ma_10_week?: number;
  ma_12_week?: number;
  ma_14_week?: number;
}

// Insider Transaction
export interface InsiderTransaction {
  insider_name: string;
  insider_title: string;
  transaction_date: string;
  transaction_type: string;
  shares: number;
  price_per_share: number;
  total_value: number;
  shares_owned_after: number;
}

// Stock Score
export interface StockScore {
  technical_score: number;
  fundamental_score: number;
  insider_score: number;
  pattern_score: number;
  total_score: number;
  score_breakdown: Record<string, any>;
}

// Stock Profile (Complete Analysis)
export interface StockProfile {
  stock: Stock;
  current_price: number;
  price_change_percent: number;
  volume: number;
  avg_volume: number;
  magic_line: MagicLineResult;
  patterns: PatternResult[];
  technical_indicators: TechnicalIndicators;
  insider_transactions: InsiderTransaction[];
  score: StockScore;
  recommendation: 'STRONG BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG SELL';
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
  entry_price?: number;
  stop_loss?: number;
  target_price?: number;
}

// Screening Criteria
export interface ScreeningCriteria {
  price_min?: number;
  price_max?: number;
  volume_min?: number;
  market_cap_min?: number;
  market_cap_max?: number;
  sectors?: string[];
  min_technical_score?: number;
  min_fundamental_score?: number;
  min_insider_score?: number;
  min_total_score?: number;
  magic_line_distance_max?: number;
  require_insider_buying?: boolean;
  require_patterns?: boolean;
  pattern_types?: string[];
}

// Screening Result
export interface ScreeningResult {
  stock: Stock;
  score: StockScore;
  magic_line_distance: number;
  latest_pattern?: string;
  insider_activity: 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE';
  recommendation: string;
  rank: number;
}

// Portfolio Position
export interface PortfolioPosition {
  id: number;
  stock: Stock;
  shares: number;
  entry_price: number;
  entry_date: string;
  current_price: number;
  current_value: number;
  unrealized_pl: number;
  unrealized_pl_percent: number;
  stop_loss?: number;
  target_price?: number;
  position_status: 'OPEN' | 'CLOSED';
}

// Watchlist Item
export interface WatchlistItem {
  id: number;
  stock: Stock;
  added_date: string;
  target_entry_price?: number;
  notes?: string;
  alerts_enabled: boolean;
  current_price: number;
  magic_line_distance: number;
  latest_pattern?: string;
}

// Alert
export interface Alert {
  id: number;
  stock: Stock;
  alert_type: string;
  message: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  created_at: string;
  is_read: boolean;
}

// API Request/Response Types

export interface ScreenRequest {
  criteria: ScreeningCriteria;
  limit?: number;
}

export interface ScreenResponse {
  results: ScreeningResult[];
  total_screened: number;
  total_matches: number;
  screen_date: string;
}

export interface QuickScanResponse {
  opportunities: ScreeningResult[];
  scan_date: string;
}

export interface PositionSizeRequest {
  account_size: number;
  risk_percent: number;
  entry_price: number;
  stop_loss: number;
}

export interface PositionSizeResponse {
  shares: number;
  position_value: number;
  risk_amount: number;
  position_size_percent: number;
}
