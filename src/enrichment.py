"""
yfinance-based enrichment: adds price, ATR(14), moving averages, and earnings data.
Downloads in batches for efficiency; handles missing data gracefully.
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

BATCH_SIZE = 50
MAX_RETRIES = 3
BASE_BACKOFF_S = 5
HISTORY_DAYS = 300  # ~215 trading days — enough for MA200 + ATR buffer


def _compute_atr(hist: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Compute ATR(period) from OHLC history DataFrame."""
    if hist is None or len(hist) < period + 1:
        return None
    try:
        high = hist["High"]
        low = hist["Low"]
        close = hist["Close"]
        prev_close = close.shift(1)

        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)

        atr = tr.tail(period).mean()
        return float(atr) if not np.isnan(atr) else None
    except Exception as e:
        log.debug(f"ATR computation error: {e}")
        return None


def _compute_ma(series: pd.Series, period: int) -> Optional[float]:
    """Compute simple moving average for last `period` bars."""
    if series is None or len(series) < period:
        return None
    val = series.tail(period).mean()
    return float(val) if not np.isnan(val) else None


def _get_next_earnings(ticker_obj) -> tuple[Optional[str], Optional[int]]:
    """Return (next_earnings_date_str, days_to_earnings) or (None, None)."""
    try:
        cal = ticker_obj.calendar
        if cal is None:
            return None, None

        # yfinance returns calendar as dict or DataFrame depending on version
        if isinstance(cal, dict):
            earnings_date = cal.get("Earnings Date")
            if earnings_date is None:
                return None, None
            if hasattr(earnings_date, "__iter__") and not isinstance(earnings_date, str):
                earnings_date = list(earnings_date)[0]
        elif isinstance(cal, pd.DataFrame):
            if "Earnings Date" in cal.columns:
                earnings_date = cal["Earnings Date"].iloc[0]
            elif cal.index.name == "Earnings Date" or "Earnings Date" in cal.index:
                earnings_date = cal.loc["Earnings Date"].iloc[0]
            else:
                return None, None
        else:
            return None, None

        if pd.isna(earnings_date):
            return None, None

        ed = pd.Timestamp(earnings_date).date()
        today = datetime.utcnow().date()
        days_to = (ed - today).days
        return str(ed), days_to

    except Exception as e:
        log.debug(f"Could not get earnings date: {e}")
        return None, None


