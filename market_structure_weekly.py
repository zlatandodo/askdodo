"""
Market Structure Weekly Scanner — runner standalone.

Analizza la struttura di mercato su timeframe settimanale per tutti i titoli S&P 1500.
Metodologia: Mac (@MacnBTC) — HH/HL uptrend, BMS bullish, pullback al HL.

Run: python3 market_structure_weekly.py
Schedule: ogni sabato alle 07:00 (dopo momentum_weekly alle 06:00)
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


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "market_structure.log",
        maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    return logging.getLogger("market_structure")


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
    log.info(f"=== Market Structure Scanner | {run_date} ===")

    load_dotenv(BASE_DIR / ".env")
    env = {k: os.environ.get(k, "") for k in
           ["GMAIL_APP_PASSWORD", "EMAIL_SENDER", "EMAIL_RECIPIENT"]}

    try:
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        log.warning(f"Config non trovata: {e}")
        config = {}

    from src.free_scanner              import get_universe, download_history
    from src.market_structure_scanner  import scan_market_structure, enrich_ms
    from src.market_structure_report   import generate_market_structure_html
    from src.notifier                  import send_report_email, send_alert_email

    try:
        # ── 1. Universo ────────────────────────────────────────────────────────
        with step(log, "Universo S&P 1500"):
            symbols, meta_map = get_universe(config)
            log.info(f"{len(symbols)} simboli")

        # ── 2. Download OHLCV ─────────────────────────────────────────────────
        with step(log, f"Download OHLCV ({len(symbols)} simboli)"):
            hist_data = download_history(symbols)
            log.info(f"{len(hist_data)} simboli OK")

        # ── 3. Market Structure Scan ──────────────────────────────────────────
        with step(log, "Market Structure scan (weekly)"):
            results = scan_market_structure(hist_data, meta_map, swing_n=3)
            log.info(f"{len(results)} setup trovati")

        if not results:
            msg = f"Nessun setup trovato ({run_date})."
            log.warning(msg)
            send_alert_email("MS Scanner — Nessun risultato", msg, config, env)
            return 0

        # ── 4. Enrich ─────────────────────────────────────────────────────────
        log.info("Pausa 30s prima dell'enrichment...")
        time.sleep(30)
        with step(log, f"Enrich ({len(results)} ticker)"):
            results = enrich_ms(results)

        # ── 5. Output ─────────────────────────────────────────────────────────
        run_dir   = OUTPUT_DIR / f"{run_date}_market_structure"
        run_dir.mkdir(parents=True, exist_ok=True)
        html_path = run_dir / f"market_structure_{run_date}.html"

        with step(log, "HTML report"):
            generate_market_structure_html(results, run_date, html_path)

        # ── 6. Email ──────────────────────────────────────────────────────────
        n_fresh  = sum(1 for r in results if "BMS_FRESH"  in r.get("signal", ""))
        n_recent = sum(1 for r in results if "BMS_RECENT" in r.get("signal", ""))

        with step(log, "Invio mail"):
            config.setdefault("email", {})
            config["email"]["subject"] = (
                f"📊 Market Structure — {run_date} — "
                f"{len(results)} setup | 🟢 {n_fresh} BMS freschi | 🔵 {n_recent} recenti"
            )
            send_report_email(
                html_path.read_text(encoding="utf-8"),
                [],
                config, env,
            )

        log.info(f"=== Done. {len(results)} setup | BMS freschi: {n_fresh} ===")
        log.info("Top 10:")
        for r in results[:10]:
            log.info(
                f"  {r['ticker']:6s} | {r['signal']:<20} | score={r['ms_score']} "
                f"| BMS {r.get('bms_weeks_ago','—')}w fa | HH dal BMS={r.get('hh_since_bms','—')}"
            )
        return 0

    except Exception:
        tb = traceback.format_exc()
        log.error(f"Errore:\n{tb}")
        try:
            send_alert_email(f"Market Structure Error {run_date}", tb, config, env)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
