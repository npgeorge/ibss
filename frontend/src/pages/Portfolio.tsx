import React from 'react';

const Portfolio: React.FC = () => {
  return (
    <div className="portfolio">
      <h2>Portfolio</h2>

      <div className="card">
        <h3>Portfolio Summary</h3>
        <div className="summary-grid">
          <div className="summary-item">
            <span className="label">Total Value</span>
            <span className="value">$0.00</span>
          </div>
          <div className="summary-item">
            <span className="label">Daily P&L</span>
            <span className="value positive">$0.00 (0.00%)</span>
          </div>
          <div className="summary-item">
            <span className="label">Open Positions</span>
            <span className="value">0</span>
          </div>
          <div className="summary-item">
            <span className="label">Buying Power</span>
            <span className="value">$0.00</span>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Current Positions</h3>
        <p>No positions yet</p>
      </div>

      <div className="card">
        <h3>Position Size Calculator</h3>
        <div className="calculator-form">
          <label>
            Entry Price: $
            <input type="number" step="0.01" />
          </label>
          <label>
            Stop Loss: $
            <input type="number" step="0.01" />
          </label>
          <label>
            Portfolio Value: $
            <input type="number" step="100" />
          </label>
          <button className="button">Calculate</button>
        </div>
      </div>
    </div>
  );
};

export default Portfolio;
