/**
 * Stock Card Component
 *
 * Displays a stock screening result in a card format
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ScreeningResult } from '../types/api';
import PriceChart from './PriceChart';
import './StockCard.css';

interface StockCardProps {
  result: ScreeningResult;
  rank?: number;
}

const StockCard: React.FC<StockCardProps> = ({ result, rank }) => {
  const navigate = useNavigate();
  const {
    stock,
    score,
    magic_line_distance,
    latest_pattern,
    insider_activity,
    recommendation,
    entry_price,
    stop_loss,
    target_price,
    entry_recommendation,
  } = result;

  const hasLevels = entry_price != null || stop_loss != null || target_price != null;
  const nearMagicLine = magic_line_distance < 5;

  const formatEntryRec = (rec: string): string =>
    rec.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  const getRecommendationColor = (rec: string): string => {
    const r = rec.toUpperCase();
    if (r.includes('STRONG')) return 'strong-buy';
    if (r.includes('BUY')) return 'buy';
    if (r.includes('SELL') || r.includes('AVOID')) return 'sell';
    return 'hold';
  };

  const formatRecommendation = (rec: string): string =>
    rec.replace(/_/g, ' ').toUpperCase();

  const getInsiderColor = (activity: string): string => {
    if (activity === 'HIGH') return 'high';
    if (activity === 'MEDIUM') return 'medium';
    return 'low';
  };

  const handleClick = () => {
    navigate(`/stock/${stock.symbol}`);
  };

  const [showChart, setShowChart] = useState(false);
  // Mounted on first open only, so tiles that never show a chart fetch nothing.
  const [chartMounted, setChartMounted] = useState(false);

  const toggleChart = (e: React.MouseEvent) => {
    e.stopPropagation();
    setChartMounted(true);
    setShowChart((open) => !open);
  };

  return (
    <div className="stock-card" onClick={handleClick}>
      <div className="stock-card-header">
        <div className="stock-info">
          {rank != null && (
            <span className="stock-rank te-num">{String(rank).padStart(2, '0')}</span>
          )}
          <div className="stock-id">
            <h3 className="stock-symbol">{stock.symbol}</h3>
            <p className="stock-name">{stock.company_name}</p>
          </div>
        </div>
        <div className="stock-card-actions">
          <button
            type="button"
            className={`chart-toggle ${showChart ? 'active' : ''}`}
            aria-pressed={showChart}
            aria-label={showChart ? `Hide ${stock.symbol} chart` : `Show ${stock.symbol} chart`}
            onClick={toggleChart}
          >
            <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
              <path d="M2 3v7M6 1v8M10 4v7M2 7h2M6 3h2M10 9h2" stroke="currentColor" strokeWidth="1.4" fill="none" />
            </svg>
            Chart
          </button>
          <div className={`recommendation-badge ${getRecommendationColor(recommendation)}`}>
            <span className="rec-dot" aria-hidden="true" />
            {formatRecommendation(recommendation)}
          </div>
        </div>
      </div>

      <div
        className={`stock-card-stage ${
          showChart ? 'chart-open' : chartMounted ? 'chart-closed' : ''
        }`}
      >
      <div className="stock-card-body">
        <div className="score-section">
          <div className="total-score">
            <span className="score-label te-label">Score</span>
            <span className="score-value te-num">{score.total_score.toFixed(1)}</span>
            <span className="score-track" aria-hidden="true">
              <span
                className="score-fill"
                style={{ width: `${Math.min(100, Math.max(0, score.total_score))}%` }}
              />
            </span>
          </div>
          <div className="score-breakdown">
            <div className="score-item">
              <span className="score-label te-label">Tech</span>
              <span className="score-value te-num">{score.technical_score.toFixed(0)}</span>
            </div>
            <div className="score-item">
              <span className="score-label te-label">Fund</span>
              <span className="score-value te-num">{score.fundamental_score.toFixed(0)}</span>
            </div>
            <div className="score-item">
              <span className="score-label te-label">Insdr</span>
              <span className="score-value te-num">{score.insider_score.toFixed(0)}</span>
            </div>
          </div>
        </div>

        <div className="indicators-section">
          {stock.sector && (
            <div className="indicator">
              <span className="indicator-label te-label">Sector</span>
              <span className="indicator-value">{stock.sector}</span>
            </div>
          )}
          {stock.current_price && (
            <div className="indicator">
              <span className="indicator-label te-label">Price</span>
              <span className="indicator-value te-num">${stock.current_price.toFixed(2)}</span>
            </div>
          )}
          <div className="indicator">
            <span className="indicator-label te-label">ML Dist</span>
            <span className={`indicator-value te-num ${nearMagicLine ? 'positive' : ''}`}>
              {magic_line_distance.toFixed(1)}%
            </span>
          </div>
          {latest_pattern && (
            <div className="indicator">
              <span className="indicator-label te-label">Pattern</span>
              <span className="indicator-value">{latest_pattern}</span>
            </div>
          )}
          <div className="indicator">
            <span className="indicator-label te-label">Insider</span>
            <span className={`indicator-value ${getInsiderColor(insider_activity)}`}>
              {insider_activity}
            </span>
          </div>
        </div>

        {hasLevels && (
          <div className="levels-section">
            {entry_recommendation && (
              <span className={`entry-rec-badge ${entry_recommendation}`}>
                {formatEntryRec(entry_recommendation)}
              </span>
            )}
            <div className="levels-row">
              {entry_price != null && (
                <div className="level">
                  <span className="level-label te-label">Entry</span>
                  <span className="level-value entry te-num">${entry_price.toFixed(2)}</span>
                </div>
              )}
              {stop_loss != null && (
                <div className="level">
                  <span className="level-label te-label">Stop</span>
                  <span className="level-value stop te-num">${stop_loss.toFixed(2)}</span>
                </div>
              )}
              {target_price != null && (
                <div className="level">
                  <span className="level-label te-label">Target</span>
                  <span className="level-value target te-num">${target_price.toFixed(2)}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      {chartMounted && (
        // Clicks inside the chart pan and inspect it; they must not open the stock page.
        <div className="stock-card-chart" onClick={(e) => e.stopPropagation()}>
          <PriceChart symbol={stock.symbol} compact />
        </div>
      )}
      </div>
    </div>
  );
};

export default StockCard;
