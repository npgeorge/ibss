/**
 * Dashboard Page
 *
 * Main landing page showing market overview and top opportunities
 */
import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/api';
import { ScreeningResult, MarketConditions, AISectorAverages } from '../types/api';
import StockCard from '../components/StockCard';
import StockTable from '../components/StockTable';
import './Dashboard.css';

type ViewMode = 'tiles' | 'table';

const ViewToggle: React.FC<{ mode: ViewMode; onChange: (m: ViewMode) => void }> = ({
  mode,
  onChange,
}) => (
  <div className="view-toggle" role="group" aria-label="View mode">
    <button
      type="button"
      className={`view-toggle-btn ${mode === 'tiles' ? 'is-active' : ''}`}
      onClick={() => onChange('tiles')}
    >
      Tiles
    </button>
    <button
      type="button"
      className={`view-toggle-btn ${mode === 'table' ? 'is-active' : ''}`}
      onClick={() => onChange('table')}
    >
      Table
    </button>
  </div>
);

const REGIME_LABELS: Record<string, string> = {
  risk_on: 'Risk-On',
  neutral: 'Neutral',
  risk_off: 'Risk-Off',
  crisis: 'Crisis',
};

const formatLastScan = (iso: string): string => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const Dashboard: React.FC = () => {
  const [topOpportunities, setTopOpportunities] = useState<ScreeningResult[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [market, setMarket] = useState<MarketConditions | null>(null);
  const [stats, setStats] = useState({
    activeSuperstocks: 0,
    magicLineTouches: 0,
    recentBreakouts: 0,
    insiderClusterBuys: 0,
  });
  const [aiResults, setAiResults] = useState<ScreeningResult[]>([]);
  const [aiAverages, setAiAverages] = useState<Partial<AISectorAverages>>({});
  const [aiScanning, setAiScanning] = useState<boolean>(false);
  const [aiLastScan, setAiLastScan] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('tiles');

  useEffect(() => {
    loadDashboardData();
    loadAISector();
    // Market regime is independent of the opportunities feed; never block on it.
    apiClient
      .getMarketConditions()
      .then(setMarket)
      .catch((err) => console.error('Market conditions unavailable:', err));
  }, []);

  // Passive load: shows the last completed scan. Never starts a scan — that is
  // explicit only (the Scan button). Keeps polling only while a scan that was
  // already triggered is still running.
  const loadAISector = async (retryCount = 0) => {
    try {
      const { results, raw } = await apiClient.getAISector();
      setAiResults(results);
      setAiAverages(raw.averages);
      setAiLastScan(raw.last_scan);
      setAiScanning(raw.scanning);
      if (raw.scanning && retryCount < 30) {
        // A scan is in progress — poll until it populates (~75 names, ~5 min).
        setTimeout(() => loadAISector(retryCount + 1), 10000);
      }
    } catch (err) {
      console.error('AI sector unavailable:', err);
      setAiScanning(false);
    }
  };

  // Explicit weekly-cadence trigger. The only thing that starts a scan.
  const startAIScan = async () => {
    if (aiScanning) return;
    try {
      setAiScanning(true);
      const { raw } = await apiClient.runAISector();
      setAiLastScan(raw.last_scan);
      setTimeout(() => loadAISector(0), 10000);
    } catch (err) {
      console.error('AI scan failed to start:', err);
      setAiScanning(false);
    }
  };

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

  const statTiles = [
    { idx: '01', label: 'Active Superstocks', value: stats.activeSuperstocks, tone: 'lime' },
    { idx: '02', label: 'Magic Line Touches', value: stats.magicLineTouches, tone: 'up' },
    { idx: '03', label: 'Recent Breakouts', value: stats.recentBreakouts, tone: 'up' },
    { idx: '04', label: 'Insider Cluster Buys', value: stats.insiderClusterBuys, tone: 'info' },
  ];

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <div className="dashboard-title">
          <h2>Dashboard</h2>
          <span className="dashboard-sub te-label">Market overview &amp; top opportunities</span>
        </div>
        <button className="te-btn" onClick={refreshData} disabled={loading}>
          <span className="te-btn-dot" aria-hidden="true" />
          {loading ? 'Scanning' : 'Refresh'}
        </button>
      </div>

      {market && (
        <div className={`market-regime-banner ${market.regime}`}>
          <div className="regime-led" aria-hidden="true" />
          <div className="regime-main">
            <span className="regime-label te-label">Market Regime</span>
            <span className="regime-value">
              {REGIME_LABELS[market.regime] || market.regime}
            </span>
            <span className="regime-score te-num">{market.overall_score.toFixed(0)}<i>/100</i></span>
          </div>
          <div className="regime-detail">
            {market.spy && (
              <span className="regime-metric te-num">
                <i>SPY</i> {market.spy.trend} ({market.spy.distance_from_50sma_pct >= 0 ? '+' : ''}
                {market.spy.distance_from_50sma_pct.toFixed(1)}% vs 50DMA)
              </span>
            )}
            {market.vix && (
              <span className="regime-metric te-num">
                <i>VIX</i> {market.vix.current_vix.toFixed(1)} — {market.vix.regime}
              </span>
            )}
          </div>
          {market.warning_message && (
            <p className="regime-warning">{market.warning_message}</p>
          )}
        </div>
      )}

      <div className="summary-grid">
        {statTiles.map((tile) => (
          <div key={tile.idx} className={`stat-tile tone-${tile.tone}`}>
            <div className="stat-tile-top">
              <span className="stat-idx te-num">{tile.idx}</span>
              <span className="stat-tick" aria-hidden="true" />
            </div>
            <span className="stat-value te-num">{tile.value}</span>
            <span className="stat-label te-label">{tile.label}</span>
          </div>
        ))}
      </div>

      <div className="card opportunities-card">
        <div className="card-header">
          <div className="ai-header-main">
            <h3>Top Opportunities</h3>
            <span className="card-subtitle te-label">
              Highest scoring · latest screening
              {topOpportunities.length > 0 && (
                <span className="card-count te-num"> [{topOpportunities.length}]</span>
              )}
            </span>
          </div>
          {topOpportunities.length > 0 && (
            <ViewToggle mode={viewMode} onChange={setViewMode} />
          )}
        </div>

        {loading && <div className="loading">Loading opportunities</div>}

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
          viewMode === 'table' ? (
            <StockTable results={topOpportunities} />
          ) : (
            <div className="opportunities-grid">
              {topOpportunities.map((result, index) => (
                <StockCard key={result.stock.symbol} result={result} rank={index + 1} />
              ))}
            </div>
          )
        )}
      </div>

      <div className="card ai-sector-card">
        <div className="card-header">
          <div className="ai-header-main">
            <h3>AI<span className="ai-accent"> Sector</span></h3>
            <span className="card-subtitle te-label">
              Nebius · Ouster &amp; peers
              {aiResults.length > 0 && (
                <span className="card-count te-num"> [{aiResults.length}]</span>
              )}
              {aiLastScan && (
                <span className="ai-last-scan te-num"> · scanned {formatLastScan(aiLastScan)}</span>
              )}
            </span>
          </div>
          <div className="ai-header-right">
            {aiAverages.total_score != null && (
              <div className="ai-averages">
                {([
                  ['Avg', aiAverages.total_score, 'lime'],
                  ['Tech', aiAverages.technical_score, 'up'],
                  ['Fund', aiAverages.fundamental_score, 'up'],
                  ['Insdr', aiAverages.insider_score, 'info'],
                  ['Patt', aiAverages.pattern_score, 'info'],
                ] as const).map(([label, value, tone]) => (
                  <div key={label} className={`ai-avg tone-${tone}`}>
                    <span className="ai-avg-value te-num">{(value ?? 0).toFixed(1)}</span>
                    <span className="ai-avg-label te-label">{label}</span>
                  </div>
                ))}
              </div>
            )}
            {aiResults.length > 0 && (
              <ViewToggle mode={viewMode} onChange={setViewMode} />
            )}
            <button className="te-btn" onClick={startAIScan} disabled={aiScanning}>
              <span className="te-btn-dot" aria-hidden="true" />
              {aiScanning ? 'Scanning' : 'Scan'}
            </button>
          </div>
        </div>

        {aiScanning && aiResults.length === 0 && (
          <div className="loading">Scanning AI sector</div>
        )}

        {!aiScanning && aiResults.length === 0 && (
          <div className="empty-state">
            <p>No AI-sector data yet. Click Scan to run a fresh sector scan.</p>
          </div>
        )}

        {aiResults.length > 0 && (
          viewMode === 'table' ? (
            <StockTable results={aiResults} />
          ) : (
            <div className="opportunities-grid">
              {aiResults.map((result, index) => (
                <StockCard key={result.stock.symbol} result={result} rank={index + 1} />
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
};

export default Dashboard;
