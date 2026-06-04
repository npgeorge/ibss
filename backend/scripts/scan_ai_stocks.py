"""
Discrete AI-stock scan.

Scores a fixed list of AI / AI-adjacent tickers (Nebius, Ouster, and peers)
with the Superstock scorer, bypassing the Finviz universe pre-filter and the
low-priced-superstock price gate so high-priced names are not silently
dropped. Prints per-stock scores and the group averages.

Usage:
    python scripts/scan_ai_stocks.py
    python scripts/scan_ai_stocks.py --symbols NBIS OUST SOUN
    python scripts/scan_ai_stocks.py --no-insider   # skip OpenInsider fetch
"""
import asyncio
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from app.services.screener import ScreeningCriteria, SuperstockScreener
from app.services.market_data import YahooFinanceCollector
from app.services.finviz_screener import FinvizDetailFetcher
from app.services.openinsider import OpenInsiderScraper
from app.api.screener import AI_SECTOR_SYMBOLS as DEFAULT_SYMBOLS

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def _relaxed_criteria() -> ScreeningCriteria:
    """Open the gates so price/market-cap never filters a name out."""
    return ScreeningCriteria(
        price_min=0.01,
        price_max=1_000_000.0,
        volume_min=0,
        market_cap_min=None,
        market_cap_max=None,
        min_total_score=0.0,
        insider_buying_days=90,
    )


async def main(symbols, fetch_insider: bool):
    criteria = _relaxed_criteria()
    screener = SuperstockScreener(criteria)

    print(f"\nDiscrete AI scan: {len(symbols)} symbols")
    print("=" * 78)

    # --- Finviz fundamentals (one quote per symbol) ---
    print("Fetching Finviz fundamentals...")
    finviz_metrics = await FinvizDetailFetcher().fetch_stock_details(symbols)

    # --- Price data + SPY benchmark ---
    print("Fetching price data (1y)...")
    price_data_map = YahooFinanceCollector.batch_fetch_historical_data(symbols, period="1y")
    benchmark_data = None
    try:
        benchmark_data = YahooFinanceCollector.batch_fetch_historical_data(
            ["SPY"], period="1y"
        ).get("SPY")
    except Exception as e:
        logger.warning(f"SPY benchmark fetch failed: {e}")

    # --- Insider data (optional, best effort) ---
    insider_by_symbol = {}
    if fetch_insider:
        print("Fetching insider purchases (best effort)...")
        try:
            async with OpenInsiderScraper() as scraper:
                all_purchases = await scraper.fetch_all_recent_purchases(
                    days=criteria.insider_buying_days,
                    price_min=0.5,
                    price_max=1_000_000.0,
                )
                wanted = set(symbols)
                for sym, txns in all_purchases.items():
                    if sym in wanted:
                        insider_by_symbol[sym] = scraper._summarize_activity(sym, txns)
        except Exception as e:
            logger.warning(f"OpenInsider fetch failed: {e}")

    # --- Score each ---
    results = []
    for sym in symbols:
        pdf = price_data_map.get(sym)
        if pdf is None or pdf.empty or len(pdf) < 50:
            print(f"  {sym:6s} - skipped (insufficient price data)")
            continue

        fm = finviz_metrics.get(sym)
        stock_info = {
            "symbol": sym,
            "company_name": fm.company if fm else sym,
            "sector": fm.sector if fm else "Unknown",
            "market_cap": int(fm.market_cap) if fm and fm.market_cap else 0,
        }
        fundamentals = None
        if fm:
            fundamentals = {
                "eps_growth_yoy": fm.eps_growth_yoy or 0,
                "revenue_growth_yoy": fm.revenue_growth_yoy or 0,
                "peg_ratio": fm.peg_ratio,
                "pe_ratio": fm.pe_ratio,
                "float_shares": fm.float_shares,
                "debt_to_equity": fm.debt_to_equity,
                "current_ratio": fm.current_ratio,
                "analyst_count": fm.analyst_count,
                "eps_growth_next_y": fm.eps_growth_next_y,
            }

        try:
            score = screener.screen_stock(
                pdf, stock_info, fundamentals, insider_by_symbol.get(sym), benchmark_data
            )
        except Exception as e:
            print(f"  {sym:6s} - scoring error: {e}")
            continue

        if score is None:
            print(f"  {sym:6s} - no score returned")
            continue

        price = float(pdf.iloc[-1]["close"])
        results.append((sym, price, score))

    if not results:
        print("\nNo scorable results.")
        return

    results.sort(key=lambda r: r[2].total_score, reverse=True)

    # --- Per-stock table ---
    print("\n" + "=" * 78)
    print(f"{'SYM':<6}{'PRICE':>9}{'TOTAL':>8}{'TECH':>7}{'FUND':>7}{'INSDR':>7}{'PATT':>7}  REC")
    print("-" * 78)
    for sym, price, s in results:
        rec = s.entry_recommendation or "-"
        print(
            f"{sym:<6}{price:>9.2f}{s.total_score:>8.1f}{s.technical_score:>7.1f}"
            f"{s.fundamental_score:>7.1f}{s.insider_score:>7.1f}{s.pattern_score:>7.1f}  {rec}"
        )

    n = len(results)
    avg = lambda f: sum(f(s) for _, _, s in results) / n
    print("-" * 78)
    print(
        f"{'AVG':<6}{'':>9}{avg(lambda s: s.total_score):>8.1f}"
        f"{avg(lambda s: s.technical_score):>7.1f}{avg(lambda s: s.fundamental_score):>7.1f}"
        f"{avg(lambda s: s.insider_score):>7.1f}{avg(lambda s: s.pattern_score):>7.1f}"
    )
    print("=" * 78)
    print(f"Scored {n}/{len(symbols)} requested symbols.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discrete AI-stock Superstock scan")
    parser.add_argument("--symbols", nargs="+", help="Override the default AI ticker list")
    parser.add_argument("--no-insider", action="store_true", help="Skip OpenInsider fetch")
    args = parser.parse_args()

    syms = [s.upper() for s in (args.symbols or DEFAULT_SYMBOLS)]
    asyncio.run(main(syms, fetch_insider=not args.no_insider))
