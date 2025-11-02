# IBSS Management Scripts

CLI tools for managing the IBSS Superstocks Dashboard database and operations.

## Setup

```bash
cd backend
pip install -r requirements.txt
```

## Scripts

### 1. Ingest Stock Data

Populates the database with stock data for screening.

```bash
# Ingest specific symbols
python scripts/ingest_stocks.py --symbols AAPL MSFT GOOGL AMZN

# Ingest from file
python scripts/ingest_stocks.py --file symbols.txt

# Ingest sample stocks for testing
python scripts/ingest_stocks.py --sample

# Ingest all S&P 500 stocks
python scripts/ingest_stocks.py --sp500
```

### 2. Database Management

General database management operations.

```bash
# Initialize database (create tables)
python scripts/manage.py init-db

# Show database statistics
python scripts/manage.py stats

# Run stock screening
python scripts/manage.py screen --min-score 70

# Update all stock prices
python scripts/manage.py update-prices

# Update insider transactions
python scripts/manage.py update-insider
```

## Workflow

### Initial Setup

```bash
# 1. Initialize database
python scripts/manage.py init-db

# 2. Ingest sample stocks for testing
python scripts/ingest_stocks.py --sample

# 3. Verify data
python scripts/manage.py stats

# 4. Run screening
python scripts/manage.py screen
```

### Production Setup

```bash
# 1. Initialize database
python scripts/manage.py init-db

# 2. Ingest S&P 500 stocks
python scripts/ingest_stocks.py --sp500

# 3. Update prices
python scripts/manage.py update-prices

# 4. Run screening
python scripts/manage.py screen

# 5. Schedule automated updates (see data_scheduler.py)
```

## Automated Updates

For production, use the data scheduler service:

```python
from app.services.data_scheduler import DataUpdateScheduler

scheduler = DataUpdateScheduler()
await scheduler.start()  # Runs continuously
```

This will automatically:
- Update prices daily (after market close)
- Check insider filings hourly
- Calculate technical indicators weekly

## Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker-compose ps

# Restart database
docker-compose restart postgres
```

### Rate Limiting

Yahoo Finance and SEC EDGAR have rate limits:
- Yahoo: Unofficial limits, recommended 0.5s between requests
- SEC: Max 10 requests per second

The scripts include automatic rate limiting.

### Data Quality

If you get errors during screening:
- Ensure stocks have at least 50 days of price data
- Check that symbols are valid (no delisted stocks)
- Verify market cap and price filters match your criteria

## Advanced Usage

### Custom Stock Lists

Create a `symbols.txt` file with one symbol per line:

```
AAPL
MSFT
GOOGL
# Comments supported
AMZN
TSLA
```

Then ingest:

```bash
python scripts/ingest_stocks.py --file symbols.txt
```

### Screening Parameters

Modify screening criteria in `manage.py`:

```python
criteria = ScreeningCriteria(
    price_min=0.5,
    price_max=10.0,
    volume_min=100000,
    min_total_score=70.0,
    # Add more filters...
)
```

### Batch Processing

For large datasets, process in batches:

```bash
# Split symbols into files: batch1.txt, batch2.txt, etc.
python scripts/ingest_stocks.py --file batch1.txt
python scripts/ingest_stocks.py --file batch2.txt
```

## Development

### Adding New Scripts

1. Create script in `scripts/` directory
2. Add to this README
3. Follow the pattern of existing scripts
4. Include logging and error handling

### Testing

```bash
# Test with small dataset first
python scripts/ingest_stocks.py --symbols AAPL MSFT
python scripts/manage.py screen
```
