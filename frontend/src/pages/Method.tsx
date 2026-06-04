/**
 * Method Page
 *
 * Documents the *actual* Superstock scoring model the backend runs.
 * Weights are fetched live from GET /screen/scoring-model (sourced straight
 * from SuperstockScorer), so this page can't drift from the code. The
 * descriptive scoring tiers mirror each _score_* method in screener.py, and
 * every law is tagged Implemented / Partial / Roadmap to stay honest.
 */
import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/api';
import { ScoringModel } from '../types/api';
import './Method.css';

type LawStatus = 'implemented' | 'partial' | 'roadmap';

interface Law {
  key: string; // matches a backend WEIGHTS sub-key
  name: string;
  why: string;
  tiers: { label: string; score: string }[];
  status: LawStatus;
  note?: string;
  highlight?: boolean;
}

// Fallback so the page renders even if the backend is unreachable. Mirrors
// SuperstockScorer's constants; the live fetch overwrites it on success.
const DEFAULT_MODEL: ScoringModel = {
  composite: { technical: 0.4, fundamental: 0.3, insider: 0.3 },
  weights: {
    technical: { magic_line: 0.15, volume: 0.1, patterns: 0.1, relative_strength: 0.05 },
    fundamental: {
      earnings_growth: 0.08,
      revenue_growth: 0.06,
      valuation: 0.03,
      share_structure: 0.05,
      balance_sheet: 0.04,
      analyst_coverage: 0.02,
      earnings_acceleration: 0.02,
    },
    insider: { recent_buying: 0.15, cluster_buying: 0.1, price_trend: 0.05 },
  },
  entry_overlay: { floor_factor: 0.9, max_factor: 1.05, dont_chase_distance_pct: 20 },
  recommendation_tiers: [
    { label: 'STRONG BUY', min_score: 85, risk: 'LOW' },
    { label: 'BUY', min_score: 75, risk: 'MEDIUM' },
    { label: 'HOLD', min_score: 60, risk: 'MEDIUM' },
    { label: 'WATCH', min_score: 50, risk: 'HIGH' },
    { label: 'AVOID', min_score: 0, risk: 'HIGH' },
  ],
};

const TECHNICAL_LAWS: Law[] = [
  {
    key: 'magic_line',
    name: 'Magic Line Respect',
    why: "The core Stine indicator: the best-fitting 8/10/12/14-week SMA the stock keeps bouncing off. A high respect rate plus repeated clean bounces signals steady institutional accumulation.",
    status: 'implemented',
    tiers: [
      { label: '>80% respect rate + multiple bounces', score: '90-100' },
      { label: '60-80% respect rate', score: '70-90' },
      { label: '40-60% respect rate', score: '40-70' },
      { label: 'Below 40% / no clear line', score: '0-40' },
    ],
  },
  {
    key: 'volume',
    name: 'Volume Surge',
    why: 'Confirms a move is real — institutions stepping in. Measured as the latest session volume vs the 20-day average.',
    status: 'implemented',
    tiers: [
      { label: '≥ 2× 20-day average', score: '100' },
      { label: '1.5–2× average', score: '70-100' },
      { label: '1–1.5× average', score: '~70' },
      { label: '< 1× average', score: '< 50' },
    ],
  },
  {
    key: 'patterns',
    name: 'Chart Patterns',
    why: 'Classic accumulation patterns (staircase, cup & handle, flat base, double bottom) signal coiled institutional buying. Scored on the average strength of detected patterns.',
    status: 'implemented',
    tiers: [
      { label: 'Strong, well-formed pattern', score: '80-100' },
      { label: 'Moderate pattern', score: '50-80' },
      { label: 'Weak / still forming', score: '20-50' },
      { label: 'No pattern detected', score: '0' },
    ],
  },
  {
    key: 'relative_strength',
    name: 'Relative Strength vs SPY',
    why: "Superstocks dramatically outperform the market. Measured as the stock's ~3-month return minus SPY's over the same window (falls back to absolute momentum if SPY is unavailable).",
    status: 'implemented',
    tiers: [
      { label: 'Outperforms SPY by ≥ 30%', score: '100' },
      { label: '+15% to +30%', score: '80-100' },
      { label: '+5% to +15%', score: '65-80' },
      { label: '0% to +5%', score: '50-65' },
      { label: 'Underperforms SPY', score: '< 50' },
    ],
  },
];

