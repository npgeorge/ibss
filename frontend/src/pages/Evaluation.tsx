/**
 * Evaluation Page
 *
 * Shows screening performance metrics and prediction tracking
 */
import React, { useEffect, useState } from 'react';
import './Evaluation.css';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

interface EvaluationMetrics {
  total_predictions: number;
  evaluated_predictions: number;
  win_rate_5pct_30d: number;
  win_rate_10pct_60d: number;
  win_rate_20pct_90d: number;
  avg_return_30d: number;
  avg_return_60d: number;
  avg_return_90d: number;
  score_return_correlation: number | null;
  signal_effectiveness: Record<string, number>;
  grade_performance: Record<string, { avg_return: number; count: number; win_rate: number }>;
}

interface EvaluationReport {
  generated_at: string;
  summary: {
    total_predictions: number;
    evaluated_predictions: number;
    pending_evaluation: number;
  };
  performance: {
    win_rates: Record<string, string>;
    average_returns: Record<string, string>;
    risk: Record<string, string>;
  };
  score_effectiveness: {
    score_return_correlation: number | null;
    interpretation: string;
  };
  signal_effectiveness: Record<string, number>;
  grade_performance: Record<string, { avg_return: number; count: number; win_rate: number }>;
  top_performers: Array<any>;
  worst_performers: Array<any>;
}

