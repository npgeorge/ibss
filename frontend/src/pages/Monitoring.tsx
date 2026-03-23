/**
 * Monitoring Page
 *
 * Shows system health, API metrics, and data source status
 */
import React, { useEffect, useState } from 'react';
import './Monitoring.css';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

interface HealthStatus {
  status: string;
  timestamp: string;
  api_healthy: boolean;
  data_sources_healthy: boolean;
  unhealthy_sources: string[];
}

interface DataSourceHealth {
  name: string;
  is_healthy: boolean;
  uptime_pct: number;
  avg_response_time_ms: number;
  consecutive_failures: number;
  last_check: string | null;
  last_error: string | null;
}

interface ScreeningMetrics {
  total_scans: number;
  successful_scans: number;
  failed_scans: number;
  success_rate: number;
  total_stocks_screened: number;
  total_stocks_scored: number;
  avg_scan_time_ms: number;
  avg_stocks_per_scan: number;
  scans_by_mode: Record<string, number>;
}

interface DashboardSummary {
  timestamp: string;
  api_health: {
    total_endpoints: number;
    endpoints_with_errors: number;
    overall_success_rate: number;
  };
  data_sources: {
    total: number;
    healthy: number;
    unhealthy: string[];
  };
  screening: {
    total_scans: number;
    avg_scan_time_seconds: number;
    stocks_scored_total: number;
  };
  active_alerts: string[];
}

