/**
 * Watchlist Page
 *
 * Monitor favorite stocks and set alerts
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './Watchlist.css';

interface WatchlistStock {
  symbol: string;
  company_name: string;
  price: number;
  change_percent: number;
  magic_line_distance: number;
  volume: number;
  score: number;
  pattern?: string;
}

const Watchlist: React.FC = () => {
  const navigate = useNavigate();
  const [symbol, setSymbol] = useState<string>('');
  const [watchlist, setWatchlist] = useState<WatchlistStock[]>([]);

  const addToWatchlist = () => {
    if (!symbol.trim()) {
      alert('Please enter a stock symbol');
      return;
    }

    // In a real app, this would fetch stock data from API
    const newStock: WatchlistStock = {
      symbol: symbol.toUpperCase(),
      company_name: 'Company Name',
      price: 0,
      change_percent: 0,
      magic_line_distance: 0,
      volume: 0,
      score: 0,
    };

    setWatchlist([...watchlist, newStock]);
    setSymbol('');
  };

  const removeFromWatchlist = (sym: string) => {
    setWatchlist(watchlist.filter((stock) => stock.symbol !== sym));
  };

  const viewStock = (sym: string) => {
    navigate(`/stock/${sym}`);
  };

  return (
    <div className="watchlist">
      <div className="watchlist-header">
        <h2>Watchlist</h2>
        <p className="watchlist-subtitle">Track your favorite stocks and get alerts</p>
      </div>

      <div className="card watchlist-card">
        <div className="watchlist-controls">
          <input
            type="text"
            className="symbol-input"
            placeholder="Enter symbol (e.g., AAPL, MSFT)..."
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            onKeyPress={(e) => e.key === 'Enter' && addToWatchlist()}
          />
          <button className="btn-add" onClick={addToWatchlist}>
            + Add to Watchlist
          </button>
        </div>

        {watchlist.length === 0 ? (
          <div className="empty-state">
            <p>Your watchlist is empty.</p>
            <p className="empty-hint">Add stocks to monitor prices, Magic Line distance, and patterns.</p>
          </div>
        ) : (
          <div className="watchlist-table-container">
            <table className="watchlist-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Company</th>
                  <th>Price</th>
                  <th>Change %</th>
                  <th>ML Distance</th>
                  <th>Volume</th>
                  <th>Score</th>
                  <th>Pattern</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {watchlist.map((stock) => (
                  <tr key={stock.symbol}>
                    <td className="symbol-cell" onClick={() => viewStock(stock.symbol)}>
                      {stock.symbol}
                    </td>
                    <td className="company-cell">{stock.company_name}</td>
                    <td className="price-cell">${stock.price.toFixed(2)}</td>
                    <td className={`change-cell ${stock.change_percent >= 0 ? 'positive' : 'negative'}`}>
                      {stock.change_percent >= 0 ? '+' : ''}
                      {stock.change_percent.toFixed(2)}%
                    </td>
                    <td className={`ml-cell ${stock.magic_line_distance < 5 ? 'near' : ''}`}>
                      {stock.magic_line_distance.toFixed(1)}%
                    </td>
                    <td className="volume-cell">{stock.volume.toLocaleString()}</td>
                    <td className="score-cell">{stock.score.toFixed(0)}</td>
                    <td className="pattern-cell">{stock.pattern || '-'}</td>
                    <td className="actions-cell">
                      <button
                        className="btn-view"
                        onClick={() => viewStock(stock.symbol)}
                      >
                        View
                      </button>
                      <button
                        className="btn-remove"
                        onClick={() => removeFromWatchlist(stock.symbol)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card alerts-card">
        <h3>Alert Settings</h3>
        <p className="alerts-description">
          Get notified when stocks on your watchlist hit key levels:
        </p>
        <ul className="alerts-list">
          <li>Magic Line touches (within 2-3%)</li>
          <li>Price breakouts above resistance</li>
          <li>Volume surges (2x+ average)</li>
          <li>New insider buying activity</li>
          <li>Chart pattern formations</li>
        </ul>
        <p className="alerts-note">
          <em>Alerts feature coming soon!</em>
        </p>
      </div>
    </div>
  );
};

export default Watchlist;
