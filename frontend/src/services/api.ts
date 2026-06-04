/**
 * IBSS API Client
 *
 * Handles all communication with the FastAPI backend
 */
import axios, { AxiosInstance } from 'axios';
import {
  StockProfile,
  MagicLineResult,
  PatternResult,
  TechnicalIndicators,
  ScreenRequest,
  ScreenResponse,
  QuickScanResponse,
  ScreeningResult,
  PositionSizeRequest,
  PositionSizeResponse,
  InsiderTransaction,
  ScreeningCriteria,
  ScanStreamEvent,
  ScanStreamResult,
  ScoringModel,
  MarketConditions,
  AISectorResponse,
} from '../types/api';

const API_BASE_URL =
  process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

/**
 * Map a flat scan/screen result (the backend StockScreenResult / ScanStreamResult
 * shape) into the nested ScreeningResult that StockCard and the pages consume.
 * Shared by the Screener stream and the Dashboard top-opportunities feed so both
 * surface the same entry/stop/target levels.
 */
export const scanResultToScreeningResult = (r: ScanStreamResult): ScreeningResult => {
  const insiderActivity: ScreeningResult['insider_activity'] =
    r.insider_score >= 66 ? 'HIGH' : r.insider_score >= 33 ? 'MEDIUM' : r.insider_score > 0 ? 'LOW' : 'NONE';

  return {
    stock: {
      id: 0,
      symbol: r.symbol,
      company_name: r.company_name || r.symbol,
      sector: r.sector || 'Unknown',
      market_cap: r.market_cap || undefined,
      current_price: r.price || undefined,
      magic_line_period: r.magic_line_period,
      is_active: true,
    },
    score: {
      technical_score: r.technical_score,
      fundamental_score: r.fundamental_score,
      insider_score: r.insider_score,
      pattern_score: r.pattern_score,
      total_score: r.total_score,
      score_breakdown: {},
    },
    magic_line_distance: r.magic_line_distance ?? 0,
    latest_pattern: r.patterns && r.patterns.length > 0 ? r.patterns[0] : undefined,
    insider_activity: insiderActivity,
    recommendation: r.entry_recommendation || (r.total_score >= 80 ? 'STRONG BUY' : r.total_score >= 65 ? 'BUY' : 'HOLD'),
    rank: r.rank ?? 0,
    entry_price: r.entry_price,
    stop_loss: r.stop_loss,
    target_price: r.target_price,
    entry_recommendation: r.entry_recommendation,
    law_scores: r.law_scores,
  };
};

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1',
      timeout: 120000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Request interceptor for auth (future)
    this.client.interceptors.request.use(
      (config) => {
        // Add auth token here when implemented
        // const token = localStorage.getItem('token');
        // if (token) {
        //   config.headers.Authorization = `Bearer ${token}`;
        // }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response) {
          console.error('API Error:', error.response.data);
        } else if (error.request) {
          console.error('Network Error:', error.message);
        }
        return Promise.reject(error);
      }
    );
  }

  // ============================================
  // Stock Endpoints
  // ============================================

  /**
   * Get complete stock profile with analysis
   */
  async getStockProfile(symbol: string): Promise<StockProfile> {
    const response = await this.client.get<StockProfile>(`/stocks/${symbol}`);
    return response.data;
  }

  /**
   * Get Magic Line analysis for a stock
   */
  async getMagicLineAnalysis(symbol: string): Promise<MagicLineResult> {
    const response = await this.client.get<MagicLineResult>(`/stocks/${symbol}/magic-line`);
    return response.data;
  }

  /**
   * Get pattern detection results
   */
  async getPatterns(symbol: string): Promise<PatternResult[]> {
    const response = await this.client.get<PatternResult[]>(`/stocks/${symbol}/patterns`);
    return response.data;
  }

  /**
   * Get technical indicators
   */
  async getTechnicalIndicators(symbol: string): Promise<TechnicalIndicators> {
    const response = await this.client.get<TechnicalIndicators>(`/stocks/${symbol}/technical-indicators`);
    return response.data;
  }

  // ============================================
  // Screener Endpoints
  // ============================================

  /**
   * Run full stock screening
   */
  async screenStocks(request: ScreenRequest): Promise<ScreenResponse> {
    const response = await this.client.post<ScreenResponse>('/screen', request);
    return response.data;
  }

  /**
   * Run the unified scan with live progress via SSE (POST /screen/run).
   *
   * Streams progress + final results from the orchestrated pipeline. When
   * persist is true (default) the backend also upserts qualifying results
   * into the database. EventSource is GET-only, so we read the POST response
   * body as a stream and parse SSE frames manually.
   *
   * Returns the final flat results; calls onEvent for every streamed event.
   */
  async runScanStream(
    criteria: ScreeningCriteria,
    onEvent: (event: ScanStreamEvent) => void,
    options: { limit?: number; persist?: boolean; signal?: AbortSignal } = {}
  ): Promise<ScanStreamResult[]> {
    const { limit = 50, persist = true, signal } = options;
    const params = new URLSearchParams({
      limit: String(limit),
      persist: String(persist),
    });

    const response = await fetch(`${API_BASE_URL}/screen/run?${params}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(criteria),
      signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(`Scan failed: HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResults: ScanStreamResult[] = [];

    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line
      const frames = buffer.split('\n\n');
      buffer = frames.pop() ?? '';

      for (const frame of frames) {
        const line = frame.trim();
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(line.indexOf('data:') + 5).trim();
        if (!payload) continue;

        let event: ScanStreamEvent;
        try {
          event = JSON.parse(payload) as ScanStreamEvent;
        } catch {
          continue;
        }

        onEvent(event);
        if (event.type === 'complete') {
          finalResults = event.results;
        } else if (event.type === 'error') {
          throw new Error(event.error);
        }
      }
    }

    return finalResults;
  }

  /**
   * Quick scan for immediate opportunities
   */
  async quickScan(): Promise<QuickScanResponse> {
    const response = await this.client.get<QuickScanResponse>('/screen/quick-scan');
    return response.data;
  }

  /**
   * Get the live scoring model (weights + composite split + entry overlay).
   * Used by the Method page so the documented weights match the scorer.
   */
  async getScoringModel(): Promise<ScoringModel> {
    const response = await this.client.get<ScoringModel>('/screen/scoring-model');
    return response.data;
  }

  /**
   * Get current market conditions (SPY trend + VIX regime — Entry Law #6).
   * Drives the Dashboard market-regime banner.
   */
  async getMarketConditions(): Promise<MarketConditions> {
    const response = await this.client.get<MarketConditions>('/market/conditions');
    return response.data;
  }

  /**
   * Get top opportunities
   */
  async getTopOpportunities(limit: number = 20): Promise<ScreeningResult[]> {
    // Backend returns the flat StockScreenResult shape; normalize to the nested
    // ScreeningResult the UI consumes (and surface entry/stop/target levels).
    const response = await this.client.get<ScanStreamResult[]>('/screen/top-opportunities', {
      params: { limit },
    });
    return response.data.map(scanResultToScreeningResult);
  }

  /**
   * Get the AI-sector watch list (Nebius, Ouster, and peers) with group
   * averages. Returns scanning=true while the background scan populates.
   */
  async getAISector(): Promise<{ results: ScreeningResult[]; raw: AISectorResponse }> {
    const response = await this.client.get<AISectorResponse>('/screen/ai');
    return {
      results: response.data.results.map(scanResultToScreeningResult),
      raw: response.data,
    };
  }

  /**
   * Explicitly start a fresh AI-sector scan (runs weekly cadence on demand).
   * Returns the current state immediately; poll getAISector() until done.
   */
  async runAISector(): Promise<{ results: ScreeningResult[]; raw: AISectorResponse }> {
    const response = await this.client.post<AISectorResponse>('/screen/ai/run');
    return {
      results: response.data.results.map(scanResultToScreeningResult),
      raw: response.data,
    };
  }

  // ============================================
  // Portfolio Endpoints
  // ============================================

  /**
   * Calculate position size
   */
  async calculatePositionSize(request: PositionSizeRequest): Promise<PositionSizeResponse> {
    const response = await this.client.post<PositionSizeResponse>('/portfolio/calculate-size', request);
    return response.data;
  }

  // ============================================
  // Insider Endpoints (Future)
  // ============================================

  /**
   * Get insider transactions for a stock
   */
  async getInsiderTransactions(symbol: string, days: number = 90): Promise<InsiderTransaction[]> {
    const response = await this.client.get<InsiderTransaction[]>(`/insider/${symbol}`, {
      params: { days },
    });
    return response.data;
  }

  /**
   * Get top insider buying activity
   */
  async getTopInsiderBuying(limit: number = 20): Promise<any[]> {
    const response = await this.client.get<any[]>('/insider/top-buying', {
      params: { limit },
    });
    return response.data;
  }

  // ============================================
  // Utility Methods
  // ============================================

  /**
   * Health check
   */
  async healthCheck(): Promise<boolean> {
    try {
      await this.client.get('/health');
      return true;
    } catch {
      return false;
    }
  }
}

// Export singleton instance
export const apiClient = new ApiClient();
export default apiClient;
