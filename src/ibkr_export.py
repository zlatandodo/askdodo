"""
Generate IBKR basket CSV files for order entry.
Produces a buy basket and a stop-loss basket.
"""
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

BASKET_COLUMNS = [
    "Action", "Quantity", "Symbol", "SecType", "Exchange",
    "Currency", "TimeInForce", "OrderType", "LmtPrice",
    "BasketTag", "Account",
]

STOP_COLUMNS = [
    "Action", "Quantity", "Symbol", "SecType", "Exchange",
    "Currency", "TimeInForce", "OrderType", "AuxPrice",
    "BasketTag", "Account",
]


def _safe_int(val) -> int:
    """Convert value to int safely."""
    try:
        v = int(val)
        return max(v, 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(val, decimals: int = 2) -> float:
    """Convert value to float safely."""
    try:
        return round(float(val), decimals)
    except (TypeError, ValueError):
        return 0.0


def generate_ibkr_baskets(
    watchlist_df: pd.DataFrame,
    output_dir: Path,
    run_date: str,
) -> tuple[Path, Path]:
    """
    Generate IBKR basket CSVs for the watchlist.

    Basket (buy orders at limit price):
      Action, Quantity, Symbol, SecType, Exchange, Currency,
      TimeInForce, OrderType, LmtPrice, BasketTag, Account

    Stops (sell stop orders):
      Action, Quantity, Symbol, SecType, Exchange, Currency,
      TimeInForce, OrderType, AuxPrice, BasketTag, Account

    Returns (basket_path, stops_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    basket_path = output_dir / f"ibkr_basket_{run_date}.csv"
    stops_path = output_dir / f"ibkr_stops_{run_date}.csv"

    basket_rows = []
    stop_rows = []

    for _, row in watchlist_df.iterrows():
        sym = str(row.get("symbol", "")).strip().upper()
        if not sym:
            continue

        shares = _safe_int(row.get("size_shares"))
        entry = _safe_float(row.get("entry"))
        stop = _safe_float(row.get("stop"))
        tier = str(row.get("tier", "")).strip()
        strategy = str(row.get("strategy", "")).strip()

        if shares <= 0 or entry <= 0:
            log.debug(f"[{sym}] Skipping — no valid size or entry price.")
            continue

        basket_tag_buy = f"AskLivermore_{strategy}_Tier{tier}_{sym}"
        basket_tag_stop = f"AskLivermore_STOP_{strategy}_Tier{tier}_{sym}"

        # Buy order — limit at entry price
        basket_rows.append({
            "Action": "BUY",
            "Quantity": shares,
            "Symbol": sym,
            "SecType": "STK",
            "Exchange": "SMART",
            "Currency": "USD",
            "TimeInForce": "DAY",
            "OrderType": "LMT",
            "LmtPrice": entry,
            "BasketTag": basket_tag_buy,
            "Account": "",
        })

        # Stop order — sell stop at stop price (only if stop is valid)
        if stop > 0:
            stop_rows.append({
                "Action": "SELL",
                "Quantity": shares,
                "Symbol": sym,
                "SecType": "STK",
                "Exchange": "SMART",
                "Currency": "USD",
                "TimeInForce": "GTC",
                "OrderType": "STP",
                "AuxPrice": stop,
                "BasketTag": basket_tag_stop,
                "Account": "",
            })

    basket_df = pd.DataFrame(basket_rows, columns=BASKET_COLUMNS) if basket_rows else pd.DataFrame(columns=BASKET_COLUMNS)
    stops_df = pd.DataFrame(stop_rows, columns=STOP_COLUMNS) if stop_rows else pd.DataFrame(columns=STOP_COLUMNS)

    basket_df.to_csv(basket_path, index=False)
    stops_df.to_csv(stops_path, index=False)

    log.info(f"IBKR basket: {len(basket_df)} buy orders → {basket_path}")
    log.info(f"IBKR stops:  {len(stops_df)} stop orders → {stops_path}")

    return basket_path, stops_path
