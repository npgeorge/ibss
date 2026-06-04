import React from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import './App.css';

import Dashboard from './pages/Dashboard';
import Screener from './pages/Screener';
import StockDetail from './pages/StockDetail';
import Portfolio from './pages/Portfolio';
import Watchlist from './pages/Watchlist';
import Method from './pages/Method';

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/screener', label: 'Screener', end: false },
  { to: '/portfolio', label: 'Portfolio', end: false },
  { to: '/watchlist', label: 'Watchlist', end: false },
  { to: '/method', label: 'Method', end: false },
];

function App() {
  return (
    <Router>
      <div className="App">
        <header className="te-topbar">
          <div className="te-brand">
            <span className="te-brand-mark">IBSS</span>
            <span className="te-brand-sub te-label">Superstocks // Terminal</span>
          </div>

          <nav className="te-nav">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `te-tab${isActive ? ' is-active' : ''}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="te-status">
            <span className="te-led" aria-hidden="true" />
            <span className="te-label">Live</span>
          </div>
        </header>

        <main className="te-main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/screener" element={<Screener />} />
            <Route path="/stock/:symbol" element={<StockDetail />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/method" element={<Method />} />
          </Routes>
        </main>

        <footer className="te-footer">
          <span className="te-label">IBSS Superstocks Dashboard</span>
          <span className="te-label te-footer-ver">v1.0.0</span>
        </footer>
      </div>
    </Router>
  );
}

export default App;
