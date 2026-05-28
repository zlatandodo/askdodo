"""
Dual-funnel conviction scoring for AskLivermore scanner results.
Runs Strategy A (Pullback in Uptrend) and Strategy B (Mean Reversion)
independently, then merges results with DUAL label for tickers in both.
"""
import logging
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)


def _fa_bonus(fa: Optional[float]) -> float:
    """Return FA conviction bonus based on FA score."""
    if fa is None or pd.isna(fa):
        return 0.0
    if fa >= 6.0:
        return 2.0
    if fa >= 4.5:
        return 1.0
    return 0.0


def _assign_tier(primary_count: int, confirm_count: int) -> str:
    """
    Assign Tier A, B, C, or DROP based on scanner hit counts.
    Rules (hardcoded):
      Tier A: primary>=3 and confirm>=1, OR primary>=2 and confirm>=2
      Tier B: primary>=2 and confirm>=1, OR primary>=1 and confirm>=2
      Tier C: primary>=1
      DROP otherwise
    """
    # Tier A
    if (primary_count >= 3 and confirm_count >= 1) or (primary_count >= 2 and confirm_count >= 2):
        return "A"
    # Tier B
    if (primary_count >= 2 and confirm_count >= 1) or (primary_count >= 1 and confirm_count >= 2):
        return "B"
    # Tier C
    if primary_count >= 1:
        return "C"
    return "DROP"


