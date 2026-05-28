"""
Recent Doublers Scanner — replica standalone dello scanner AskLivermore.

Identifica titoli nell'universo S&P 1500 che hanno raddoppiato il prezzo
(+100%) in uno dei seguenti timeframe: 3 mesi, 6 mesi, 12 mesi.

Logica:
  - Un "doubler" è un titolo il cui prezzo è almeno +100% dal punto di partenza
  - Si classifica in base alla velocità del raddoppio (più rapido = qualità A+)
  - Deve essere ancora in uptrend (non aver collassato dopo il raddoppio)
  - Deve essere un leader di mercato (RS Rating ≥ 70)

Run: ogni sabato (settimanale — le opportunità non cambiano giorno per giorno).
"""
import bisect
import logging
import time

import numpy as np
import yfinance as yf

log = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────────
_DEF_MIN_PRICE    = 5.0     # prezzo minimo
_DEF_MIN_VOL      = 200_000 # volume medio 50gg minimo
_DEF_MIN_RS       = 0       # RS Rating minimo — 0 = nessun filtro (come AskLivermore)
_DEF_MAX_DIST_52W = 999.0   # distanza massima dal 52w high — 999 = nessun filtro (come AskLivermore)

# Timeframe (in trading days)
_TF = {
    "3m":  63,
    "6m":  126,
    "9m":  189,
    "12m": 252,
}


# ── RS Rating ─────────────────────────────────────────────────────────────────

def _build_rs_ratings(hist_data: dict) -> dict[str, int]:
    """
    RS Rating 12m — percentile rank 1-99 sull'universo (stile IBD).
    Usa il massimo storico disponibile (fino a 252 barre).
    """
    rs_raw: dict[str, float] = {}
    for ticker, df in hist_data.items():
        try:
            if len(df) < 120:
                continue
            c = df["Close"].squeeze() if hasattr(df["Close"], "squeeze") else df["Close"]
            lookback = min(252, len(c) - 1)
            rs_raw[ticker] = float(c.iloc[-1]) / float(c.iloc[-lookback - 1])
        except Exception:
            continue

    if not rs_raw:
        return {}

    sorted_vals = sorted(rs_raw.values())
    n = len(sorted_vals)
    ratings: dict[str, int] = {}
    for ticker, val in rs_raw.items():
        pos = bisect.bisect_left(sorted_vals, val)
        ratings[ticker] = max(1, min(99, round(pos / (n - 1) * 98 + 1))) if n > 1 else 50

    log.info(f"RS Rating calcolato per {len(ratings)} titoli")
    return ratings


# ── Score ─────────────────────────────────────────────────────────────────────

def _doubler_score(fastest_tf: str, best_return: float, rs_rating: int,
                   dist_from_high_pct: float) -> float:
    """
    Doubler Score 0-100.

    Componenti:
      Speed       (40pt) : velocità del raddoppio
      Magnitude   (25pt) : quanto supera il 100%
      RS Rating   (25pt) : leadership relativa 12m
      Near High   (10pt) : quanto è ancora vicino al massimo
    """
    # Speed (40pt)
    speed_pts = {"3m": 40.0, "6m": 28.0, "9m": 16.0, "12m": 8.0}
    speed_score = speed_pts.get(fastest_tf, 0.0)

    # Magnitude (25pt): 100% = 0pt, 400%+ = 25pt
    magnitude_score = min(1.0, max(0.0, (best_return - 1.0) / 3.0)) * 25

    # RS Rating (25pt): 50 = 0pt, 99 = 25pt (range 50-99 come riferimento pratico)
    rs_score = min(1.0, max(0.0, (rs_rating - 50) / (99 - 50))) * 25

    # Near 52w High (10pt): 0% di distanza = 10pt, 50%+ = 0pt
    high_score = min(1.0, max(0.0, 1.0 - dist_from_high_pct / 50.0)) * 10

    return round(speed_score + magnitude_score + rs_score + high_score, 1)


def _quality_grade(fastest_tf: str) -> str:
    """Grade basato sulla velocità del raddoppio."""
    return {"3m": "A+", "6m": "A", "9m": "B+", "12m": "B"}.get(fastest_tf, "B")


# ── Main scanner ──────────────────────────────────────────────────────────────

