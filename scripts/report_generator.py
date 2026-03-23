"""
Report Generator (Phase B2)

Generates a markdown report with:
- Market conditions summary
- Top 15-20 candidates ranked by composite score
- Per-stock score breakdown, entry signals, Magic Line status, insider activity
- Output to Obsidian vault: IBSS/Notes/Weekly Scans/YYYY-MM-DD.md

Can be used standalone or imported by weekly_scan.py.
"""
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "Obsidian Vault" / "IBSS" / "Notes" / "Weekly Scans"


def generate_report(
    scores: "List",
    output_path: Optional[str] = None,
    scan_date: Optional[date] = None,
) -> Path:
    """
    Generate a markdown report from scored stocks.

    Args:
        scores: List of StockScore objects (from screener.run_full_pipeline)
        output_path: Override output file path
        scan_date: Date for the report (defaults to today)

    Returns:
        Path to the generated report file
    """
    if scan_date is None:
        scan_date = date.today()

    if output_path:
        out = Path(output_path)
    else:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = DEFAULT_OUTPUT_DIR / f"{scan_date.isoformat()}.md"

    md = _build_markdown(scores, scan_date)
    out.write_text(md, encoding="utf-8")
    logger.info(f"Report written to {out}")
    return out


def _build_markdown(scores: list, scan_date: date) -> str:
    """Build the full markdown report string."""
    lines: list[str] = []

    # --- Header ---
    lines.append(f"# IBSS Weekly Scan — {scan_date.isoformat()}")
    lines.append("")
    lines.append(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> Candidates passing filters: **{len(scores)}**")
    lines.append("")

    # --- Market Conditions Summary ---
    lines.append("## Market Conditions")
    lines.append("")
    if scores:
        avg_score = sum(s.total_score for s in scores) / len(scores)
        bullish_count = sum(
            1 for s in scores
            if s.volume_signal in ("accumulating", "breakout_ready", "pullback_entry")
        )
        lines.append(f"- Average composite score: **{avg_score:.1f}**")
        lines.append(f"- Stocks with bullish volume signal: **{bullish_count}** / {len(scores)}")
        lines.append(f"- Top score: **{scores[0].total_score:.1f}** ({scores[0].symbol})")
    else:
        lines.append("_No stocks passed screening criteria this week._")
    lines.append("")

    # --- Summary Table ---
    lines.append("## Top Candidates")
    lines.append("")
    lines.append("| Rank | Symbol | Total | Tech | Fund | Insider | Pattern | Volume Signal | Entry |")
    lines.append("|------|--------|-------|------|------|---------|---------|---------------|-------|")

    for s in scores:
        rank = s.rank or "-"
        vol_sig = s.volume_signal or "—"
        entry = s.entry_recommendation or "—"
        lines.append(
            f"| {rank} | **{s.symbol}** | {s.total_score:.1f} | "
            f"{s.technical_score:.1f} | {s.fundamental_score:.1f} | "
            f"{s.insider_score:.1f} | {s.pattern_score:.1f} | "
            f"{vol_sig} | {entry} |"
        )
    lines.append("")

    # --- Per-Stock Detail ---
    lines.append("## Stock Details")
    lines.append("")

    for s in scores:
        lines.append(f"### {s.symbol}")
        lines.append("")
        lines.append(f"**Rank:** {s.rank or '—'}  &nbsp; **Composite Score:** {s.total_score:.1f}")
        lines.append("")

        # Score breakdown
        lines.append("| Component | Score |")
        lines.append("|-----------|-------|")
        lines.append(f"| Technical | {s.technical_score:.1f} |")
        lines.append(f"| Fundamental | {s.fundamental_score:.1f} |")
        lines.append(f"| Insider | {s.insider_score:.1f} |")
        lines.append(f"| Pattern | {s.pattern_score:.1f} |")
        lines.append("")

        # Magic Line
        if s.magic_line_period:
            lines.append(f"- **Magic Line:** {s.magic_line_period}-week SMA")
            if s.magic_line_distance is not None:
                lines.append(f"- **Distance from ML:** {s.magic_line_distance:.1f}%")

        # Patterns
        if s.patterns_detected:
            lines.append(f"- **Patterns:** {', '.join(s.patterns_detected)}")

        # Volume
        if s.volume_signal:
            lines.append(f"- **Volume Signal:** {s.volume_signal}")

        # Entry
        if s.entry_recommendation:
            lines.append(f"- **Entry Recommendation:** {s.entry_recommendation}")
        if s.entry_price:
            lines.append(f"- **Entry Price:** ${s.entry_price:.2f}")
        if s.stop_loss:
            lines.append(f"- **Stop Loss:** ${s.stop_loss:.2f}")
        if s.target_price:
            lines.append(f"- **Target Price:** ${s.target_price:.2f}")

        # Insider detail from breakdown
        breakdown = s.score_breakdown or {}
        insider_info = breakdown.get("insider", {})
        if insider_info.get("recent_purchases"):
            lines.append(f"- **Insider Purchases (recent):** {insider_info['recent_purchases']}")
        if insider_info.get("cluster_buying"):
            lines.append(f"- **Cluster Buying:** Yes")
        if insider_info.get("overall_confidence"):
            lines.append(f"- **Buyer Conviction:** {insider_info['overall_confidence']:.0f}/100")

        lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by IBSS Superstock Screener*")
    lines.append("")

    return "\n".join(lines)