const FUNDAMENTAL_LAWS: Law[] = [
  {
    key: 'earnings_growth',
    name: 'Earnings Growth (YoY EPS)',
    why: "Earnings drive prices long-term. Stine's superstocks show explosive EPS growth.",
    status: 'implemented',
    tiers: [
      { label: '≥ 50% YoY', score: '100' },
      { label: '20–50%', score: '70-100' },
      { label: '0–20%', score: '0-70' },
      { label: 'Negative', score: '0' },
    ],
  },
  {
    key: 'revenue_growth',
    name: 'Revenue Growth (YoY)',
    why: 'Top-line expansion confirms a real, growing business rather than one-off margin gains.',
    status: 'implemented',
    tiers: [
      { label: '≥ 50% YoY', score: '100' },
      { label: '20–50%', score: '70-100' },
      { label: '0–20%', score: '0-70' },
      { label: 'Negative', score: '0' },
    ],
  },
  {
    key: 'valuation',
    name: 'Valuation (PEG)',
    why: 'Growth at a reasonable price — undervalued relative to its own growth rate.',
    status: 'implemented',
    tiers: [
      { label: 'PEG < 1.0', score: '100' },
      { label: 'PEG 1.0–2.0', score: '50-100' },
      { label: 'PEG > 2.0', score: 'tapers to 0' },
      { label: 'No data', score: '50 (neutral)' },
    ],
  },
  {
    key: 'share_structure',
    name: 'Small Float',
    why: 'A critical Stine law — a small share supply means explosive moves once demand arrives.',
    status: 'implemented',
    highlight: true,
    tiers: [
      { label: '< 20M shares', score: '100' },
      { label: '20–50M', score: '85' },
      { label: '50–100M', score: '70' },
      { label: '100–300M', score: '50' },
      { label: '> 1B', score: '15' },
    ],
  },
  {
    key: 'balance_sheet',
    name: 'Balance Sheet (Debt + Cash)',
    why: 'Low debt and adequate liquidity give the company flexibility. Averages a debt-to-equity score and a current-ratio score.',
    status: 'implemented',
    tiers: [
      { label: 'D/E < 0.3 & Current Ratio ≥ 2', score: '~100' },
      { label: 'Low debt / solid liquidity', score: '55-80' },
      { label: 'Stretched', score: '25-55' },
      { label: 'High debt / illiquid', score: '25' },
    ],
  },
  {
    key: 'analyst_coverage',
    name: 'Low Analyst Coverage',
    why: "Under-followed names are undiscovered — the institutional crowd hasn't arrived yet.",
    status: 'partial',
    note: "Analyst count isn't always available from the data feed; when missing it scores neutral (50).",
    tiers: [
      { label: '≤ 2 analysts', score: '90' },
      { label: '3–5', score: '70' },
      { label: '6–10', score: '50' },
      { label: '> 20', score: '15' },
    ],
  },
  {
    key: 'earnings_acceleration',
    name: 'Earnings Acceleration',
    why: "Forward EPS growth exceeding trailing growth signals an inflection the market hasn't priced.",
    status: 'implemented',
    tiers: [
      { label: 'Forward growth > +20pp vs trailing', score: '100' },
      { label: 'Accelerating', score: '60-100' },
      { label: 'Flat / slight decel', score: '40-60' },
      { label: 'Sharp deceleration', score: '20' },
    ],
  },
];

const INSIDER_LAWS: Law[] = [
  {
    key: 'recent_buying',
    name: 'Recent Insider Buying',
    why: 'THE core Stine signal — insiders know more than anyone. Scored on the count of recent open-market purchases.',
    status: 'implemented',
    highlight: true,
    tiers: [
      { label: '5+ recent purchases', score: '100' },
      { label: '3–4 purchases', score: '60-80' },
      { label: '1–2 purchases', score: '20-40' },
      { label: 'None', score: '0' },
    ],
  },
  {
    key: 'cluster_buying',
    name: 'Cluster Buying',
    why: 'Multiple insiders buying together (a cluster) is the strongest conviction signal.',
    status: 'implemented',
    tiers: [
      { label: 'Cluster detected (multiple insiders)', score: '100' },
      { label: 'No cluster', score: '30' },
    ],
  },
  {
    key: 'price_trend',
    name: 'Buying Into Strength',
    why: 'Insiders adding at progressively higher prices shows escalating conviction.',
    status: 'implemented',
    tiers: [
      { label: 'Buying at rising prices', score: '100' },
      { label: 'Buying at flat / falling prices', score: '30' },
      { label: '< 2 purchases', score: '50 (neutral)' },
    ],
  },
];

const STATUS_LABEL: Record<LawStatus, string> = {
  implemented: 'Implemented',
  partial: 'Partial',
  roadmap: 'Roadmap',
};

