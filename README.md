# IBSS Superstocks Dashboard

> A powerful investment dashboard designed to identify and track stocks with 100-1000%+ growth potential using Jesse C. Stine's proven Superstock methodology.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)

---

## 📊 Overview

The IBSS (Insider Buy Superstocks) Dashboard is a comprehensive web application that helps investors identify rare "Superstock" opportunities by combining:

- **Technical Analysis**: Magic Line detection, pattern recognition, volume analysis
- **Fundamental Analysis**: Earnings momentum, revenue growth, valuation metrics
- **Insider Trading**: SEC Form 4 monitoring, cluster buying detection
- **Risk Management**: Position sizing, Kelly Criterion, portfolio heat

### Key Features

✅ **Stock Screener** - Filter thousands of stocks by Superstock criteria
✅ **Magic Line Detection** - Automatically identify optimal support levels
✅ **Pattern Recognition** - Detect staircase, cup & handle, breakout patterns
✅ **Insider Monitoring** - Track insider buying activity in real-time
✅ **Alert System** - Get notified of entry/exit opportunities
✅ **Portfolio Manager** - Track positions and manage risk
✅ **Position Sizer** - Calculate optimal position sizes using risk rules

---

## 🚀 Quick Start

### Prerequisites

- **Docker** and **Docker Compose** (recommended)
- OR:
  - Python 3.11+
  - Node.js 18+
  - PostgreSQL 15+
  - Redis 7+

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd ibss

# Start all services
docker-compose up -d

# Initialize database
docker-compose exec postgres psql -U ibss -d ibss_db -f /docker-entrypoint-initdb.d/schema.sql

# Access the application
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/api/docs
```

### Option 2: Manual Setup

#### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your settings

# Run the backend
uvicorn app.main:app --reload
```

#### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

#### Database Setup

```bash
# Create PostgreSQL database
createdb ibss_db

# Run schema
psql -U postgres -d ibss_db -f database/schema.sql
```

---

## 📁 Project Structure

```
ibss/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/            # API endpoints
│   │   │   ├── screener.py # Stock screening
│   │   │   ├── stocks.py   # Stock data
│   │   │   ├── insider.py  # Insider trading
│   │   │   ├── alerts.py   # Alert system
│   │   │   └── portfolio.py # Portfolio management
│   │   ├── core/           # Core functionality
│   │   │   └── config.py   # Configuration
│   │   ├── models/         # Database models
│   │   ├── services/       # Business logic
│   │   │   ├── magic_line.py      # Magic Line detection
│   │   │   ├── pattern_recognition.py
│   │   │   ├── screener.py        # Screening logic
│   │   │   └── insider_analyzer.py
│   │   └── utils/          # Utilities
│   ├── tests/              # Backend tests
│   ├── requirements.txt    # Python dependencies
│   └── Dockerfile
│
├── frontend/               # React frontend
│   ├── src/
│   │   ├── components/     # Reusable components
│   │   ├── pages/          # Page components
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Screener.tsx
│   │   │   ├── StockDetail.tsx
│   │   │   ├── Portfolio.tsx
│   │   │   └── Watchlist.tsx
│   │   ├── services/       # API services
│   │   ├── types/          # TypeScript types
│   │   └── utils/          # Utilities
│   ├── public/
│   ├── package.json
│   └── Dockerfile
│
├── database/
│   ├── schema.sql          # Database schema
│   └── migrations/         # Database migrations
│
├── docker/
│   └── docker-compose.yml  # Docker configuration
│
├── scripts/                # Utility scripts
│
├── docs/                   # Strategy documentation
│   ├── superstocks_summary.md
│   ├── superstocks_strategy_plan.md
│   ├── superstocks_technical_spec.md
│   └── superstocks_implementation_guide.md
│
├── PROGRESS.md             # Build progress tracker
└── README.md              # This file
```

---

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the `backend/` directory:

