/**
 * Dashboard Page
 *
 * Main landing page showing market overview and top opportunities
 */
import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/api';
import { ScreeningResult } from '../types/api';
import StockCard from '../components/StockCard';
import './Dashboard.css';

const Dashboard: React.FC = () => {
  const [topOpportunities, setTopOpportunities] = useState<ScreeningResult[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState({
    activeSuperstocks: 0,
    magicLineTouches: 0,
    recentBreakouts: 0,
    insiderClusterBuys: 0,
  });

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async (retryCount = 0) => {
    try {
      setLoading(true);
      setError(null);

      // Load top opportunities
      const opportunities = await apiClient.getTopOpportunities(10);

      if (opportunities.length === 0 && retryCount < 5) {
        // Pipeline is running in the background — retry after a delay
        setLoading(true);
        setTimeout(() => loadDashboardData(retryCount + 1), 10000);
        return;
      }

      setTopOpportunities(opportunities);

      // Calculate stats from opportunities
      const stats = {
        activeSuperstocks: opportunities.filter(o => o.score.total_score >= 70).length,
        magicLineTouches: opportunities.filter(o => o.magic_line_distance < 5).length,
        recentBreakouts: opportunities.filter(o => o.latest_pattern?.toLowerCase().includes('breakout')).length,
        insiderClusterBuys: opportunities.filter(o => o.insider_activity === 'HIGH').length,
      };
      setStats(stats);

    } catch (err: any) {
      console.error('Error loading dashboard data:', err);
      setError(err.message || 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  const refreshData = () => {
    loadDashboardData();
  };

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h2>Dashboard</h2>
        <button className="refresh-btn" onClick={refreshData} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      <div className="dashboard-summary card">
        <h3>Market Overview</h3>
        <div className="summary-grid">
          <div className="summary-item">
            <span className="label">Active Superstocks</span>
            <span className="value">{stats.activeSuperstocks}</span>
          </div>
          <div className="summary-item">
            <span className="label">Magic Line Touches</span>
            <span className="value positive">{stats.magicLineTouches}</span>
          </div>
          <div className="summary-item">
            <span className="label">Recent Breakouts</span>
            <span className="value positive">{stats.recentBreakouts}</span>
          </div>
          <div className="summary-item">
            <span className="label">Insider Cluster Buys</span>
            <span className="value positive">{stats.insiderClusterBuys}</span>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Top Opportunities</h3>
          <span className="card-subtitle">Highest scoring stocks from latest screening</span>
        </div>

        {loading && <div className="loading">Loading opportunities...</div>}

        {error && (
          <div className="error">
            <p>{error}</p>
            <button onClick={refreshData}>Retry</button>
          </div>
        )}

        {!loading && !error && topOpportunities.length === 0 && (
          <div className="empty-state">
            <p>No opportunities found. Run a screening to get started.</p>
          </div>
        )}

        {!loading && !error && topOpportunities.length > 0 && (
          <div className="opportunities-grid">
            {topOpportunities.map((result, index) => (
              <StockCard key={result.stock.symbol} result={result} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
