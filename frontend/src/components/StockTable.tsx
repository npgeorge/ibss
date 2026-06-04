/**
 * Stock Table Component
 *
 * Dense, full-sub-law breakdown of screening results. Each scored law gets its
 * own column; columns are sortable and each numeric column has a "min" filter
 * so you can isolate stocks that are strongest on a given law.
 */
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ScreeningResult } from '../types/api';
import './StockTable.css';

interface StockTableProps {
  results: ScreeningResult[];
}

type ColType = 'score' | 'num' | 'text';

interface ColumnDef {
  key: string;
  label: string;
  group: string;
  type: ColType;
  // Numeric value used for sorting/filtering (null when not computed).
  value: (r: ScreeningResult) => number | null;
  // Rendered cell content.
  render: (r: ScreeningResult) => React.ReactNode;
}

const law = (r: ScreeningResult, key: string): number | null => {
  const v = r.law_scores?.[key];
  return typeof v === 'number' ? v : null;
};

const scoreCell = (v: number | null): React.ReactNode => {
  if (v == null) return <span className="st-na">–</span>;
  return <span className={`st-score ${scoreTone(v)}`}>{v.toFixed(0)}</span>;
};

const scoreTone = (v: number): string => {
  if (v >= 70) return 'tone-strong';
  if (v >= 40) return 'tone-mid';
  if (v > 0) return 'tone-weak';
  return 'tone-zero';
};

const COLUMNS: ColumnDef[] = [
  // Composite
  {
    key: 'total_score',
    label: 'Total',
    group: 'Composite',
    type: 'score',
    value: (r) => r.score.total_score,
    render: (r) => scoreCell(r.score.total_score),
  },
  {
    key: 'recommendation',
    label: 'Rec',
    group: 'Composite',
    type: 'text',
    value: () => null,
    render: (r) => (
      <span className={`st-rec ${recTone(r.recommendation)}`}>
        {r.recommendation.replace(/_/g, ' ').toUpperCase()}
      </span>
    ),
  },
  { key: 'technical_score', label: 'Tech', group: 'Category', type: 'score', value: (r) => r.score.technical_score, render: (r) => scoreCell(r.score.technical_score) },
  { key: 'fundamental_score', label: 'Fund', group: 'Category', type: 'score', value: (r) => r.score.fundamental_score, render: (r) => scoreCell(r.score.fundamental_score) },
  { key: 'insider_score', label: 'Insdr', group: 'Category', type: 'score', value: (r) => r.score.insider_score, render: (r) => scoreCell(r.score.insider_score) },
  { key: 'pattern_score', label: 'Patt', group: 'Category', type: 'score', value: (r) => r.score.pattern_score, render: (r) => scoreCell(r.score.pattern_score) },

  // Technical sub-laws
  { key: 'magic_line', label: 'Magic Ln', group: 'Technical', type: 'score', value: (r) => law(r, 'magic_line'), render: (r) => scoreCell(law(r, 'magic_line')) },
  { key: 'volume', label: 'Volume', group: 'Technical', type: 'score', value: (r) => law(r, 'volume'), render: (r) => scoreCell(law(r, 'volume')) },
  { key: 'patterns', label: 'Patterns', group: 'Technical', type: 'score', value: (r) => law(r, 'patterns'), render: (r) => scoreCell(law(r, 'patterns')) },
  { key: 'relative_strength', label: 'Rel Str', group: 'Technical', type: 'score', value: (r) => law(r, 'relative_strength'), render: (r) => scoreCell(law(r, 'relative_strength')) },

  // Fundamental sub-laws
  { key: 'earnings_growth', label: 'Earnings', group: 'Fundamental', type: 'score', value: (r) => law(r, 'earnings_growth'), render: (r) => scoreCell(law(r, 'earnings_growth')) },
  { key: 'revenue_growth', label: 'Revenue', group: 'Fundamental', type: 'score', value: (r) => law(r, 'revenue_growth'), render: (r) => scoreCell(law(r, 'revenue_growth')) },
  { key: 'valuation', label: 'Value', group: 'Fundamental', type: 'score', value: (r) => law(r, 'valuation'), render: (r) => scoreCell(law(r, 'valuation')) },
  { key: 'share_structure', label: 'Float', group: 'Fundamental', type: 'score', value: (r) => law(r, 'share_structure'), render: (r) => scoreCell(law(r, 'share_structure')) },
  { key: 'balance_sheet', label: 'Balance', group: 'Fundamental', type: 'score', value: (r) => law(r, 'balance_sheet'), render: (r) => scoreCell(law(r, 'balance_sheet')) },
  { key: 'analyst_coverage', label: 'Coverage', group: 'Fundamental', type: 'score', value: (r) => law(r, 'analyst_coverage'), render: (r) => scoreCell(law(r, 'analyst_coverage')) },
  { key: 'earnings_acceleration', label: 'Accel', group: 'Fundamental', type: 'score', value: (r) => law(r, 'earnings_acceleration'), render: (r) => scoreCell(law(r, 'earnings_acceleration')) },

  // Insider sub-laws
  { key: 'recent_buying', label: 'Recent Buy', group: 'Insider', type: 'score', value: (r) => law(r, 'recent_buying'), render: (r) => scoreCell(law(r, 'recent_buying')) },
  { key: 'cluster_buying', label: 'Cluster', group: 'Insider', type: 'score', value: (r) => law(r, 'cluster_buying'), render: (r) => scoreCell(law(r, 'cluster_buying')) },
  { key: 'price_trend', label: 'Px Trend', group: 'Insider', type: 'score', value: (r) => law(r, 'price_trend'), render: (r) => scoreCell(law(r, 'price_trend')) },

  // Context
  {
    key: 'price',
    label: 'Price',
    group: 'Context',
    type: 'num',
    value: (r) => r.stock.current_price ?? null,
    render: (r) => (r.stock.current_price != null ? <span className="st-num">${r.stock.current_price.toFixed(2)}</span> : <span className="st-na">–</span>),
  },
  {
    key: 'magic_line_distance',
    label: 'ML Dist %',
    group: 'Context',
    type: 'num',
    value: (r) => r.magic_line_distance ?? null,
    render: (r) => <span className="st-num">{r.magic_line_distance.toFixed(1)}</span>,
  },
];

