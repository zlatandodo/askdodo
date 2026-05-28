"""
Dual-funnel filter pipeline for the scored + enriched watchlist.
Applies strategy-aware filtering for Strategy A (Pullback) and B (Mean Reversion),
with progressive threshold relaxation if too few tickers pass.
"""
import logging
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

MAX_WATCHLIST = 10
MIN_WATCHLIST = 3


def _log_stage(stage: str, df: pd.DataFrame, note: str = "") -> None:
    log.info(f"[Filter] {stage}: {len(df)} tickers remaining. {note}")


def _apply_shared_filters(
    df: pd.DataFrame,
    cfg: dict,
    ars_threshold: float,
) -> pd.DataFrame:
    """
    Apply shared pre-filters to all tickers regardless of strategy:
      - ARS >= ars_threshold
      - market_cap_m >= market_cap_min_m
      - price between price_min and price_max
      - avg_vol >= avg_vol_min
      - days_to_earnings > earnings_days_buffer (skip if None)
      - dist_ma10_pct <= ma10_chase_pct (skip if None)
    Returns filtered DataFrame.
    """
    market_cap_min_m = cfg.get("market_cap_min_m", 300)
    price_min = cfg.get("price_min", 10)
    price_max = cfg.get("price_max", 500)
    avg_vol_min = cfg.get("avg_vol_min", 500_000)
    earnings_buffer = cfg.get("earnings_days_buffer", 5)
    ma10_chase_pct = cfg.get("ma10_chase_pct", 0.10)
    dist_52w_min = cfg.get("dist_52w_high_min", -0.03)
    rsi14_max = cfg.get("rsi14_max", 70)
    require_sector = cfg.get("require_sector", True)

    working = df.copy()

    # ARS minimum
    has_ars = working["ars"].notna()
    working = working[~has_ars | (working["ars"] >= ars_threshold)]

    # Market cap
    has_mcap = working["market_cap_m"].notna()
    working = working[~has_mcap | (working["market_cap_m"] >= market_cap_min_m)]

    # Price range
    price_col = "price"
    if price_col in working.columns:
        has_price = working[price_col].notna()
        working = working[
            ~has_price |
            ((working[price_col] >= price_min) & (working[price_col] <= price_max))
        ]

    # Average volume
    vol_col = "avg_vol_live" if "avg_vol_live" in working.columns else "avg_vol"
    if vol_col in working.columns:
        has_vol = working[vol_col].notna()
        working = working[~has_vol | (working[vol_col] >= avg_vol_min)]

    # Earnings date buffer
    if "days_to_earnings" in working.columns:
        def _safe_days(val) -> Optional[int]:
            try:
                return int(val) if val is not None and not pd.isna(val) else None
            except (TypeError, ValueError):
                return None

        def _keep_row(days) -> bool:
            d = _safe_days(days)
            if d is None:
                return True
            return d < 0 or d > earnings_buffer

        working = working[working["days_to_earnings"].apply(_keep_row)]

    # MA10 chase filter
    if "price" in working.columns and "ma10" in working.columns:
        def _not_chasing(row) -> bool:
            p = row.get("price")
            m10 = row.get("ma10")
            if p is None or m10 is None or pd.isna(p) or pd.isna(m10) or m10 == 0:
                return True
            return p <= m10 * (1 + ma10_chase_pct)

        working = working[working.apply(_not_chasing, axis=1)]

    # Distance from 52-week high: exclude stocks too close to ATH
    if "dist_52w_high" in working.columns:
        has_d52 = working["dist_52w_high"].notna()
        working = working[~has_d52 | (working["dist_52w_high"] <= dist_52w_min)]

    # Global RSI cap: exclude clearly overbought
    if "rsi14" in working.columns:
        has_rsi = working["rsi14"].notna()
        working = working[~has_rsi | (working["rsi14"] <= rsi14_max)]

    # ETF/instrument filter: require a GICS sector (excludes ETFs, indices)
    if require_sector and "sector" in working.columns:
        working = working[working["sector"].notna() & (working["sector"] != "")]

    return working


