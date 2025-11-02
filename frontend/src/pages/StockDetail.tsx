/**
 * Stock Detail Page
 *
 * Complete stock analysis with Magic Line, patterns, and recommendations
 */
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiClient } from '../services/api';
import { StockProfile } from '../types/api';
import { format } from 'date-fns';
import './StockDetail.css';

const StockDetail: React.FC = () => {
  const { symbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<StockProfile | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (symbol) {
      loadStockProfile(symbol);
    }
  }, [symbol]);

  const loadStockProfile = async (sym: string) => {
    try {
      setLoading(true);
      setError(null);

      const data = await apiClient.getStockProfile(sym.toUpperCase());
      setProfile(data);
    } catch (err: any) {
      console.error('Error loading stock profile:', err);
      setError(err.message || 'Failed to load stock data');
    } finally {
      setLoading(false);
    }
  };

  const getRecommendationColor = (rec: string): string => {
    if (rec.includes('STRONG BUY')) return 'strong-buy';
    if (rec.includes('BUY')) return 'buy';
    if (rec.includes('SELL')) return 'sell';
    return 'hold';
  };

  const getRiskColor = (risk: string): string => {
    if (risk === 'LOW') return 'low';
    if (risk === 'MEDIUM') return 'medium';
    return 'high';
  };

  if (loading) {
    return (
      <div className="stock-detail">
        <div className="loading-state">Loading {symbol}...</div>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="stock-detail">
        <div className="error-state">
          <p>{error || 'Stock not found'}</p>
          <button onClick={() => navigate(-1)}>Go Back</button>
        </div>
      </div>
    );
  }

  return (
    <div className="stock-detail">
      <div className="stock-detail-header">
        <div className="header-left">
          <div className="back-button" onClick={() => navigate(-1)}>
            ← Back
          </div>
          <div className="stock-title">
            <h1>{profile.stock.symbol}</h1>
            <p className="company-name">{profile.stock.company_name}</p>
          </div>
        </div>
        <div className="header-right">
          <div className="price-info">
            <div className="current-price">${profile.current_price.toFixed(2)}</div>
            <div className={`price-change ${profile.price_change_percent >= 0 ? 'positive' : 'negative'}`}>
              {profile.price_change_percent >= 0 ? '+' : ''}
              {profile.price_change_percent.toFixed(2)}%
            </div>
          </div>
          <div className={`recommendation-badge ${getRecommendationColor(profile.recommendation)}`}>
            {profile.recommendation}
          </div>
        </div>
      </div>

      <div className="stock-detail-content">
        {/* Score Overview */}
        <div className="card score-overview">
          <h3>Analysis Scores</h3>
          <div className="score-grid">
            <div className="score-box total">
              <span className="score-label">Total Score</span>
              <span className="score-value">{profile.score.total_score.toFixed(1)}</span>
            </div>
            <div className="score-box">
              <span className="score-label">Technical</span>
              <span className="score-value">{profile.score.technical_score.toFixed(0)}</span>
            </div>
            <div className="score-box">
              <span className="score-label">Fundamental</span>
              <span className="score-value">{profile.score.fundamental_score.toFixed(0)}</span>
            </div>
            <div className="score-box">
              <span className="score-label">Insider</span>
              <span className="score-value">{profile.score.insider_score.toFixed(0)}</span>
            </div>
          </div>
          <div className="risk-level">
            <span className="risk-label">Risk Level:</span>
            <span className={`risk-badge ${getRiskColor(profile.risk_level)}`}>
              {profile.risk_level}
            </span>
          </div>
        </div>

        {/* Magic Line Analysis */}
        <div className="card magic-line-card">
          <h3>Magic Line Analysis</h3>
          <div className="magic-line-info">
            <div className="ml-stat">
              <span className="ml-label">Period</span>
              <span className="ml-value">{profile.magic_line.period}-week MA</span>
            </div>
            <div className="ml-stat">
              <span className="ml-label">Magic Line Value</span>
              <span className="ml-value">${profile.magic_line.magic_line_value.toFixed(2)}</span>
            </div>
            <div className="ml-stat">
              <span className="ml-label">Distance</span>
              <span className={`ml-value ${profile.magic_line.is_above ? 'positive' : 'negative'}`}>
                {profile.magic_line.is_above ? '+' : ''}
                {profile.magic_line.distance_percent.toFixed(2)}%
              </span>
            </div>
            <div className="ml-stat">
              <span className="ml-label">Respect Rate</span>
              <span className="ml-value">{(profile.magic_line.respect_rate * 100).toFixed(0)}%</span>
            </div>
            <div className="ml-stat">
              <span className="ml-label">Bounce Count</span>
              <span className="ml-value">
                {profile.magic_line.bounce_count} / {profile.magic_line.total_tests}
              </span>
            </div>
            {profile.magic_line.violation_detected && (
              <div className="ml-violation">
                ⚠️ Magic Line Violation Detected - Consider Selling
              </div>
            )}
          </div>
          <div className="ml-recommendation">
            <strong>Recommendation:</strong> {profile.magic_line.recommendation}
          </div>
        </div>

        {/* Entry/Exit Levels */}
        {(profile.entry_price || profile.stop_loss || profile.target_price) && (
          <div className="card levels-card">
            <h3>Entry & Exit Levels</h3>
            <div className="levels-grid">
              {profile.entry_price && (
                <div className="level-item">
                  <span className="level-label">Entry Price</span>
                  <span className="level-value entry">${profile.entry_price.toFixed(2)}</span>
                </div>
              )}
              {profile.stop_loss && (
                <div className="level-item">
                  <span className="level-label">Stop Loss</span>
                  <span className="level-value stop">${profile.stop_loss.toFixed(2)}</span>
                </div>
              )}
              {profile.target_price && (
                <div className="level-item">
                  <span className="level-label">Target Price</span>
                  <span className="level-value target">${profile.target_price.toFixed(2)}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Chart Patterns */}
        {profile.patterns && profile.patterns.length > 0 && (
          <div className="card patterns-card">
            <h3>Chart Patterns</h3>
            <div className="patterns-list">
              {profile.patterns.map((pattern, index) => (
                <div key={index} className="pattern-item">
                  <div className="pattern-header">
                    <span className="pattern-type">{pattern.pattern_type}</span>
                    <span className="pattern-strength">
                      Strength: {(pattern.strength * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="pattern-description">{pattern.description}</p>
                  <div className="pattern-dates">
                    {pattern.start_date} to {pattern.end_date}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Technical Indicators */}
        <div className="card indicators-card">
          <h3>Technical Indicators</h3>
          <div className="indicators-grid">
            {profile.technical_indicators.rsi_14 && (
              <div className="indicator-item">
                <span className="indicator-label">RSI (14)</span>
                <span className="indicator-value">{profile.technical_indicators.rsi_14.toFixed(1)}</span>
              </div>
            )}
            {profile.technical_indicators.macd && (
              <div className="indicator-item">
                <span className="indicator-label">MACD</span>
                <span className="indicator-value">{profile.technical_indicators.macd.toFixed(4)}</span>
              </div>
            )}
            {profile.technical_indicators.volume_ratio && (
              <div className="indicator-item">
                <span className="indicator-label">Volume Ratio</span>
                <span className="indicator-value">{profile.technical_indicators.volume_ratio.toFixed(2)}x</span>
              </div>
            )}
            {profile.technical_indicators.relative_strength && (
              <div className="indicator-item">
                <span className="indicator-label">Relative Strength</span>
                <span className="indicator-value">{profile.technical_indicators.relative_strength.toFixed(2)}</span>
              </div>
            )}
          </div>
        </div>

        {/* Insider Transactions */}
        {profile.insider_transactions && profile.insider_transactions.length > 0 && (
          <div className="card insider-card">
            <h3>Recent Insider Activity</h3>
            <div className="insider-table">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Insider</th>
                    <th>Title</th>
                    <th>Type</th>
                    <th>Shares</th>
                    <th>Price</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {profile.insider_transactions.slice(0, 10).map((trans, index) => (
                    <tr key={index}>
                      <td>{trans.transaction_date}</td>
                      <td>{trans.insider_name}</td>
                      <td>{trans.insider_title}</td>
                      <td className={trans.transaction_type === 'BUY' ? 'buy-type' : 'sell-type'}>
                        {trans.transaction_type}
                      </td>
                      <td>{trans.shares.toLocaleString()}</td>
                      <td>${trans.price_per_share.toFixed(2)}</td>
                      <td>${trans.total_value.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Stock Info */}
        <div className="card info-card">
          <h3>Stock Information</h3>
          <div className="info-grid">
            {profile.stock.sector && (
              <div className="info-item">
                <span className="info-label">Sector</span>
                <span className="info-value">{profile.stock.sector}</span>
              </div>
            )}
            {profile.stock.industry && (
              <div className="info-item">
                <span className="info-label">Industry</span>
                <span className="info-value">{profile.stock.industry}</span>
              </div>
            )}
            {profile.stock.market_cap && (
              <div className="info-item">
                <span className="info-label">Market Cap</span>
                <span className="info-value">${(profile.stock.market_cap / 1_000_000).toFixed(0)}M</span>
              </div>
            )}
            <div className="info-item">
              <span className="info-label">Volume</span>
              <span className="info-value">{profile.volume.toLocaleString()}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Avg Volume</span>
              <span className="info-value">{profile.avg_volume.toLocaleString()}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StockDetail;
