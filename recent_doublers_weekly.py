"""
Recent Doublers Weekly Scanner — runner standalone.

Identifica i titoli S&P 1500 che hanno raddoppiato (+100%) in 3/6/9/12 mesi,
sono ancora in uptrend e sono leader del mercato (RS Rating ≥ 70).

Run: python3 recent_doublers_weekly.py
Schedule: ogni sabato alle 08:00 (dopo market_structure alle 07:00)
"""
import logging
import logging.handlers
import os
import sys
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR    = Path(__file__).parent
LOG_DIR     = BASE_DIR / "logs"
OUTPUT_DIR  = BASE_DIR / "output"
CONFIG_PATH = BASE_DIR / "momentum_config.yaml"

sys.path.insert(0, str(BASE_DIR))

# Fix per launchd: yfinance cache in percorso esplicito (evita OperationalError SQLite)
import yfinance as yf
_YF_CACHE = BASE_DIR / ".yf_cache"
_YF_CACHE.mkdir(exist_ok=True)
yf.set_tz_cache_location(str(_YF_CACHE))


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "recent_doublers.log",
        maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    return logging.getLogger("recent_doublers")


@contextmanager
def step(log, name):
    log.info(f"▶ {name}")
    t0 = time.perf_counter()
    try:
        yield
    finally:
        log.info(f"✓ {name} ({time.perf_counter() - t0:.1f}s)")


def main() -> int:
    log      = setup_logging()
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info(f"=== Recent Doublers Scanner | {run_date} ===")

    load_dotenv(BASE_DIR / ".env")
    env = {k: os.environ.get(k, "") for k in
           ["GMAIL_APP_PASSWORD", "EMAIL_SENDER", "EMAIL_RECIPIENT"]}

    try:
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        log.warning(f"Config non trovata: {e}")
        config = {}

    from src.free_scanner               import get_universe, download_history
    from src.recent_doublers_scanner    import scan_recent_doublers, enrich_doublers
    from src.recent_doublers_report     import (generate_recent_doublers_html,
                                                generate_recent_doublers_excel)
    from src.notifier                   import send_report_email, send_alert_email

    try:
        # ── 1. Universo ────────────────────────────────────────────────────────
        with step(log, "Universo S&P 1500"):
            symbols, meta_map = get_universe(config)
            log.info(f"{len(symbols)} simboli")

        # ── 2. Download OHLCV (2 anni) ─────────────────────────────────────────
        # Usa 520 giorni calendario (~370 trading days) per coprire 12 mesi + buffer
        with step(log, f"Download OHLCV 2y ({len(symbols)} simboli)"):
            hist_data = download_history(symbols, days=520)
            log.info(f"{len(hist_data)} simboli OK")

        # ── 3. Scan ────────────────────────────────────────────────────────────
        with step(log, "Recent Doublers scan"):
            results = scan_recent_doublers(hist_data, meta_map, config)
            log.info(f"{len(results)} doublers trovati")

        if not results:
            msg = f"Nessun doubler trovato ({run_date}). Mercato debole o filtri troppo stretti."
            log.warning(msg)
            send_alert_email("Recent Doublers — Nessun risultato", msg, config, env)
            return 0

        # ── 4. Enrich ─────────────────────────────────────────────────────────
        log.info("Pausa 20s prima dell'enrichment...")
        time.sleep(20)
        with step(log, f"Enrich market cap ({len(results)} ticker)"):
            results = enrich_doublers(results)

        # ── 5. Output ─────────────────────────────────────────────────────────
        run_dir    = OUTPUT_DIR / f"{run_date}_recent_doublers"
        run_dir.mkdir(parents=True, exist_ok=True)
        html_path  = run_dir / f"recent_doublers_{run_date}.html"
        excel_path = run_dir / f"recent_doublers_{run_date}.xlsx"

        with step(log, "HTML report"):
            generate_recent_doublers_html(results, run_date, html_path)

        with step(log, "Excel report"):
            generate_recent_doublers_excel(results, run_date, excel_path)

        # ── 6. Email ──────────────────────────────────────────────────────────
        n_ap = sum(1 for r in results if r["quality"] == "A+")
        n_a  = sum(1 for r in results if r["quality"] == "A")
        n_bp = sum(1 for r in results if r["quality"] == "B+")

        with step(log, "Invio mail"):
            config.setdefault("email", {})
            config["email"]["subject"] = (
                f"🚀 Recent Doublers — {run_date} — "
                f"{len(results)} doublers | 🟢 {n_ap} A+ | 🔵 {n_a} A | 🟠 {n_bp} B+"
            )
            send_report_email(
                html_path.read_text(encoding="utf-8"),
                [excel_path],
                config, env,
            )

        log.info(f"=== Done. {len(results)} doublers | A+: {n_ap} | A: {n_a} | B+: {n_bp} ===")
        log.info("Top 10:")
        for r in results[:10]:
            log.info(
                f"  {r['ticker']:6s} | {r['quality']:<3} | score={r['doubler_score']:5.1f} "
                f"| best={r['best_return']:+.0f}% in {r['fastest_tf']} "
                f"| rs={r['rs_rating']} | dist52w={r['dist_52w_pct']:.1f}%"
            )
        return 0

    except Exception:
        tb = traceback.format_exc()
        log.error(f"Errore:\n{tb}")
        try:
            send_alert_email(f"Recent Doublers Error {run_date}", tb, config, env)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