const Monitoring: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [dataSources, setDataSources] = useState<Record<string, DataSourceHealth>>({});
  const [screeningMetrics, setScreeningMetrics] = useState<ScreeningMetrics | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadMonitoringData();
  }, []);

  const loadMonitoringData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [healthRes, dataSourcesRes, screeningRes, summaryRes] = await Promise.all([
        fetch(`${API_BASE}/monitoring/health`),
        fetch(`${API_BASE}/monitoring/metrics/data-sources`),
        fetch(`${API_BASE}/monitoring/metrics/screening`),
        fetch(`${API_BASE}/monitoring/dashboard`),
      ]);

      if (healthRes.ok) setHealth(await healthRes.json());
      if (dataSourcesRes.ok) setDataSources(await dataSourcesRes.json());
      if (screeningRes.ok) setScreeningMetrics(await screeningRes.json());
      if (summaryRes.ok) setSummary(await summaryRes.json());

    } catch (err: any) {
      setError(err.message || 'Failed to load monitoring data');
    } finally {
      setLoading(false);
    }
  };

  const triggerHealthChecks = async () => {
    try {
      await fetch(`${API_BASE}/monitoring/data-sources/check`, { method: 'POST' });
      setTimeout(loadMonitoringData, 3000); // Reload after 3 seconds
    } catch (err) {
      console.error('Failed to trigger health checks:', err);
    }
  };

  const formatTime = (timestamp: string | null) => {
    if (!timestamp) return 'Never';
    return new Date(timestamp).toLocaleString();
  };

  return (
    <div className="monitoring">
      <div className="monitoring-header">
        <h2>System Monitoring</h2>
        <div className="header-actions">
          <button className="refresh-btn" onClick={loadMonitoringData} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
          <button className="check-btn" onClick={triggerHealthChecks}>
            Run Health Checks
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <p>{error}</p>
        </div>
      )}

      {/* Overall Health Status */}
      <div className={`card health-card ${health?.status || 'unknown'}`}>
        <h3>System Health</h3>
        <div className="health-status">
          <div className={`status-indicator ${health?.status || 'unknown'}`}>
            {health?.status === 'healthy' ? '✓' : '⚠'}
          </div>
          <div className="status-text">
            <span className="status-label">{health?.status?.toUpperCase() || 'UNKNOWN'}</span>
            <span className="status-time">Last checked: {formatTime(health?.timestamp || null)}</span>
          </div>
        </div>
        <div className="health-details">
          <div className={`health-item ${health?.api_healthy ? 'ok' : 'warn'}`}>
            <span>API</span>
            <span>{health?.api_healthy ? 'Healthy' : 'Degraded'}</span>
          </div>
          <div className={`health-item ${health?.data_sources_healthy ? 'ok' : 'warn'}`}>
            <span>Data Sources</span>
            <span>{health?.data_sources_healthy ? 'All Healthy' : `${health?.unhealthy_sources?.length || 0} Issues`}</span>
          </div>
        </div>
      </div>

      {/* Active Alerts */}
      {summary?.active_alerts && summary.active_alerts.length > 0 && (
        <div className="card alerts-card">
          <h3>Active Alerts</h3>
          <ul className="alerts-list">
            {summary.active_alerts.map((alert, idx) => (
              <li key={idx} className="alert-item">{alert}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Data Sources */}
      <div className="card">
        <h3>Data Sources</h3>
        <div className="data-sources-grid">
          {Object.entries(dataSources).map(([name, source]) => (
            <div key={name} className={`source-card ${source.is_healthy ? 'healthy' : 'unhealthy'}`}>
              <div className="source-header">
                <span className="source-name">{source.name}</span>
                <span className={`source-status ${source.is_healthy ? 'ok' : 'error'}`}>
                  {source.is_healthy ? 'Healthy' : 'Unhealthy'}
                </span>
              </div>
              <div className="source-metrics">
                <div className="metric">
                  <span className="label">Uptime</span>
                  <span className="value">{source.uptime_pct.toFixed(1)}%</span>
                </div>
                <div className="metric">
                  <span className="label">Avg Response</span>
                  <span className="value">{source.avg_response_time_ms.toFixed(0)}ms</span>
                </div>
                <div className="metric">
                  <span className="label">Failures</span>
                  <span className="value">{source.consecutive_failures}</span>
                </div>
              </div>
              {source.last_error && (
                <div className="source-error">
                  Last error: {source.last_error}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Screening Metrics */}
      <div className="card">
        <h3>Screening Performance</h3>
        {screeningMetrics && (
          <div className="screening-metrics">
            <div className="metrics-row">
              <div className="metric-box">
                <span className="metric-value">{screeningMetrics.total_scans}</span>
                <span className="metric-label">Total Scans</span>
              </div>
              <div className="metric-box">
                <span className="metric-value">{screeningMetrics.success_rate.toFixed(1)}%</span>
                <span className="metric-label">Success Rate</span>
              </div>
              <div className="metric-box">
                <span className="metric-value">{(screeningMetrics.avg_scan_time_ms / 1000).toFixed(1)}s</span>
                <span className="metric-label">Avg Scan Time</span>
              </div>
              <div className="metric-box">
                <span className="metric-value">{screeningMetrics.total_stocks_scored.toLocaleString()}</span>
                <span className="metric-label">Stocks Scored</span>
              </div>
            </div>

            <div className="scans-by-mode">
              <h4>Scans by Mode</h4>
              <div className="mode-breakdown">
                {Object.entries(screeningMetrics.scans_by_mode).map(([mode, count]) => (
                  <div key={mode} className="mode-item">
                    <span className={`mode-badge ${mode}`}>{mode}</span>
                    <span className="mode-count">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* API Summary */}
      {summary && (
        <div className="card">
          <h3>API Health Summary</h3>
          <div className="api-summary">
            <div className="summary-item">
              <span className="label">Total Endpoints</span>
              <span className="value">{summary.api_health.total_endpoints}</span>
            </div>
            <div className="summary-item">
              <span className="label">Endpoints with Errors</span>
              <span className={`value ${summary.api_health.endpoints_with_errors > 0 ? 'warn' : ''}`}>
                {summary.api_health.endpoints_with_errors}
              </span>
            </div>
            <div className="summary-item">
              <span className="label">Overall Success Rate</span>
              <span className="value">{summary.api_health.overall_success_rate.toFixed(1)}%</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Monitoring;
