/**
 * Portfolio Page
 *
 * Displays portfolio positions and position size calculator
 */
import React, { useState } from 'react';
import { apiClient } from '../services/api';
import { PositionSizeResponse } from '../types/api';
import './Portfolio.css';

const Portfolio: React.FC = () => {
  // Position size calculator state
  const [accountSize, setAccountSize] = useState<number>(100000);
  const [riskPercent, setRiskPercent] = useState<number>(2);
  const [entryPrice, setEntryPrice] = useState<number>(0);
  const [stopLoss, setStopLoss] = useState<number>(0);
  const [positionSize, setPositionSize] = useState<PositionSizeResponse | null>(null);
  const [calculating, setCalculating] = useState<boolean>(false);

  const calculatePositionSize = async () => {
    if (!entryPrice || !stopLoss || !accountSize) {
      alert('Please fill in all fields');
      return;
    }

    if (stopLoss >= entryPrice) {
      alert('Stop loss must be below entry price');
      return;
    }

    try {
      setCalculating(true);
      const result = await apiClient.calculatePositionSize({
        account_size: accountSize,
        risk_percent: riskPercent,
        entry_price: entryPrice,
        stop_loss: stopLoss,
      });
      setPositionSize(result);
    } catch (err: any) {
      console.error('Error calculating position size:', err);
      alert('Failed to calculate position size');
    } finally {
      setCalculating(false);
    }
  };

  return (
    <div className="portfolio">
      <div className="portfolio-header">
        <h2>Portfolio Manager</h2>
        <p className="portfolio-subtitle">Manage positions and calculate optimal sizing</p>
      </div>

      <div className="card summary-card">
        <h3>Portfolio Summary</h3>
        <div className="summary-grid">
          <div className="summary-item">
            <span className="label">Account Value</span>
            <span className="value">${accountSize.toLocaleString()}</span>
          </div>
          <div className="summary-item">
            <span className="label">Open Positions</span>
            <span className="value">0</span>
          </div>
          <div className="summary-item">
            <span className="label">Total P&L</span>
            <span className="value positive">$0.00 (0.00%)</span>
          </div>
          <div className="summary-item">
            <span className="label">Risk Exposure</span>
            <span className="value">0%</span>
          </div>
        </div>
      </div>

      <div className="card positions-card">
        <h3>Current Positions</h3>
        <div className="empty-state">
          <p>No positions yet. Use the screener to find opportunities!</p>
        </div>
      </div>

      <div className="card calculator-card">
        <h3>Position Size Calculator</h3>
        <p className="calculator-description">
          Calculate optimal position size based on Jesse Stine's 2% risk rule
        </p>

        <div className="calculator-form">
          <div className="form-row">
            <div className="form-group">
              <label>
                <span className="label-text">Account Size ($)</span>
                <input
                  type="number"
                  value={accountSize}
                  onChange={(e) => setAccountSize(parseFloat(e.target.value))}
                  step="1000"
                  min="0"
                />
              </label>
            </div>

            <div className="form-group">
              <label>
                <span className="label-text">Risk per Trade (%)</span>
                <input
                  type="number"
                  value={riskPercent}
                  onChange={(e) => setRiskPercent(parseFloat(e.target.value))}
                  step="0.1"
                  min="0.1"
                  max="5"
                />
              </label>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>
                <span className="label-text">Entry Price ($)</span>
                <input
                  type="number"
                  value={entryPrice || ''}
                  onChange={(e) => setEntryPrice(parseFloat(e.target.value))}
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                />
              </label>
            </div>

            <div className="form-group">
              <label>
                <span className="label-text">Stop Loss ($)</span>
                <input
                  type="number"
                  value={stopLoss || ''}
                  onChange={(e) => setStopLoss(parseFloat(e.target.value))}
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                />
              </label>
            </div>
          </div>

          <button
            className="btn-calculate"
            onClick={calculatePositionSize}
            disabled={calculating}
          >
            {calculating ? 'Calculating...' : 'Calculate Position Size'}
          </button>
        </div>

        {positionSize && (
          <div className="calculator-results">
            <h4>Recommended Position</h4>
            <div className="results-grid">
              <div className="result-item">
                <span className="result-label">Shares to Buy</span>
                <span className="result-value highlight">{positionSize.shares.toLocaleString()}</span>
              </div>
              <div className="result-item">
                <span className="result-label">Position Value</span>
                <span className="result-value">${positionSize.position_value.toLocaleString()}</span>
              </div>
              <div className="result-item">
                <span className="result-label">Risk Amount</span>
                <span className="result-value risk">${positionSize.risk_amount.toLocaleString()}</span>
              </div>
              <div className="result-item">
                <span className="result-label">Position Size</span>
                <span className="result-value">{positionSize.position_size_percent.toFixed(1)}%</span>
              </div>
            </div>

            <div className="risk-warning">
              <strong>⚠️ Risk Management:</strong> This position will risk $
              {positionSize.risk_amount.toLocaleString()} ({riskPercent}% of account) if stop loss is hit.
            </div>
          </div>
        )}
      </div>

      <div className="card rules-card">
        <h3>Portfolio Rules</h3>
        <ul className="rules-list">
          <li>
            <strong>Max Risk per Trade:</strong> 2% of account value (adjustable in calculator)
          </li>
          <li>
            <strong>Max Position Size:</strong> 40% of account value for any single position
          </li>
          <li>
            <strong>Portfolio Concentration:</strong> 3-5 high-conviction positions at most
          </li>
          <li>
            <strong>Stop Loss:</strong> Always use mental stops 15-20% below entry or at Magic Line
          </li>
          <li>
            <strong>Sell Signal:</strong> Exit immediately when price closes below Magic Line
          </li>
        </ul>
      </div>
    </div>
  );
};

export default Portfolio;
