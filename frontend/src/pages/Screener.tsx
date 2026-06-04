/**
 * Screener Page
 *
 * Advanced stock screening with customizable filters
 */
import React, { useState } from 'react';
import { apiClient, scanResultToScreeningResult } from '../services/api';
import { ScreeningCriteria, ScreeningResult } from '../types/api';
import StockCard from '../components/StockCard';
import ScanProgress, { ScanProgressData } from '../components/ScanProgress';
import './Screener.css';

const IDLE_PROGRESS: ScanProgressData = {
  status: '',
  current: 0,
  total: 0,
  currentSymbol: '',
  percentComplete: 0,
  resultsFound: 0,
  phase: 'idle',
};

const STAGE_TO_PHASE: Record<string, ScanProgressData['phase']> = {
  finviz: 'prefilter',
  fetch: 'scanning',
  insider: 'scanning',
  score: 'scanning',
  persist: 'scanning',
  done: 'complete',
};

const Screener: React.FC = () => {
  const [criteria, setCriteria] = useState<ScreeningCriteria>({
    price_min: 0.5,
    price_max: 10.0,
    volume_min: 100000,
    min_total_score: 70.0,
  });

  const [results, setResults] = useState<ScreeningResult[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [totalScreened, setTotalScreened] = useState<number>(0);
  const [progress, setProgress] = useState<ScanProgressData>(IDLE_PROGRESS);

  const handleInputChange = (field: keyof ScreeningCriteria, value: any) => {
    setCriteria((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const runScreening = async () => {
    const start = Date.now();
    try {
      setLoading(true);
      setError(null);
      setProgress({ ...IDLE_PROGRESS, phase: 'starting', status: 'Launching scan...' });

      const streamed = await apiClient.runScanStream(
        criteria,
        (event) => {
          if (event.type === 'progress') {
            setProgress((prev) => ({
              ...prev,
              phase: STAGE_TO_PHASE[event.stage] ?? 'scanning',
              percentComplete: event.percent,
              status: event.message,
              currentSymbol: event.stage,
            }));
          } else if (event.type === 'complete') {
            setProgress((prev) => ({
              ...prev,
              phase: 'complete',
              percentComplete: 100,
              total: event.total,
              resultsFound: event.total,
              scanTimeMs: Date.now() - start,
            }));
          }
        },
        { limit: 50, persist: true }
      );

      const mapped = streamed.map(scanResultToScreeningResult);
      setResults(mapped);
      setTotalScreened(mapped.length);
    } catch (err: any) {
      console.error('Screening error:', err);
      setError(err.message || 'Failed to run screening');
      setProgress((prev) => ({ ...prev, phase: 'error', errorMessage: err.message || 'Scan failed' }));
    } finally {
      setLoading(false);
    }
  };

  const resetFilters = () => {
    setCriteria({
      price_min: 0.5,
      price_max: 10.0,
      volume_min: 100000,
      min_total_score: 70.0,
    });
  };

  return (
    <div className="screener">
      <div className="screener-header">
        <h2>Superstock Screener</h2>
        <p className="screener-subtitle">Find high-potential stocks using Jesse Stine's proven methodology</p>
      </div>

      <div className="card filters-card">
        <h3>Screening Criteria</h3>

        <div className="filter-form">
          <div className="filter-section">
            <h4>Price & Volume</h4>
            <div className="filter-group">
              <label>
                <span className="label-text">Min Price ($)</span>
                <input
                  type="number"
                  value={criteria.price_min || ''}
                  onChange={(e) => handleInputChange('price_min', parseFloat(e.target.value))}
                  step="0.1"
                  min="0"
                />
              </label>
              <label>
                <span className="label-text">Max Price ($)</span>
                <input
                  type="number"
                  value={criteria.price_max || ''}
                  onChange={(e) => handleInputChange('price_max', parseFloat(e.target.value))}
                  step="0.5"
                  min="0"
                />
              </label>
            </div>
            <div className="filter-group">
              <label>
                <span className="label-text">Min Volume</span>
                <input
                  type="number"
                  value={criteria.volume_min || ''}
                  onChange={(e) => handleInputChange('volume_min', parseInt(e.target.value))}
                  step="10000"
                  min="0"
                />
              </label>
            </div>
          </div>

          <div className="filter-section">
            <h4>Technical Scores</h4>
            <div className="filter-group">
              <label>
                <span className="label-text">Min Total Score</span>
                <input
                  type="number"
                  value={criteria.min_total_score || ''}
                  onChange={(e) => handleInputChange('min_total_score', parseFloat(e.target.value))}
                  step="5"
                  min="0"
                  max="100"
                />
              </label>
              <label>
                <span className="label-text">Min Technical Score</span>
                <input
                  type="number"
                  value={criteria.min_technical_score || ''}
                  onChange={(e) => handleInputChange('min_technical_score', parseFloat(e.target.value))}
                  step="5"
                  min="0"
                  max="100"
                />
              </label>
            </div>
            <div className="filter-group">
              <label>
                <span className="label-text">Min Fundamental Score</span>
                <input
                  type="number"
                  value={criteria.min_fundamental_score || ''}
                  onChange={(e) => handleInputChange('min_fundamental_score', parseFloat(e.target.value))}
                  step="5"
                  min="0"
                  max="100"
                />
              </label>
              <label>
                <span className="label-text">Min Insider Score</span>
                <input
                  type="number"
                  value={criteria.min_insider_score || ''}
                  onChange={(e) => handleInputChange('min_insider_score', parseFloat(e.target.value))}
                  step="5"
                  min="0"
                  max="100"
                />
              </label>
            </div>
          </div>

          <div className="filter-section">
            <h4>Magic Line & Patterns</h4>
            <div className="filter-group">
              <label>
                <span className="label-text">Max Magic Line Distance (%)</span>
                <input
                  type="number"
                  value={criteria.magic_line_distance_max || ''}
                  onChange={(e) => handleInputChange('magic_line_distance_max', parseFloat(e.target.value))}
                  step="1"
                  min="0"
                  placeholder="Any"
                />
              </label>
            </div>
            <div className="filter-group checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={criteria.require_insider_buying || false}
                  onChange={(e) => handleInputChange('require_insider_buying', e.target.checked)}
                />
                <span>Require Insider Buying</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={criteria.require_patterns || false}
                  onChange={(e) => handleInputChange('require_patterns', e.target.checked)}
                />
                <span>Require Chart Patterns</span>
              </label>
            </div>
          </div>
        </div>

        <div className="filter-actions">
          <button className="btn-secondary" onClick={resetFilters} disabled={loading}>
            Reset Filters
          </button>
          <button className="btn-primary" onClick={runScreening} disabled={loading}>
            {loading ? 'Screening...' : 'Run Screening'}
          </button>
        </div>
      </div>

      <div className="card results-card">
        <div className="results-header">
          <h3>Screening Results</h3>
          {results.length > 0 && (
            <span className="results-count">
              {results.length} matches from {totalScreened} stocks screened
            </span>
          )}
        </div>

        {progress.phase !== 'idle' && <ScanProgress progress={progress} />}

        {error && (
          <div className="error">
            <p>{error}</p>
            <button onClick={runScreening}>Retry</button>
          </div>
        )}

        {!loading && !error && results.length === 0 && (
          <div className="empty-state">
            <p>No results yet. Adjust your criteria and run a screening.</p>
          </div>
        )}

        {!loading && !error && results.length > 0 && (
          <div className="results-grid">
            {results.map((result) => (
              <StockCard key={result.stock.symbol} result={result} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Screener;