// ── General vs AI Sector scan ────────────────────────────────────────────
// The scoring model (the 40/30/30 SuperstockScorer above) is IDENTICAL for
// both scans. Only universe construction, structural gates, the insider data
// source, and the run cadence differ.
interface ScanDiff {
  dimension: string;
  general: string;
  ai: string;
  differs: boolean;
}

const SCAN_COMPARISON: ScanDiff[] = [
  {
    dimension: 'Universe',
    general: 'Finviz pre-filter rebuilds the candidate list each run (the low-priced superstock band).',
    ai: 'Fixed, hand-curated list of ~77 AI / AI-adjacent tickers across 8 segments.',
    differs: true,
  },
  {
    dimension: 'Price & market-cap gates',
    general: 'Enforced — favors small, low-priced, undiscovered names.',
    ai: 'Opened wide (price ≥ $0.01, no cap ceiling). AI spans micro-cap to multi-trillion, so the gates would wrongly drop most of the sector.',
    differs: true,
  },
  {
    dimension: 'Insider data source',
    general: 'One market-wide OpenInsider pull (cluster buys + recent purchases), shared across all candidates.',
    ai: 'Per-symbol OpenInsider lookups — the market-wide buy feed rarely overlaps a fixed list, and per-symbol queries also surface selling.',
    differs: true,
  },
  {
    dimension: 'Trigger & cadence',
    general: 'Runs as part of the screening pipeline (Quick / Standard / Deep modes).',
    ai: 'Explicit, on-demand weekly Scan button. Result cached 14 days; page refreshes never auto-start a scan.',
    differs: true,
  },
  {
    dimension: 'Scoring model',
    general: '40% Technical / 30% Fundamental / 30% Insider, plus the entry-timing overlay.',
    ai: 'Identical — the exact same SuperstockScorer, weights, and overlay.',
    differs: false,
  },
];

const AI_SEGMENTS: { name: string; examples: string }[] = [
  { name: 'Semiconductors & AI compute', examples: 'NVDA, AMD, AVGO, TSM, ARM, MRVL, MU, ASML' },
  { name: 'Networking & data-center infra', examples: 'ANET, VRT, DELL, CIEN, CRWV' },
  { name: 'Cloud, platforms & mega-cap', examples: 'NBIS, MSFT, GOOGL, AMZN, META, ORCL' },
  { name: 'AI software & pure-plays', examples: 'PLTR, AI, PATH, DDOG, CRWD, PANW, SNOW' },
  { name: 'Quantum computing', examples: 'IONQ, RGTI, QBTS, QUBT, ARQQ' },
  { name: 'Autonomy & robotics', examples: 'TSLA, SERV, PONY, AUR, SYM' },
  { name: 'Lidar & perception sensors', examples: 'OUST, LAZR, INVZ, AEVA, MVIS' },
  { name: 'AI drug discovery & health', examples: 'RXRX, SDGR, ABCL' },
];

const pct = (fraction: number | undefined): string =>
  fraction == null ? '—' : `${Math.round(fraction * 100)}%`;

