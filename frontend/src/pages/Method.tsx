/**
 * Method Page
 *
 * Documents the complete Jesse Stine Superstock methodology
 * with all 19 criteria and their scoring logic
 */
import React from 'react';
import './Method.css';

const Method: React.FC = () => {
  return (
    <div className="method">
      <div className="method-header">
        <h2>Superstock Screening Methodology</h2>
        <p className="method-subtitle">
          Based on Jesse Stine's "Insider Buy Superstocks" approach - 19 criteria scored and weighted
        </p>
      </div>

      {/* Key Principle */}
      <div className="card principle-card">
        <h3>Key Principle: Rank, Don't Hard-Filter</h3>
        <p>
          Stocks are <strong>scored and ranked</strong> by how many criteria they meet - NOT hard-filtered.
          A stock meeting 14/19 criteria ranks above one meeting 10/19, but BOTH appear in results.
          This prevents missing good opportunities that fail just 1-2 criteria.
        </p>
        <div className="principle-highlight">
          <span className="highlight-label">Minimum Threshold:</span>
          <span className="highlight-value">Only stocks meeting &lt;5 criteria are excluded</span>
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
                <td><span className="mode-badge quick">Quick</span></td>
                <td>&lt;30 sec</td>
                <td>~200-500 stocks</td>
                <td>OpenInsider (cached)</td>
                <td>Daily monitoring, quick checks</td>
              </tr>
              <tr>
                <td><span className="mode-badge standard">Standard</span></td>
                <td>&lt;2 min</td>
                <td>~500-1000 stocks</td>
                <td>OpenInsider (live)</td>
                <td>Regular screening sessions</td>
              </tr>
              <tr>
                <td><span className="mode-badge deep">Deep</span></td>
                <td>&lt;5 min</td>
                <td>~1000-2000 stocks</td>
                <td>OpenInsider + SEC</td>
                <td>Comprehensive weekend analysis</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Technical Criteria */}
      <div className="card criteria-section">
        <h3>Technical Criteria (45% of total score)</h3>
        <p className="section-desc">Price action, volume, and trend-based indicators</p>

        <div className="criteria-grid">
          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Price Range</span>
              <span className="criterion-weight">4%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Sweet spot for explosive moves - enough liquidity but not over-owned</p>
              <div className="scoring-table">
                <div className="score-row"><span>$3-10</span><span className="score">100</span></div>
                <div className="score-row"><span>$1-3 or $10-20</span><span className="score">70</span></div>
                <div className="score-row"><span>$20-50</span><span className="score">40</span></div>
                <div className="score-row"><span>&lt;$1 or &gt;$50</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Magic Line Respect</span>
              <span className="criterion-weight">10%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Core Jesse indicator - stocks that respect their MA show institutional accumulation</p>
              <div className="scoring-table">
                <div className="score-row"><span>8/10/12/14 WMA tested with &gt;80% respect rate</span><span className="score">100</span></div>
                <div className="score-row"><span>60-80% respect rate</span><span className="score">70</span></div>
                <div className="score-row"><span>40-60% respect rate</span><span className="score">40</span></div>
                <div className="score-row"><span>&lt;40% respect rate</span><span className="score">0</span></div>
              </div>
              <p className="criterion-detail">+ Bonus for bounce count (up to +30 points)</p>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Volume Surge</span>
              <span className="criterion-weight">5%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Confirms breakout validity - institutions moving in</p>
              <div className="scoring-table">
                <div className="score-row"><span>&gt;2x average volume</span><span className="score">100</span></div>
                <div className="score-row"><span>1.5-2x average</span><span className="score">70</span></div>
                <div className="score-row"><span>1-1.5x average</span><span className="score">40</span></div>
                <div className="score-row"><span>&lt;1x average</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Volume Dry-Up</span>
              <span className="criterion-weight">5%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Accumulation signature - sellers exhausted before breakout</p>
              <div className="scoring-table">
                <div className="score-row"><span>Volume decreased &gt;50% with tight price range</span><span className="score">100</span></div>
                <div className="score-row"><span>Volume decreased 30-50%</span><span className="score">70</span></div>
                <div className="score-row"><span>Volume decreased 10-30%</span><span className="score">40</span></div>
                <div className="score-row"><span>No dry-up pattern</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Near 52-Week High</span>
              <span className="criterion-weight">4%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Strength indicator - leaders lead, don't catch falling knives</p>
              <div className="scoring-table">
                <div className="score-row"><span>Within 10% of 52w high</span><span className="score">100</span></div>
                <div className="score-row"><span>Within 25%</span><span className="score">70</span></div>
                <div className="score-row"><span>Within 40%</span><span className="score">40</span></div>
                <div className="score-row"><span>&gt;40% below high</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Relative Strength vs SPY</span>
              <span className="criterion-weight">5%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Must outperform the market - institutional preference</p>
              <div className="scoring-table">
                <div className="score-row"><span>RS &gt; 1.5 (50%+ outperformance)</span><span className="score">100</span></div>
                <div className="score-row"><span>RS 1.2-1.5</span><span className="score">70</span></div>
                <div className="score-row"><span>RS 1.0-1.2</span><span className="score">40</span></div>
                <div className="score-row"><span>RS &lt; 1.0 (underperforming)</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Orderly Pullbacks</span>
              <span className="criterion-weight">4%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Low volatility during consolidation = controlled selling</p>
              <div className="scoring-table">
                <div className="score-row"><span>ATR &lt;3% during pullback</span><span className="score">100</span></div>
                <div className="score-row"><span>ATR 3-5%</span><span className="score">70</span></div>
                <div className="score-row"><span>ATR 5-8%</span><span className="score">40</span></div>
                <div className="score-row"><span>ATR &gt;8% (volatile)</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Distance from Magic Line</span>
              <span className="criterion-weight">3%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Don't chase extended stocks - wait for pullback to ML</p>
              <div className="scoring-table">
                <div className="score-row"><span>Within 5% of ML (ideal entry)</span><span className="score">100</span></div>
                <div className="score-row"><span>5-10% above ML</span><span className="score">70</span></div>
                <div className="score-row"><span>10-20% above ML</span><span className="score">40</span></div>
                <div className="score-row"><span>&gt;20% above ML (extended)</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Pattern Detected</span>
              <span className="criterion-weight">5%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Classic accumulation patterns signal institutional buying</p>
              <div className="scoring-table">
                <div className="score-row"><span>Staircase pattern (Jesse's favorite)</span><span className="score">100</span></div>
                <div className="score-row"><span>Cup & Handle, Flat Base</span><span className="score">85</span></div>
                <div className="score-row"><span>Double Bottom, Ascending Triangle</span><span className="score">70</span></div>
                <div className="score-row"><span>No clear pattern</span><span className="score">0</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Fundamental Criteria */}
      <div className="card criteria-section">
        <h3>Fundamental Criteria (30% of total score)</h3>
        <p className="section-desc">Financial health and growth indicators</p>

        <div className="criteria-grid">
          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Small Float</span>
              <span className="criterion-weight">7%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> CRITICAL - small supply = explosive moves when demand increases</p>
              <div className="scoring-table">
                <div className="score-row"><span>&lt;20M shares</span><span className="score">100</span></div>
                <div className="score-row"><span>20-50M shares</span><span className="score">80</span></div>
                <div className="score-row"><span>50-100M shares</span><span className="score">50</span></div>
                <div className="score-row"><span>&gt;100M shares</span><span className="score">20</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Earnings Growth</span>
              <span className="criterion-weight">7%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Earnings drive stock prices long-term</p>
              <div className="scoring-table">
                <div className="score-row"><span>&gt;50% YoY EPS growth</span><span className="score">100</span></div>
                <div className="score-row"><span>25-50% growth</span><span className="score">70</span></div>
                <div className="score-row"><span>10-25% growth</span><span className="score">40</span></div>
                <div className="score-row"><span>&lt;10% or negative</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Earnings Surprise</span>
              <span className="criterion-weight">3%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Consecutive beats signal underestimated growth</p>
              <div className="scoring-table">
                <div className="score-row"><span>4+ consecutive beats</span><span className="score">100</span></div>
                <div className="score-row"><span>2-3 consecutive beats</span><span className="score">70</span></div>
                <div className="score-row"><span>1 beat</span><span className="score">40</span></div>
                <div className="score-row"><span>Miss or no data</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Revenue Growth</span>
              <span className="criterion-weight">5%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Top-line growth shows business expansion</p>
              <div className="scoring-table">
                <div className="score-row"><span>&gt;30% YoY revenue growth</span><span className="score">100</span></div>
                <div className="score-row"><span>15-30% growth</span><span className="score">70</span></div>
                <div className="score-row"><span>5-15% growth</span><span className="score">40</span></div>
                <div className="score-row"><span>&lt;5% or negative</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">PEG Ratio</span>
              <span className="criterion-weight">4%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Undervalued relative to growth rate</p>
              <div className="scoring-table">
                <div className="score-row"><span>PEG &lt;0.5</span><span className="score">100</span></div>
                <div className="score-row"><span>PEG 0.5-1.0</span><span className="score">75</span></div>
                <div className="score-row"><span>PEG 1.0-1.5</span><span className="score">50</span></div>
                <div className="score-row"><span>PEG &gt;1.5</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Low Debt</span>
              <span className="criterion-weight">2%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Strong balance sheet = financial flexibility</p>
              <div className="scoring-table">
                <div className="score-row"><span>Debt/Equity &lt;0.3</span><span className="score">100</span></div>
                <div className="score-row"><span>D/E 0.3-0.5</span><span className="score">70</span></div>
                <div className="score-row"><span>D/E 0.5-1.0</span><span className="score">40</span></div>
                <div className="score-row"><span>D/E &gt;1.0</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Adequate Cash</span>
              <span className="criterion-weight">2%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Liquidity for operations and opportunities</p>
              <div className="scoring-table">
                <div className="score-row"><span>Current Ratio &gt;2.0</span><span className="score">100</span></div>
                <div className="score-row"><span>CR 1.5-2.0</span><span className="score">70</span></div>
                <div className="score-row"><span>CR 1.0-1.5</span><span className="score">40</span></div>
                <div className="score-row"><span>CR &lt;1.0</span><span className="score">0</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Insider & Market Criteria */}
      <div className="card criteria-section">
        <h3>Insider & Market Criteria (25% of total score)</h3>
        <p className="section-desc">Smart money signals and market structure</p>

        <div className="criteria-grid">
          <div className="criterion-card highlight">
            <div className="criterion-header">
              <span className="criterion-name">Insider Buying</span>
              <span className="criterion-weight">15%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> THE core signal - insiders know more than anyone</p>
              <div className="scoring-table">
                <div className="score-row"><span>Cluster buy (3+ insiders, 90 days)</span><span className="score">100</span></div>
                <div className="score-row"><span>Multiple buys, meaningful size</span><span className="score">80</span></div>
                <div className="score-row"><span>Single significant buy</span><span className="score">60</span></div>
                <div className="score-row"><span>No recent buying</span><span className="score">0</span></div>
              </div>
              <p className="criterion-detail">
                Factors: Recency (more recent = higher score), buyer seniority (CEO &gt; Director),
                purchase size relative to salary, price trend since purchase
              </p>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">Low Analyst Coverage</span>
              <span className="criterion-weight">5%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Under-followed = undiscovered opportunity</p>
              <div className="scoring-table">
                <div className="score-row"><span>0-2 analysts</span><span className="score">100</span></div>
                <div className="score-row"><span>3-5 analysts</span><span className="score">75</span></div>
                <div className="score-row"><span>6-10 analysts</span><span className="score">50</span></div>
                <div className="score-row"><span>&gt;10 analysts</span><span className="score">0</span></div>
              </div>
            </div>
          </div>

          <div className="criterion-card">
            <div className="criterion-header">
              <span className="criterion-name">No Listed Options</span>
              <span className="criterion-weight">5%</span>
            </div>
            <div className="criterion-body">
              <p className="criterion-why"><strong>Why:</strong> Less manipulation, cleaner price action</p>
              <div className="scoring-table">
                <div className="score-row"><span>No options available</span><span className="score">100</span></div>
                <div className="score-row"><span>Options exist (illiquid)</span><span className="score">50</span></div>
                <div className="score-row"><span>Active options market</span><span className="score">0</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Market Conditions */}
      <div className="card criteria-section">
        <h3>Market Conditions (Entry Timing)</h3>
        <p className="section-desc">These don't affect stock scores but guide position timing</p>

        <div className="market-conditions-grid">
          <div className="condition-card">
            <h4>SPY Trend</h4>
            <p>SPY above 50-day MA = Bullish market environment</p>
            <ul>
              <li><strong>Favorable:</strong> Aggressive position sizing</li>
              <li><strong>Unfavorable:</strong> Reduce exposure, wait for confirmation</li>
            </ul>
          </div>

          <div className="condition-card">
            <h4>VIX Regime</h4>
            <p>Fear gauge - lower is better for new positions</p>
            <ul>
              <li><strong>&lt;15:</strong> Complacent (excellent)</li>
              <li><strong>15-20:</strong> Normal (good)</li>
              <li><strong>20-25:</strong> Elevated (caution)</li>
              <li><strong>25-30:</strong> Fear (reduce size)</li>
              <li><strong>&gt;30:</strong> Panic (stay out or hedge)</li>
            </ul>
          </div>

          <div className="condition-card">
            <h4>Entry Signals</h4>
            <p>Best entry points for qualified stocks</p>
            <ul>
              <li><strong>Magic Line Touch:</strong> Price at ML support - lowest risk</li>
              <li><strong>Pullback 15-25%:</strong> Buy the dip in uptrend</li>
              <li><strong>Breakout + Volume:</strong> Momentum entry on confirmation</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Grade Scale */}
      <div className="card">
        <h3>Grade Scale</h3>
        <div className="grade-scale">
          <div className="grade-item grade-a">
            <span className="grade">A+ / A / A-</span>
            <span className="range">90-100 / 85-89 / 80-84</span>
            <span className="desc">Elite Superstock candidates</span>
          </div>
          <div className="grade-item grade-b">
            <span className="grade">B+ / B / B-</span>
            <span className="range">75-79 / 70-74 / 65-69</span>
            <span className="desc">Strong candidates, minor weaknesses</span>
          </div>
          <div className="grade-item grade-c">
            <span className="grade">C+ / C / C-</span>
            <span className="range">60-64 / 55-59 / 50-54</span>
            <span className="desc">Average, needs more criteria</span>
          </div>
          <div className="grade-item grade-d">
            <span className="grade">D / F</span>
            <span className="range">40-49 / &lt;40</span>
            <span className="desc">Below threshold, not recommended</span>
          </div>
        </div>
      </div>

      {/* Data Sources */}
      <div className="card">
        <h3>Data Sources</h3>
        <ul className="data-sources">
          <li><strong>Price Data:</strong> Yahoo Finance (daily/weekly OHLCV)</li>
          <li><strong>Fundamentals:</strong> Finviz (EPS, revenue, P/E, PEG, debt ratios)</li>
          <li><strong>Float & Options:</strong> Finviz screener</li>
          <li><strong>Insider Transactions:</strong> OpenInsider (aggregated SEC Form 4)</li>
          <li><strong>Market Conditions:</strong> SPY & VIX real-time data</li>
        </ul>
      </div>
    </div>
  );
};

export default Method;
