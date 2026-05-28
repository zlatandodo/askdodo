"""
Market Structure Scanner — basato sulla metodologia di Mac (@MacnBTC).

Logica core:
  1. Resampla daily OHLCV → weekly candles
  2. Rileva swing highs e swing lows (N=3 bars di conferma)
  3. Classifica struttura: uptrend (HH+HL), downtrend (LH+LL), ranging
  4. Individua Bullish Break of Market Structure (BMS): rottura di un LH in downtrend
  5. Segnala pullback al Higher Low in uptrend confermato
  6. Filtra "crazy late": se 3+ HH già stampati dal BMS, scarta

Segnali output (per MS Score decrescente):
  BMS_FRESH   — BMS bullish < 4 settimane fa          (max probabilità)
  BMS_RECENT  — BMS bullish 4-12 settimane fa          (alta probabilità)
  HL_ENTRY    — pullback al Higher Low in uptrend       (entry pulita)
  UPTREND     — uptrend confermato, non esteso          (tienilo d'occhio)
"""
import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def _resample_weekly(daily_hist: pd.DataFrame) -> pd.DataFrame:
    """Resampla daily OHLCV a candle settimanali (chiusura venerdì)."""
    h = daily_hist.copy()
    if not isinstance(h.index, pd.DatetimeIndex):
        h.index = pd.to_datetime(h.index)

    # Gestisci colonne MultiIndex (yfinance v0.2+)
    if isinstance(h.columns, pd.MultiIndex):
        h.columns = h.columns.get_level_values(0)

    weekly = h.resample("W-FRI").agg({
        "Open":   "first",
        "High":   "max",
        "Low":    "min",
        "Close":  "last",
        "Volume": "sum",
    }).dropna(subset=["Close"])
    return weekly


def _detect_swings(high_arr: np.ndarray, low_arr: np.ndarray, n: int = 3):
    """
    Rileva swing highs e swing lows.

    Swing high: high[i] >= tutti i N candles a sinistra E >= tutti i N a destra.
    Swing low : low[i]  <= tutti i N candles a sinistra E <= tutti i N a destra.

    Returns (sh_list, sl_list) — lista di (index, price).
    """
    sh_list, sl_list = [], []

    for i in range(n, len(high_arr) - n):
        # Swing high
        left_h  = high_arr[i - n:i]
        right_h = high_arr[i + 1:i + n + 1]
        if high_arr[i] >= np.max(left_h) and high_arr[i] >= np.max(right_h):
            if not sh_list or float(high_arr[i]) != sh_list[-1][1]:
                sh_list.append((i, float(high_arr[i])))

        # Swing low
        left_l  = low_arr[i - n:i]
        right_l = low_arr[i + 1:i + n + 1]
        if low_arr[i] <= np.min(left_l) and low_arr[i] <= np.min(right_l):
            if not sl_list or float(low_arr[i]) != sl_list[-1][1]:
                sl_list.append((i, float(low_arr[i])))

    return sh_list, sl_list


def _classify_structure(sh_list: list, sl_list: list) -> str:
    """
    Classifica struttura con gli ultimi 2 swing highs e 2 swing lows.
    Returns: 'uptrend' | 'downtrend' | 'ranging' | 'undefined'
    """
    if len(sh_list) < 2 or len(sl_list) < 2:
        return "undefined"

    sh_old, sh_new = sh_list[-2][1], sh_list[-1][1]
    sl_old, sl_new = sl_list[-2][1], sl_list[-1][1]

    hh = sh_new > sh_old
    hl = sl_new > sl_old
    lh = sh_new < sh_old
    ll = sl_new < sl_old

    if hh and hl:
        return "uptrend"
    elif lh and ll:
        return "downtrend"
    else:
        return "ranging"


