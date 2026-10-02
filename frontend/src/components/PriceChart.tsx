/**
 * Price Chart
 *
 * IBD-style bar chart: high-low bars with a close tick, coloured by the change
 * from the prior close, over volume bars and moving averages, on a log price
 * scale. Daily / weekly / monthly views. `compact` is the in-tile version shown
 * on dashboard cards.
 */
import React, { useEffect, useRef, useState } from 'react';
import { ColorType, CrosshairMode, PriceScaleMode, Time, createChart } from 'lightweight-charts';
import { apiClient } from '../services/api';
import { ChartInterval, ChartLine, StockChart } from '../types/api';
import './PriceChart.css';

interface PriceChartProps {
  symbol: string;
  compact?: boolean;
}

const INTERVALS: { value: ChartInterval; label: string; short: string }[] = [
  { value: 'daily', label: 'Daily', short: 'D' },
  { value: 'weekly', label: 'Weekly', short: 'W' },
  { value: 'monthly', label: 'Monthly', short: 'M' },
];

// Bars in view when a chart opens; older ones are reachable by scrolling back.
const INITIAL_BARS: Record<ChartInterval, number> = { daily: 190, weekly: 156, monthly: 120 };
const COMPACT_INITIAL_BARS: Record<ChartInterval, number> = { daily: 90, weekly: 78, monthly: 60 };

// Design tokens (index.css) each line is drawn in; the canvas can't read CSS variables.
const LINE_TOKENS: Record<ChartLine['key'], string> = {
  fast_average: '--amber',
  slow_average: '--ink-dim',
  magic_line: '--lime',
  volume_average: '--info',
};

const token = (name: string): string =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim().replace(/\s+/g, ' ');

const withAlpha = (hex: string, alpha: number): string => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};

const formatVolume = (volume: number): string => {
  if (volume >= 1e9) return `${(volume / 1e9).toFixed(2)}B`;
  if (volume >= 1e6) return `${(volume / 1e6).toFixed(2)}M`;
  if (volume >= 1e3) return `${(volume / 1e3).toFixed(0)}K`;
  return String(volume);
};

const PriceChart: React.FC<PriceChartProps> = ({ symbol, compact = false }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [interval, setChartInterval] = useState<ChartInterval>('daily');
  const [chart, setChart] = useState<StockChart | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiClient
      .getStockChart(symbol, interval)
      .then((data) => {
        if (cancelled) return;
        setChart(data);
        setHoverIndex(null);
      })
      .catch((err: any) => {
        if (cancelled) return;
        console.error('Error loading chart:', err);
        setError(err.response?.data?.detail || 'Chart unavailable');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, interval]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !chart || chart.bars.length === 0) return;

    const up = token('--up');
    const down = token('--down');
    const line = token('--line');

    const api = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: token('--panel') },
        textColor: token('--ink-faint'),
        fontFamily: token('--font-mono'),
        fontSize: compact ? 9 : 11,
      },
      grid: {
        vertLines: { color: withAlpha(line, 0.5) },
        horzLines: { color: line },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        mode: PriceScaleMode.Logarithmic,
        borderColor: line,
        // Leave the bottom of the pane to the volume bars.
        scaleMargins: { top: 0.06, bottom: 0.26 },
      },
      timeScale: { borderColor: line, rightOffset: 2 },
    });

    const barColor = (i: number): string =>
      i > 0 && chart.bars[i].close < chart.bars[i - 1].close ? down : up;

    const priceSeries = api.addBarSeries({
      openVisible: false,
      thinBars: false,
      upColor: up,
      downColor: down,
      priceLineVisible: false,
    });
    priceSeries.setData(
      chart.bars.map((bar, i) => ({
        time: bar.time as Time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        color: barColor(i),
      }))
    );

    const volumeSeries = api.addHistogramSeries({
      priceScaleId: 'volume',
      priceFormat: { type: 'volume' },
      priceLineVisible: false,
      lastValueVisible: false,
    });
    volumeSeries.setData(
      chart.bars.map((bar, i) => ({
        time: bar.time as Time,
        value: bar.volume,
        color: withAlpha(barColor(i), 0.55),
      }))
    );
    api.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const addLine = (source: ChartLine, onVolumeScale: boolean) => {
      const series = api.addLineSeries({
        color: token(LINE_TOKENS[source.key]),
        lineWidth: source.key === 'magic_line' ? 2 : 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
        ...(onVolumeScale ? { priceScaleId: 'volume' } : {}),
      });
      series.setData(source.points.map((p) => ({ time: p.time as Time, value: p.value })));
    };
    chart.lines.forEach((source) => addLine(source, false));
    if (chart.volume_average) addLine(chart.volume_average, true);

    const total = chart.bars.length;
    const initial = (compact ? COMPACT_INITIAL_BARS : INITIAL_BARS)[chart.interval];
    if (total > initial) {
      api.timeScale().setVisibleLogicalRange({ from: total - initial, to: total + 1 });
    } else {
      api.timeScale().fitContent();
    }

    api.subscribeCrosshairMove((param) => {
      const index = param.logical;
      setHoverIndex(index !== undefined && index >= 0 && index < total ? index : null);
    });

    return () => api.remove();
  }, [chart, compact]);

  const bars = chart?.bars ?? [];
  const shownIndex = hoverIndex ?? bars.length - 1;
  const shown = bars[shownIndex];
  const prior = bars[shownIndex - 1];
  const change = shown && prior ? ((shown.close - prior.close) / prior.close) * 100 : null;
  const keys = chart ? [...chart.lines, ...(chart.volume_average ? [chart.volume_average] : [])] : [];

  return (
    <div className={`price-chart ${compact ? 'compact' : ''}`}>
      <div className="price-chart-header">
        <div className="price-chart-readout te-num">
          {shown && (
            <>
              <span className="readout-date">{shown.time}</span>
              {!compact && (
                <>
                  <span><i>H</i>{shown.high.toFixed(2)}</span>
                  <span><i>L</i>{shown.low.toFixed(2)}</span>
                </>
              )}
              <span><i>C</i>{shown.close.toFixed(2)}</span>
              {change !== null && (
                <span className={change >= 0 ? 'up' : 'down'}>
                  {change >= 0 ? '+' : ''}
                  {change.toFixed(2)}%
                </span>
              )}
              {!compact && <span><i>Vol</i>{formatVolume(shown.volume)}</span>}
            </>
          )}
        </div>
        <div className="price-chart-intervals" role="group" aria-label="Chart interval">
          {INTERVALS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={option.value === interval ? 'active' : ''}
              aria-pressed={option.value === interval}
              aria-label={option.label}
              onClick={() => setChartInterval(option.value)}
            >
              {compact ? option.short : option.label}
            </button>
          ))}
        </div>
      </div>

      {!compact && keys.length > 0 && (
        <div className="price-chart-keys">
          {keys.map((source) => (
            <span key={source.key} className="price-chart-key">
              <span className={`key-swatch ${source.key}`} aria-hidden="true" />
              {source.label}
            </span>
          ))}
        </div>
      )}

      <div className="price-chart-stage">
        <div ref={containerRef} className="price-chart-canvas" />
        {(loading || error) && (
          <div className="price-chart-status">{error || 'Loading chart…'}</div>
        )}
      </div>

      {!compact && chart?.source === 'database' && (
        <p className="price-chart-note">
          Live history unavailable — showing the prices stored by the last scan.
        </p>
      )}
    </div>
  );
};

export default PriceChart;
