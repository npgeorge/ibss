import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './App.css';

// Pages (to be created)
import Dashboard from './pages/Dashboard';
import Screener from './pages/Screener';
import StockDetail from './pages/StockDetail';
import Portfolio from './pages/Portfolio';
import Watchlist from './pages/Watchlist';

function App() {
  return (
    <Router>
      <div className="App">
        <header className="App-header">
          <h1>IBSS Superstocks Dashboard</h1>
          <nav>
            <a href="/">Dashboard</a>
            <a href="/screener">Screener</a>
            <a href="/portfolio">Portfolio</a>
            <a href="/watchlist">Watchlist</a>
          </nav>
        </header>

        <main>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/screener" element={<Screener />} />
            <Route path="/stock/:symbol" element={<StockDetail />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/watchlist" element={<Watchlist />} />
          </Routes>
        </main>

        <footer>
          <p>IBSS Superstocks Dashboard v1.0.0</p>
        </footer>
      </div>
    </Router>
  );
}

export default App;
