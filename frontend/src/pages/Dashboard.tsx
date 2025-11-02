import React from 'react';

const Dashboard: React.FC = () => {
  return (
    <div className="dashboard">
      <h2>Dashboard</h2>

      <div className="dashboard-summary card">
        <h3>Market Overview</h3>
        <div className="summary-grid">
          <div className="summary-item">
            <span className="label">Active Superstocks</span>
            <span className="value">12</span>
          </div>
          <div className="summary-item">
            <span className="label">Magic Line Touches</span>
            <span className="value positive">5</span>
          </div>
          <div className="summary-item">
            <span className="label">Recent Breakouts</span>
            <span className="value positive">3</span>
          </div>
          <div className="summary-item">
            <span className="label">Insider Cluster Buys</span>
            <span className="value positive">7</span>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Top Opportunities</h3>
        <p>Loading top-scoring superstocks...</p>
      </div>

      <div className="card">
        <h3>Recent Alerts</h3>
        <p>No recent alerts</p>
      </div>
    </div>
  );
};

export default Dashboard;
