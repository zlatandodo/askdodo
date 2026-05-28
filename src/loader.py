"""
Loads and normalizes AskLivermore API results into DataFrames.
"""
import logging
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

# API field → our normalized column name
FIELD_MAP = {
    "ticker":        "symbol",
    "name":          "company_name",
    "sector":        "sector",
    "market_cap":    "market_cap_usd",
    "ta_rating":     "ta",
    "fa_rating":     "fa",
    "rs_rating":     "ars",
    "change_pct":    "pct_chg",
    "avg_vol_50":    "avg_vol",
    "price":         "price",
    "ma50":          "ma50",
    "ma150":         "ma150",
    "ma200":         "ma200",
    "vol_ratio":     "vol_ratio",
    "pct_above_200": "pct_above_200",
    "pct_from_high": "pct_from_high",
}


def _normalize_record(record: dict) -> dict:
    """Map API fields to internal column names."""
    out = {}
    for api_field, col in FIELD_MAP.items():
        out[col] = record.get(api_field)
    mc = out.get("market_cap_usd")
    out["market_cap_m"] = (mc / 1_000_000) if mc else None
    if out.get("symbol"):
        out["symbol"] = str(out["symbol"]).upper().strip()
    return out


def build_dataframes(
    scanner_results: dict[str, Optional[list[dict]]],
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build (universe_df, all_scanners_df) from raw API results.
    universe_df: tickers from trend_template
    all_scanners_df: all tickers across all scanners with scanner_name column
    """
    universe_df = pd.DataFrame()
    all_rows: list[dict] = []
    scanner_cfgs = {s["name"]: s for s in config.get("scanners", [])}

    for scanner_name, records in scanner_results.items():
        if records is None:
            log.warning(f"[{scanner_name}] No data — skipped.")
            continue
        normalized = [_normalize_record(r) for r in records]
        for row in normalized:
            row["scanner_name"] = scanner_name
        all_rows.extend(normalized)

        if scanner_cfgs.get(scanner_name, {}).get("is_universe"):
            universe_df = pd.DataFrame([_normalize_record(r) for r in records])
            log.info(f"Universe (trend_template): {len(universe_df)} tickers")

    all_df = pd.DataFrame(all_rows) if all_rows else pd.DataFrame()

    numeric_cols = ["ta", "fa", "ars", "pct_chg", "avg_vol", "market_cap_m", "price",
                    "ma50", "ma150", "ma200", "vol_ratio", "pct_above_200", "pct_from_high"]
    for col in numeric_cols:
        for df in [universe_df, all_df]:
            if not df.empty and col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

    log.info(f"Loader: universe={len(universe_df)}, all_scanners rows={len(all_df)}")
    return universe_df, all_df


def get_scanner_stats(scanner_results: dict[str, Optional[list[dict]]]) -> dict:
    """Summary dict for reporting."""
    return {
        name: {
            "count": len(records) if records else 0,
            "status": "OK" if records is not None else "FAILED",
            "sample": [r.get("ticker", "") for r in (records or [])[:5]],
        }
        for name, records in scanner_results.items()
    }
