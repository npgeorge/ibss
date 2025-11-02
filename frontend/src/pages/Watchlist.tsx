import React from 'react';

const Watchlist: React.FC = () => {
  return (
    <div className="watchlist">
      <h2>Watchlist</h2>

      <div className="card">
        <h3>My Watchlist</h3>
        <div className="watchlist-controls">
          <input type="text" placeholder="Add symbol..." />
          <button className="button">Add to Watchlist</button>
        </div>

        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Price</th>
              <th>Change %</th>
              <th>Magic Line</th>
              <th>Volume</th>
              <th>Score</th>
              <th>Patterns</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={8} style={{ textAlign: 'center', padding: '2rem' }}>
                No stocks in watchlist
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Quick Alerts</h3>
        <p>Set alerts for your watchlist stocks</p>
      </div>
    </div>
  );
};

export default Watchlist;
