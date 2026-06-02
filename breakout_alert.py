"""
Breakout Alert — runs daily after market close (Mon-Fri, ~22:30 Italian time).

Loads the focus list saved by momentum_weekly.py, re-downloads only those
tickers, checks for breakouts with volume confirmation, and sends an alert
email if any are found. Silent if nothing broke out today.

Run: python3 breakout_alert.py
"""
import json
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

BASE_DIR      = Path(__file__).parent
LOG_DIR       = BASE_DIR / "logs"
OUTPUT_DIR    = BASE_DIR / "output"
CONFIG_PATH   = BASE_DIR / "momentum_config.yaml"
FOCUS_LIST_PATH = BASE_DIR / "db" / "momentum_focus_list.json"

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
        LOG_DIR / "breakout_alert.log",
        maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    return logging.getLogger("breakout_alert")


@contextmanager
def step(log: logging.Logger, name: str):
    log.info(f"▶ {name}")
    t0 = time.perf_counter()
    try:
        yield
    finally:
        log.info(f"✓ {name} ({time.perf_counter() - t0:.1f}s)")


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
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"FATAL: cannot load momentum_config.yaml: {e}", file=sys.stderr)
        return 1

    load_dotenv(BASE_DIR / ".env")
    env = {k: os.environ.get(k, "") for k in
           ["GMAIL_APP_PASSWORD", "EMAIL_SENDER", "EMAIL_RECIPIENT"]}

    log      = setup_logging(config)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info(f"=== Breakout Alert | {run_date} ===")

    from src.free_scanner      import download_history
    from src.momentum_scanner  import check_market_regime, detect_breakouts, enrich_with_fundamentals
    from src.momentum_report   import generate_breakout_html
    from src.notifier          import send_report_email, send_alert_email

    try:
        if not check_internet():
            log.error("No internet.")
            return 1

        # ── 1. Load focus list saved by momentum_weekly ───────────────────────
        if not FOCUS_LIST_PATH.exists():
            log.warning("No focus list found — run momentum_weekly.py first.")
            return 0

        with open(FOCUS_LIST_PATH) as f:
            focus_list = json.load(f)

        if not focus_list:
            log.info("Focus list is empty — nothing to check.")
            return 0

        symbols = [c["symbol"] for c in focus_list]
        log.info(f"Focus list loaded: {len(symbols)} tickers — {', '.join(symbols)}")

        # ── 2. Download only focus list tickers + SPY/QQQ ────────────────────
        dl_symbols = ["SPY", "QQQ"] + symbols
        with step(log, f"Downloading {len(dl_symbols)} tickers"):
            hist_data = download_history(dl_symbols)

        # ── 3. Market regime ──────────────────────────────────────────────────
        regime = check_market_regime(hist_data)
        for sym, d in regime.get("details", {}).items():
            log.info(f"  {sym}: {'✅ BULL' if d['bullish'] else '⚠️ WEAK'} — price={d['price']}")

        # ── 4. Detect breakouts ───────────────────────────────────────────────
        with step(log, "Breakout detection"):
            cfg       = config.get("momentum", {})
            breakouts = detect_breakouts(hist_data, focus_list, cfg)

        if not breakouts:
            log.info("No breakouts today — no email sent.")
            return 0

        log.info(f"🔥 {len(breakouts)} breakout(s) found!")

        # ── 5. Enrich breakouts with fundamentals ─────────────────────────────
        with step(log, "Fundamentals enrichment"):
            breakouts = enrich_with_fundamentals(breakouts, hist_data)

        # ── 6. HTML report ────────────────────────────────────────────────────
        run_dir   = OUTPUT_DIR / f"{run_date}_breakout"
        run_dir.mkdir(parents=True, exist_ok=True)
        html_path = run_dir / f"breakout_{run_date}.html"

        with step(log, "HTML report"):
            generate_breakout_html(breakouts, regime, run_date, html_path)

        # ── 7. Send email ─────────────────────────────────────────────────────
        with step(log, "Send alert email"):
            syms_str = ", ".join(b["symbol"] for b in breakouts)
            config["email"]["subject"] = f"⚡ Breakout Alert — {run_date} — {syms_str}"
            send_report_email(html_path.read_text(encoding="utf-8"), [], config, env)

        log.info(f"=== Done. {len(breakouts)} breakout(s) — {syms_str} ===")
        return 0

    except Exception:
        tb = traceback.format_exc()
        log.error(f"Unhandled error:\n{tb}")
        try:
            send_alert_email(f"Breakout Alert Error {run_date}", tb, config, env)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
