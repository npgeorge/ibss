import React from 'react';

const Screener: React.FC = () => {
  return (
    <div className="screener">
      <h2>Superstock Screener</h2>

      <div className="card">
        <h3>Screening Criteria</h3>
        <div className="filter-form">
          <div className="filter-section">
            <h4>Technical Filters</h4>
            <label>
              Price Range: $
              <input type="number" defaultValue="0.5" step="0.1" /> - $
              <input type="number" defaultValue="10" step="0.5" />
            </label>
            <label>
              <input type="checkbox" defaultChecked /> Magic Line Respect
            </label>
          </div>

          <div className="filter-section">
            <h4>Fundamental Filters</h4>
            <label>
              Min Earnings Growth:
              <input type="number" defaultValue="20" /> %
            </label>
            <label>
              Min Revenue Growth:
              <input type="number" defaultValue="20" /> %
            </label>
          </div>

          <div className="filter-section">
            <h4>Insider Activity</h4>
            <label>
              Recent Activity (days):
              <input type="number" defaultValue="90" />
            </label>
          </div>

          <button className="button">Run Scan</button>
        </div>
      </div>

      <div className="card">
        <h3>Screening Results</h3>
        <p>Run a scan to see results...</p>
      </div>
    </div>
  );
};

export default Screener;
