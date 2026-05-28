"""
Simple scanner-overlap scoring for AskLivermore watchlist.

Logic:
  1. Collect all tickers from the configured scanners.
  2. Score each ticker by how many scanners it appears in (multi-scanner = stronger signal).
  3. After yfinance enrichment, add quality bonuses (RSI, 52w-distance, ARS, volume, mcap).
  4. Apply hard filters and return top N by conviction_score.
"""
import logging
from collections import defaultdict
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)


# ── Tier assignment ──────────────────────────────────────────────────────────

def _assign_tier(n_scanners: int) -> str:
    """Tier based on how many scanners the ticker appears in."""
    if n_scanners >= 3:
        return "A"
    if n_scanners == 2:
        return "B"
    if n_scanners == 1:
        return "C"
    return "DROP"


# ── Step 1: Aggregate scanner results into a single DataFrame ────────────────

def aggregate_scanners(
    scanner_results: dict[str, Optional[list[dict]]],
    config: dict,
) -> pd.DataFrame:
    """
    Build a DataFrame of all unique tickers across all scanners.

    For each ticker:
      - n_scanners: how many different scanners it appears in
      - scanners_hit: comma-separated list of scanner names
      - ticker metadata (company_name, sector, market_cap_m, ars, ta, fa, price)
        taken from the first scanner that returns it
      - conviction_score (base): n_scanners * 10
      - tier: A/B/C based on n_scanners

    Returns DataFrame sorted by conviction_score DESC.
    """
    # Which scanners are configured?
    scanner_names = [s["name"] for s in config.get("scanners", [])]

    # ticker → list of scanner names where it appears
    ticker_scanners: dict[str, list[str]] = defaultdict(list)
    # ticker → metadata (first scanner wins)
    ticker_meta: dict[str, dict] = {}

    for sc_name in scanner_names:
        records = scanner_results.get(sc_name)
        if not records:
            log.warning(f"[{sc_name}] No results — skipping.")
            continue

        for rec in records:
            sym = str(rec.get("ticker") or rec.get("symbol") or "").upper().strip()
            if not sym:
                continue

            ticker_scanners[sym].append(sc_name)

            # Store metadata from first encounter
            if sym not in ticker_meta:
                mc_raw = rec.get("market_cap")
                ticker_meta[sym] = {
                    "company_name": rec.get("name") or rec.get("company_name"),
                    "sector":       rec.get("sector"),
                    "market_cap_m": (mc_raw / 1_000_000) if mc_raw else None,
                    "ars":          rec.get("rs_rating") or rec.get("ars"),
                    "ta":           rec.get("ta_rating") or rec.get("ta"),
                    "fa":           rec.get("fa_rating") or rec.get("fa"),
                    "price":        rec.get("price"),
                }

    if not ticker_scanners:
        log.warning("No tickers found across all scanners.")
        return pd.DataFrame()

    rows = []
    for sym, hit_list in ticker_scanners.items():
        n = len(hit_list)
        meta = ticker_meta.get(sym, {})
        rows.append({
            "symbol":          sym,
            "company_name":    meta.get("company_name"),
            "sector":          meta.get("sector"),
            "market_cap_m":    meta.get("market_cap_m"),
            "ars":             meta.get("ars"),
            "ta":              meta.get("ta"),
            "fa":              meta.get("fa"),
            "price":           meta.get("price"),
            "n_scanners":      n,
            "scanners_hit":    ", ".join(sorted(set(hit_list))),
            "conviction_score": float(n * 10),
            "tier":            _assign_tier(n),
        })

    df = pd.DataFrame(rows)

    # Cast numeric columns
    for col in ["market_cap_m", "ars", "ta", "fa", "price", "n_scanners", "conviction_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("conviction_score", ascending=False).reset_index(drop=True)

    n_total = len(df)
    n_multi = (df["n_scanners"] >= 2).sum()
    log.info(
        f"Aggregated {n_total} unique tickers from {len(scanner_names)} scanners. "
        f"Multi-scanner (≥2): {n_multi}. "
        f"Tier A: {(df['tier']=='A').sum()}, "
        f"Tier B: {(df['tier']=='B').sum()}, "
        f"Tier C: {(df['tier']=='C').sum()}."
    )
    return df


# ── Step 2: Quality scoring (post-enrichment) ────────────────────────────────

def _quality_bonus(row: dict) -> float:
    """Compute quality bonus from enriched data. Added on top of base n_scanners*10."""
    bonus = 0.0

    # RSI bonus — sweet spot 40-60 (setup building, not overbought)
    rsi = row.get("rsi14")
    if rsi is not None and not (isinstance(rsi, float) and pd.isna(rsi)):
        rsi = float(rsi)
        if 40 <= rsi <= 60:
            bonus += 5.0
        elif (30 <= rsi < 40) or (60 < rsi <= 70):
            bonus += 2.0

    # Distance from 52-week high bonus — optimal pullback zone
    dist = row.get("dist_52w_high")
    if dist is not None and not (isinstance(dist, float) and pd.isna(dist)):
        dist = float(dist)
        if -0.15 <= dist <= -0.05:
            bonus += 5.0   # tight pullback, still in strength zone
        elif -0.25 <= dist < -0.15:
            bonus += 3.0   # moderate pullback
        elif -0.30 <= dist < -0.25:
            bonus += 1.0   # deeper pullback, still ok

    # ARS (Relative Strength Rating) bonus
    ars = row.get("ars")
    if ars is not None and not (isinstance(ars, float) and pd.isna(ars)):
        ars = float(ars)
        if ars >= 90:
            bonus += 5.0
        elif ars >= 80:
            bonus += 3.0
        elif ars >= 70:
            bonus += 1.0

    # Volume bonus (avg_vol_live = 50-day avg from yfinance)
    vol = row.get("avg_vol_live")
    if vol is not None and not (isinstance(vol, float) and pd.isna(vol)):
        vol = float(vol)
        if vol >= 1_000_000:
            bonus += 3.0
        elif vol >= 500_000:
            bonus += 1.0

    # RVOL bonus — premia attività istituzionale recente
    rvol = row.get("rvol_max_3d")
    if rvol is not None and not (isinstance(rvol, float) and pd.isna(rvol)):
        rvol = float(rvol)
        if rvol >= 2.0:
            bonus += 8.0   # volume doppio: segnale forte
        elif rvol >= 1.5:
            bonus += 5.0
        elif rvol >= 1.2:
            bonus += 2.0

    # Market cap bonus — prefer larger, more liquid companies
    mcap = row.get("market_cap_m")
    if mcap is not None and not (isinstance(mcap, float) and pd.isna(mcap)):
        mcap = float(mcap)
        if mcap >= 2_000:
            bonus += 3.0
        elif mcap >= 1_000:
            bonus += 2.0
        elif mcap >= 500:
            bonus += 1.0

    return bonus


def score_and_filter(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Post-enrichment: compute quality bonus, update conviction_score, apply hard
    filters, sector cap, and return top N tickers.

    Filters applied (in order):
      1. Tier: only A and B (≥2 scanners); fallback to C if < 3 pass
      2. Market cap ≥ market_cap_min_m
      3. Price between price_min and price_max
      4. Average volume ≥ avg_vol_min
      5. Earnings buffer: exclude if earnings within N days
      6. RSI between rsi14_min and rsi14_max (skip if missing)
      7. Distance from 52w high between dist_52w_high_min and dist_52w_high_max (skip if missing)
      8. Sector not null (exclude ETFs)
      9. Max max_per_sector per GICS sector
      10. Top watchlist_size by conviction_score
    """
    if df.empty:
        log.warning("score_and_filter: empty DataFrame.")
        return df

    cfg = config.get("filters", {})
    market_cap_min  = cfg.get("market_cap_min_m", 300)
    price_min       = cfg.get("price_min", 10)
    price_max       = cfg.get("price_max", 600)
    avg_vol_min     = cfg.get("avg_vol_min", 400_000)
    earnings_buffer = cfg.get("earnings_days_buffer", 5)
    rsi_min         = cfg.get("rsi14_min", 30)
    rsi_max         = cfg.get("rsi14_max", 70)
    dist_min        = cfg.get("dist_52w_high_min", -0.30)
    dist_max        = cfg.get("dist_52w_high_max", -0.03)
    require_sector  = cfg.get("require_sector", True)
    max_per_sector  = cfg.get("max_per_sector", 3)
    watchlist_size  = cfg.get("watchlist_size", 10)
    min_watchlist   = 3

    # Add quality bonuses first (so ordering is meaningful)
    df = df.copy()
    df["conviction_score"] = df.apply(
        lambda row: round(row["conviction_score"] + _quality_bonus(row.to_dict()), 2),
        axis=1,
    )

    def _apply_hard_filters(working: pd.DataFrame, include_tier_c: bool) -> pd.DataFrame:
        """Apply all hard filters. Returns filtered DataFrame."""

        # Tier filter
        if "tier" in working.columns:
            tiers = ["A", "B", "C"] if include_tier_c else ["A", "B"]
            working = working[working["tier"].isin(tiers)]
        _log_f("Tier filter", working)

        # Market cap
        if "market_cap_m" in working.columns:
            has = working["market_cap_m"].notna()
            working = working[~has | (working["market_cap_m"] >= market_cap_min)]
        _log_f("Market cap", working)

        # Price range
        price_col = "price"
        if price_col in working.columns:
            has = working[price_col].notna()
            working = working[
                ~has | ((working[price_col] >= price_min) & (working[price_col] <= price_max))
            ]
        _log_f("Price range", working)

        # Volume
        vol_col = "avg_vol_live" if "avg_vol_live" in working.columns else "avg_vol"
        if vol_col in working.columns:
            has = working[vol_col].notna()
            working = working[~has | (working[vol_col] >= avg_vol_min)]
        _log_f("Volume", working)

        # Earnings buffer
        if "days_to_earnings" in working.columns:
            def _keep(days) -> bool:
                try:
                    d = int(days)
                    return d < 0 or d > earnings_buffer
                except (TypeError, ValueError):
                    return True  # unknown → keep
            working = working[working["days_to_earnings"].apply(_keep)]
        _log_f("Earnings buffer", working)

        # RSI filter
        if "rsi14" in working.columns:
            has = working["rsi14"].notna()
            working = working[
                ~has | ((working["rsi14"] >= rsi_min) & (working["rsi14"] <= rsi_max))
            ]
        _log_f("RSI", working)

        # 52-week high distance
        if "dist_52w_high" in working.columns:
            has = working["dist_52w_high"].notna()
            working = working[
                ~has | (
                    (working["dist_52w_high"] >= dist_min) &
                    (working["dist_52w_high"] <= dist_max)
                )
            ]
        _log_f("52w high distance", working)

        # RVOL filter: almeno un giorno recente con volume > 1.2× media 20gg
        if "rvol_max_3d" in working.columns:
            has_rvol = working["rvol_max_3d"].notna()
            working = working[~has_rvol | (working["rvol_max_3d"] >= 1.2)]
        _log_f("RVOL >= 1.2", working)

        # Price above MA50 (no stocks in downtrend below key support)
        if "price" in working.columns and "ma50" in working.columns:
            has_both = working["price"].notna() & working["ma50"].notna()
            working = working[~has_both | (working["price"] >= working["ma50"])]
        _log_f("Price >= MA50", working)

        # Price above MA200 (long-term uptrend required — stage 2 confirmed)
        # Hard rule: if MA200 is not available, exclude the ticker (don't give benefit of doubt)
        if "ma200" in working.columns:
            ma200_num = pd.to_numeric(working["ma200"], errors="coerce")
            price_num = pd.to_numeric(working["price"], errors="coerce")
            working = working[ma200_num.notna() & (price_num >= ma200_num)]
        _log_f("Price >= MA200", working)

        # Sector required (exclude ETFs)
        if require_sector and "sector" in working.columns:
            working = working[working["sector"].notna() & (working["sector"] != "")]
        _log_f("Sector required", working)

        # Sector cap
        working = _sector_cap(working, max_per_sector)
        _log_f(f"Sector cap (max {max_per_sector})", working)

        # Top N
        if not working.empty and "conviction_score" in working.columns:
            working = working.sort_values("conviction_score", ascending=False).head(watchlist_size)
        _log_f(f"Top {watchlist_size}", working)

        return working

    def _log_f(stage: str, wdf: pd.DataFrame) -> None:
        log.info(f"[Filter] {stage}: {len(wdf)} tickers")

    def _sector_cap(wdf: pd.DataFrame, limit: int) -> pd.DataFrame:
        if "sector" not in wdf.columns or wdf.empty:
            return wdf
        out = wdf.sort_values("conviction_score", ascending=False)
        kept = []
        counts: dict[str, int] = {}
        for _, row in out.iterrows():
            sec = str(row.get("sector") or "Unknown")
            n = counts.get(sec, 0)
            if n < limit:
                kept.append(row)
                counts[sec] = n + 1
        return pd.DataFrame(kept) if kept else pd.DataFrame(columns=wdf.columns)

    # First pass: strict (A + B only)
    result = _apply_hard_filters(df, include_tier_c=False)

    # Relaxed pass: if too few, include Tier C
    if len(result) < min_watchlist:
        log.info(
            f"Only {len(result)} tickers passed strict filters. "
            f"Relaxing: including Tier C (single-scanner hits)."
        )
        result = _apply_hard_filters(df, include_tier_c=True)

    result = result.copy()
    result["filter_note"] = ""  # kept for report compatibility

    log.info(
        f"Final watchlist: {len(result)} tickers "
        f"(Tier A: {(result['tier']=='A').sum()}, "
        f"Tier B: {(result['tier']=='B').sum()}, "
        f"Tier C: {(result['tier']=='C').sum()})."
    )
    return result.reset_index(drop=True)