const Evaluation: React.FC = () => {
  const [metrics, setMetrics] = useState<EvaluationMetrics | null>(null);
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadEvaluationData();
  }, []);

  const loadEvaluationData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [metricsRes, reportRes] = await Promise.all([
        fetch(`${API_BASE}/screen/evaluation/metrics`),
        fetch(`${API_BASE}/screen/evaluation/report`),
      ]);

      if (metricsRes.ok) setMetrics(await metricsRes.json());
      if (reportRes.ok) setReport(await reportRes.json());

    } catch (err: any) {
      setError(err.message || 'Failed to load evaluation data');
    } finally {
      setLoading(false);
    }
  };

  const recordPredictions = async () => {
    try {
      setRecording(true);
      const response = await fetch(`${API_BASE}/screen/evaluation/record`, {
        method: 'POST',
      });
      const data = await response.json();
      alert(`Recorded ${data.recorded} predictions for future evaluation`);
      loadEvaluationData();
    } catch (err: any) {
      alert('Failed to record predictions: ' + err.message);
    } finally {
      setRecording(false);
    }
  };

  const formatPct = (value: number | null | undefined) => {
    if (value === null || value === undefined) return 'N/A';
    return `${(value * 100).toFixed(1)}%`;
  };

  const getCorrelationColor = (corr: number | null) => {
    if (corr === null) return 'neutral';
    if (corr > 0.4) return 'positive';
    if (corr > 0.1) return 'weak-positive';
    if (corr > -0.1) return 'neutral';
    return 'negative';
  };

  return (
    <div className="evaluation">
      <div className="evaluation-header">
        <h2>Screening Evaluation</h2>
        <p className="eval-subtitle">
          Track the accuracy of screening predictions over time
        </p>
        <div className="header-actions">
          <button className="refresh-btn" onClick={loadEvaluationData} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
          <button className="record-btn" onClick={recordPredictions} disabled={recording}>
            {recording ? 'Recording...' : 'Record Current Predictions'}
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <p>{error}</p>
        </div>
      )}

      {/* Summary Stats */}
      <div className="card summary-card">
        <h3>Prediction Summary</h3>
        <div className="summary-grid">
          <div className="summary-item">
            <span className="value">{metrics?.total_predictions || 0}</span>
            <span className="label">Total Predictions</span>
          </div>
          <div className="summary-item">
            <span className="value">{metrics?.evaluated_predictions || 0}</span>
            <span className="label">Evaluated (90+ days old)</span>
          </div>
          <div className="summary-item">
            <span className="value">{(metrics?.total_predictions || 0) - (metrics?.evaluated_predictions || 0)}</span>
            <span className="label">Pending Evaluation</span>
          </div>
        </div>
      </div>

      {/* Win Rates */}
      <div className="card">
        <h3>Win Rates</h3>
        <p className="section-desc">Percentage of predictions that achieved target returns</p>
        <div className="win-rates-grid">
          <div className="win-rate-card">
            <div className="win-rate-header">
              <span className="period">30 Days</span>
              <span className="target">5%+ Return</span>
            </div>
            <div className="win-rate-value">{formatPct(metrics?.win_rate_5pct_30d)}</div>
          </div>
          <div className="win-rate-card">
            <div className="win-rate-header">
              <span className="period">60 Days</span>
              <span className="target">10%+ Return</span>
            </div>
            <div className="win-rate-value">{formatPct(metrics?.win_rate_10pct_60d)}</div>
          </div>
          <div className="win-rate-card">
            <div className="win-rate-header">
              <span className="period">90 Days</span>
              <span className="target">20%+ Return</span>
            </div>
            <div className="win-rate-value">{formatPct(metrics?.win_rate_20pct_90d)}</div>
          </div>
        </div>
      </div>

      {/* Average Returns */}
      <div className="card">
        <h3>Average Returns</h3>
        <div className="returns-grid">
          <div className={`return-card ${(metrics?.avg_return_30d || 0) >= 0 ? 'positive' : 'negative'}`}>
            <span className="return-period">30 Day</span>
            <span className="return-value">{formatPct(metrics?.avg_return_30d)}</span>
          </div>
          <div className={`return-card ${(metrics?.avg_return_60d || 0) >= 0 ? 'positive' : 'negative'}`}>
            <span className="return-period">60 Day</span>
            <span className="return-value">{formatPct(metrics?.avg_return_60d)}</span>
          </div>
          <div className={`return-card ${(metrics?.avg_return_90d || 0) >= 0 ? 'positive' : 'negative'}`}>
            <span className="return-period">90 Day</span>
            <span className="return-value">{formatPct(metrics?.avg_return_90d)}</span>
          </div>
        </div>
      </div>

      {/* Score Effectiveness */}
      <div className="card">
        <h3>Score Effectiveness</h3>
        <p className="section-desc">
          Does a higher composite score predict better returns?
        </p>
        <div className={`correlation-display ${getCorrelationColor(metrics?.score_return_correlation ?? null)}`}>
          <span className="corr-label">Score-Return Correlation</span>
          <span className="corr-value">
            {metrics?.score_return_correlation !== null && metrics?.score_return_correlation !== undefined
              ? metrics.score_return_correlation.toFixed(3)
              : 'N/A'}
          </span>
          <span className="corr-interpretation">
            {report?.score_effectiveness?.interpretation || 'Insufficient data'}
          </span>
        </div>
      </div>

      {/* Signal Effectiveness */}
      {metrics?.signal_effectiveness && Object.keys(metrics.signal_effectiveness).length > 0 && (
        <div className="card">
          <h3>Entry Signal Effectiveness</h3>
          <p className="section-desc">Average 90-day return by entry signal type</p>
          <div className="signals-grid">
            {Object.entries(metrics.signal_effectiveness).map(([signal, avgReturn]) => (
              <div key={signal} className={`signal-card ${avgReturn >= 0 ? 'positive' : 'negative'}`}>
                <span className="signal-name">{signal.replace(/_/g, ' ')}</span>
                <span className="signal-return">{formatPct(avgReturn)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Grade Performance */}
      {metrics?.grade_performance && Object.keys(metrics.grade_performance).length > 0 && (
        <div className="card">
          <h3>Performance by Grade</h3>
          <p className="section-desc">How do different grades perform over time?</p>
          <table className="grade-table">
            <thead>
              <tr>
                <th>Grade</th>
                <th>Count</th>
                <th>Avg Return (90d)</th>
                <th>Win Rate</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(metrics.grade_performance)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([grade, data]) => (
                  <tr key={grade}>
                    <td><span className={`grade-badge grade-${grade.charAt(0).toLowerCase()}`}>{grade}</span></td>
                    <td>{data.count}</td>
                    <td className={data.avg_return >= 0 ? 'positive' : 'negative'}>
                      {formatPct(data.avg_return)}
                    </td>
                    <td>{formatPct(data.win_rate)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Top/Worst Performers */}
      {report && (
        <div className="performers-section">
          {report.top_performers && report.top_performers.length > 0 && (
            <div className="card">
              <h3>Top Performers</h3>
              <div className="performers-list">
                {report.top_performers.slice(0, 5).map((pred: any, idx: number) => (
                  <div key={idx} className="performer-card positive">
                    <span className="performer-symbol">{pred.symbol}</span>
                    <span className="performer-score">Score: {pred.composite_score?.toFixed(1)}</span>
                    <span className="performer-return">
                      {formatPct(pred.price_90d && pred.price_at_scan
                        ? (pred.price_90d - pred.price_at_scan) / pred.price_at_scan
                        : null)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {report.worst_performers && report.worst_performers.length > 0 && (
            <div className="card">
              <h3>Worst Performers</h3>
              <div className="performers-list">
                {report.worst_performers.slice(0, 5).map((pred: any, idx: number) => (
                  <div key={idx} className="performer-card negative">
                    <span className="performer-symbol">{pred.symbol}</span>
                    <span className="performer-score">Score: {pred.composite_score?.toFixed(1)}</span>
                    <span className="performer-return">
                      {formatPct(pred.price_90d && pred.price_at_scan
                        ? (pred.price_90d - pred.price_at_scan) / pred.price_at_scan
                        : null)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {!loading && metrics?.total_predictions === 0 && (
        <div className="card empty-state">
          <h3>No Predictions Yet</h3>
          <p>
            Start tracking screening predictions by clicking "Record Current Predictions".
            After 90 days, you'll see performance metrics here.
          </p>
        </div>
      )}
    </div>
  );
};

export default Evaluation;