def _find_bms_bullish(sh_list: list, total_bars: int) -> dict | None:
    """
    Trova il BMS bullish più recente.

    Pattern cercato (dalla più recente coppia all'indietro):
      sh[i-2] > sh[i-1]  (lower high formato)
      sh[i]   > sh[i-1]  (lower high rotto → BMS!)

    Returns dict con info BMS o None.
    """
    if len(sh_list) < 3:
        return None

    for i in range(len(sh_list) - 1, 1, -1):
        sh_curr  = sh_list[i]
        sh_prev  = sh_list[i - 1]
        sh_pprev = sh_list[i - 2]

        # sh_prev è un lower high rispetto a sh_pprev
        # sh_curr rompe al rialzo sh_prev → BMS bullish
        if sh_prev[1] < sh_pprev[1] and sh_curr[1] > sh_prev[1]:
            bms_idx   = sh_curr[0]
            weeks_ago = total_bars - 1 - bms_idx

            # Conta quanti HH consecutivi dal BMS
            hh_since = 0
            for j in range(i, len(sh_list)):
                if j > 0 and sh_list[j][1] > sh_list[j - 1][1]:
                    hh_since += 1

            return {
                "bms_idx":      bms_idx,
                "bms_level":    round(sh_prev[1], 2),  # livello rotto
                "weeks_ago":    weeks_ago,
                "hh_since_bms": hh_since,
            }

    return None


def _hl_distance(sl_list: list, current_price: float, structure: str) -> float | None:
    """
    Distanza percentuale del prezzo attuale dall'ultimo swing low (Higher Low).
    Calcolata solo in uptrend. Valori bassi = price vicino al supporto = entry migliore.
    """
    if structure != "uptrend" or len(sl_list) < 1:
        return None
    last_hl = sl_list[-1][1]
    return round((current_price - last_hl) / last_hl * 100, 1)


def _compute_score(structure: str, bms: dict | None, hl_dist: float | None) -> tuple[float, str]:
    """
    MS Score (0-100) e label del segnale.

    Componenti:
      Signal base  (0-50): tipo di segnale
      Recency      (0-20): più il BMS è recente, meglio
      Not extended (0-20): meno HH dal BMS, meglio (max 3 poi "crazy late")
      HL proximity (0-10): vicino al supporto = bonus
    """
    score  = 0.0
    signal = "NONE"

    if bms:
        weeks_ago = bms["weeks_ago"]
        hh_count  = bms.get("hh_since_bms", 0)

        # Base score per tipo BMS
        if weeks_ago <= 4:
            score  += 50
            signal  = "BMS_FRESH"
        elif weeks_ago <= 12:
            score  += 35
            signal  = "BMS_RECENT"
        elif weeks_ago <= 24:
            score  += 20
            signal  = "BMS_OLD"
        else:
            signal = "UPTREND" if structure == "uptrend" else "NONE"

        # Recency bonus
        score += max(0.0, 1.0 - weeks_ago / 24.0) * 20

        # "Not crazy late": 0 HH = max, 3+ HH = 0
        ext_score = max(0.0, 1.0 - hh_count / 3.0)
        score += ext_score * 20

    elif structure == "uptrend":
        score  += 15
        signal  = "UPTREND"

    # HL proximity bonus (max +10 se price è sopra HL di < 5%)
    if hl_dist is not None and 0.0 <= hl_dist <= 8.0:
        score += max(0.0, 1.0 - hl_dist / 8.0) * 10
        if "_HL" not in signal and signal not in ("NONE",):
            signal += "_HL"

    return round(score, 1), signal