const recTone = (rec: string): string => {
  const r = rec.toUpperCase();
  if (r.includes('STRONG')) return 'strong-buy';
  if (r.includes('BUY')) return 'buy';
  if (r.includes('SELL') || r.includes('AVOID')) return 'sell';
  return 'hold';
};

const StockTable: React.FC<StockTableProps> = ({ results }) => {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<string>('total_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [filters, setFilters] = useState<Record<string, number>>({});

  const colByKey = useMemo(() => {
    const m: Record<string, ColumnDef> = {};
    COLUMNS.forEach((c) => (m[c.key] = c));
    return m;
  }, []);

  const groups = useMemo(() => {
    const order: string[] = [];
    const counts: Record<string, number> = {};
    COLUMNS.forEach((c) => {
      if (!(c.group in counts)) {
        counts[c.group] = 0;
        order.push(c.group);
      }
      counts[c.group] += 1;
    });
    return order.map((g) => ({ group: g, span: counts[g] }));
  }, []);

  const visible = useMemo(() => {
    const activeFilters = Object.entries(filters).filter(([, v]) => !Number.isNaN(v));

    const filtered = results.filter((r) =>
      activeFilters.every(([key, min]) => {
        const v = colByKey[key]?.value(r);
        return v != null && v >= min;
      })
    );

    const col = colByKey[sortKey];
    if (!col) return filtered;

    const sorted = [...filtered].sort((a, b) => {
      const av = col.value(a);
      const bv = col.value(b);
      // nulls always sink to the bottom regardless of direction
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return sortDir === 'asc' ? av - bv : bv - av;
    });
    return sorted;
  }, [results, filters, sortKey, sortDir, colByKey]);

  const onSort = (key: string) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const onFilterChange = (key: string, raw: string) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (raw.trim() === '') {
        delete next[key];
      } else {
        next[key] = parseFloat(raw);
      }
      return next;
    });
  };

  const activeFilterCount = Object.keys(filters).length;

  return (
    <div className="stock-table-wrap">
      <div className="st-toolbar">
        <span className="te-label">
          {visible.length} of {results.length} shown
        </span>
        {activeFilterCount > 0 && (
          <button className="st-clear" onClick={() => setFilters({})}>
            Clear {activeFilterCount} filter{activeFilterCount > 1 ? 's' : ''}
          </button>
        )}
      </div>

      <div className="st-scroll">
        <table className="stock-table">
          <thead>
            <tr className="st-grouprow">
              <th className="st-sticky st-corner" rowSpan={3} onClick={() => onSort('total_score')}>
                Symbol
              </th>
              {groups.map((g) => (
                <th key={g.group} colSpan={g.span} className="st-group">
                  {g.group}
                </th>
              ))}
            </tr>
            <tr className="st-headrow">
              {COLUMNS.map((c) => {
                const isSorted = c.key === sortKey;
                return (
                  <th
                    key={c.key}
                    className={`st-col ${isSorted ? 'is-sorted' : ''}`}
                    onClick={() => onSort(c.key)}
                  >
                    {c.label}
                    <span className="st-arrow">{isSorted ? (sortDir === 'asc' ? '▲' : '▼') : ''}</span>
                  </th>
                );
              })}
            </tr>
            <tr className="st-filterrow">
              {COLUMNS.map((c) => (
                <th key={c.key} className="st-filtercell">
                  {c.type !== 'text' ? (
                    <input
                      type="number"
                      className="st-filter-input"
                      placeholder="min"
                      value={filters[c.key] ?? ''}
                      onChange={(e) => onFilterChange(c.key, e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={r.stock.symbol} onClick={() => navigate(`/stock/${r.stock.symbol}`)}>
                <th className="st-sticky st-symcell">
                  <span className="st-sym">{r.stock.symbol}</span>
                  <span className="st-name">{r.stock.company_name}</span>
                </th>
                {COLUMNS.map((c) => (
                  <td key={c.key} className={`st-cell type-${c.type}`}>
                    {c.render(r)}
                  </td>
                ))}
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td className="st-empty" colSpan={COLUMNS.length + 1}>
                  No stocks match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default StockTable;