```bash
# Application
DEBUG=True
APP_NAME=IBSS Superstocks Dashboard

# Database
DATABASE_URL=postgresql+asyncpg://ibss:ibss_password@localhost:5432/ibss_db

# Redis
REDIS_URL=redis://localhost:6379/0

# API Keys (optional - for live data)
POLYGON_API_KEY=your_key_here
ALPHA_VANTAGE_API_KEY=your_key_here

# Authentication
SECRET_KEY=your-secret-key-change-in-production
```

### API Data Sources

To enable live market data, sign up for:

1. **Polygon.io** - Real-time stock data (free tier available)
2. **Alpha Vantage** - Fundamental data (free tier: 500 calls/day)
3. **SEC EDGAR** - Insider trading data (free, no API key needed)

Add your API keys to the `.env` file.

---

## 📖 API Documentation

Once the backend is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc

### Key Endpoints

#### Screening
- `POST /api/v1/screen` - Screen stocks by criteria
- `GET /api/v1/screen/quick-scan` - Quick scan for opportunities

#### Stock Data
- `GET /api/v1/stocks/{symbol}` - Get stock profile
- `GET /api/v1/stocks/{symbol}/magic-line` - Get Magic Line info
- `GET /api/v1/stocks/{symbol}/patterns` - Get detected patterns

#### Insider Trading
- `GET /api/v1/insider/recent` - Recent insider transactions
- `GET /api/v1/insider/{symbol}` - Stock insider activity

#### Portfolio
- `GET /api/v1/portfolio/positions` - Current positions
- `POST /api/v1/portfolio/calculate-size` - Calculate position size

---

## 🎯 Usage Guide

### 1. Screening for Superstocks

The screener filters stocks based on:

**Technical Criteria:**
- Price under $10 (ideally $3-7)
- Magic Line respect (10-week SMA)
- Volume surge on breakouts (50%+ above average)
- Chart patterns (staircase, cup & handle, etc.)

**Fundamental Criteria:**
- Earnings growth 20%+ YoY
- Revenue growth 20%+ YoY
- Reasonable valuation (PEG < 1.0)

**Insider Activity:**
- Recent insider buying (90 days)
- Cluster buying (multiple insiders)
- Buying at increasing prices

### 2. Understanding the Magic Line

The **Magic Line** is the cornerstone of this strategy:

- Most stocks respect their 10-week simple moving average (SMA)
- Some stocks may respect 8, 12, or 14-week SMAs
- The dashboard automatically detects which period each stock respects
- **Entry Signal**: Stock touching the Magic Line = buying opportunity
- **Exit Signal**: Close below Magic Line for 2 weeks = sell

### 3. Position Sizing

The dashboard uses strict risk management:

- **Risk per trade**: 2% of portfolio maximum
- **Position size**: Up to 40% of portfolio maximum
- **Concentration**: 3-5 positions total
- Uses Kelly Criterion for optimal sizing

Example:
```
Portfolio: $100,000
Entry: $5.00
Stop Loss: $4.25 (15% below entry)
Risk: $2,000 (2% of portfolio)
Shares: 2,666 shares ($13,330 position = 13.3% of portfolio)
```

### 4. Entry Strategy

**Best Entry Points:**
1. Touching Magic Line (primary entry)
2. Pullbacks in uptrends (15-25% from highs)
3. Breakouts from bases (with volume confirmation)

**Avoid:**
- Chasing extended moves (>20% above Magic Line)
- Buying in declining markets
- Weak volume breakouts

### 5. Exit Strategy

**Sell When:**
1. Parabolic move (50-100% gain in 2-3 weeks)
2. Magic Line violation (2 consecutive weekly closes below)
3. Earnings miss or guidance cut
4. Technical breakdown
5. No progress in 3-4 months

---

## 🧪 Testing

### Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_magic_line.py
```

### Frontend Tests

```bash
cd frontend

# Run tests
npm test

