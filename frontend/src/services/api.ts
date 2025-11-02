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
  Stock,
  InsiderTransaction,
} from '../types/api';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1',
      timeout: 30000,
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
   * Quick scan for immediate opportunities
   */
  async quickScan(): Promise<QuickScanResponse> {
    const response = await this.client.get<QuickScanResponse>('/screen/quick-scan');
    return response.data;
  }

  /**
   * Get top opportunities
   */
  async getTopOpportunities(limit: number = 20): Promise<ScreeningResult[]> {
    const response = await this.client.get<ScreeningResult[]>('/screen/top-opportunities', {
      params: { limit },
    });
    return response.data;
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
