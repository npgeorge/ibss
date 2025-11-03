/**
 * Stock Card Component
 *
 * Displays a stock screening result in a card format
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ScreeningResult } from '../types/api';
import './StockCard.css';

interface StockCardProps {
  result: ScreeningResult;
}

const StockCard: React.FC<StockCardProps> = ({ result }) => {
  const navigate = useNavigate();
  const { stock, score, magic_line_distance, latest_pattern, insider_activity, recommendation } = result;

  const getRecommendationColor = (rec: string): string => {
    if (rec.includes('STRONG BUY')) return 'strong-buy';
    if (rec.includes('BUY')) return 'buy';
    if (rec.includes('SELL')) return 'sell';
    return 'hold';
  };

  const getInsiderColor = (activity: string): string => {
    if (activity === 'HIGH') return 'high';
    if (activity === 'MEDIUM') return 'medium';
    return 'low';
  };

  const handleClick = () => {
    navigate(`/stock/${stock.symbol}`);
  };

  return (
    <div className="stock-card" onClick={handleClick}>
      <div className="stock-card-header">
        <div className="stock-info">
          <h3 className="stock-symbol">{stock.symbol}</h3>
          <p className="stock-name">{stock.company_name}</p>
        </div>
        <div className={`recommendation-badge ${getRecommendationColor(recommendation)}`}>
          {recommendation}
        </div>
      </div>

      <div className="stock-card-body">
        <div className="score-section">
          <div className="total-score">
            <span className="score-label">Total Score</span>
            <span className="score-value">{score.total_score.toFixed(1)}</span>
          </div>
          <div className="score-breakdown">
            <div className="score-item">
              <span className="score-label">Technical</span>
              <span className="score-value">{score.technical_score.toFixed(0)}</span>
            </div>
            <div className="score-item">
              <span className="score-label">Fundamental</span>
              <span className="score-value">{score.fundamental_score.toFixed(0)}</span>
            </div>
            <div className="score-item">
              <span className="score-label">Insider</span>
              <span className="score-value">{score.insider_score.toFixed(0)}</span>
            </div>
          </div>
        </div>

        <div className="indicators-section">
          {stock.sector && (
            <div className="indicator">
              <span className="indicator-label">Sector</span>
              <span className="indicator-value">{stock.sector}</span>
            </div>
          )}
          {stock.current_price && (
            <div className="indicator">
              <span className="indicator-label">Price</span>
              <span className="indicator-value">${stock.current_price.toFixed(2)}</span>
            </div>
          )}
          <div className="indicator">
            <span className="indicator-label">ML Distance</span>
            <span className={`indicator-value ${magic_line_distance < 5 ? 'positive' : ''}`}>
              {magic_line_distance.toFixed(1)}%
            </span>
          </div>
          {latest_pattern && (
            <div className="indicator">
              <span className="indicator-label">Pattern</span>
              <span className="indicator-value">{latest_pattern}</span>
            </div>
          )}
          <div className="indicator">
            <span className="indicator-label">Insider</span>
            <span className={`indicator-value ${getInsiderColor(insider_activity)}`}>
              {insider_activity}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StockCard;
