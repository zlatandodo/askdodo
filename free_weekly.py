"""
AskLivermore Auto-Funnel — FREE version (no subscription required).
Uses only yfinance + Wikipedia data to implement 3 classic swing-trading patterns:
  - Livermore Buy the Dip
  - Pocket Pivot
  - Golden Pocket

Run: python3 free_weekly.py
"""
import logging
import logging.handlers
import os
import sys
import time
import traceback
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR    = Path(__file__).parent
LOG_DIR     = BASE_DIR / "logs"
OUTPUT_DIR  = BASE_DIR / "output"
DB_DIR      = BASE_DIR / "db"
DB_PATH     = DB_DIR / "trades_free.sqlite"
CONFIG_PATH = BASE_DIR / "free_config.yaml"

sys.path.insert(0, str(BASE_DIR))


def setup_logging(config: dict) -> logging.Logger:
    log_cfg = config.get("logging", {})
    level   = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "free_weekly.log",
        maxBytes=int(log_cfg.get("max_bytes", 10 * 1024 * 1024)),
        backupCount=int(log_cfg.get("backup_count", 5)),
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    return logging.getLogger("free_weekly")


@contextmanager
def step(log: logging.Logger, name: str):
    log.info(f"▶ {name}")
    t0 = time.perf_counter()
    try:
        yield
    finally:
        log.info(f"✓ {name} ({time.perf_counter() - t0:.1f}s)")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_env() -> dict:
    load_dotenv(BASE_DIR / ".env")
    return {k: os.environ.get(k, "") for k in
            ["GMAIL_APP_PASSWORD", "EMAIL_SENDER", "EMAIL_RECIPIENT", "CAPITAL_USD"]}


def check_internet() -> bool:
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    try:
        urllib.request.urlopen("https://www.google.com", timeout=10, context=ctx)
        return True
    except Exception:
        return False


def get_scanner_stats(scanner_results: dict) -> dict:
    return {
        name: {
            "count":  len(records) if records else 0,
            "status": "OK" if records is not None else "FAILED",
            "sample": [r.get("ticker", "") for r in (records or [])[:5]],
        }
        for name, records in scanner_results.items()
    }


def main() -> int:
    try:
        config = load_config()
    except Exception as e:
        print(f"FATAL: cannot load free_config.yaml: {e}", file=sys.stderr)
        return 1

    log      = setup_logging(config)
    env      = load_env()
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info(f"=== AskLivermore FREE Funnel | {run_date} ===")

    capital = float(env.get("CAPITAL_USD") or config.get("capital_usd", 100_000))
    config["capital_usd"] = capital

    from src.free_scanner   import run_free_scanners
    from src.simple_scoring import aggregate_scanners, score_and_filter
    from src.enrichment     import enrich_tickers
    from src.risk           import calculate_trade_plans
    from src.report_html    import generate_html
    from src.ibkr_export    import generate_ibkr_baskets
    from src.history        import init_db, save_run
    from src.notifier       import send_report_email, send_alert_email

    try:
        # ── 1. Health check ──────────────────────────────────────────────────
        with step(log, "Health check"):
            if not check_internet():
                log.error("No internet. Aborting.")
                send_alert_email("No internet", "Free weekly run aborted.", config, env)
                return 1
            log.info("Internet OK")

        # ── 2. Run free scanners (universe + pattern detection) ───────────────
        with step(log, "Free scanners (yfinance + Wikipedia)"):
            scanner_results, meta_map = run_free_scanners(config)

        scanner_stats = get_scanner_stats(scanner_results)

        n_ok = sum(1 for v in scanner_results.values() if v is not None)
        if n_ok == 0:
            msg = "All free scanner runs returned 0 results."
            log.error(msg)
            send_alert_email("Free scanner failed", msg, config, env)
            return 1

        # ── 3. Aggregate overlap → scored candidates ──────────────────────────
        with step(log, "Aggregate scanner overlap"):
            scored_df = aggregate_scanners(scanner_results, config)

        if scored_df.empty:
            log.error("No tickers found across all free scanners.")
            send_alert_email("Empty results", "All free scanners returned 0 tickers.", config, env)
            return 1

        log.info(
            f"Candidates: {len(scored_df)} unique tickers "
            f"(multi-scanner ≥2: {(scored_df['n_scanners'] >= 2).sum()})"
        )

        # ── 4. Enrich with yfinance (ATR, MA, RSI, earnings) ─────────────────
        # NOTE: enrichment re-downloads data for the shortlisted tickers only.
        # The full history was already downloaded for scanning, but we reuse
        # the enrichment module for consistency with the rest of the pipeline.
        with step(log, "Enrichment (yfinance)"):
            enriched_df = enrich_tickers(scored_df)

        # ── 5. Quality scoring + filters → final watchlist ───────────────────
        with step(log, "Quality scoring + filters"):
            filtered_df = score_and_filter(enriched_df, config)

        n = len(filtered_df)
        log.info(f"After filters: {n} tickers")

        if filtered_df.empty:
            msg = f"Run {run_date}: 0 tickers passed filters."
            log.warning(msg)
            send_alert_email("Empty watchlist (free)", msg, config, env)
            return 0

        # ── 6. Trade plans + position sizing ─────────────────────────────────
        with step(log, "Trade plans"):
            watchlist_df, portfolio_summary = calculate_trade_plans(filtered_df, config)

        portfolio_summary["run_date"] = run_date
        exposure = portfolio_summary.get("exposure_pct", 0)
        log.info(f"Portfolio: {n} positions, {exposure:.1f}% exposure")

        # ── 7-8. Generate reports ─────────────────────────────────────────────
        run_dir   = OUTPUT_DIR / f"{run_date}_free"
        run_dir.mkdir(parents=True, exist_ok=True)
        html_path = run_dir / f"report_free_{run_date}.html"

        with step(log, "HTML report"):
            generate_html(watchlist_df, portfolio_summary, run_date, html_path)

        with step(log, "IBKR baskets"):
            basket_path, stops_path = generate_ibkr_baskets(watchlist_df, run_dir, run_date)

        # ── 9. SQLite history ─────────────────────────────────────────────────
        with step(log, "Save to DB"):
            DB_DIR.mkdir(parents=True, exist_ok=True)
            init_db(DB_PATH)
            save_run(DB_PATH, run_date, watchlist_df, portfolio_summary, scanner_stats)

        # ── 10. Send email ────────────────────────────────────────────────────
        with step(log, "Send email"):
            subject_tmpl = config.get("email", {}).get(
                "subject_template",
                "📊 Watchlist FREE - {date} - {n} ticker (esposizione {exposure_pct}%)"
            )
            config["email"]["subject"] = subject_tmpl.format(
                date=run_date, n=n, exposure_pct=f"{exposure:.1f}"
            )
            attachments = [p for p in [basket_path, stops_path] if p.exists()]
            send_report_email(html_path.read_text(encoding="utf-8"), attachments, config, env)

        log.info(f"=== Done. {n} tickers | {exposure:.1f}% exposure | outputs → {run_dir} ===")
        return 0

    except Exception:
        tb = traceback.format_exc()
        log.error(f"Unhandled error:\n{tb}")
        try:
            send_alert_email(f"Free Pipeline Error {run_date}", tb, config, env)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