const Method: React.FC = () => {
  const [model, setModel] = useState<ScoringModel>(DEFAULT_MODEL);

  useEffect(() => {
    apiClient
      .getScoringModel()
      .then(setModel)
      .catch(() => {
        /* keep DEFAULT_MODEL — page stays useful offline */
      });
  }, []);

  const renderLaw = (law: Law, weights: Record<string, number>) => (
    <div key={law.key} className={`criterion-card ${law.highlight ? 'highlight' : ''}`}>
      <div className="criterion-header">
        <div className="criterion-title">
          <span className="criterion-name">{law.name}</span>
          <span className={`law-status ${law.status}`}>{STATUS_LABEL[law.status]}</span>
        </div>
        <span className="criterion-weight">{pct(weights[law.key])}</span>
      </div>
      <div className="criterion-body">
        <p className="criterion-why">
          <strong>Why:</strong> {law.why}
        </p>
        <div className="scoring-table">
          {law.tiers.map((t) => (
            <div className="score-row" key={t.label}>
              <span>{t.label}</span>
              <span className="score">{t.score}</span>
            </div>
          ))}
        </div>
        {law.note && <p className="criterion-detail">{law.note}</p>}
      </div>
    </div>
  );

  const { composite, weights, entry_overlay, recommendation_tiers } = model;

  return (
    <div className="method">
      <div className="method-header">
        <h2>Superstock Scoring Model</h2>
        <p className="method-subtitle">
          Based on Jesse Stine's "Insider Buy Superstocks" — a weighted composite of Technical (
          {pct(composite.technical)}), Fundamental ({pct(composite.fundamental)}) and Insider (
          {pct(composite.insider)}) sub-laws. Weights are read live from the scoring engine. The
          same model powers both the general screener and the AI-sector watch — the two scans differ
          only in how they pick and gate the universe (see below).
        </p>
      </div>

      {/* Key Principle */}
      <div className="card principle-card">
        <h3>Key Principle: Rank, Don't Hard-Filter</h3>
        <p>
          Stocks are <strong>scored and ranked</strong> on a 0&ndash;100 composite — not pass/fail
          filtered. Only structural requirements (price range, volume, market cap) are hard gates;
          everything else is scored so a stock that misses one law on quality still surfaces if the
          rest of its profile is strong.
        </p>
        <div className="principle-highlight">
          <span className="highlight-label">Composite split:</span>
          <span className="highlight-value">
            Technical {pct(composite.technical)} &nbsp;•&nbsp; Fundamental {pct(composite.fundamental)}{' '}
            &nbsp;•&nbsp; Insider {pct(composite.insider)}
          </span>
        </div>
      </div>

      {/* Scan Modes */}
      <div className="card">
        <h3>Scan Modes</h3>
        <div className="scan-modes-table">
          <table>
            <thead>
              <tr>
                <th>Mode</th>
                <th>Target Time</th>
                <th>Universe Size</th>
                <th>Insider Source</th>
                <th>Best For</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <span className="mode-badge quick">Quick</span>
                </td>
                <td>&lt;30 sec</td>
                <td>~200-500 stocks</td>
                <td>OpenInsider (cached)</td>
                <td>Daily monitoring, quick checks</td>
              </tr>
              <tr>
                <td>
                  <span className="mode-badge standard">Standard</span>
                </td>
                <td>&lt;2 min</td>
                <td>~500-1000 stocks</td>
                <td>OpenInsider (live)</td>
                <td>Regular screening sessions</td>
              </tr>
              <tr>
                <td>
                  <span className="mode-badge deep">Deep</span>
                </td>
                <td>&lt;5 min</td>
                <td>~1000-2000 stocks</td>
                <td>OpenInsider + SEC</td>
                <td>Comprehensive weekend analysis</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* General vs AI Sector */}
      <div className="card criteria-section">
        <h3>General Screener vs AI Sector</h3>
        <p className="section-desc">
          Same scoring lens, different universe. Both paths run the identical{' '}
          {pct(composite.technical)}/{pct(composite.fundamental)}/{pct(composite.insider)}{' '}
          SuperstockScorer — only how the candidate list is built, gated, and sourced for insider
          data changes.
        </p>
        <div className="scan-modes-table">
          <table>
            <thead>
              <tr>
                <th></th>
                <th>General Screener</th>
                <th>AI Sector</th>
              </tr>
            </thead>
            <tbody>
              {SCAN_COMPARISON.map((row) => (
                <tr key={row.dimension}>
                  <td>
                    <strong>{row.dimension}</strong>
                  </td>
                  <td>{row.general}</td>
                  <td className={row.differs ? 'ai-cell-differs' : ''}>{row.ai}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="principle-highlight ai-note">
          <span className="highlight-label">Aligns with the book:</span>
          <span className="highlight-value">
            Stine's superstocks are small, undiscovered, low-float, low-priced names with heavy
            insider <em>buying</em>. Much of the AI sector is the structural opposite — mega-cap,
            heavily covered, large-float, and dominated by insider <em>selling</em>. The same lens
            therefore scores most AI names low on the small-float, low-coverage, valuation, and
            insider-buying laws. That is the point: it cuts through sector hype and surfaces the
            rare AI name showing genuine superstock traits — real cluster buying, accelerating
            earnings, relative strength — rather than rewarding the whole theme.
          </span>
        </div>

        <h4 className="ai-universe-title">AI Universe — 8 Segments (~77 names)</h4>
        <div className="market-conditions-grid">
          {AI_SEGMENTS.map((seg) => (
            <div className="condition-card" key={seg.name}>
              <h4>{seg.name}</h4>
              <p>{seg.examples}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Technical */}
      <div className="card criteria-section">
        <h3>Technical Laws ({pct(composite.technical)} of total score)</h3>
        <p className="section-desc">Price action, volume, trend, and market-relative strength</p>
        <div className="criteria-grid">{TECHNICAL_LAWS.map((l) => renderLaw(l, weights.technical))}</div>
      </div>

      {/* Fundamental */}
      <div className="card criteria-section">
        <h3>Fundamental Laws ({pct(composite.fundamental)} of total score)</h3>
        <p className="section-desc">Growth, valuation, share structure, and balance-sheet health</p>
        <div className="criteria-grid">{FUNDAMENTAL_LAWS.map((l) => renderLaw(l, weights.fundamental))}</div>
      </div>

      {/* Insider */}
      <div className="card criteria-section">
        <h3>Insider Laws ({pct(composite.insider)} of total score)</h3>
        <p className="section-desc">Open-market insider buying — the heart of the methodology</p>
        <div className="criteria-grid">{INSIDER_LAWS.map((l) => renderLaw(l, weights.insider))}</div>
      </div>

      {/* Entry-Timing Overlay */}
      <div className="card">
        <h3>Entry-Timing Overlay</h3>
        <p className="section-desc">A multiplier on the composite — rewards clean entries, penalizes chasing</p>
        <p>
          After the {pct(composite.technical)}/{pct(composite.fundamental)}/{pct(composite.insider)}{' '}
          composite is computed, an entry-timing multiplier between{' '}
          <strong>{entry_overlay.floor_factor.toFixed(2)}×</strong> and{' '}
          <strong>{entry_overlay.max_factor.toFixed(2)}×</strong> nudges the score by how clean
          the entry is relative to the Magic Line.
        </p>
        <ul>
          <li>
            <strong>Don't chase:</strong> a stock extended more than{' '}
            {entry_overlay.dont_chase_distance_pct}% above its Magic Line is capped at the floor
            multiplier and any Buy is downgraded to Watch.
          </li>
          <li>
            <strong>Scale-in guidance:</strong> qualifying setups return tranche-based entry
            suggestions (e.g. buy at the Magic Line, add on confirmation).
          </li>
        </ul>
      </div>

      {/* Recommendation tiers */}
      <div className="card">
        <h3>Recommendation Tiers</h3>
        <div className="scan-modes-table">
          <table>
            <thead>
              <tr>
                <th>Recommendation</th>
                <th>Composite Score</th>
                <th>Risk Level</th>
              </tr>
            </thead>
            <tbody>
              {recommendation_tiers.map((t, i) => (
                <tr key={t.label}>
                  <td>
                    <strong>{t.label}</strong>
                  </td>
                  <td>
                    {t.min_score > 0
                      ? `≥ ${t.min_score}`
                      : `< ${recommendation_tiers[i - 1]?.min_score ?? 50}`}
                  </td>
                  <td>{t.risk}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="criterion-detail">
          A confirmed Magic Line violation forces a SELL regardless of score. The don't-chase rule
          downgrades an otherwise-qualifying Buy to Watch.
        </p>
      </div>

      {/* Roadmap */}
      <div className="card criteria-section">
        <h3>Roadmap — Not Yet Scored</h3>
        <p className="section-desc">
          Stine concepts the engine doesn't yet fold into the composite. Listed here so the model
          stays honest about its current scope.
        </p>
        <div className="market-conditions-grid">
          <div className="condition-card">
            <h4>Market Regime Filter</h4>
            <p>Gate or annotate recommendations by the broad market environment.</p>
            <ul>
              <li>SPY trend vs its 50-day MA</li>
              <li>VIX regime (calm vs panic)</li>
              <li>Market breadth</li>
            </ul>
          </div>
          <div className="condition-card">
            <h4>Advanced Exit Signals</h4>
            <p>Exits beyond the Magic-Line violation.</p>
            <ul>
              <li>Parabolic blow-off exit</li>
              <li>Time-stop on stalled positions</li>
            </ul>
          </div>
          <div className="condition-card">
            <h4>Additional Quality Laws</h4>
            <p>Computed or planned, but not in the score yet.</p>
            <ul>
              <li>Volume dry-up / orderly pullback (currently enrichment only)</li>
              <li>Consecutive earnings-surprise streak</li>
              <li>Options availability (favor no liquid options)</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Data Sources */}
      <div className="card">
        <h3>Data Sources</h3>
        <ul className="data-sources">
          <li>
            <strong>Price Data:</strong> Yahoo Finance (daily/weekly OHLCV)
          </li>
          <li>
            <strong>Fundamentals & Float:</strong> Finviz (EPS, revenue, PEG, debt, float, analysts)
          </li>
          <li>
            <strong>Insider Transactions:</strong> OpenInsider (aggregated SEC Form 4)
          </li>
          <li>
            <strong>Relative Strength Benchmark:</strong> SPY
          </li>
        </ul>
      </div>
    </div>
  );
};

export default Method;