def _accumulation_score(vol_arr: np.ndarray, bms_idx: int | None,
                        close_arr: np.ndarray, spy_close: np.ndarray | None) -> tuple[float, dict]:
    """
    Accumulation Score (0-100) — misura la firma istituzionale.

    Tre componenti:

    1. Volume sul BMS (0-40 pt)
       Rapporto tra volume della settimana BMS e media delle 12 settimane precedenti.
       Istituzioni comprano in massa quando rompono → volume esplosivo sul BMS.
         ≥ 3×  → 40 pt
         ≥ 2×  → 30 pt
         ≥ 1.5× → 18 pt
         ≥ 1.2× → 8 pt
         < 1.2× → 0 pt

    2. Contrazione di volume nella base (0-30 pt)
       Volume medio 8 settimane PRIMA del BMS vs 8 settimane ancora prima.
       Calo = smart money accumula silenziosamente.
         Contrazione ≥ 40% → 30 pt (firma classica accumulo)
         Contrazione ≥ 25% → 20 pt
         Contrazione ≥ 10% → 10 pt
         Nessuna contrazione → 0 pt

    3. Forza relativa vs SPY su 12 settimane (0-30 pt)
       (prezzo_ora / prezzo_12w_fa) / (SPY_ora / SPY_12w_fa)
       Titolo che outperforma il mercato anche in downtrend = accumulo reale.
         RS ≥ 1.15 → 30 pt
         RS ≥ 1.05 → 20 pt
         RS ≥ 0.95 → 8 pt
         RS < 0.95 → 0 pt

    Returns (accum_score, details_dict)
    """
    details = {
        "bms_vol_ratio":    None,
        "base_vol_contract": None,
        "rs_vs_spy":        None,
    }
    score = 0.0

    n = len(vol_arr)

    # ── 1. Volume sul BMS ──────────────────────────────────────────────────────
    if bms_idx is not None and bms_idx > 12:
        bms_vol      = float(vol_arr[bms_idx])
        pre_bms_avg  = float(vol_arr[max(0, bms_idx - 12):bms_idx].mean())
        if pre_bms_avg > 0:
            bvr = bms_vol / pre_bms_avg
            details["bms_vol_ratio"] = round(bvr, 2)
            if bvr >= 3.0:
                score += 40
            elif bvr >= 2.0:
                score += 30
            elif bvr >= 1.5:
                score += 18
            elif bvr >= 1.2:
                score += 8

    # ── 2. Contrazione volume nella base ──────────────────────────────────────
    if bms_idx is not None and bms_idx >= 16:
        base_vol  = float(vol_arr[max(0, bms_idx - 8):bms_idx].mean())
        prior_vol = float(vol_arr[max(0, bms_idx - 16):bms_idx - 8].mean())
        if prior_vol > 0:
            contraction = 1.0 - (base_vol / prior_vol)
            details["base_vol_contract"] = round(contraction * 100, 1)
            if contraction >= 0.40:
                score += 30
            elif contraction >= 0.25:
                score += 20
            elif contraction >= 0.10:
                score += 10

    # ── 3. RS vs SPY su 12 settimane ──────────────────────────────────────────
    if spy_close is not None and len(close_arr) >= 13 and len(spy_close) >= 13:
        try:
            rs = (close_arr[-1] / close_arr[-13]) / (spy_close[-1] / spy_close[-13])
            details["rs_vs_spy"] = round(rs, 3)
            if rs >= 1.15:
                score += 30
            elif rs >= 1.05:
                score += 20
            elif rs >= 0.95:
                score += 8
        except Exception:
            pass

    return round(score, 1), details


