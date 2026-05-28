"""
SQLite-based run history tracking.
Tables: runs (metadata), positions (per-ticker per-run), scanner_stats.
"""
import json
import logging
import sqlite3
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    run_ts TEXT NOT NULL,
    n_positions INTEGER,
    exposure_pct REAL,
    total_risk_pct REAL,
    total_allocated_usd REAL,
    tier_a_count INTEGER,
    tier_b_count INTEGER,
    portfolio_summary_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    run_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    company_name TEXT,
    sector TEXT,
    tier TEXT,
    conviction_score REAL,
    price REAL,
    entry REAL,
    stop REAL,
    target1 REAL,
    target2 REAL,
    size_usd REAL,
    size_shares INTEGER,
    size_pct REAL,
    risk_usd REAL,
    rr_t1 REAL,
    rr_t2 REAL,
    ars REAL,
    ta REAL,
    fa REAL,
    scanners_hit TEXT,
    next_earnings_date TEXT,
    days_to_earnings INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scanner_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    run_date TEXT NOT NULL,
    scanner_name TEXT NOT NULL,
    csv_available INTEGER,
    ticker_count INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def init_db(db_path: Path) -> None:
    """Initialize SQLite database and create tables if they don't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    log.info(f"Database initialized: {db_path}")


def save_run(
    db_path: Path,
    run_date: str,
    watchlist_df: pd.DataFrame,
    portfolio_summary: dict,
    scanner_stats: dict = None,
) -> int:
    """
    Persist a run to the database.
    Returns the new run_id.
    """
    from datetime import datetime, timezone

    run_ts = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()

        # Insert run record
        cursor.execute(
            """
            INSERT INTO runs (
                run_date, run_ts, n_positions, exposure_pct, total_risk_pct,
                total_allocated_usd, tier_a_count, tier_b_count, portfolio_summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_date,
                run_ts,
                portfolio_summary.get("n_positions", 0),
                portfolio_summary.get("exposure_pct"),
                portfolio_summary.get("total_risk_pct"),
                portfolio_summary.get("total_allocated_usd"),
                portfolio_summary.get("tier_a_count", 0),
                portfolio_summary.get("tier_b_count", 0),
                json.dumps(portfolio_summary),
            ),
        )
        run_id = cursor.lastrowid

        # Insert positions
        for _, row in watchlist_df.iterrows():
            cursor.execute(
                """
                INSERT INTO positions (
                    run_id, run_date, symbol, company_name, sector, tier,
                    conviction_score, price, entry, stop, target1, target2,
                    size_usd, size_shares, size_pct, risk_usd, rr_t1, rr_t2,
                    ars, ta, fa, scanners_hit, next_earnings_date, days_to_earnings
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    run_id,
                    run_date,
                    row.get("symbol"),
                    row.get("company_name"),
                    row.get("sector"),
                    row.get("tier"),
                    row.get("conviction_score"),
                    row.get("price"),
                    row.get("entry"),
                    row.get("stop"),
                    row.get("target1"),
                    row.get("target2"),
                    row.get("size_usd"),
                    row.get("size_shares"),
                    row.get("size_pct"),
                    row.get("risk_usd"),
                    row.get("rr_t1"),
                    row.get("rr_t2"),
                    row.get("ars"),
                    row.get("ta"),
                    row.get("fa"),
                    row.get("scanners_hit"),
                    row.get("next_earnings_date"),
                    row.get("days_to_earnings"),
                ),
            )

        # Insert scanner stats if provided
        if scanner_stats:
            for sc_name, info in scanner_stats.items():
                cursor.execute(
                    """
                    INSERT INTO scanner_stats (run_id, run_date, scanner_name, csv_available, ticker_count)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        run_date,
                        sc_name,
                        1 if info.get("available") else 0,
                        info.get("count", 0),
                    ),
                )

        conn.commit()

    log.info(f"Run saved to DB: run_id={run_id}, date={run_date}, positions={len(watchlist_df)}")
    return run_id


def get_recent_runs(db_path: Path, n: int = 10) -> list[dict]:
    """Return the n most recent runs with their positions."""
    if not db_path.exists():
        return []

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (n,)
        )
        runs = [dict(r) for r in cursor.fetchall()]

        for run in runs:
            cursor.execute(
                "SELECT * FROM positions WHERE run_id = ? ORDER BY conviction_score DESC",
                (run["id"],),
            )
            run["positions"] = [dict(p) for p in cursor.fetchall()]

    log.debug(f"Retrieved {len(runs)} recent runs from DB.")
    return runs
