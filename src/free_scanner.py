"""
Free scanner — no AskLivermore subscription required.
Implements three classic swing-trading patterns using only yfinance + Wikipedia.

Patterns:
  - Livermore Buy the Dip  : stage-2 uptrend pulling back to support
  - Pocket Pivot           : up-day volume > highest down-day volume in prior 10 days
  - Golden Pocket          : price in 61.8%–65% Fibonacci retracement zone

Universe: S&P 500 + S&P 400 MidCap (~900 liquid US stocks) from Wikipedia.
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

HISTORY_DAYS = 330       # ~16 months — 200 trading days needs ~280+ calendar days
BATCH_SIZE   = 100       # tickers per yf.download() call
MAX_RETRIES  = 3


# ── Universe ──────────────────────────────────────────────────────────────────

def _fetch_sp_table(url: str, symbol_col: str = "Symbol") -> pd.DataFrame:
    """Scrape an S&P index table from Wikipedia. Returns DataFrame with Symbol + GICS Sector."""
    import requests
    import io
    # macOS often has SSL cert issues with urllib — use requests which handles it better
    resp = requests.get(url, timeout=30, verify=False, headers={
        "User-Agent": "Mozilla/5.0 (compatible; AskLivermore-Bot/1.0)"
    })
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text), flavor="lxml")
    for t in tables:
        if symbol_col in t.columns:
            return t[[symbol_col, "GICS Sector", "Security"]].rename(
                columns={symbol_col: "symbol", "GICS Sector": "sector", "Security": "company_name"}
            )
    raise ValueError(f"Symbol column '{symbol_col}' not found in any table at {url}")


def get_universe(config: dict) -> tuple[list[str], dict[str, dict]]:
    """
    Download S&P 500 + S&P 400 MidCap components from Wikipedia.

    Returns:
        symbols  : list of ticker symbols
        meta_map : {symbol: {company_name, sector}}
    """
    frames = []

    sources = [
        ("S&P 500",  "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"),
        ("S&P 400",  "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"),
        ("S&P 600",  "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"),
    ]

    for name, url in sources:
        try:
            df = _fetch_sp_table(url)
            df["symbol"] = df["symbol"].str.replace(".", "-", regex=False).str.strip()
            frames.append(df)
            log.info(f"Universe | {name}: {len(df)} symbols")
        except Exception as e:
            log.warning(f"Universe | {name}: failed — {e}")

    if not frames:
        log.error("Could not fetch any universe. Using empty list.")
        return [], {}

    combined = pd.concat(frames, ignore_index=True).drop_duplicates("symbol")
    meta_map = {
        row["symbol"]: {"company_name": row["company_name"], "sector": row["sector"]}
        for _, row in combined.iterrows()
    }
    symbols = list(meta_map.keys())
    log.info(f"Universe total: {len(symbols)} unique symbols")
    return symbols, meta_map


# ── History download ──────────────────────────────────────────────────────────

def download_history(symbols: list[str], days: int = HISTORY_DAYS) -> dict[str, pd.DataFrame]:
    """
    Download OHLCV history for all symbols via yf.download() in batches.
    Returns {symbol: DataFrame with Open/High/Low/Close/Volume columns}.

    Parameters
    ----------
    symbols : list of ticker strings
    days    : calendar days of history to download (default HISTORY_DAYS ≈ 330)
              Use 520 for ~2 years (Recent Doublers scanner).
    """
    import yfinance as yf

    end   = datetime.utcnow()
    start = end - timedelta(days=days)
    start_str = start.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")

    all_data: dict[str, pd.DataFrame] = {}
    total_batches = (len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[batch_idx: batch_idx + BATCH_SIZE]
        bn = batch_idx // BATCH_SIZE + 1
        log.info(f"  History batch {bn}/{total_batches}: {len(batch)} symbols")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                raw = yf.download(
                    " ".join(batch),
                    start=start_str,
                    end=end_str,
                    auto_adjust=True,
                    progress=False,
                    group_by="ticker",
                    threads=True,
                )

                if raw.empty:
                    break

                if len(batch) == 1:
                    sym = batch[0]
                    df = raw.dropna(how="all")
                    if len(df) >= 30:
                        all_data[sym] = df
                else:
                    for sym in batch:
                        try:
                            df = raw[sym].dropna(how="all")
                            if len(df) >= 30:
                                all_data[sym] = df
                        except (KeyError, TypeError):
                            pass
                break

            except Exception as e:
                log.warning(f"  Batch {bn} attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(5 * attempt)

    log.info(f"History download complete: {len(all_data)}/{len(symbols)} symbols OK")
    return all_data


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sma(series: pd.Series, n: int) -> float:
    """Simple moving average of last n bars. Returns nan if not enough data."""
    if len(series) < n:
        return float("nan")
    return float(series.iloc[-n:].mean())


def _sma_at(series: pd.Series, n: int, offset: int) -> float:
    """SMA(n) calculated offset bars ago."""
    end = len(series) - offset
    if end < n:
        return float("nan")
    return float(series.iloc[end - n: end].mean())


# ── Scanner 1: Livermore Buy the Dip ─────────────────────────────────────────
#
# Reverse-engineered from AskLivermore API (101 results analyzed):
#   - Uses EMA65, EMA88, EMA100 — NOT SMA50/150/200
#   - StochRSI(14) ≤ 30  → hard cap (all 101 results confirmed)
#   - price ≥ EMA65       → none were below it
#   - price > SMA200      → 101/101 hard requirement
#   - EMA65 > EMA88 > EMA100 ("ma_stacked") → 97/101 soft requirement
#   - pct_from_ema65 range observed: 0% to ~20% (sweet spot 0-5%)

def _stoch_rsi(close: pd.Series, rsi_len: int = 14, stoch_len: int = 14, smooth_k: int = 3) -> float:
    """
    Stochastic RSI — AskLivermore / Wilder style:
      1. RSI(rsi_len) using Wilder's RMA (alpha=1/n) — NOT standard SMA rolling mean
      2. Stoch = (RSI - lowest(RSI, stoch_len)) / (highest(RSI, stoch_len) - lowest(RSI, stoch_len)) * 100
      3. %K = SMA(Stoch, smooth_k)
    Wilder's RMA matches AskLivermore's values exactly (verified on 6 tickers).
    Returns the latest %K value (0-100), or NaN if not enough data.
    """
    min_bars = rsi_len + stoch_len + smooth_k + 5
    if len(close) < min_bars:
        return float("nan")

    # Step 1: RSI using Wilder's RMA (alpha = 1/rsi_len)
    alpha = 1.0 / rsi_len
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(alpha=alpha, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=alpha, adjust=False).mean()
    rs    = gain / loss.replace(0, float("nan"))
    rsi   = 100 - 100 / (1 + rs)

    # Step 2: raw Stochastic of RSI
    rsi_min = rsi.rolling(stoch_len).min()
    rsi_max = rsi.rolling(stoch_len).max()
    rsi_range = rsi_max - rsi_min
    stoch_raw = ((rsi - rsi_min) / rsi_range.replace(0, float("nan"))) * 100

    # Step 3: smooth %K with SMA(smooth_k)
    k = stoch_raw.rolling(smooth_k).mean()

    val = float(k.iloc[-1])
    if np.isnan(val):
        return float("nan")
    return round(val, 1)


def scan_livermore_buy_the_dip(
    hist_data: dict[str, pd.DataFrame],
    meta_map: dict[str, dict],
) -> list[dict]:
    """
    Livermore Buy the Dip — reverse-engineered from AskLivermore API.

    Rules (confirmed by comparing 101 AskLivermore results with yfinance data):
      1. price > SMA200               (macro uptrend — 101/101 hard requirement)
      2. EMA65 > EMA100               (trend stacked — soft, ~97%)
      3. price >= EMA65               (not broken below key support — 101/101)
      4. pct_from_ema65 <= 20%        (not too far extended — 101/101)
      5. StochRSI(14,14,3) <= 30      (short-term oversold — 101/101 hard cap)
         ↑ Uses Wilder's RMA (alpha=1/14) NOT standard SMA rolling mean
           Verified exactly against AskLivermore's stoch_rsi field values.
      6. avg_vol_50d >= 200k           (AskLivermore's observed minimum: 202k)

    Limitations:
      - AskLivermore scans ~30k+ US stocks (incl. Russell2000, ETFs, small-caps)
      - We scan only S&P1500; ~66 of their 101 BTD results are outside our universe
      - Within S&P1500: 35/35 AskLivermore BTD results correctly found (100% recall)
    """
    results = []

    for sym, hist in hist_data.items():
        try:
            if len(hist) < 215:   # need 200 for SMA200 + buffer
                continue

            close  = hist["Close"]
            volume = hist["Volume"]

            price  = float(close.iloc[-1])
            ma200  = _sma(close, 200)

            if np.isnan(ma200):
                continue

            # 1. Above SMA200
            if price <= ma200:
                continue

            # 6. Minimum average volume 200k (AskLivermore's observed minimum: 202k)
            avg_vol_50 = float(volume.tail(50).mean()) if len(volume) >= 50 else float("nan")
            if np.isnan(avg_vol_50) or avg_vol_50 < 200_000:
                continue

            # Compute EMAs
            ema65_s  = close.ewm(span=65,  adjust=False).mean()
            ema88_s  = close.ewm(span=88,  adjust=False).mean()
            ema100_s = close.ewm(span=100, adjust=False).mean()

            ema65  = float(ema65_s.iloc[-1])
            ema88  = float(ema88_s.iloc[-1])
            ema100 = float(ema100_s.iloc[-1])

            # 2. MA stacked: EMA65 > EMA100 (soft — AskLiv allows ~3% exceptions)
            if not (ema65 > ema100):
                continue

            # 3. Price >= EMA65 (bouncing off support, not broken below)
            if price < ema65:
                continue

            # 4. Not too extended from EMA65
            pct_from_ema65 = (price - ema65) / ema65 * 100
            if pct_from_ema65 > 20.0:
                continue

            # 5. StochRSI(14,14,3) <= 30 — Wilder RMA-based (matches AskLivermore)
            srsi = _stoch_rsi(close, 14)
            if np.isnan(srsi) or srsi > 30:
                continue

            meta = meta_map.get(sym, {})
            results.append({
                "ticker":          sym,
                "name":            meta.get("company_name", sym),
                "sector":          meta.get("sector"),
                "price":           round(price, 2),
                "ema65":           round(ema65, 2),
                "ema88":           round(ema88, 2),
                "ema100":          round(ema100, 2),
                "ma200":           round(ma200, 2),
                "pct_from_ema65":  round(pct_from_ema65, 1),
                "stoch_rsi":       srsi,
                "avg_vol_50":      round(avg_vol_50),
            })

        except Exception as e:
            log.debug(f"[{sym}] livermore_dip: {e}")

    log.info(f"Livermore Buy the Dip: {len(results)} matches")
    return results


# ── Scanner 2: Pocket Pivot ───────────────────────────────────────────────────

def scan_pocket_pivot(
    hist_data: dict[str, pd.DataFrame],
    meta_map: dict[str, dict],
) -> list[dict]:
    """
    Pocket Pivot: an up-day where volume exceeds the highest volume
    of any down-day in the prior 10 days.

    Rules:
      1. Stock is above MA50 (uptrend context)
      2. Today (or within last 3 days) is an up-day (close > prev close)
      3. Volume on that up-day > max down-day volume in prior 10 days
      4. Price within 15% of MA50 (near key support, not extended)
    """
    results = []

    for sym, hist in hist_data.items():
        try:
            if len(hist) < 60:
                continue

            close  = hist["Close"]
            volume = hist["Volume"]

            price  = float(close.iloc[-1])
            ma50   = _sma(close, 50)

            if np.isnan(ma50):
                continue

            # 1. Uptrend context
            if price < ma50 * 0.90:
                continue

            # 4. Not too extended
            if price > ma50 * 1.15:
                continue

            # 2 & 3. Check pocket pivot in last 3 days
            found = False
            for d in range(1, 4):        # 0=today offset from end
                idx = -(d)               # index into array

                prev_close = float(close.iloc[idx - 1])
                day_close  = float(close.iloc[idx])

                if day_close <= prev_close:  # not an up-day
                    continue

                day_vol = float(volume.iloc[idx])

                # Down-day volumes in the 10 days BEFORE this day
                start = idx - 10
                end   = idx            # exclusive in iloc

                prior_closes = close.iloc[start:end]
                prior_prev   = close.iloc[start - 1:end - 1]
                prior_vols   = volume.iloc[start:end]

                down_mask = prior_closes.values < prior_prev.values

                if down_mask.any():
                    max_down_vol = float(prior_vols.values[down_mask].max())
                else:
                    # No down days: use 80% of average volume as baseline
                    max_down_vol = float(prior_vols.mean()) * 0.80

                if day_vol > max_down_vol:
                    found = True
                    break

            if not found:
                continue

            meta = meta_map.get(sym, {})
            results.append({
                "ticker":  sym,
                "name":    meta.get("company_name", sym),
                "sector":  meta.get("sector"),
                "price":   round(price, 2),
                "ma50":    round(ma50, 2),
            })

        except Exception as e:
            log.debug(f"[{sym}] pocket_pivot: {e}")

    log.info(f"Pocket Pivot: {len(results)} matches")
    return results


# ── Scanner 3: Golden Pocket ──────────────────────────────────────────────────

def _find_swing_points(
    hist: pd.DataFrame,
    lookback_high: int = 60,
    min_move_pct: float = 0.15,
) -> Optional[tuple[float, float]]:
    """
    Find (swing_low, swing_high) for Fibonacci calculation.

    Method:
    - Swing high = highest High in the window [-(lookback_high+5) : -5]
      (exclude last 5 days so a fresh ATH doesn't count)
    - Swing low  = lowest Low in the 60 days before the swing high

    Returns (swing_low, swing_high) or None if no valid setup.
    """
    high = hist["High"]
    low  = hist["Low"]

    n = len(high)
    if n < lookback_high + 35:
        return None

    # Swing high: look back between 5 and lookback_high+5 days ago
    window_high = high.iloc[-(lookback_high + 5): -5]
    if window_high.empty:
        return None

    sh_local = int(window_high.values.argmax())
    swing_high = float(window_high.iloc[sh_local])

    # Absolute position of swing high in full array
    sh_abs = n - (lookback_high + 5) + sh_local

    # Swing low: lowest Low in 60 days before the swing high
    sl_start = max(0, sh_abs - 60)
    sl_end   = sh_abs
    if sl_end <= sl_start:
        return None

    window_low = low.iloc[sl_start:sl_end]
    swing_low  = float(window_low.min())

    if swing_low <= 0:
        return None

    move_pct = (swing_high - swing_low) / swing_low
    if move_pct < min_move_pct:      # move too small to be meaningful
        return None

    return swing_low, swing_high


def scan_golden_pocket(
    hist_data: dict[str, pd.DataFrame],
    meta_map: dict[str, dict],
) -> list[dict]:
    """
    Golden Pocket: current price in the 61.8%–65% Fibonacci retracement zone
    of the most recent significant swing move.

    Rules:
      1. Stock is above MA200 (macro uptrend)
      2. A valid swing low → swing high move exists (≥ 15%)
      3. Current price is between the 61.8% and 65% retracement levels
         (with ±1% tolerance)
      4. Current price is below the swing high (it's actually pulling back)
    """
    results = []

    for sym, hist in hist_data.items():
        try:
            if len(hist) < 130:
                continue

            close = hist["Close"]
            price = float(close.iloc[-1])
            ma200 = _sma(close, 200)

            if np.isnan(ma200):
                continue

            # 1. Macro uptrend
            if price < ma200 * 0.95:
                continue

            # 2. Find swing points
            pts = _find_swing_points(hist)
            if pts is None:
                continue

            swing_low, swing_high = pts

            # 4. Current price must be below swing high
            if price >= swing_high:
                continue

            # 3. Golden Pocket zone: 61.8% to 65% retracement (with 1% tolerance)
            fib618 = swing_high - 0.618 * (swing_high - swing_low)
            fib650 = swing_high - 0.650 * (swing_high - swing_low)

            lower = min(fib618, fib650) * 0.99
            upper = max(fib618, fib650) * 1.01

            if not (lower <= price <= upper):
                continue

            meta = meta_map.get(sym, {})
            results.append({
                "ticker":      sym,
                "name":        meta.get("company_name", sym),
                "sector":      meta.get("sector"),
                "price":       round(price, 2),
                "swing_low":   round(swing_low, 2),
                "swing_high":  round(swing_high, 2),
                "fib_618":     round(fib618, 2),
                "fib_650":     round(fib650, 2),
                "ma200":       round(ma200, 2),
            })

        except Exception as e:
            log.debug(f"[{sym}] golden_pocket: {e}")

    log.info(f"Golden Pocket: {len(results)} matches")
    return results


# ── Scanner 4: Sean Momentum (Focus List) ────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def _check_market_regime(hist_data: dict[str, pd.DataFrame]) -> dict:
    """
    Check if SPY and QQQ are in bullish regime (price > EMA21 and EMA50).
    Returns dict with regime info and overall bullish flag.
    """
    result: dict = {"bullish": False, "details": {}}
    bullish_count = 0
    for sym in ["SPY", "QQQ"]:
        h = hist_data.get(sym)
        if h is None or len(h) < 55:
            continue
        close = h["Close"]
        price = float(close.iloc[-1])
        ema21 = float(_ema(close, 21).iloc[-1])
        ema50 = float(_ema(close, 50).iloc[-1])
        is_bullish = price > ema21 and price > ema50
        result["details"][sym] = {
            "price": round(price, 2),
            "ema21": round(ema21, 2),
            "ema50": round(ema50, 2),
            "bullish": is_bullish,
        }
        if is_bullish:
            bullish_count += 1
    result["bullish"] = bullish_count >= 1
    return result


def scan_sean_momentum(
    hist_data: dict[str, pd.DataFrame],
    meta_map: dict[str, dict],
) -> list[dict]:
    """
    Momentum Focus List scanner — based on Sean's swing trading framework.

    Rules:
      1. Price > EMA8 > EMA21 > EMA50  (confirmed uptrend, stock is a leader)
      2. ADR(20) > 2%                  (enough daily range for swing trading)
      3. Prior move: +10% in 40 sessions BEFORE the current base
         (momentum was real before consolidation)
      4. Tight base: last 15 days range (high-low) < 12% of price
         (coiled spring — consolidation is happening)
      5. Volume contraction in base: avg vol last 10 days < avg vol prior 20 days
         (no institutional distribution during the base)
    """
    BASE_DAYS  = 15   # consolidation window to measure tightness
    PRIOR_DAYS = 40   # lookback to measure prior momentum
    MIN_HISTORY = BASE_DAYS + PRIOR_DAYS + 55  # need EMAs too

    results = []

    for sym, h in hist_data.items():
        if sym in ("SPY", "QQQ"):
            continue
        if h is None or len(h) < MIN_HISTORY:
            continue
        try:
            close = h["Close"]
            high  = h["High"]
            low   = h["Low"]
            vol   = h["Volume"]

            price = float(close.iloc[-1])

            # 1. Uptrend: price > EMA8 > EMA21 > EMA50
            ema8  = float(_ema(close, 8).iloc[-1])
            ema21 = float(_ema(close, 21).iloc[-1])
            ema50 = float(_ema(close, 50).iloc[-1])
            if not (price > ema8 and ema8 > ema21 and ema21 > ema50):
                continue

            # 2. ADR(20) > 2%
            adr20 = float(((high - low) / close).tail(20).mean())
            if adr20 < 0.02:
                continue

            # 3. Prior momentum: stock moved > 10% in the 40 sessions before the base
            price_before_base = float(close.iloc[-(BASE_DAYS + PRIOR_DAYS)])
            price_at_base_start = float(close.iloc[-BASE_DAYS])
            prior_move = (price_at_base_start - price_before_base) / abs(price_before_base)
            if prior_move < 0.10:
                continue

            # 4. Tight base: range of last 15 days < 12%
            base_high = float(high.tail(BASE_DAYS).max())
            base_low  = float(low.tail(BASE_DAYS).min())
            base_range = (base_high - base_low) / base_low
            if base_range > 0.12:
                continue

            # 5. Volume contracting during base
            avg_vol_base  = float(vol.tail(10).mean())
            avg_vol_prior = float(vol.iloc[-(BASE_DAYS + 20):-BASE_DAYS].mean())
            if avg_vol_prior > 0 and avg_vol_base >= avg_vol_prior * 0.90:
                continue  # volume not declining enough

            meta = meta_map.get(sym, {})
            results.append({
                "ticker":        sym,
                "name":          meta.get("company_name", sym),
                "sector":        meta.get("sector"),
                "price":         round(price, 2),
                "ema8":          round(ema8, 2),
                "ema21":         round(ema21, 2),
                "ema50":         round(ema50, 2),
                "adr20_pct":     round(adr20 * 100, 2),
                "prior_move_pct": round(prior_move * 100, 1),
                "base_range_pct": round(base_range * 100, 1),
                "vol_ratio":     round(avg_vol_base / avg_vol_prior, 2) if avg_vol_prior > 0 else None,
            })

        except Exception as e:
            log.debug(f"[{sym}] sean_momentum: {e}")

    log.info(f"Sean Momentum (Focus List): {len(results)} matches")
    return results


# ── Main entry point ──────────────────────────────────────────────────────────

def run_free_scanners(config: dict) -> tuple[dict[str, Optional[list[dict]]], dict[str, dict]]:
    """
    Run all three free scanners.

    Returns:
        scanner_results : {scanner_name: [list of ticker dicts]}  — same format as run_all_downloads()
        meta_map        : {symbol: {company_name, sector}}        — for aggregate_scanners
    """
    log.info("=== Free Scanner Mode (no AskLivermore needed) ===")

    # 1. Universe
    log.info("Step 1/4 — Fetching universe (S&P 500 + S&P 400 + S&P 600)...")
    symbols, meta_map = get_universe(config)

    if not symbols:
        log.error("Empty universe — cannot continue.")
        return {}, {}

    # 2. History (include SPY + QQQ for market regime check)
    all_symbols = ["SPY", "QQQ"] + [s for s in symbols if s not in ("SPY", "QQQ")]
    log.info(f"Step 2/4 — Downloading {HISTORY_DAYS}d OHLCV for {len(all_symbols)} symbols...")
    hist_data = download_history(all_symbols)

    if not hist_data:
        log.error("No history data — cannot continue.")
        return {}, {}

    # 3. Market regime check
    regime = _check_market_regime(hist_data)
    regime_str = " | ".join(
        f"{sym}: {'✅ BULL' if d['bullish'] else '⚠️ WEAK'} "
        f"(price={d['price']} EMA21={d['ema21']} EMA50={d['ema50']})"
        for sym, d in regime["details"].items()
    )
    log.info(f"Market regime — {regime_str}")
    if regime["bullish"]:
        log.info("Market regime: BULLISH — full conviction mode")
    else:
        log.warning("Market regime: WEAK — reduce size, be selective")

    # 4. Scan
    enabled = {s["name"] for s in config.get("scanners", [])}
    log.info("Step 3/4 — Running pattern scanners...")

    scanner_results: dict[str, Optional[list[dict]]] = {}

    if "livermore_buy_the_dip" in enabled:
        scanner_results["livermore_buy_the_dip"] = scan_livermore_buy_the_dip(hist_data, meta_map)
    if "pocket_pivot" in enabled:
        scanner_results["pocket_pivot"] = scan_pocket_pivot(hist_data, meta_map)
    if "golden_pocket" in enabled:
        scanner_results["golden_pocket"] = scan_golden_pocket(hist_data, meta_map)
    if "sean_momentum" in enabled:
        scanner_results["sean_momentum"] = scan_sean_momentum(hist_data, meta_map)

    ok    = sum(1 for v in scanner_results.values() if v is not None)
    total = sum(len(v) for v in scanner_results.values() if v)
    log.info(f"Free scanners done: {ok} scanners, {total} total matches")

    return scanner_results, meta_map