def _score_strategy(
    universe_df: pd.DataFrame,
    scanner_results: dict,
    strategy: dict,
) -> pd.DataFrame:
    """
    Score all tickers in universe_df for a single strategy.
    Returns DataFrame with one row per ticker.
    """
    strategy_id = strategy["id"]
    strategy_name = strategy["name"]
    strategy_scanners = strategy["scanners"]

    # Build O(1) lookup: scanner_name -> set of tickers present
    scanner_ticker_sets: dict[str, set] = {}
    for sc in strategy_scanners:
        sc_name = sc["name"]
        records = scanner_results.get(sc_name)
        if records:
            scanner_ticker_sets[sc_name] = {
                str(r.get("ticker", r.get("symbol", ""))).upper()
                for r in records
                if r.get("ticker") or r.get("symbol")
            }
        else:
            scanner_ticker_sets[sc_name] = set()

    # Non-universe scanners only (for scoring)
    scoring_scanners = [sc for sc in strategy_scanners if not sc.get("is_universe", False)]

    rows = []
    for _, row in universe_df.iterrows():
        sym = str(row.get("symbol", "")).upper()
        if not sym:
            continue

        conviction_score = 0.0
        primary_count = 0
        confirm_count = 0
        scanners_hit: list[str] = []

        for sc in scoring_scanners:
            sc_name = sc["name"]
            in_scanner = sym in scanner_ticker_sets.get(sc_name, set())
            if in_scanner:
                scanners_hit.append(sc_name)
                conviction_score += sc.get("weight", 0)
                if sc.get("primary", False):
                    primary_count += 1
                else:
                    confirm_count += 1

        # ARS contribution: ars/10
        ars_val = row.get("ars")
        if ars_val is not None and not pd.isna(ars_val):
            conviction_score += float(ars_val) / 10.0

        # FA bonus
        fa_val = row.get("fa")
        conviction_score += _fa_bonus(fa_val)

        tier = _assign_tier(primary_count, confirm_count)

        rows.append({
            "symbol": sym,
            "company_name": row.get("company_name"),
            "sector": row.get("sector"),
            "market_cap_m": row.get("market_cap_m"),
            "ars": ars_val,
            "ta": row.get("ta"),
            "fa": fa_val,
            "price": row.get("price"),
            "ma50": row.get("ma50"),
            "ma150": row.get("ma150"),
            "ma200": row.get("ma200"),
            "conviction_score": round(conviction_score, 2),
            "tier": tier,
            "primary_count": primary_count,
            "confirm_count": confirm_count,
            "scanners_hit": ", ".join(scanners_hit),
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("conviction_score", ascending=False).reset_index(drop=True)

    log.info(
        f"Strategy {strategy_id} ({strategy_name}): {len(result)} tickers scored. "
        f"Tier A: {(result['tier']=='A').sum() if not result.empty else 0}, "
        f"Tier B: {(result['tier']=='B').sum() if not result.empty else 0}, "
        f"Tier C: {(result['tier']=='C').sum() if not result.empty else 0}, "
        f"DROP: {(result['tier']=='DROP').sum() if not result.empty else 0}."
    )
    return result


def compute_scores_dual(
    universe_df: pd.DataFrame,
    scanner_results: dict[str, list[dict] | None],
    config: dict,
) -> pd.DataFrame:
    """
    Compute conviction scores for both strategies (A and B) independently,
    then merge their outputs with DUAL label for tickers appearing in both.

    Returns a single combined DataFrame sorted by conviction_score DESC,
    with a 'strategy' column ('A', 'B', or 'DUAL').
    """
    if universe_df.empty:
        log.warning("Universe is empty — no tickers to score.")
        return pd.DataFrame()

    strategies = config.get("strategies", [])
    if not strategies:
        log.warning("No strategies defined in config.")
        return pd.DataFrame()

    dual_bonus = float(config.get("dual_bonus", 5))

    # Score each strategy independently
    strategy_dfs: dict[str, pd.DataFrame] = {}
    for strategy in strategies:
        sid = strategy["id"]
        df = _score_strategy(universe_df, scanner_results, strategy)
        strategy_dfs[sid] = df

    # Merge: find tickers present in all strategies
    if len(strategy_dfs) < 2:
        # Only one strategy — return as-is
        sid = list(strategy_dfs.keys())[0]
        result = strategy_dfs[sid].copy()
        result["strategy"] = sid
        return result.sort_values("conviction_score", ascending=False).reset_index(drop=True)

    df_a = strategy_dfs.get("A", pd.DataFrame())
    df_b = strategy_dfs.get("B", pd.DataFrame())

    if df_a.empty and df_b.empty:
        return pd.DataFrame()

    # Only count a ticker as qualifying for a strategy if it has at least 1 scanner hit (tier != DROP)
    syms_a = set(df_a[df_a["tier"] != "DROP"]["symbol"].values) if not df_a.empty else set()
    syms_b = set(df_b[df_b["tier"] != "DROP"]["symbol"].values) if not df_b.empty else set()
    syms_dual = syms_a & syms_b

    # Each universe symbol gets exactly ONE row in the output.
    # Priority: DUAL > A-only (non-DROP for A) > B-only (non-DROP for B) > DROP (neither)
    all_universe_syms = set(df_a["symbol"].values) if not df_a.empty else set()
    syms_a_only = syms_a - syms_dual       # non-DROP for A, not DUAL
    syms_b_only = syms_b - syms_dual       # non-DROP for B, not DUAL
    syms_neither = all_universe_syms - syms_a - syms_b  # DROP in both

    merged_rows = []

    # A-only tickers (non-DROP for A, not in B at all)
    for _, row in df_a[df_a["symbol"].isin(syms_a_only)].iterrows():
        r = row.to_dict()
        r["strategy"] = "A"
        merged_rows.append(r)

    # B-only tickers (non-DROP for B, not in A at all)
    for _, row in df_b[df_b["symbol"].isin(syms_b_only)].iterrows():
        r = row.to_dict()
        r["strategy"] = "B"
        merged_rows.append(r)

    # DROP tickers (qualify for neither strategy): include once from df_a
    for _, row in df_a[df_a["symbol"].isin(syms_neither)].iterrows():
        r = row.to_dict()
        r["strategy"] = "DROP"
        merged_rows.append(r)

    # DUAL tickers: pick best score from either strategy, add dual_bonus
    score_a = df_a.set_index("symbol")["conviction_score"] if not df_a.empty else pd.Series(dtype=float)
    score_b = df_b.set_index("symbol")["conviction_score"] if not df_b.empty else pd.Series(dtype=float)

    for sym in syms_dual:
        sa = score_a.get(sym, 0.0)
        sb = score_b.get(sym, 0.0)
        best_score = max(sa, sb) + dual_bonus

        # Use the row from whichever strategy had the higher score
        if sa >= sb:
            base_row = df_a[df_a["symbol"] == sym].iloc[0].to_dict()
        else:
            base_row = df_b[df_b["symbol"] == sym].iloc[0].to_dict()

        base_row["conviction_score"] = round(best_score, 2)
        base_row["strategy"] = "DUAL"

        # Combine scanners_hit from both strategies
        hit_a = set(s.strip() for s in (df_a[df_a["symbol"] == sym].iloc[0].get("scanners_hit", "") or "").split(",") if s.strip())
        hit_b = set(s.strip() for s in (df_b[df_b["symbol"] == sym].iloc[0].get("scanners_hit", "") or "").split(",") if s.strip())
        base_row["scanners_hit"] = ", ".join(sorted(hit_a | hit_b))

        merged_rows.append(base_row)

    result = pd.DataFrame(merged_rows)
    if not result.empty:
        result = result.sort_values("conviction_score", ascending=False).reset_index(drop=True)

    if not result.empty:
        a_count = (result["strategy"] == "A").sum()
        b_count = (result["strategy"] == "B").sum()
        dual_count = (result["strategy"] == "DUAL").sum()
        log.info(
            f"Dual-funnel scoring complete: {len(result)} total. "
            f"A: {a_count}, B: {b_count}, DUAL: {dual_count}."
        )

    return result


# Backward-compat alias: keep compute_scores for any direct callers
def compute_scores(
    universe_df: pd.DataFrame,
    all_scanners_df: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """
    Legacy wrapper. Converts all_scanners_df back into scanner_results dict
    and delegates to compute_scores_dual.
    """
    # Reconstruct scanner_results dict from all_scanners_df
    scanner_results: dict[str, list[dict] | None] = {}
    if not all_scanners_df.empty and "scanner_name" in all_scanners_df.columns:
        for sc_name, grp in all_scanners_df.groupby("scanner_name"):
            scanner_results[str(sc_name)] = [
                {"ticker": str(r).upper()}
                for r in grp["symbol"].dropna()
            ]

    # If config uses old-style (no strategies), build minimal strategies from scanners
    if "strategies" not in config:
        scanners_cfg = config.get("scanners", [])
        weights = config.get("scanner_weights", {})
        strategy_scanners = []
        for sc in scanners_cfg:
            name = sc["name"]
            strategy_scanners.append({
                "name": name,
                "slug": sc.get("slug", name),
                "is_universe": sc.get("is_universe", False),
                "primary": sc.get("primary", False),
                "weight": weights.get(name, 0),
            })
        config = dict(config)
        config["strategies"] = [{
            "id": "A",
            "name": "Default",
            "max_positions": 10,
            "universe_scanner": "trend_template",
            "scanners": strategy_scanners,
        }]
        config["dual_bonus"] = 0

    return compute_scores_dual(universe_df, scanner_results, config)
