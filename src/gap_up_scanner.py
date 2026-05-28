"""
Buyable Gap Up Scanner — replica della logica AskLivermore BGU.

Metodologia (basata sull'analisi diretta di AskLivermore):
  "Gap-up on institutional volume that holds above prior day's high.
   The gap IS the breakout. buy on the first pullback to the gap zone."

  Il scanner:
  1. Cerca gap avvenuti negli ULTIMI 10 GIORNI (non solo oggi)
  2. Il gap deve essere ancora VALIDO (prezzo attuale > close pre-gap)
  3. Volume sul gap day ≥ 1.5× media 20gg
  4. Nessun filtro RS Rating (AskLivermore include tutti i titoli)
  5. Nessun filtro market cap o SMA200
  6. Nessun requisito di base/prior move

Differenza dalla versione v2:
  - v2 cercava solo gap del giorno corrente, richiedeva base + pivot + RS ≥ 70
  - v3 (questa): replica la logica reale di AskLivermore — gap recenti (1-10gg),
    validi (gap zone intatta), su volume istituzionale

Run: ogni sera lun-ven dopo la chiusura US (21:30 UTC).
"""
import bisect
import logging
import time

import numpy as np
import yfinance as yf

log = logging.getLogger(__name__)

# ── Config defaults ───────────────────────────────────────────────────────────
_DEF_MIN_GAP      = 3.0      # gap minimo % (open vs prev_close)
_DEF_MAX_GAP      = 50.0     # esclude solo gap assurdi (>50%)
_DEF_MIN_RVOL     = 1.5      # RVOL minimo sul gap day
_DEF_MIN_VOL      = 200_000  # volume medio 20gg minimo (liquidità minima)
_DEF_LOOKBACK     = 10       # giorni a ritroso per cercare il gap event


# ═══════════════════════════════════════════════════════════════════════════════
#  RS Rating 12 mesi — percentile rank sull'universo (solo per scoring)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_rs_ratings(hist_data: dict) -> dict[str, int]:
    """
    Calcola l'RS Rating (1-99) per tutti i titoli dell'universo.
    Usato solo per il PUNTEGGIO (non come filtro hard).
    """
    rs_raw: dict[str, float] = {}
    for ticker, df in hist_data.items():
        try:
            if len(df) < 60:
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


# ═══════════════════════════════════════════════════════════════════════════════
#  Gap Score
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_gap_score(gap_pct: float, rvol: float, gap_held_pct: float,
                       days_ago: int, rs_rating: int) -> float:
    """
    Gap Score 0-100 — logica AskLivermore BGU.

    Componenti:
      Gap Size     (30pt) : gap più grande = più istituzionale
      RVOL         (30pt) : volume sul gap day
      Gap Held     (20pt) : quanto del gap è ancora intatto
      Freshness    (20pt) : gap più recente = più actionable
    """
    # Gap Size (30pt): 3% = 0pt, 20%+ = 30pt
    gap_score = min(1.0, max(0.0, (gap_pct - _DEF_MIN_GAP) / (20.0 - _DEF_MIN_GAP))) * 30

    # RVOL (30pt): 1.5x = 0pt, 5x+ = 30pt
    rvol_score = min(1.0, max(0.0, (rvol - 1.5) / 3.5)) * 30

    # Gap Held (20pt): >100% gap held (aperto sopra il gap) = 20pt, 0% = 0pt
    held_score = min(1.0, max(0.0, gap_held_pct / 100.0)) * 20

    # Freshness (20pt): gap oggi = 20pt, 10gg fa = 0pt
    fresh_score = max(0.0, (1.0 - (days_ago - 1) / 9.0)) * 20

    return round(gap_score + rvol_score + held_score + fresh_score, 1)


def _quality_grade(score: float) -> str:
    if score >= 70: return "A+"
    if score >= 50: return "A"
    if score >= 35: return "B+"
    return "B"


# ═══════════════════════════════════════════════════════════════════════════════
#  SPY baseline
# ═══════════════════════════════════════════════════════════════════════════════

def _get_spy_day_return() -> float:
    """Rendimento SPY nell'ultima sessione (close[-1] / close[-2] - 1)."""
    try:
        spy = yf.download("SPY", period="5d", interval="1d",
                          progress=False, auto_adjust=True)
        if len(spy) < 2:
            return 0.0
        c = spy["Close"].squeeze()
        return float(c.iloc[-1]) / float(c.iloc[-2]) - 1.0
    except Exception as e:
        log.warning(f"SPY fetch fallita: {e}")
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
#  Main scanner
# ═══════════════════════════════════════════════════════════════════════════════

