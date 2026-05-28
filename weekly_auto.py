"""
AskLivermore Auto-Funnel — Weekly Orchestrator
Run: python3 weekly_auto.py
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

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"
DB_DIR = BASE_DIR / "db"
DB_PATH = DB_DIR / "trades.sqlite"
CONFIG_PATH = BASE_DIR / "config.yaml"

sys.path.insert(0, str(BASE_DIR))


def setup_logging(config: dict) -> logging.Logger:
    """Configure rotating file + console handlers."""
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "weekly_auto.log",
        maxBytes=int(log_cfg.get("max_bytes", 10 * 1024 * 1024)),
        backupCount=int(log_cfg.get("backup_count", 5)),
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    return logging.getLogger("weekly_auto")


@contextmanager
def step(log: logging.Logger, name: str):
    """Log step start/end/duration."""
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
    env = {k: os.environ.get(k, "") for k in
           ["ASKLIVERMORE_EMAIL", "ASKLIVERMORE_PASSWORD",
            "GMAIL_APP_PASSWORD", "EMAIL_SENDER", "EMAIL_RECIPIENT", "CAPITAL_USD"]}
    return env


def check_internet() -> bool:
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        urllib.request.urlopen("https://www.google.com", timeout=10, context=ctx)
        return True
    except Exception:
        return False


def main() -> int:
    try:
        config = load_config()
    except Exception as e:
        print(f"FATAL: cannot load config.yaml: {e}", file=sys.stderr)
        return 1

    log = setup_logging(config)
    env = load_env()
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info(f"=== AskLivermore Auto-Funnel | {run_date} ===")

    capital = float(env.get("CAPITAL_USD") or config.get("capital_usd", 100000))
    config["capital_usd"] = capital

    from src.scraper import run_all_downloads, AuthError
    from src.loader import get_scanner_stats
    from src.simple_scoring import aggregate_scanners, score_and_filter
    from src.enrichment import enrich_tickers
    from src.risk import calculate_trade_plans
    from src.report_excel import generate_excel
    from src.report_html import generate_html
    from src.ibkr_export import generate_ibkr_baskets
    from src.history import init_db, save_run
    from src.notifier import send_report_email, send_alert_email

    try:
        # ── 1. Health check ──────────────────────────────────────────────────
        with step(log, "Health check"):
            if not check_internet():
                log.error("No internet. Aborting.")
                send_alert_email("No internet", "Weekly run aborted — no internet.", config, env)
                return 1
            log.info("Internet OK")

        # ── 2. Fetch scanners via API ────────────────────────────────────────
        scanner_names = [s["name"] for s in config.get("scanners", [])]
        with step(log, f"Fetch {len(scanner_names)} scanners (API)"):
            scanner_results = run_all_downloads(config)

        scanner_stats = get_scanner_stats(scanner_results)

        n_ok = sum(1 for v in scanner_results.values() if v is not None)
        if n_ok == 0:
            log.error("All scanner fetches failed — cannot continue.")
            send_alert_email("Fetch failed", "All scanner API calls failed.", config, env)
            return 1

        # ── 3. Aggregate scanner results → scored candidates ─────────────────
        with step(log, "Aggregate scanner overlap"):
            scored_df = aggregate_scanners(scanner_results, config)

        if scored_df.empty:
            log.error("No tickers found across all scanners.")
            send_alert_email("Empty results", "All scanners returned 0 tickers.", config, env)
            return 1

        log.info(
            f"Candidates: {len(scored_df)} unique tickers "
            f"(multi-scanner ≥2: {(scored_df['n_scanners'] >= 2).sum()})"
        )

        # ── 4. Enrich with yfinance (price, ATR, MA, RSI, earnings) ──────────
        with step(log, "Enrichment (yfinance)"):
            enriched_df = enrich_tickers(scored_df)

        # ── 5. Quality scoring + filters → final watchlist ───────────────────
        with step(log, "Quality scoring + filters"):
            filtered_df = score_and_filter(enriched_df, config)

        n = len(filtered_df)
        log.info(f"After filters: {n} tickers")

        if filtered_df.empty:
            msg = f"Run {run_date}: 0 tickers passed filters. Regime may be weak."
            log.warning(msg)
            send_alert_email("Empty watchlist", msg, config, env)
            return 0

        # ── 7. Trade plans + position sizing ────────────────────────────────
        with step(log, "Trade plans"):
            watchlist_df, portfolio_summary = calculate_trade_plans(filtered_df, config)

        portfolio_summary["run_date"] = run_date
        exposure = portfolio_summary.get("exposure_pct", 0)
        log.info(f"Portfolio: {n} positions, {exposure:.1f}% exposure")

        # ── 8-10. Generate reports ───────────────────────────────────────────
        run_dir = OUTPUT_DIR / run_date
        run_dir.mkdir(parents=True, exist_ok=True)
        excel_path = run_dir / f"watchlist_{run_date}.xlsx"
        html_path  = run_dir / f"report_{run_date}.html"

        with step(log, "Excel report"):
            generate_excel(watchlist_df, enriched_df, portfolio_summary, scanner_stats, excel_path)

        with step(log, "HTML report"):
            generate_html(watchlist_df, portfolio_summary, run_date, html_path)

        with step(log, "IBKR baskets"):
            basket_path, stops_path = generate_ibkr_baskets(watchlist_df, run_dir, run_date)

        # ── 11. SQLite history ───────────────────────────────────────────────
        with step(log, "Save to DB"):
            DB_DIR.mkdir(parents=True, exist_ok=True)
            init_db(DB_PATH)
            save_run(DB_PATH, run_date, watchlist_df, portfolio_summary, scanner_stats)

        # ── 12. Send email ───────────────────────────────────────────────────
        with step(log, "Send email"):
            subject_tmpl = config.get("email", {}).get(
                "subject_template",
                "📊 AskLivermore Watchlist - {date} - {n} ticker (esposizione {exposure_pct}%)"
            )
            config["email"]["subject"] = subject_tmpl.format(
                date=run_date, n=n, exposure_pct=f"{exposure:.1f}"
            )
            attachments = [p for p in [excel_path, basket_path, stops_path] if p.exists()]
            send_report_email(html_path.read_text(encoding="utf-8"), attachments, config, env)

        log.info(f"=== Done. {n} tickers | {exposure:.1f}% exposure | outputs → {run_dir} ===")
        return 0

    except AuthError as e:
        log.error(f"Auth failed: {e}")
        send_alert_email("Auth Error", str(e), config, env)
        return 1

    except Exception:
        tb = traceback.format_exc()
        log.error(f"Unhandled error:\n{tb}")
        try:
            send_alert_email(f"Pipeline Error {run_date}", tb, config, env)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
