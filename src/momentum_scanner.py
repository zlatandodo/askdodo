"""
Standalone Momentum Focus List scanner.

Based on Sean's swing trading framework:
  1. Market regime check: SPY/QQQ above EMA21 and EMA50
  2. Stock leadership: price > EMA8 > EMA21 > EMA50
  3. ADR(20) > 2% — enough daily range for swing trading
  4. Prior move: +10% in the 40 sessions before the base
  5. Tight base: last 15 days range < 12% (coiled spring)
  6. Volume contraction during base (no institutional distribution)

Quality score (for ranking):
  - Tightness:   tighter base → higher score  (max 30 pts)
  - Vol ratio:   more contraction → higher    (max 20 pts)
  - Prior move:  stronger leg up → higher     (max 20 pts)
  - ADR:         more range → higher          (max 15 pts)
  - EMA spacing: price well above EMAs        (max 15 pts)
"""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _sma(series: pd.Series, n: int) -> float:
    if len(series) < n:
        return float("nan")
    return float(series.iloc[-n:].mean())


# ── Market regime ─────────────────────────────────────────────────────────────

def check_market_regime(hist_data: dict) -> dict:
    """
    SPY and QQQ: are they above EMA21 and EMA50?
    Returns: {bullish: bool, details: {SPY: {...}, QQQ: {...}}}
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
        is_bull = price > ema21 and price > ema50
        result["details"][sym] = {
            "price": round(price, 2),
            "ema21": round(ema21, 2),
            "ema50": round(ema50, 2),
            "bullish": is_bull,
        }
        if is_bull:
            bullish_count += 1
    result["bullish"] = bullish_count >= 1
    return result


# ── Quality score ─────────────────────────────────────────────────────────────

def _quality_score(
    base_range_pct: float,
    vol_ratio: float,
    prior_move_pct: float,
    adr20: float,
    price: float,
    ema8: float,
    ema21: float,
    ema50: float,
) -> float:
    score = 0.0

    # Tightness (0-30): tighter base = more coiled = better
    # base_range_pct: 0% = perfect, 12% = minimum accepted
    tightness = max(0.0, 1.0 - base_range_pct / 12.0)
    score += tightness * 30

    # Volume contraction (0-20): lower ratio = stronger contraction
    # vol_ratio: 0.0 = no volume at all (best), 0.90 = barely contracting (min)
    if vol_ratio is not None and vol_ratio < 0.90:
        contraction = max(0.0, 1.0 - vol_ratio / 0.90)
        score += contraction * 20

    # Prior move (0-20): stronger leg up before the base = better
    # 10% = minimum, 50%+ = excellent
    move_score = min(1.0, max(0.0, (prior_move_pct - 10.0) / 40.0))
    score += move_score * 20

    # ADR (0-15): higher daily range = more swing trading potential
    # 2% = minimum, 6%+ = excellent
    adr_score = min(1.0, max(0.0, (adr20 * 100 - 2.0) / 4.0))
    score += adr_score * 15

    # EMA spacing (0-15): price distance above EMA50 = trend strength
    if ema50 > 0:
        spacing = (price - ema50) / ema50
        ema_score = min(1.0, max(0.0, spacing / 0.20))  # 20% above = max score
        score += ema_score * 15

    return round(score, 2)


# ── Main scanner ──────────────────────────────────────────────────────────────

def scan_momentum(
    hist_data: dict,
    meta_map: dict,
    cfg: dict,
) -> list[dict]:
    """
    Run the momentum focus list scan.
    Returns list of dicts sorted by quality_score DESC.
    """
    BASE_DAYS        = int(cfg.get("base_days", 15))
    PRIOR_DAYS       = int(cfg.get("prior_days", 40))
    BASE_RANGE_MAX   = float(cfg.get("base_range_max_pct", 12.0)) / 100.0
    PRIOR_MOVE_MIN   = float(cfg.get("prior_move_min_pct", 10.0)) / 100.0
    VOL_CONTRACT_MAX = float(cfg.get("vol_contraction_max", 0.90))
    ADR_MIN          = float(cfg.get("adr_min_pct", 2.0)) / 100.0
    PRICE_MIN        = float(cfg.get("price_min", 5))
    MCAP_MIN         = float(cfg.get("market_cap_min_m", 300))
    VOL_MIN          = float(cfg.get("avg_vol_min", 500_000))
    SECTOR_CAP       = int(cfg.get("max_per_sector", 2))
    FOCUS_SIZE       = int(cfg.get("focus_list_size", 10))
    MIN_HISTORY      = BASE_DAYS + PRIOR_DAYS + 60

    candidates = []

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

            # Price filter
            if price < PRICE_MIN:
                continue

            # EMA alignment: price > EMA8 > EMA21 > EMA50
            ema8  = float(_ema(close, 8).iloc[-1])
            ema21 = float(_ema(close, 21).iloc[-1])
            ema50 = float(_ema(close, 50).iloc[-1])
            if not (price > ema8 and ema8 > ema21 and ema21 > ema50):
                continue

            # Must also be above MA200 (long-term uptrend)
            ma200 = _sma(close, 200)
            if np.isnan(ma200) or price < ma200:
                continue

            # ADR(20) > 2%
            adr20 = float(((high - low) / close).tail(20).mean())
            if adr20 < ADR_MIN:
                continue

            # Average volume >= 500K
            avg_vol = float(vol.tail(50).mean()) if len(vol) >= 50 else float(vol.mean())
            if avg_vol < VOL_MIN:
                continue

            # Prior momentum: +10% in PRIOR_DAYS sessions before the base
            if len(close) < BASE_DAYS + PRIOR_DAYS:
                continue
            price_before = float(close.iloc[-(BASE_DAYS + PRIOR_DAYS)])
            price_at_base = float(close.iloc[-BASE_DAYS])
            prior_move = (price_at_base - price_before) / abs(price_before)
            if prior_move < PRIOR_MOVE_MIN:
                continue

            # Tight base: last BASE_DAYS range < BASE_RANGE_MAX
            base_high = float(high.tail(BASE_DAYS).max())
            base_low  = float(low.tail(BASE_DAYS).min())
            base_range = (base_high - base_low) / base_low
            if base_range > BASE_RANGE_MAX:
                continue

            # Volume contraction in base
            avg_vol_base  = float(vol.tail(10).mean())
            avg_vol_prior = float(vol.iloc[-(BASE_DAYS + 20):-BASE_DAYS].mean())
            vol_ratio = (avg_vol_base / avg_vol_prior) if avg_vol_prior > 0 else None
            if vol_ratio is not None and vol_ratio >= VOL_CONTRACT_MAX:
                continue

            # Quality score
            score = _quality_score(
                base_range_pct=base_range * 100,
                vol_ratio=vol_ratio,
                prior_move_pct=prior_move * 100,
                adr20=adr20,
                price=price,
                ema8=ema8, ema21=ema21, ema50=ema50,
            )

            meta = meta_map.get(sym, {})
            mc_raw = meta.get("market_cap")
            mcap_m = (mc_raw / 1_000_000) if mc_raw else None

            # Market cap filter (if available)
            if mcap_m is not None and mcap_m < MCAP_MIN:
                continue

            candidates.append({
                "symbol":          sym,
                "company_name":    meta.get("company_name", sym),
                "sector":          meta.get("sector"),
                "market_cap_m":    mcap_m,
                "price":           round(price, 2),
                "ema8":            round(ema8, 2),
                "ema21":           round(ema21, 2),
                "ema50":           round(ema50, 2),
                "ma200":           round(ma200, 2),
                "adr20_pct":       round(adr20 * 100, 2),
                "avg_vol":         avg_vol,
                "prior_move_pct":  round(prior_move * 100, 1),
                "base_range_pct":  round(base_range * 100, 1),
                "vol_ratio":       round(vol_ratio, 2) if vol_ratio else None,
                "quality_score":   score,
            })

        except Exception as e:
            log.debug(f"[{sym}] momentum_scan: {e}")

    log.info(f"Momentum scan: {len(candidates)} raw candidates before sector cap / top N")

    if not candidates:
        return []

    # Sort by average volume (last month) descending
    candidates.sort(key=lambda x: x["avg_vol"], reverse=True)

    # Sector cap
    sector_counts: dict[str, int] = {}
    focus_list = []
    for c in candidates:
        sec = c.get("sector") or "Unknown"
        n = sector_counts.get(sec, 0)
        if n < SECTOR_CAP:
            focus_list.append(c)
            sector_counts[sec] = n + 1
        if len(focus_list) >= FOCUS_SIZE:
            break

    log.info(f"Momentum focus list: {len(focus_list)} setups")
    return focus_list


# ── Fundamentals enrichment ───────────────────────────────────────────────────

def enrich_with_fundamentals(focus_list: list[dict], hist_data: dict) -> list[dict]:
    """
    Add company description, revenue, and last-week volume to each candidate.
    Fetches yfinance .info for each ticker (only the focus list — max 10 tickers).
    """
    import yfinance as yf

    enriched = []
    for c in focus_list:
        sym = c["symbol"]
        description = None
        revenue_b   = None
        vol_week    = None

        # Market cap via fast_info (endpoint leggero, non rate-limited)
        try:
            mc = yf.Ticker(sym).fast_info.market_cap
            c["market_cap_m"] = round(mc / 1_000_000) if mc else None
        except Exception:
            c["market_cap_m"] = None

        try:
            info = yf.Ticker(sym).info

            # Company description — first 2 sentences, max 300 chars
            bio = info.get("longBusinessSummary") or ""
            sentences = [s.strip() for s in bio.split(".") if s.strip()]
            desc_raw = ". ".join(sentences[:2]) + "." if sentences else ""
            description = desc_raw[:320] if desc_raw else None

            # Revenue (totalRevenue in USD → billions)
            rev = info.get("totalRevenue")
            if rev:
                revenue_b = round(rev / 1e9, 1)

        except Exception as e:
            log.debug(f"[{sym}] fundamentals fetch error: {e}")

        # Last week volume from hist_data (last 5 trading days)
        try:
            h = hist_data.get(sym)
            if h is not None and len(h) >= 5:
                vol_week = float(h["Volume"].tail(5).sum())
        except Exception:
            pass

        enriched.append({
            **c,
            "description": description,
            "revenue_b":   revenue_b,
            "vol_week":    vol_week,
        })
        log.debug(f"[{sym}] enriched — rev=${revenue_b}B | vol_week={vol_week}")

    log.info(f"Fundamentals enriched: {len(enriched)} tickers")
    return enriched


# ── Breakout detector ─────────────────────────────────────────────────────────

def detect_breakouts(hist_data: dict, focus_list: list[dict], cfg: dict) -> list[dict]:
    """
    For each stock in the focus list, check if today it broke above the base high
    with volume confirmation.

    Breakout conditions:
      1. Today's CLOSE > max High of the prior BASE_DAYS + at least breakout_min_pct%
      2. Today's volume > avg volume during the base × breakout_vol_multiplier
      3. Stock is still above EMA21 and EMA50 (no false breakdown)

    Returns list of breakout dicts, sorted by vol_ratio DESC.
    """
    BASE_DAYS   = int(cfg.get("base_days", 20))
    VOL_MULT    = float(cfg.get("breakout_vol_multiplier", 1.2))
    MIN_PCT     = float(cfg.get("breakout_min_pct", 1.0)) / 100.0

    breakouts = []

    for c in focus_list:
        sym = c["symbol"]
        h = hist_data.get(sym)
        if h is None or len(h) < BASE_DAYS + 5:
            continue
        try:
            close = h["Close"]
            high  = h["High"]
            vol   = h["Volume"]

            # Base = the BASE_DAYS days ending BEFORE today
            base_high    = float(high.iloc[-(BASE_DAYS + 1):-1].max())
            base_vol_avg = float(vol.iloc[-(BASE_DAYS + 1):-1].mean())

            today_close = float(close.iloc[-1])
            today_vol   = float(vol.iloc[-1])

            # Chiusura almeno +MIN_PCT% sopra il massimo della base
            if today_close < base_high * (1 + MIN_PCT):
                continue
            # Volume >= VOL_MULT × media base
            if base_vol_avg <= 0 or today_vol < base_vol_avg * VOL_MULT:
                continue

            # EMA check — still above EMA21 and EMA50
            ema21 = float(_ema(close, 21).iloc[-1])
            ema50 = float(_ema(close, 50).iloc[-1])
            if today_close < ema21 or today_close < ema50:
                continue

            vol_ratio_today = round(today_vol / base_vol_avg, 1)
            breakout_pct    = round((today_close - base_high) / base_high * 100, 1)

            breakouts.append({
                **c,
                "breakout_level":   round(base_high, 2),
                "today_close":      round(today_close, 2),
                "today_vol":        today_vol,
                "vol_ratio_today":  vol_ratio_today,
                "breakout_pct":     breakout_pct,
            })
            log.info(
                f"[{sym}] BREAKOUT — close={today_close:.2f} "
                f"above base={base_high:.2f} (+{breakout_pct}%) "
                f"vol={vol_ratio_today}× avg"
            )

        except Exception as e:
            log.debug(f"[{sym}] breakout check error: {e}")

    breakouts.sort(key=lambda x: x["vol_ratio_today"], reverse=True)
    log.info(f"Breakout detector: {len(breakouts)} breakout(s) found")
    return breakouts
