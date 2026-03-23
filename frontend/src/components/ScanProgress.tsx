/**
 * ScanProgress Component
 *
 * Displays real-time progress during stock screening with streaming updates.
 */
import React from 'react';
import './ScanProgress.css';

export interface ScanProgressData {
  status: string;
  current: number;
  total: number;
  currentSymbol: string;
  percentComplete: number;
  resultsFound: number;
  phase: 'idle' | 'starting' | 'prefilter' | 'scanning' | 'complete' | 'error';
  errorMessage?: string;
  scanTimeMs?: number;
}

interface ScanProgressProps {
  progress: ScanProgressData;
  onCancel?: () => void;
}

const ScanProgress: React.FC<ScanProgressProps> = ({ progress, onCancel }) => {
  const getPhaseLabel = () => {
    switch (progress.phase) {
      case 'idle':
        return 'Ready to scan';
      case 'starting':
        return 'Initializing...';
      case 'prefilter':
        return 'Pre-filtering universe...';
      case 'scanning':
        return `Scanning ${progress.currentSymbol}`;
      case 'complete':
        return 'Scan complete!';
      case 'error':
        return 'Scan failed';
      default:
        return 'Processing...';
    }
  };

  const getProgressColor = () => {
    if (progress.phase === 'error') return '#ef4444';
    if (progress.phase === 'complete') return '#22c55e';
    return '#3b82f6';
  };

  if (progress.phase === 'idle') {
    return null;
  }

  return (
    <div className="scan-progress">
      <div className="scan-progress-header">
        <span className="scan-progress-label">{getPhaseLabel()}</span>
        {progress.phase === 'scanning' && onCancel && (
          <button className="scan-cancel-btn" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>

      {/* Progress bar */}
      <div className="scan-progress-bar-container">
        <div
          className="scan-progress-bar"
          style={{
            width: `${progress.percentComplete}%`,
            backgroundColor: getProgressColor(),
          }}
        />
      </div>

      {/* Stats */}
      <div className="scan-progress-stats">
        {progress.phase === 'scanning' && (
          <>
            <span className="scan-stat">
              <strong>{progress.current}</strong> / {progress.total} stocks
            </span>
            <span className="scan-stat">
              <strong>{progress.resultsFound}</strong> matches found
            </span>
            <span className="scan-stat">
              {progress.percentComplete.toFixed(0)}%
            </span>
          </>
        )}

        {progress.phase === 'complete' && (
          <>
            <span className="scan-stat">
              Scanned <strong>{progress.total}</strong> stocks
            </span>
            <span className="scan-stat">
              Found <strong>{progress.resultsFound}</strong> matches
            </span>
            {progress.scanTimeMs && (
              <span className="scan-stat">
                in <strong>{(progress.scanTimeMs / 1000).toFixed(1)}s</strong>
              </span>
            )}
          </>
        )}

        {progress.phase === 'error' && progress.errorMessage && (
          <span className="scan-error">{progress.errorMessage}</span>
        )}
      </div>

      {/* Status message */}
      {progress.status && progress.phase !== 'scanning' && (
        <div className="scan-status-message">{progress.status}</div>
      )}
    </div>
  );
};

export default ScanProgress;