def scan_gap_up(hist_data: dict, meta_map: dict, config: dict = None) -> list[dict]:
    """
    Identifica i Buyable Gap Up recenti (ultimi 10 giorni).

    Pipeline (allineata al BGU reale di AskLivermore):
      1. Per ogni titolo, cerca gap ≥ 3% negli ultimi `lookback_days` giorni
      2. Volume sul gap day ≥ 1.5× media 20gg
      3. Il gap è ancora VALIDO: prezzo attuale > close pre-gap (gap zone intatta)
      4. Calcola Gap Score e ordina per score decrescente

    Nessun filtro hard su RS Rating, SMA200, base pattern.
    Questi erano nella v2 ma non sono presenti nel BGU reale di AskLivermore.
    """
    cfg          = (config or {}).get("gap_up", {})
    min_gap      = float(cfg.get("min_gap_pct",   _DEF_MIN_GAP))
    max_gap      = float(cfg.get("max_gap_pct",   _DEF_MAX_GAP))
    min_rvol     = float(cfg.get("min_rvol",      _DEF_MIN_RVOL))
    min_vol      = int(  cfg.get("min_vol_avg",   _DEF_MIN_VOL))
    lookback     = int(  cfg.get("lookback_days", _DEF_LOOKBACK))

    # ── RS Rating (solo per scoring, non per filtrare) ────────────────────────
    log.info("Calcolo RS Rating 12m su tutto l'universo (solo scoring)...")
    rs_ratings = _build_rs_ratings(hist_data)

    # ── SPY rendimento giornaliero ────────────────────────────────────────────
    log.info("Download rendimento SPY...")
    spy_ret = _get_spy_day_return()
    log.info(f"SPY giornaliero: {spy_ret:+.2%}")

    results    = []
    skipped    = {"no_data": 0, "no_vol": 0, "no_gap_found": 0, "gap_filled": 0}

    for ticker, df in hist_data.items():
        try:
            if len(df) < lookback + 25:
                skipped["no_data"] += 1
                continue

            # ── Volume medio 20gg (liquidità minima) ──────────────────────────
            avg_vol_20 = float(df["Volume"].iloc[-21:-1].mean())
            if avg_vol_20 < min_vol:
                skipped["no_vol"] += 1
                continue

            # ── Cerca il gap più recente e significativo negli ultimi N giorni ─
            best_gap = None
            current_close = float(df["Close"].iloc[-1])

            # Scansione a ritroso: giorni -1 (ieri/più recente con gap), -2, ..., -lookback
            # NB: df.iloc[-1] = ultima barra disponibile (oggi o ieri se mercato chiuso)
            # Cerchiamo gap dal giorno -lookback fino a -1
            for days_ago in range(1, lookback + 1):
                idx_gap  = -(days_ago)       # barra del possibile gap
                idx_prev = -(days_ago + 1)   # barra precedente al gap

                if abs(idx_prev) > len(df):
                    break

                gap_day  = df.iloc[idx_gap]
                prev_day = df.iloc[idx_prev]

                open_gap   = float(gap_day["Open"])
                prev_close = float(prev_day["Close"])
                vol_gap    = float(gap_day["Volume"])

                if prev_close <= 0 or open_gap <= 0:
                    continue

                gap_pct = (open_gap / prev_close - 1.0) * 100.0

                # Gap size check
                if gap_pct < min_gap or gap_pct > max_gap:
                    continue

                # Volume sul gap day ≥ 1.5× media 20gg prima del gap
                vol_avg_before = float(df["Volume"].iloc[idx_prev - 20: idx_prev].mean())
                if vol_avg_before <= 0:
                    vol_avg_before = avg_vol_20
                rvol = vol_gap / vol_avg_before

                if rvol < min_rvol:
                    continue

                # Gap ancora valido? Prezzo attuale > close pre-gap (gap zone intatta)
                if current_close < prev_close:
                    skipped["gap_filled"] += 1
                    continue  # gap riempito — non è più un BGU valido

                # Trovato un gap valido! Prendi il più recente (days_ago più basso)
                best_gap = {
                    "days_ago":   days_ago,
                    "gap_pct":    gap_pct,
                    "rvol":       rvol,
                    "open_gap":   open_gap,
                    "prev_close": prev_close,
                    "gap_day":    gap_day,
                }
                break  # primo (più recente) gap valido trovato

            if best_gap is None:
                skipped["no_gap_found"] += 1
                continue

            # ── Metriche della barra più recente ──────────────────────────────
            last_bar   = df.iloc[-1]
            close_     = float(last_bar["Close"])
            high_last  = float(last_bar["High"])
            low_last   = float(last_bar["Low"])
            open_last  = float(last_bar["Open"])
            vol_last   = float(last_bar["Volume"])

            prev_bar   = df.iloc[-2]
            prev_close_today = float(prev_bar["Close"])

            # Gap held %: quanto del gap originale è ancora intatto
            gap_abs      = best_gap["open_gap"] - best_gap["prev_close"]
            if gap_abs > 0:
                gap_held_pct = min(150.0, max(0.0,
                    (close_ - best_gap["prev_close"]) / gap_abs * 100.0))
            else:
                gap_held_pct = 0.0

            # Posizione chiusura nel range giornaliero
            day_range = high_last - low_last
            close_pos = (close_ - low_last) / day_range if day_range > 0 else 0.5

            # SMA50 e SMA200 (solo informativi)
            closes  = df["Close"]
            sma50   = float(closes.iloc[-51:-1].mean()) if len(df) >= 52 else float(closes.mean())
            sma200  = float(closes.iloc[-201:-1].mean()) if len(df) >= 202 else float(closes.mean())

            # Variazione % nella sessione più recente
            day_chg_pct = (close_ / prev_close_today - 1.0) * 100.0

            # RS Rating e score
            rs_rating = rs_ratings.get(ticker, 0)
            score     = _compute_gap_score(
                best_gap["gap_pct"], best_gap["rvol"], gap_held_pct,
                best_gap["days_ago"], rs_rating
            )
            quality   = _quality_grade(score)

            meta = meta_map.get(ticker, {})
            results.append({
                "ticker":         ticker,
                "name":           meta.get("name", ticker),
                "sector":         meta.get("sector", "—"),
                "quality":        quality,
                "gap_score":      score,
                # Gap event
                "gap_pct":        round(best_gap["gap_pct"], 2),
                "gap_days_ago":   best_gap["days_ago"],
                "open_gap":       round(best_gap["open_gap"], 2),
                "prev_close_gap": round(best_gap["prev_close"], 2),
                "rvol":           round(best_gap["rvol"], 2),
                # Gap status
                "gap_held_pct":   round(gap_held_pct, 1),
                "gap_zone_low":   round(best_gap["prev_close"], 2),
                "gap_zone_high":  round(best_gap["open_gap"], 2),
                # Barra più recente
                "price":          round(close_, 2),
                "day_chg_pct":    round(day_chg_pct, 2),
                "close_pos_pct":  round(close_pos * 100.0, 1),
                "volume":         int(vol_last),
                "avg_vol_20":     int(avg_vol_20),
                # Trend (informativo)
                "sma50":          round(sma50, 2),
                "sma200":         round(sma200, 2),
                "above_sma50":    close_ > sma50,
                "above_sma200":   close_ > sma200,
                # Leadership (informativo)
                "rs_rating":      rs_rating,
                # Placeholder
                "market_cap_m":   0.0,
            })

        except Exception as e:
            log.debug(f"{ticker}: {e}")
            continue

    results.sort(key=lambda x: x["gap_score"], reverse=True)

    log.info(f"Filtri: no_data={skipped['no_data']} | no_vol={skipped['no_vol']} | "
             f"no_gap_found={skipped['no_gap_found']} | gap_filled={skipped['gap_filled']}")
    log.info(f"BGU trovati: {len(results)} "
             f"(A+={sum(1 for r in results if r['quality']=='A+')}, "
             f"A={sum(1 for r in results if r['quality']=='A')}, "
             f"B+={sum(1 for r in results if r['quality']=='B+')})")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  Enrich
# ═══════════════════════════════════════════════════════════════════════════════

def enrich_gap_up(results: list[dict]) -> list[dict]:
    """Aggiunge market cap via yfinance fast_info."""
    for r in results:
        try:
            fi = yf.Ticker(r["ticker"]).fast_info
            r["market_cap_m"] = round(getattr(fi, "market_cap", 0) / 1e6, 1)
        except Exception:
            pass
        time.sleep(0.05)
    return results