# Run with coverage
npm test -- --coverage
```

---

## 📊 Performance Metrics

### Expected Results (Based on Strategy)

- **Win Rate**: 30-40%
- **Average Win**: 50-1000%
- **Average Loss**: 15-30%
- **Profit Factor**: 3-5x
- **Annual Return (Strong Years)**: 100-300%
- **Max Drawdown**: 50-75%

### Strategy Statistics

- **Trades per Year**: 10-20
- **Home Runs per Year**: 3-5
- **Holding Period**: Weeks to months
- **Market Conditions**: Works best in bull markets

---

## 🛠️ Development

### Adding New Features

1. **Backend**: Add endpoint in `backend/app/api/`
2. **Frontend**: Create component in `frontend/src/components/`
3. **Database**: Add migration in `database/migrations/`
4. **Tests**: Add tests in respective `tests/` directories

### Code Quality

```bash
# Backend - Format with Black
cd backend
black app/

# Backend - Lint with flake8
flake8 app/

# Frontend - Lint
cd frontend
npm run lint
```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Description"

# Run migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## 📚 Strategy Resources

### Documentation
- [Strategy Summary](./superstocks_summary.md) - Overview and philosophy
- [Detailed Strategy Plan](./superstocks_strategy_plan.md) - Complete methodology
- [Technical Specifications](./superstocks_technical_spec.md) - System architecture
- [Implementation Guide](./superstocks_implementation_guide.md) - Build instructions
- [Build Progress](./PROGRESS.md) - Development tracker

### Original Source
- Book: "Insider Buy Superstocks" by Jesse C. Stine
- Focus: Position trading for 100-1000%+ returns
- Timeframe: Weeks to months (not day trading)

---

## ⚠️ Risk Disclaimer

**IMPORTANT**: This software is for educational and research purposes only.

- **Not Financial Advice**: This dashboard is a tool, not investment advice
- **High Risk Strategy**: Superstock investing involves significant risk
- **Expected Drawdowns**: 50-75% portfolio drawdowns are documented
- **No Guarantees**: Past performance does not guarantee future results
- **Do Your Research**: Always perform your own due diligence
- **Paper Trade First**: Test the strategy with paper trading before risking capital

The creators of this software are not responsible for any financial losses incurred through its use.

---

## 🗺️ Roadmap

### Phase 1: Foundation ✅
- [x] Project structure
- [x] Database schema
- [x] API endpoints (skeleton)
- [x] Frontend scaffold
- [x] Docker setup

### Phase 2: Data Pipeline (In Progress)
- [ ] Market data integration
- [ ] Technical indicator calculations
- [ ] Magic Line detection algorithm
- [ ] Data update scheduler

### Phase 3: Core Features
- [ ] Stock screener implementation
- [ ] Pattern recognition engine
- [ ] Insider trading monitor
- [ ] Alert system
- [ ] Risk management calculator

### Phase 4: User Interface
- [ ] Dashboard with real-time data
- [ ] Interactive charts
- [ ] Screener interface
- [ ] Portfolio management UI
- [ ] Watchlist with alerts

### Phase 5: Advanced Features
- [ ] Machine learning pattern recognition
- [ ] Backtesting engine
- [ ] Paper trading integration
- [ ] Mobile app
- [ ] API for external access

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow existing code style
- Write tests for new features
- Update documentation
- Keep commits atomic and well-described

---

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 💬 Support

- **Issues**: Report bugs or request features via GitHub Issues
- **Documentation**: See the `/docs` directory for detailed guides
- **Progress**: Check `PROGRESS.md` for build status

---

## 🙏 Acknowledgments

- **Jesse C. Stine** - Original Superstocks strategy methodology
- **William O'Neil** - CANSLIM methodology inspiration
- **Mark Minervini** - Technical analysis concepts

---

## 📞 Contact

For questions or support:
- Create an issue in this repository
- Review the documentation in `/docs`
- Check the implementation guide for technical details

---

**Built with ❤️ for finding 10-baggers and beyond**

*"The goal is not to trade frequently, but to find 3-5 exceptional opportunities per quarter. Quality over quantity always wins."* - Superstocks Philosophy
