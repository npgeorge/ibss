"""
Context Builder Service

Normalizes and merges data from multiple sources (Finviz, yfinance, OpenInsider)
into a unified StockContext that the screener can use.

This is the single source of truth for stock data.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd
import numpy as np

from app.models.context import (
    StockContext,
    NormalizedFinancials,
    NormalizedTechnicals,
    NormalizedInsider,
    NormalizedPatterns,
)
from app.services.finviz_screener import StockMetrics
from app.services.magic_line import MagicLineDetector
from app.services.volume_analysis import VolumeAnalyzer
from app.services.pattern_recognition import PatternRecognizer

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Build normalized StockContext from multiple data sources.

    Usage:
        builder = ContextBuilder()
        context = builder.build_context(
            symbol="AAPL",
            finviz_data=finviz_metrics,
            price_df=price_dataframe,
            insider_transactions=insider_list,
        )
    """

    def build_context(
        self,
        symbol: str,
        finviz_data: Optional[StockMetrics] = None,
        price_df: Optional[pd.DataFrame] = None,
        insider_transactions: Optional[List[Any]] = None,
    ) -> StockContext:
        """
        Build a complete StockContext from available data sources.

        Args:
            symbol: Stock ticker symbol
            finviz_data: StockMetrics from Finviz screener
            price_df: DataFrame with OHLCV data from yfinance
            insider_transactions: List of insider transactions from OpenInsider

        Returns:
            StockContext with normalized data
        """
        # Normalize each component
        financials = self._normalize_financials(finviz_data)
        technicals = self._normalize_technicals(price_df, finviz_data)
        insider = self._normalize_insider(insider_transactions)
        patterns = self._detect_patterns(price_df)

        # Calculate confidence based on data completeness
        confidence = self._calculate_confidence(financials, technicals, insider, price_df)

        # Build identity info
        company_name = finviz_data.company if finviz_data else ""
        sector = finviz_data.sector if finviz_data else "Unknown"
        industry = finviz_data.industry if finviz_data else "Unknown"

        return StockContext(
            symbol=symbol.upper(),
            company_name=company_name,
            sector=sector,
            industry=industry,
            confidence_score=confidence,
            financials=financials,
            technicals=technicals,
            insider=insider,
            patterns=patterns,
            _source_finviz=self._finviz_to_dict(finviz_data) if finviz_data else None,
        )

    def _normalize_financials(
        self,
        finviz: Optional[StockMetrics],
    ) -> NormalizedFinancials:
        """Normalize financial data from Finviz."""
        if not finviz:
            return NormalizedFinancials()

        return NormalizedFinancials(
            # Market cap already in millions from Finviz parser
            market_cap=finviz.market_cap if finviz.market_cap else None,
            pe_ratio=finviz.pe_ratio,
            forward_pe=finviz.forward_pe,
            peg_ratio=finviz.peg_ratio,
            eps_ttm=finviz.eps_ttm,
            eps_growth_yoy=self._to_decimal(finviz.eps_growth_yoy),
            eps_growth_next_y=self._to_decimal(finviz.eps_growth_next_y),
            revenue_growth_yoy=self._to_decimal(finviz.revenue_growth_yoy),
            debt_to_equity=finviz.debt_to_equity,
            current_ratio=finviz.current_ratio,
            float_shares=finviz.float_shares,
            shares_outstanding=finviz.shares_outstanding,
            short_float_pct=self._to_decimal(finviz.short_float),
            analyst_count=finviz.analyst_count,
            target_price=finviz.target_price,
        )

    def _normalize_technicals(
        self,
        price_df: Optional[pd.DataFrame],
        finviz: Optional[StockMetrics],
    ) -> NormalizedTechnicals:
        """Calculate technical indicators from price data."""
        # Return default if no price data
        if price_df is None or price_df.empty:
            return NormalizedTechnicals(
                price=finviz.price if finviz else 0,
                volume=finviz.volume if finviz else 0,
                avg_volume_20d=finviz.avg_volume if finviz else 0,
                relative_volume=finviz.relative_volume if finviz else 1.0,
            )

        # Ensure we have enough data
        if len(price_df) < 20:
            current_price = float(price_df.iloc[-1]["close"]) if len(price_df) > 0 else 0
            return NormalizedTechnicals(
                price=current_price,
                volume=int(price_df.iloc[-1]["volume"]) if len(price_df) > 0 else 0,
                avg_volume_20d=int(price_df["volume"].mean()) if len(price_df) > 0 else 0,
                relative_volume=1.0,
            )

        # Get current values
        current_price = float(price_df.iloc[-1]["close"])
        current_volume = int(price_df.iloc[-1]["volume"])

        # Calculate moving averages
        sma_20 = float(price_df["close"].tail(20).mean())
        sma_50 = float(price_df["close"].tail(50).mean()) if len(price_df) >= 50 else None
        sma_200 = float(price_df["close"].tail(200).mean()) if len(price_df) >= 200 else None

        # Average volume
        avg_volume_20d = int(price_df["volume"].tail(20).mean())
        relative_volume = current_volume / avg_volume_20d if avg_volume_20d > 0 else 1.0

        # 52-week high/low
        week_52_data = price_df.tail(252) if len(price_df) >= 252 else price_df
        week_52_high = float(week_52_data["high"].max())
        week_52_low = float(week_52_data["low"].min())

        # Distance calculations
        pct_from_52w_high = (current_price - week_52_high) / week_52_high if week_52_high > 0 else None
        pct_from_52w_low = (current_price - week_52_low) / week_52_low if week_52_low > 0 else None

        # Magic Line analysis
        magic_line_period = None
        magic_line_value = None
        magic_line_distance_pct = None
        magic_line_bounces = 0
        magic_line_respect_rate = None

        try:
            ml_detector = MagicLineDetector(price_df)
            ml_result = ml_detector.find_magic_line()
            if ml_result:
                magic_line_period = ml_result.period
                magic_line_value = ml_result.magic_line_value
                magic_line_distance_pct = ml_result.distance_percent / 100 if ml_result.distance_percent else None
                magic_line_bounces = ml_result.bounces
                magic_line_respect_rate = ml_result.respect_rate
        except Exception as e:
            logger.debug(f"Magic Line detection failed: {e}")

        # Volume analysis
        volume_dryup_ratio = None
        volume_surge_ratio = None
        try:
            vol_analyzer = VolumeAnalyzer(price_df)
            dryup = vol_analyzer.detect_volume_dryup()
            if dryup:
                volume_dryup_ratio = dryup.dryup_ratio
            # Surge is just relative volume
            volume_surge_ratio = relative_volume
        except Exception as e:
            logger.debug(f"Volume analysis failed: {e}")

        # RSI calculation
        rsi_14 = self._calculate_rsi(price_df, 14)

        # ATR calculation
        atr_14 = self._calculate_atr(price_df, 14)
        atr_pct = atr_14 / current_price if atr_14 and current_price > 0 else None

        # Price changes
        change_1d_pct = None
        change_5d_pct = None
        change_20d_pct = None

        if len(price_df) >= 2:
            prev_close = float(price_df.iloc[-2]["close"])
            change_1d_pct = (current_price - prev_close) / prev_close if prev_close > 0 else None

        if len(price_df) >= 6:
            close_5d_ago = float(price_df.iloc[-6]["close"])
            change_5d_pct = (current_price - close_5d_ago) / close_5d_ago if close_5d_ago > 0 else None

        if len(price_df) >= 21:
            close_20d_ago = float(price_df.iloc[-21]["close"])
            change_20d_pct = (current_price - close_20d_ago) / close_20d_ago if close_20d_ago > 0 else None

        return NormalizedTechnicals(
            price=current_price,
            volume=current_volume,
            avg_volume_20d=avg_volume_20d,
            relative_volume=relative_volume,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            above_sma_20=current_price > sma_20 if sma_20 else False,
            above_sma_50=current_price > sma_50 if sma_50 else False,
            above_sma_200=current_price > sma_200 if sma_200 else False,
            distance_from_sma_20=(current_price - sma_20) / sma_20 if sma_20 else None,
            distance_from_sma_50=(current_price - sma_50) / sma_50 if sma_50 else None,
            distance_from_sma_200=(current_price - sma_200) / sma_200 if sma_200 else None,
            week_52_high=week_52_high,
            week_52_low=week_52_low,
            pct_from_52w_high=pct_from_52w_high,
            pct_from_52w_low=pct_from_52w_low,
            magic_line_period=magic_line_period,
            magic_line_value=magic_line_value,
            magic_line_distance_pct=magic_line_distance_pct,
            magic_line_bounces=magic_line_bounces,
            magic_line_respect_rate=magic_line_respect_rate,
            atr_14=atr_14,
            atr_pct=atr_pct,
            rsi_14=rsi_14,
            volume_dryup_ratio=volume_dryup_ratio,
            volume_surge_ratio=volume_surge_ratio,
            change_1d_pct=change_1d_pct,
            change_5d_pct=change_5d_pct,
            change_20d_pct=change_20d_pct,
        )

    def _normalize_insider(
        self,
        transactions: Optional[List[Any]],
    ) -> NormalizedInsider:
        """Normalize insider activity from transaction list."""
        if not transactions:
            return NormalizedInsider()

        # Aggregate transactions
        buy_count = 0
        sell_count = 0
        total_buy_value = 0.0
        total_sell_value = 0.0
        unique_buyers = set()
        insider_names = []
        most_recent_buy_date = None
        most_recent_sell_date = None
        ceo_bought = False
        cfo_bought = False

        for txn in transactions:
            # Handle both dict and object forms
            if isinstance(txn, dict):
                txn_type = txn.get("transaction_type", "").upper()
                value = txn.get("total_value", 0) or 0
                txn_date = txn.get("transaction_date")
                insider_name = txn.get("insider_name", "")
                title = txn.get("title", "").upper()
            else:
                txn_type = getattr(txn, "transaction_type", "").upper()
                value = getattr(txn, "total_value", 0) or 0
                txn_date = getattr(txn, "transaction_date", None)
                insider_name = getattr(txn, "insider_name", "")
                title = getattr(txn, "title", "").upper()

            if "BUY" in txn_type or "P" == txn_type:
                buy_count += 1
                total_buy_value += value
                unique_buyers.add(insider_name)
                if insider_name and insider_name not in insider_names:
                    insider_names.append(insider_name)

                if txn_date:
                    if isinstance(txn_date, str):
                        try:
                            txn_date = datetime.strptime(txn_date, "%Y-%m-%d").date()
                        except:
                            txn_date = None
                    if txn_date and (most_recent_buy_date is None or txn_date > most_recent_buy_date):
                        most_recent_buy_date = txn_date

                # Check for C-suite
                if "CEO" in title or "CHIEF EXECUTIVE" in title:
                    ceo_bought = True
                if "CFO" in title or "CHIEF FINANCIAL" in title:
                    cfo_bought = True

            elif "SELL" in txn_type or "S" == txn_type:
                sell_count += 1
                total_sell_value += value
                if txn_date:
                    if isinstance(txn_date, str):
                        try:
                            txn_date = datetime.strptime(txn_date, "%Y-%m-%d").date()
                        except:
                            txn_date = None
                    if txn_date and (most_recent_sell_date is None or txn_date > most_recent_sell_date):
                        most_recent_sell_date = txn_date

        # Calculate derived values
        net_value = total_buy_value - total_sell_value
        is_cluster_buy = len(unique_buyers) >= 3 or (len(unique_buyers) >= 2 and total_buy_value > 500_000)

        days_since_last_buy = None
        if most_recent_buy_date:
            days_since_last_buy = (date.today() - most_recent_buy_date).days

        return NormalizedInsider(
            has_recent_buys=buy_count > 0,
            buy_count_90d=buy_count,
            sell_count_90d=sell_count,
            total_buy_value_90d=total_buy_value,
            total_sell_value_90d=total_sell_value,
            net_value_90d=net_value,
            is_cluster_buy=is_cluster_buy,
            unique_buyers_90d=len(unique_buyers),
            most_recent_buy_date=most_recent_buy_date,
            most_recent_sell_date=most_recent_sell_date,
            days_since_last_buy=days_since_last_buy,
            insider_names=insider_names[:5],  # Limit to 5 names
            ceo_bought=ceo_bought,
            cfo_bought=cfo_bought,
        )

    def _detect_patterns(
        self,
        price_df: Optional[pd.DataFrame],
    ) -> NormalizedPatterns:
        """Detect chart patterns from price data."""
        if price_df is None or len(price_df) < 50:
            return NormalizedPatterns()

        patterns_detected = []
        pattern_quality_score = 0.0

        try:
            recognizer = PatternRecognizer(price_df)
            patterns = recognizer.detect_all_patterns()

            for pattern in patterns:
                if pattern.confidence > 0.6:  # Only include confident patterns
                    patterns_detected.append(pattern.pattern_type)
                    pattern_quality_score = max(pattern_quality_score, pattern.confidence * 100)

        except Exception as e:
            logger.debug(f"Pattern detection failed: {e}")

        return NormalizedPatterns(
            has_cup_and_handle="cup_and_handle" in patterns_detected,
            has_flat_base="flat_base" in patterns_detected,
            has_ascending_base="ascending_base" in patterns_detected or "staircase" in patterns_detected,
            has_double_bottom="double_bottom" in patterns_detected,
            has_breakout="breakout" in patterns_detected,
            patterns_detected=patterns_detected,
            pattern_quality_score=pattern_quality_score,
        )

    def _calculate_confidence(
        self,
        financials: NormalizedFinancials,
        technicals: NormalizedTechnicals,
        insider: NormalizedInsider,
        price_df: Optional[pd.DataFrame],
    ) -> float:
        """
        Calculate confidence score (0-1) based on data completeness.

        Higher scores mean more complete data, more reliable screening.
        """
        score = 0.0
        max_score = 0.0

        # Price data (most important)
        max_score += 30
        if price_df is not None:
            if len(price_df) >= 252:
                score += 30  # Full year of data
            elif len(price_df) >= 100:
                score += 20
            elif len(price_df) >= 50:
                score += 10

        # Current price and volume
        max_score += 20
        if technicals.price > 0:
            score += 10
        if technicals.avg_volume_20d > 0:
            score += 10

        # Magic Line analysis
        max_score += 15
        if technicals.magic_line_period is not None:
            score += 15

        # Financial data
        max_score += 20
        if financials.market_cap is not None:
            score += 5
        if financials.pe_ratio is not None or financials.peg_ratio is not None:
            score += 5
        if financials.eps_growth_yoy is not None:
            score += 5
        if financials.float_shares is not None:
            score += 5

        # Insider data (nice to have)
        max_score += 15
        if insider.buy_count_90d > 0 or insider.sell_count_90d > 0:
            score += 15
        elif insider.has_recent_buys is not None:
            score += 5

        return score / max_score if max_score > 0 else 0.0

    def _calculate_rsi(self, price_df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate RSI indicator."""
        if len(price_df) < period + 1:
            return None

        try:
            delta = price_df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None
        except Exception:
            return None

    def _calculate_atr(self, price_df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate Average True Range."""
        if len(price_df) < period + 1:
            return None

        try:
            high = price_df["high"]
            low = price_df["low"]
            close = price_df["close"]

            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())

            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean()

            return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else None
        except Exception:
            return None

    @staticmethod
    def _to_decimal(value: Optional[float]) -> Optional[float]:
        """Convert percentage to decimal if needed."""
        if value is None:
            return None
        # Assume values > 1 are percentages
        if abs(value) > 1:
            return value / 100
        return value

    @staticmethod
    def _finviz_to_dict(finviz: StockMetrics) -> Dict[str, Any]:
        """Convert Finviz StockMetrics to dict for storage."""
        return {
            "symbol": finviz.symbol,
            "company": finviz.company,
            "sector": finviz.sector,
            "industry": finviz.industry,
            "market_cap": finviz.market_cap,
            "price": finviz.price,
            "pe_ratio": finviz.pe_ratio,
            "peg_ratio": finviz.peg_ratio,
        }


# Convenience function
def build_stock_context(
    symbol: str,
    finviz_data: Optional[StockMetrics] = None,
    price_df: Optional[pd.DataFrame] = None,
    insider_transactions: Optional[List[Any]] = None,
) -> StockContext:
    """
    Convenience function to build a StockContext.

    Args:
        symbol: Stock ticker symbol
        finviz_data: StockMetrics from Finviz
        price_df: OHLCV DataFrame
        insider_transactions: List of insider transactions

    Returns:
        Normalized StockContext
    """
    builder = ContextBuilder()
    return builder.build_context(symbol, finviz_data, price_df, insider_transactions)