def _enrich_batch(symbols: list[str]) -> dict[str, dict]:
    """Download and compute enrichment for a batch of symbols."""
    import yfinance as yf

    results: dict[str, dict] = {s: {} for s in symbols}
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=HISTORY_DAYS)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            tickers = yf.Tickers(" ".join(symbols))

            for sym in symbols:
                try:
                    ticker = tickers.tickers.get(sym)
                    if ticker is None:
                        log.debug(f"[{sym}] No ticker object from yfinance.")
                        continue

                    hist = ticker.history(start=start_date.strftime("%Y-%m-%d"),
                                         end=end_date.strftime("%Y-%m-%d"),
                                         auto_adjust=True)

                    if hist.empty:
                        log.debug(f"[{sym}] Empty history.")
                        continue

                    close = hist["Close"]
                    latest_price = float(close.iloc[-1]) if len(close) > 0 else None
                    latest_vol = float(hist["Volume"].iloc[-1]) if "Volume" in hist else None

                    atr14 = _compute_atr(hist, 14)
                    ma10 = _compute_ma(close, 10)
                    ma20 = _compute_ma(close, 20)
                    ma50 = _compute_ma(close, 50)
                    ma200 = _compute_ma(close, 200)

                    dist_ma10 = None
                    if latest_price and ma10:
                        dist_ma10 = (latest_price - ma10) / ma10

                    dist_ma50 = None
                    if latest_price and ma50:
                        dist_ma50 = (latest_price - ma50) / ma50

                    # 52-week high and distance from it
                    high52w = float(hist["High"].max()) if len(hist) > 0 else None
                    dist_52w_high = None
                    if latest_price and high52w and high52w > 0:
                        dist_52w_high = (latest_price - high52w) / high52w

                    # RSI(14)
                    rsi14 = None
                    if len(close) >= 15:
                        delta = close.diff()
                        gain = delta.clip(lower=0).rolling(14).mean()
                        loss = (-delta.clip(upper=0)).rolling(14).mean()
                        rs = gain / loss.replace(0, float("nan"))
                        rsi_series = 100 - 100 / (1 + rs)
                        rsi14 = float(rsi_series.iloc[-1]) if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]) else None

                    # Average 50-day volume
                    avg_vol_live = None
                    if "Volume" in hist and len(hist) >= 50:
                        avg_vol_live = float(hist["Volume"].tail(50).mean())
                    elif "Volume" in hist:
                        avg_vol_live = float(hist["Volume"].mean())

                    # RVOL: max relative volume over last 3 days vs 20-day avg
                    rvol_max_3d = None
                    if "Volume" in hist and len(hist) >= 20:
                        avg_vol_20d = float(hist["Volume"].tail(20).mean())
                        if avg_vol_20d > 0:
                            rvol_max_3d = float(
                                (hist["Volume"].tail(3) / avg_vol_20d).max()
                            )

                    next_ed, days_to_ed = _get_next_earnings(ticker)

                    results[sym] = {
                        "price": latest_price,
                        "atr14": atr14,
                        "ma10": ma10,
                        "ma20": ma20,
                        "ma50": ma50,
                        "ma200": ma200,
                        "dist_ma10_pct": dist_ma10,
                        "dist_ma50_pct": dist_ma50,
                        "high52w": high52w,
                        "dist_52w_high": dist_52w_high,
                        "rsi14": rsi14,
                        "avg_vol_live": avg_vol_live,
                        "rvol_max_3d": rvol_max_3d,
                        "next_earnings_date": next_ed,
                        "days_to_earnings": days_to_ed,
                    }

                except Exception as sym_err:
                    log.warning(f"[{sym}] Enrichment error: {sym_err}")

            break  # success

        except Exception as e:
            log.warning(f"Batch download attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                wait = BASE_BACKOFF_S * (2 ** (attempt - 1))
                log.info(f"Retrying in {wait}s...")
                time.sleep(wait)
            else:
                log.error("All retry attempts for batch failed.")

    return results


def enrich_tickers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich the scored DataFrame with live price, ATR, MA, and earnings data from yfinance.
    Adds columns: price (updated), atr14, ma10, ma20, ma50, ma200,
    dist_ma10_pct, avg_vol_live, next_earnings_date, days_to_earnings.
    """
    if df.empty:
        log.warning("Empty DataFrame passed to enrichment — returning as-is.")
        return df

    symbols = df["symbol"].dropna().unique().tolist()
    log.info(f"Enriching {len(symbols)} tickers via yfinance...")

    all_results: dict[str, dict] = {}

    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i: i + BATCH_SIZE]
        log.info(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} symbols")
        batch_results = _enrich_batch(batch)
        all_results.update(batch_results)

    enrich_cols = ["price", "atr14", "ma10", "ma20", "ma50", "ma200",
                   "dist_ma10_pct", "dist_ma50_pct", "high52w", "dist_52w_high",
                   "rsi14", "avg_vol_live", "rvol_max_3d",
                   "next_earnings_date", "days_to_earnings"]

    for col in enrich_cols:
        df[col] = df["symbol"].map(lambda s: all_results.get(s, {}).get(col))

    # Overwrite price from yfinance if available (more reliable than scanner CSV)
    # but keep original if yfinance returned None
    if "price" in df.columns:
        yf_prices = df["symbol"].map(lambda s: all_results.get(s, {}).get("price"))
        df["price"] = yf_prices.combine_first(df.get("price"))

    enriched_count = sum(1 for s in symbols if all_results.get(s))
    log.info(f"Enrichment complete: {enriched_count}/{len(symbols)} tickers enriched.")
    return df