def scan_market_structure(hist_data: dict, meta_map: dict, swing_n: int = 3) -> list[dict]:
    """
    Scansiona l'universo S&P 1500 analizzando la market structure settimanale.

    Returns: lista di dict ordinati per ms_score + accum_score DESC.
             Contiene solo ticker con segnale actionable (BMS o HL in uptrend).
    """
    # SPY weekly close per RS calculation
    spy_weekly_close = None
    if "SPY" in hist_data and hist_data["SPY"] is not None:
        try:
            spy_w = _resample_weekly(hist_data["SPY"])
            spy_weekly_close = spy_w["Close"].values.astype(float)
        except Exception:
            pass

    results = []

    for sym, daily_hist in hist_data.items():
        if sym in ("SPY", "QQQ"):
            continue
        if daily_hist is None or len(daily_hist) < 80:
            continue

        try:
            weekly = _resample_weekly(daily_hist)
            if len(weekly) < 24:
                continue

            high_arr  = weekly["High"].values.astype(float)
            low_arr   = weekly["Low"].values.astype(float)
            close_arr = weekly["Close"].values.astype(float)
            vol_arr   = weekly["Volume"].values.astype(float)

            current_price = float(close_arr[-1])
            if current_price < 5:
                continue

            # Swing detection
            sh_list, sl_list = _detect_swings(high_arr, low_arr, n=swing_n)
            if len(sh_list) < 2 or len(sl_list) < 2:
                continue

            # Struttura
            structure = _classify_structure(sh_list, sl_list)
            if structure == "undefined":
                continue

            # BMS bullish
            bms = _find_bms_bullish(sh_list, len(weekly))

            # Scarta downtrend senza BMS recente
            if structure == "downtrend":
                if bms is None or bms["weeks_ago"] > 12:
                    continue

            # Scarta ranging senza BMS recente
            if structure == "ranging":
                if bms is None or bms["weeks_ago"] > 8:
                    continue

            # "Crazy late": troppi HH dal BMS senza pullback recente
            if bms and bms["hh_since_bms"] >= 4:
                continue

            # HL distance
            hl_dist = _hl_distance(sl_list, current_price, structure)

            # Score
            score, signal = _compute_score(structure, bms, hl_dist)
            if score < 5 or signal == "NONE":
                continue

            # Volume ratio (settimana corrente vs media 12 settimane)
            vol_last  = float(vol_arr[-1])
            vol_avg12 = float(vol_arr[-13:-1].mean()) if len(vol_arr) >= 14 else float(vol_arr[:-1].mean())
            vol_ratio = round(vol_last / vol_avg12, 2) if vol_avg12 > 0 else None

            # Accumulation Score
            bms_idx_abs = bms["bms_idx"] if bms else None
            # Allinea SPY weekly alla stessa lunghezza
            spy_close_aligned = None
            if spy_weekly_close is not None:
                min_len = min(len(close_arr), len(spy_weekly_close))
                spy_close_aligned = spy_weekly_close[-min_len:]
                close_aligned     = close_arr[-min_len:]
            else:
                close_aligned = close_arr

            accum_score, accum_details = _accumulation_score(
                vol_arr, bms_idx_abs, close_aligned, spy_close_aligned
            )

            # Ultimi swing levels per contesto
            last_sh = sh_list[-1][1] if sh_list else None
            last_sl = sl_list[-1][1] if sl_list else None

            meta = meta_map.get(sym, {})

            results.append({
                "ticker":           sym,
                "name":             meta.get("company_name", sym),
                "sector":           meta.get("sector", "—"),
                "price":            round(current_price, 2),
                "structure":        structure,
                "signal":           signal,
                "ms_score":         score,
                "accum_score":      accum_score,
                "bms_vol_ratio":    accum_details["bms_vol_ratio"],
                "base_vol_contract":accum_details["base_vol_contract"],
                "rs_vs_spy":        accum_details["rs_vs_spy"],
                "last_sh":          round(last_sh, 2) if last_sh else None,
                "last_sl":          round(last_sl, 2) if last_sl else None,
                "hl_dist_pct":      hl_dist,
                "bms_weeks_ago":    bms["weeks_ago"] if bms else None,
                "bms_level":        bms["bms_level"] if bms else None,
                "hh_since_bms":     bms["hh_since_bms"] if bms else None,
                "vol_ratio_w":      vol_ratio,
                "market_cap_m":     None,
                "description":      "",
            })

        except Exception as e:
            log.debug(f"[{sym}] ms_scan error: {e}")

    # Ordina per MS Score + Accumulation Score combinati
    results.sort(key=lambda x: (x["ms_score"] + x["accum_score"]), reverse=True)
    log.info(f"Market Structure scan: {len(results)} setup trovati")
    return results


def enrich_ms(results: list[dict]) -> list[dict]:
    """Aggiunge market cap (fast_info) e descrizione (.info) per ogni ticker."""
    import re
    import time
    import yfinance as yf

    for r in results:
        sym = r["ticker"]

        # Market cap
        try:
            mc = yf.Ticker(sym).fast_info.market_cap
            r["market_cap_m"] = round(mc / 1_000_000) if mc else None
        except Exception:
            r["market_cap_m"] = None
        time.sleep(0.1)

        # Descrizione (3 frasi)
        for attempt in range(3):
            try:
                info    = yf.Ticker(sym).info
                summary = info.get("longBusinessSummary") or ""
                if summary:
                    sentences    = re.split(r"(?<=[.!?])\s+", summary.strip())
                    r["description"] = " ".join(sentences[:3])
                break
            except Exception:
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))

    return results
