"""
Trade plan and position sizing calculation.
All parameters sourced from config.yaml — no hardcoded magic numbers.
"""
import logging
import math
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)


def _calc_position(
    entry: float,
    stop: float,
    capital: float,
    risk_per_trade_pct: float,
    max_position_pct: float,
) -> tuple[float, int, float, float]:
    """
    Calculate position size.
    Returns (size_usd, size_shares, size_pct, risk_usd).
    """
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return 0.0, 0, 0.0, 0.0

    risk_usd = capital * risk_per_trade_pct
    raw_size_usd = risk_usd / (risk_per_share / entry)  # based on % stop

    # Alternative: direct size from risk
    direct_size_usd = risk_usd * entry / risk_per_share

    # Use the more conservative
    size_usd = min(direct_size_usd, capital * max_position_pct)
    size_usd = max(size_usd, 0.0)

    size_shares = math.floor(size_usd / entry)
    actual_size_usd = size_shares * entry
    size_pct = actual_size_usd / capital if capital > 0 else 0.0
    actual_risk_usd = size_shares * risk_per_share

    return actual_size_usd, size_shares, size_pct, actual_risk_usd


def calculate_trade_plans(
    df: pd.DataFrame,
    config: dict,
) -> tuple[pd.DataFrame, dict]:
    """
    Calculate entry, stop, targets, and position sizes for each ticker.

    Adds columns: entry, stop, target1, target2, risk_per_share,
    size_usd, size_shares, size_pct, risk_usd, rr_t1, rr_t2.

    Returns (enriched_df, portfolio_summary).
    """
    capital = float(config.get("capital_usd", 100_000))
    risk_per_trade_pct = float(config.get("risk_per_trade_pct", 0.0075))
    trade_plan_cfg = config.get("trade_plan", {})
    max_pos_cfg = config.get("max_position_pct", {})

    atr_stop_mult = float(trade_plan_cfg.get("atr_stop_multiplier", 1.5))
    atr_t1_mult = float(trade_plan_cfg.get("atr_target1_multiplier", 2.0))
    atr_t2_mult = float(trade_plan_cfg.get("atr_target2_multiplier", 5.0))
    max_stop_pct = float(trade_plan_cfg.get("max_stop_pct", 0.10))

    max_pos_a = float(max_pos_cfg.get("tier_a", 0.05))
    max_pos_b = float(max_pos_cfg.get("tier_b", 0.035))
    hard_cap = float(max_pos_cfg.get("hard_cap", 0.06))

    result_rows = []
    total_allocated_usd = 0.0
    total_risk_usd = 0.0

    for _, row in df.iterrows():
        price = row.get("price")
        atr14 = row.get("atr14")
        tier = row.get("tier", "C")

        # Determine max position size based on tier
        if tier == "A":
            max_position_pct = min(max_pos_a, hard_cap)
        else:
            max_position_pct = min(max_pos_b, hard_cap)

        # Compute entry (use current price as entry point)
        entry: Optional[float] = float(price) if price is not None and not pd.isna(price) else None

        stop: Optional[float] = None
        target1: Optional[float] = None
        target2: Optional[float] = None
        risk_per_share: Optional[float] = None
        size_usd: Optional[float] = None
        size_shares: Optional[int] = None
        size_pct: Optional[float] = None
        risk_usd: Optional[float] = None
        rr_t1: Optional[float] = None
        rr_t2: Optional[float] = None

        if entry and atr14 and not pd.isna(atr14) and atr14 > 0:
            atr = float(atr14)

            # Stop: entry - 1.5 * ATR, floored at max_stop_pct below entry
            raw_stop = entry - atr_stop_mult * atr
            min_stop = entry * (1 - max_stop_pct)
            stop = max(raw_stop, min_stop)
            stop = round(stop, 2)

            target1 = round(entry + atr_t1_mult * atr, 2)
            target2 = round(entry + atr_t2_mult * atr, 2)

            risk_per_share = round(entry - stop, 2)

            s_usd, s_shares, s_pct, r_usd = _calc_position(
                entry=entry,
                stop=stop,
                capital=capital,
                risk_per_trade_pct=risk_per_trade_pct,
                max_position_pct=max_position_pct,
            )
            size_usd = round(s_usd, 2)
            size_shares = s_shares
            size_pct = round(s_pct * 100, 2)  # as percentage
            risk_usd = round(r_usd, 2)

            if risk_per_share and risk_per_share > 0:
                rr_t1 = round((target1 - entry) / risk_per_share, 2)
                rr_t2 = round((target2 - entry) / risk_per_share, 2)

            total_allocated_usd += size_usd or 0
            total_risk_usd += risk_usd or 0

        new_row = row.to_dict()
        new_row.update({
            "entry": round(entry, 2) if entry else None,
            "stop": stop,
            "target1": target1,
            "target2": target2,
            "risk_per_share": risk_per_share,
            "size_usd": size_usd,
            "size_shares": size_shares,
            "size_pct": size_pct,
            "risk_usd": risk_usd,
            "rr_t1": rr_t1,
            "rr_t2": rr_t2,
        })
        result_rows.append(new_row)

    result_df = pd.DataFrame(result_rows)

    exposure_pct = round(total_allocated_usd / capital * 100, 1) if capital > 0 else 0
    total_risk_pct = round(total_risk_usd / capital * 100, 2) if capital > 0 else 0

    tier_counts = result_df["tier"].value_counts().to_dict() if not result_df.empty else {}

    portfolio_summary = {
        "capital_usd": capital,
        "n_positions": len(result_df),
        "total_allocated_usd": round(total_allocated_usd, 2),
        "exposure_pct": exposure_pct,
        "total_risk_usd": round(total_risk_usd, 2),
        "total_risk_pct": total_risk_pct,
        "tier_a_count": tier_counts.get("A", 0),
        "tier_b_count": tier_counts.get("B", 0),
        "tier_c_count": tier_counts.get("C", 0),
        "risk_per_trade_pct": round(risk_per_trade_pct * 100, 3),
    }

    log.info(
        f"Trade plans: {len(result_df)} positions, "
        f"exposure {exposure_pct}%, total risk {total_risk_pct}%."
    )
    return result_df, portfolio_summary
