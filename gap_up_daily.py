"""
Gap Up Daily Scanner — runner standalone.

Rileva i gap up della sessione corrente su tutto l'universo S&P 1500.
Metodologia: replica standalone dello scanner AskLivermore BGU con dati yfinance.

Run: python3 gap_up_daily.py
Schedule: lun-ven alle 21:30 UTC (23:30 ora italiana CET, 1.5h dopo chiusura US)
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
        LOG_DIR / "gap_up.log",
        maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    return logging.getLogger("gap_up")


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
    log.info(f"=== Gap Up Scanner | {run_date} ===")

    load_dotenv(BASE_DIR / ".env")
    env = {k: os.environ.get(k, "") for k in
           ["GMAIL_APP_PASSWORD", "EMAIL_SENDER", "EMAIL_RECIPIENT"]}

    try:
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        log.warning(f"Config non trovata: {e}")
        config = {}

    from src.free_scanner    import get_universe, download_history
    from src.gap_up_scanner  import scan_gap_up, enrich_gap_up
    from src.gap_up_report   import generate_gap_up_html, generate_gap_up_excel
    from src.notifier        import send_report_email, send_alert_email

    try:
        # ── 1. Universo ────────────────────────────────────────────────────────
        with step(log, "Universo S&P 1500"):
            symbols, meta_map = get_universe(config)
            log.info(f"{len(symbols)} simboli")

        # ── 2. Download OHLCV ─────────────────────────────────────────────────
        with step(log, f"Download OHLCV ({len(symbols)} simboli)"):
            hist_data = download_history(symbols)
            log.info(f"{len(hist_data)} simboli OK")

        # ── 3. Gap Up Scan ────────────────────────────────────────────────────
        with step(log, "Gap Up scan"):
            results = scan_gap_up(hist_data, meta_map, config)
            log.info(f"{len(results)} gap up trovati")

        if not results:
            msg = f"Nessun gap up trovato ({run_date}). Mercato piatto o dati non disponibili."
            log.warning(msg)
            # Silenzio totale se non ci sono gap — no email
            return 0

        # ── 4. Enrich ─────────────────────────────────────────────────────────
        log.info("Pausa 15s prima dell'enrichment...")
        time.sleep(15)
        with step(log, f"Enrich market cap ({len(results)} ticker)"):
            results = enrich_gap_up(results)

        # ── 5. Output ─────────────────────────────────────────────────────────
        run_dir    = OUTPUT_DIR / f"{run_date}_gap_up"
        run_dir.mkdir(parents=True, exist_ok=True)
        html_path  = run_dir / f"gap_up_{run_date}.html"
        excel_path = run_dir / f"gap_up_{run_date}.xlsx"

        with step(log, "HTML report"):
            generate_gap_up_html(results, run_date, html_path)

        with step(log, "Excel report"):
            generate_gap_up_excel(results, run_date, excel_path)

        # ── 6. Email ──────────────────────────────────────────────────────────
        n_ap = sum(1 for r in results if r["quality"] == "A+")
        n_a  = sum(1 for r in results if r["quality"] == "A")
        n_bp = sum(1 for r in results if r["quality"] == "B+")

        with step(log, "Invio mail"):
            config.setdefault("email", {})
            config["email"]["subject"] = (
                f"📊 Gap Up — {run_date} — "
                f"{len(results)} gap | 🟢 {n_ap} A+ | 🔵 {n_a} A | 🟠 {n_bp} B+"
            )
            send_report_email(
                html_path.read_text(encoding="utf-8"),
                [excel_path],
                config, env,
            )

        log.info(f"=== Done. {len(results)} gap up | A+: {n_ap} | A: {n_a} | B+: {n_bp} ===")
        log.info("Top 10:")
        for r in results[:10]:
            log.info(
                f"  {r['ticker']:6s} | {r['quality']:<3} | score={r['gap_score']:5.1f} "
                f"| gap={r['gap_pct']:+.2f}% ({r['gap_days_ago']}gg fa) "
                f"| held={r['gap_held_pct']:.0f}% | rvol={r['rvol']:.2f}x | ars={r['rs_rating']}"
            )
        return 0

    except Exception:
        tb = traceback.format_exc()
        log.error(f"Errore:\n{tb}")
        try:
            send_alert_email(f"Gap Up Error {run_date}", tb, config, env)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
