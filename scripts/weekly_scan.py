"""
Weekly Scan CLI  (Phase B1)

Usage:
    python -m scripts.weekly_scan --mode standard --output markdown
    python -m scripts.weekly_scan --mode quick --output json
    python -m scripts.weekly_scan --help

Runs full pipeline: Finviz filter → batch fetch → compute → score → rank → report
Exit 0 on success, 1 on failure.
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

# Ensure project root is on sys.path so `app.*` imports work when invoked as
# `python -m scripts.weekly_scan` from the repo root.
_project_root = Path(__file__).resolve().parent.parent
_backend_root = _project_root / "backend"
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.services.screener import run_full_pipeline, ScreeningCriteria, StockScore
from app.services.finviz_screener import ScanMode
from scripts.report_generator import generate_report, DEFAULT_OUTPUT_DIR

logger = logging.getLogger("weekly_scan")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IBSS Weekly Superstock Scan",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m scripts.weekly_scan\n"
            "  python -m scripts.weekly_scan --mode quick --top 10\n"
            "  python -m scripts.weekly_scan --mode deep --output json --outfile results.json\n"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "standard", "deep"],
        default="standard",
        help="Finviz scan mode (default: standard)",
    )
    parser.add_argument(
        "--output",
        choices=["markdown", "json", "both"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of top candidates in report (default: 20)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=50.0,
        help="Minimum composite score threshold (default: 50.0)",
    )
    parser.add_argument(
        "--outfile",
        type=str,
        default=None,
        help="Custom output file path (overrides default Obsidian vault path)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    """Execute the scan pipeline. Returns exit code."""
    start = time.time()

    criteria = ScreeningCriteria(min_total_score=args.min_score)
    mode = ScanMode(args.mode)

    # Progress callback for CLI
    async def on_progress(stage: str, pct: int, msg: str):
        print(f"  [{stage:>7}] {pct:3d}% | {msg}")

    print(f"=== IBSS Weekly Scan ({args.mode} mode) ===")
    print(f"Date: {date.today().isoformat()}")
    print()

    scored = await run_full_pipeline(
        criteria=criteria,
        mode=mode,
        progress_callback=on_progress,
    )

    elapsed = time.time() - start
    print()
    print(f"Pipeline completed in {elapsed:.1f}s — {len(scored)} stocks passed filters")

    if not scored:
        print("No stocks passed the screening criteria.")
        return 0

    top = scored[: args.top]

    # --- Output ---
    if args.output in ("markdown", "both"):
        outpath = args.outfile if args.outfile else None
        report_path = generate_report(top, output_path=outpath)
        print(f"\nMarkdown report written to: {report_path}")

    if args.output in ("json", "both"):
        json_data = [
            {
                "rank": s.rank,
                "symbol": s.symbol,
                "total_score": s.total_score,
                "technical_score": s.technical_score,
                "fundamental_score": s.fundamental_score,
                "insider_score": s.insider_score,
                "pattern_score": s.pattern_score,
                "volume_signal": s.volume_signal,
                "entry_recommendation": s.entry_recommendation,
                "patterns": s.patterns_detected or [],
                "magic_line_period": s.magic_line_period,
            }
            for s in top
        ]

        if args.outfile and args.output == "json":
            Path(args.outfile).write_text(json.dumps(json_data, indent=2))
            print(f"JSON results written to: {args.outfile}")
        else:
            json_path = DEFAULT_OUTPUT_DIR / f"{date.today().isoformat()}.json"
            json_path.write_text(json.dumps(json_data, indent=2))
            print(f"JSON results written to: {json_path}")

    # Print summary table to stdout
    print(f"\n{'Rank':>4}  {'Symbol':<8} {'Score':>6}  {'Tech':>5}  {'Fund':>5}  {'Ins':>5}  {'Vol Signal':<16}  {'Entry':<12}")
    print("-" * 80)
    for s in top:
        print(
            f"{s.rank or 0:4d}  {s.symbol:<8} {s.total_score:6.1f}  "
            f"{s.technical_score:5.1f}  {s.fundamental_score:5.1f}  {s.insider_score:5.1f}  "
            f"{(s.volume_signal or 'n/a'):<16}  {(s.entry_recommendation or 'n/a'):<12}"
        )

    return 0


def main():
    args = _parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy libraries
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("finvizfinance").setLevel(logging.WARNING)

    try:
        exit_code = asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\nScan interrupted.")
        exit_code = 1
    except Exception as e:
        logger.exception("Fatal error during scan")
        print(f"\nFATAL: {e}", file=sys.stderr)
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
