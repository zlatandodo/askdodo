"""
Momentum Focus List — standalone runner.
Scansiona S&P 1500 e individua i migliori setup momentum
basati sul framework di Sean (swing trading).

Run: python3 momentum_weekly.py
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

BASE_DIR         = Path(__file__).parent
LOG_DIR          = BASE_DIR / "logs"
OUTPUT_DIR       = BASE_DIR / "output"
CONFIG_PATH      = BASE_DIR / "momentum_config.yaml"
FOCUS_LIST_PATH  = BASE_DIR / "db" / "momentum_focus_list.json"

sys.path.insert(0, str(BASE_DIR))

# Fix per launchd: yfinance cache in percorso esplicito (evita OperationalError SQLite)
import yfinance as yf
_YF_CACHE = BASE_DIR / ".yf_cache"
_YF_CACHE.mkdir(exist_ok=True)
yf.set_tz_cache_location(str(_YF_CACHE))


def setup_logging(config: dict) -> logging.Logger:
    log_cfg = config.get("logging", {})
    level   = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "momentum_weekly.log",
        maxBytes=int(log_cfg.get("max_bytes", 10 * 1024 * 1024)),
        backupCount=int(log_cfg.get("backup_count", 5)),
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    return logging.getLogger("momentum_weekly")


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


def main() -> int:
    try:
        config = load_config()
    except Exception as e:
        print(f"FATAL: cannot load momentum_config.yaml: {e}", file=sys.stderr)
        return 1

    log      = setup_logging(config)
    env      = load_env()
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info(f"=== Momentum Focus List | {run_date} ===")

    import json
    from src.free_scanner      import get_universe, download_history
    from src.momentum_scanner  import check_market_regime, scan_momentum, enrich_with_fundamentals
    from src.momentum_report   import generate_momentum_html, generate_momentum_excel
    from src.notifier          import send_report_email, send_alert_email

    try:
        # ── 1. Health check ──────────────────────────────────────────────────
        with step(log, "Health check"):
            if not check_internet():
                log.error("No internet. Aborting.")
                send_alert_email("No internet", "Momentum run aborted.", config, env)
                return 1
            log.info("Internet OK")

        # ── 2. Universe ───────────────────────────────────────────────────────
        with step(log, "Universe (S&P 500 + 400 + 600)"):
            symbols, meta_map = get_universe(config)
            if not symbols:
                log.error("Empty universe.")
                return 1
            log.info(f"{len(symbols)} symbols")

        # ── 3. Download history ───────────────────────────────────────────────
        all_symbols = ["SPY", "QQQ"] + [s for s in symbols if s not in ("SPY", "QQQ")]
        with step(log, f"Download OHLCV ({len(all_symbols)} symbols)"):
            hist_data = download_history(all_symbols)
            log.info(f"{len(hist_data)} symbols OK")

        # ── 4. Market regime ─────────────────────────────────────────────────
        with step(log, "Market regime check"):
            regime = check_market_regime(hist_data)
            for sym, d in regime.get("details", {}).items():
                status = "✅ BULL" if d["bullish"] else "⚠️ WEAK"
                log.info(f"  {sym}: {status} — price={d['price']} EMA21={d['ema21']} EMA50={d['ema50']}")
            log.info(f"  Overall: {'BULLISH' if regime['bullish'] else 'WEAK'}")

        # ── 5. Momentum scan ─────────────────────────────────────────────────
        with step(log, "Momentum scan"):
            cfg = config.get("momentum", {})
            focus_list = scan_momentum(hist_data, meta_map, cfg)

        n = len(focus_list)
        log.info(f"Focus list: {n} setups")

        # Save focus list for daily breakout_alert.py
        DB_DIR = BASE_DIR / "db"
        DB_DIR.mkdir(parents=True, exist_ok=True)
        with open(FOCUS_LIST_PATH, "w") as f:
            json.dump(focus_list, f, indent=2)
        log.info(f"Focus list saved → {FOCUS_LIST_PATH}")

        if not focus_list:
            msg = f"Run {run_date}: 0 momentum setups found."
            log.warning(msg)
            send_alert_email("Empty Momentum Focus List", msg, config, env)
            return 0

        # ── 6. Enrich with fundamentals (description, revenue, last week vol) ─
        # Pausa 60s: il download di 1500 ticker esaurisce il rate limit yfinance.
        # .info richiede un endpoint diverso — aspettiamo che si resetti.
        log.info("Pausa 90s prima dell'enrich (rate limit yfinance post-bulk-download)...")
        time.sleep(90)
        with step(log, "Fundamentals enrichment"):
            focus_list = enrich_with_fundamentals(focus_list, hist_data)

        # ── 7. HTML report ───────────────────────────────────────────────────
        run_dir   = OUTPUT_DIR / f"{run_date}_momentum"
        run_dir.mkdir(parents=True, exist_ok=True)
        html_path = run_dir / f"momentum_{run_date}.html"

        with step(log, "HTML report"):
            generate_momentum_html(focus_list, regime, run_date, html_path)

        excel_path = run_dir / f"momentum_{run_date}.xlsx"
        with step(log, "Excel report"):
            generate_momentum_excel(focus_list, run_date, excel_path)

        # ── 8. Send email ─────────────────────────────────────────────────────
        with step(log, "Send email"):
            subject_tmpl = config.get("email", {}).get(
                "subject_template",
                "🚀 Momentum Focus List - {date} - {n} setup"
            )
            config["email"]["subject"] = subject_tmpl.format(date=run_date, n=n)
            send_report_email(html_path.read_text(encoding="utf-8"), [excel_path], config, env)

        log.info(f"=== Done. {n} setups | outputs → {run_dir} ===")
        return 0

    except Exception:
        tb = traceback.format_exc()
        log.error(f"Unhandled error:\n{tb}")
        try:
            send_alert_email(f"Momentum Pipeline Error {run_date}", tb, config, env)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