def _limit_per_sector(df_in: pd.DataFrame, limit: int) -> pd.DataFrame:
    """Keep top N tickers per sector by conviction_score."""
    if "sector" not in df_in.columns or df_in.empty:
        return df_in
    df_sorted = df_in.sort_values("conviction_score", ascending=False)
    kept = []
    sector_counts: dict[str, int] = {}
    for _, row in df_sorted.iterrows():
        sector = row.get("sector") or "Unknown"
        count = sector_counts.get(str(sector), 0)
        if count < limit:
            kept.append(row)
            sector_counts[str(sector)] = count + 1
    return pd.DataFrame(kept) if kept else pd.DataFrame(columns=df_in.columns)


def apply_filters_dual(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Apply dual-funnel filters.

    1. Apply shared pre-filters to ALL tickers (ARS, market cap, price, vol, earnings, MA10).
    2. Tier C exclusion on each funnel.
    3. Split by strategy: group_a (strategy in A/DUAL), group_b (strategy in B/DUAL).
    4. Per-strategy sector cap (max 3/sector) + top max_positions.
    5. DUAL tickers: allocate to whichever strategy has fewer slots (prefer A first).
    6. Combine: total watchlist = A_selected + B_selected (max 10 total).
    7. Progressive relaxation if total < 5: lower ars_min to 70, sector cap to 5, include Tier C.

    Returns final DataFrame with filter_note column.
    """
    if df.empty:
        log.warning("Empty DataFrame passed to filters.")
        return df

    cfg = config.get("filters", {})
    ars_min = cfg.get("ars_min", 80)
    ars_fallback = cfg.get("ars_fallback", 70)
    max_per_sector = cfg.get("max_per_sector", 3)
    max_per_sector_fallback = cfg.get("max_per_sector_fallback", 5)
    rsi14_max_b = cfg.get("rsi14_max_b", 60)

    # Per-strategy max_positions from strategies config
    strategies = config.get("strategies", [])
    max_pos_map: dict[str, int] = {}
    for st in strategies:
        max_pos_map[st["id"]] = st.get("max_positions", 5)
    max_pos_a = max_pos_map.get("A", 5)
    max_pos_b = max_pos_map.get("B", 5)

    notes: list[str] = []

    def _run_filters(
        df_in: pd.DataFrame,
        ars_threshold: float,
        sector_limit: int,
        include_tier_c: bool,
    ) -> pd.DataFrame:
        """Run shared filters + strategy split + selection."""
        # Shared pre-filters
        filtered = _apply_shared_filters(df_in, cfg, ars_threshold)
        _log_stage(f"Shared filters (ARS>={ars_threshold})", filtered)

        if filtered.empty:
            return filtered

        # Tier filter
        if "tier" in filtered.columns:
            if include_tier_c:
                filtered = filtered[filtered["tier"].isin(["A", "B", "C"])]
            else:
                filtered = filtered[filtered["tier"].isin(["A", "B"])]
        _log_stage("Tier filter", filtered)

        if filtered.empty:
            return filtered

        # Split by strategy membership
        # "strategy" column holds: "A", "B", or "DUAL"
        has_strategy = "strategy" in filtered.columns

        if has_strategy:
            group_a = filtered[filtered["strategy"].isin(["A", "DUAL"])].copy()
            group_b = filtered[filtered["strategy"].isin(["B", "DUAL"])].copy()
            dual = filtered[filtered["strategy"] == "DUAL"].copy()

            # Strategy B extra RSI filter: mean reversion should NOT be overbought
            if "rsi14" in group_b.columns:
                has_rsi = group_b["rsi14"].notna()
                group_b = group_b[~has_rsi | (group_b["rsi14"] <= rsi14_max_b)]
                if not dual.empty and "rsi14" in dual.columns:
                    has_rsi_d = dual["rsi14"].notna()
                    dual = dual[~has_rsi_d | (dual["rsi14"] <= rsi14_max_b)]
        else:
            # Fallback: treat everything as A
            group_a = filtered.copy()
            group_b = pd.DataFrame(columns=filtered.columns)
            dual = pd.DataFrame(columns=filtered.columns)

        # Apply sector cap to each group
        group_a_capped = _limit_per_sector(group_a, sector_limit)
        group_b_capped = _limit_per_sector(group_b, sector_limit)

        # Select top N from each group
        a_sorted = group_a_capped.sort_values("conviction_score", ascending=False)
        b_sorted = group_b_capped.sort_values("conviction_score", ascending=False)

        # DUAL tickers: allocate to whichever strategy has fewer slots (prefer A first)
        selected_a_syms: set[str] = set()
        selected_b_syms: set[str] = set()

        # Symbols that survived the sector cap in each group
        syms_a_capped = set(group_a_capped["symbol"].values) if not group_a_capped.empty else set()
        syms_b_capped = set(group_b_capped["symbol"].values) if not group_b_capped.empty else set()

        # Process DUAL tickers first — try to place in A, then B, respecting sector cap
        dual_syms = set(dual["symbol"].values) if not dual.empty else set()
        for sym in sorted(dual_syms, key=lambda s: -(filtered[filtered["symbol"] == s]["conviction_score"].iloc[0] if not filtered[filtered["symbol"] == s].empty else 0)):
            if len(selected_a_syms) < max_pos_a and sym in syms_a_capped:
                selected_a_syms.add(sym)
            elif len(selected_b_syms) < max_pos_b and sym in syms_b_capped:
                selected_b_syms.add(sym)

        # Fill remaining A slots from A-only tickers
        for _, row in a_sorted.iterrows():
            sym = row["symbol"]
            if sym in selected_a_syms:
                continue  # already allocated
            if row.get("strategy") == "B":
                continue  # B-only, skip for A
            if len(selected_a_syms) >= max_pos_a:
                break
            selected_a_syms.add(sym)

        # Fill remaining B slots from B-only tickers (exclude already-in-A)
        for _, row in b_sorted.iterrows():
            sym = row["symbol"]
            if sym in selected_b_syms or sym in selected_a_syms:
                continue
            if row.get("strategy") == "A":
                continue  # A-only, skip for B
            if len(selected_b_syms) >= max_pos_b:
                break
            selected_b_syms.add(sym)

        all_selected = selected_a_syms | selected_b_syms
        result = filtered[filtered["symbol"].isin(all_selected)].copy()
        result = result.sort_values("conviction_score", ascending=False).head(MAX_WATCHLIST)
        return result

    # First pass: strict filters
    result = _run_filters(df, ars_min, max_per_sector, include_tier_c=False)
    _log_stage(f"After first-pass filters", result)

    # Progressive relaxation if total < MIN_WATCHLIST: only relax ARS and sector cap, NOT tier
    if len(result) < MIN_WATCHLIST:
        log.info(
            f"Only {len(result)} tickers passed strict filters. "
            f"Relaxing: ARS→{ars_fallback}, sector cap→{max_per_sector_fallback} (Tier B minimum maintained)."
        )
        result = _run_filters(df, ars_fallback, max_per_sector_fallback, include_tier_c=False)
        _log_stage("After relaxed filters", result)
        notes.append(f"ARS threshold relaxed to {ars_fallback}")
        notes.append(f"Sector limit relaxed to {max_per_sector_fallback}")

    result = result.copy()
    result["filter_note"] = "; ".join(notes) if notes else ""

    if not result.empty:
        a_ct = result["strategy"].isin(["A", "DUAL"]).sum() if "strategy" in result.columns else 0
        b_ct = result["strategy"].isin(["B", "DUAL"]).sum() if "strategy" in result.columns else 0
        dual_ct = (result["strategy"] == "DUAL").sum() if "strategy" in result.columns else 0
        log.info(
            f"Final watchlist: {len(result)} tickers "
            f"(Tier A: {(result['tier']=='A').sum()}, Tier B: {(result['tier']=='B').sum()}, "
            f"Strategy A: {a_ct}, Strategy B: {b_ct}, DUAL: {dual_ct})."
        )

    return result.reset_index(drop=True)


def apply_filters(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Backward-compat wrapper: delegates to apply_filters_dual.
    If the DataFrame doesn't have a 'strategy' column, adds a default 'A'.
    """
    if "strategy" not in df.columns:
        df = df.copy()
        df["strategy"] = "A"
    return apply_filters_dual(df, config)