def scan_recent_doublers(hist_data: dict, meta_map: dict,
                         config: dict = None) -> list[dict]:
    """
    Identifica i Recent Doublers nell'universo S&P 1500.

    Richiede hist_data con almeno 2 anni di storia
    (download_history con days=520).

    Returns
    -------
    Lista di dict ordinata per doubler_score decrescente.
    """
    cfg         = (config or {}).get("recent_doublers", {})
    min_price   = float(cfg.get("min_price",       _DEF_MIN_PRICE))
    min_vol     = int(  cfg.get("min_vol_avg",     _DEF_MIN_VOL))
    min_rs      = int(  cfg.get("min_rs_rating",   _DEF_MIN_RS))
    max_dist_52w= float(cfg.get("max_dist_52w_pct",_DEF_MAX_DIST_52W))

    log.info("Calcolo RS Rating 12m su tutto l'universo...")
    rs_ratings = _build_rs_ratings(hist_data)

    results = []
    skipped = {"no_data": 0, "no_double": 0, "collapsed": 0,
               "no_vol": 0, "no_price": 0, "no_rs": 0}

    for ticker, df in hist_data.items():
        try:
            c = df["Close"].squeeze() if hasattr(df["Close"], "squeeze") else df["Close"]
            v = df["Volume"].squeeze() if hasattr(df["Volume"], "squeeze") else df["Volume"]

            if len(c) < 70:
                skipped["no_data"] += 1
                continue

            price = float(c.iloc[-1])
            if price < min_price:
                skipped["no_price"] += 1
                continue

            # Volume
            avg_vol = float(v.iloc[-51:-1].mean()) if len(v) > 51 else float(v.mean())
            if avg_vol < min_vol:
                skipped["no_vol"] += 1
                continue

            # ── Ritorni per timeframe ─────────────────────────────────────────
            returns: dict[str, float] = {}
            for tf_name, tf_days in _TF.items():
                if len(c) < tf_days + 1:
                    continue
                past_price = float(c.iloc[-tf_days - 1])
                if past_price > 0:
                    returns[tf_name] = price / past_price - 1.0

            # Deve aver raddoppiato in almeno un timeframe
            doubled = {k: v for k, v in returns.items() if v >= 1.0}
            if not doubled:
                skipped["no_double"] += 1
                continue

            # ── 52w High e distanza ───────────────────────────────────────────
            high_arr = df["High"].squeeze() if hasattr(df["High"], "squeeze") else df["High"]
            lookback_52w = min(252, len(high_arr) - 1)
            high_52w = float(high_arr.iloc[-lookback_52w:].max())
            dist_52w_pct = (high_52w - price) / high_52w * 100.0

            if dist_52w_pct > max_dist_52w:
                skipped["collapsed"] += 1
                continue

            # SMA50
            sma50 = float(c.iloc[-51:-1].mean()) if len(c) > 51 else float(c.mean())
            above_sma50 = price > sma50

            # ── RS Rating ─────────────────────────────────────────────────────
            rs_rating = rs_ratings.get(ticker, 0)
            if rs_rating < min_rs:
                skipped["no_rs"] += 1
                continue

            # ── Fastest timeframe con doubling ────────────────────────────────
            tf_order = ["3m", "6m", "9m", "12m"]
            fastest_tf = next(tf for tf in tf_order if tf in doubled)
            best_return = max(doubled.values())

            score   = _doubler_score(fastest_tf, best_return, rs_rating, dist_52w_pct)
            quality = _quality_grade(fastest_tf)

            meta = meta_map.get(ticker, {})
            results.append({
                "ticker":        ticker,
                "name":          meta.get("company_name", meta.get("name", ticker)),
                "sector":        meta.get("sector", "—"),
                "quality":       quality,
                "doubler_score": score,
                # Ritorni per timeframe
                "ret_3m":        round(returns.get("3m",  0) * 100, 1),
                "ret_6m":        round(returns.get("6m",  0) * 100, 1),
                "ret_12m":       round(returns.get("12m", 0) * 100, 1),
                "fastest_tf":    fastest_tf,
                "best_return":   round(best_return * 100, 1),
                # Leadership
                "rs_rating":     rs_rating,
                # Posizione vs massimi
                "high_52w":      round(high_52w, 2),
                "dist_52w_pct":  round(dist_52w_pct, 1),
                # Trend
                "price":         round(price, 2),
                "sma50":         round(sma50, 2),
                "above_sma50":   above_sma50,
                # Volume
                "avg_vol_50":    int(avg_vol),
                # Placeholder
                "market_cap_m":  0.0,
            })

        except Exception as e:
            log.debug(f"{ticker}: {e}")
            continue

    results.sort(key=lambda x: x["doubler_score"], reverse=True)

    log.info(f"Filtri: no_data={skipped['no_data']} | no_double={skipped['no_double']} | "
             f"collapsed={skipped['collapsed']} | no_vol={skipped['no_vol']} | "
             f"no_rs={skipped['no_rs']}")
    log.info(f"Recent Doublers: {len(results)} "
             f"(A+={sum(1 for r in results if r['quality']=='A+')}, "
             f"A={sum(1 for r in results if r['quality']=='A')}, "
             f"B+={sum(1 for r in results if r['quality']=='B+')})")
    return results


# ── Enrich ────────────────────────────────────────────────────────────────────

def enrich_doublers(results: list[dict]) -> list[dict]:
    """Aggiunge market cap via yfinance fast_info."""
    for r in results:
        try:
            fi = yf.Ticker(r["ticker"]).fast_info
            r["market_cap_m"] = round(getattr(fi, "market_cap", 0) / 1e6, 1)
        except Exception:
            pass
        time.sleep(0.05)
    return results
