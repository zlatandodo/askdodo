"""
Diagnose the Livermore Buy the Dip scanner discrepancies.

Strategy:
1. Fetch fresh AskLivermore results for BTD + Trend Template
2. Run our scanner on the full universe
3. Analyse:
   - False positives: what do they have that AskLiv's results don't?
   - Missing: why do we miss tickers?

Run: python3 tools/diagnose_livermore_dip.py
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from src.scraper import get_token, _api_get, SCANNER_SLUGS


# ── AskLivermore fetch ────────────────────────────────────────────────────────

def fetch_scanner_tickers(name: str, token: str) -> set[str]:
    slug = SCANNER_SLUGS.get(name, name)
    try:
        data    = _api_get(f"/api/scanners/{slug}/results", token)
        matches = data.get("matches", [])
        tickers = set()
        for m in matches:
            for key in ("ticker", "symbol", "Ticker", "Symbol"):
                if key in m:
                    tickers.add(str(m[key]).upper().strip())
                    break
        print(f"  {name} ({slug}): {len(tickers)} tickers")
        return tickers
    except Exception as e:
        print(f"  {name}: FAILED — {e}")
        return set()


def fetch_scanner_raw(name: str, token: str) -> list[dict]:
    slug = SCANNER_SLUGS.get(name, name)
    try:
        data    = _api_get(f"/api/scanners/{slug}/results", token)
        return data.get("matches", [])
    except Exception as e:
        print(f"  {name}: FAILED — {e}")
        return []


# ── Our scanner with full diagnostics ────────────────────────────────────────

def _stoch_rsi(close: pd.Series, rsi_len: int = 14, stoch_len: int = 14, smooth_k: int = 3) -> float:
    """Wilder RMA-based StochRSI (matches AskLivermore exactly)."""
    min_bars = rsi_len + stoch_len + smooth_k + 5
    if len(close) < min_bars:
        return float("nan")
    alpha = 1.0 / rsi_len
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(alpha=alpha, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=alpha, adjust=False).mean()
    rs    = gain / loss.replace(0, float("nan"))
    rsi   = 100 - 100 / (1 + rs)
    rsi_min   = rsi.rolling(stoch_len).min()
    rsi_max   = rsi.rolling(stoch_len).max()
    rsi_range = rsi_max - rsi_min
    stoch_raw = ((rsi - rsi_min) / rsi_range.replace(0, float("nan"))) * 100
    k         = stoch_raw.rolling(smooth_k).mean()
    val       = float(k.iloc[-1])
    return float("nan") if np.isnan(val) else round(val, 1)


def _sma(series: pd.Series, n: int) -> float:
    if len(series) < n:
        return float("nan")
    return float(series.iloc[-n:].mean())


def run_our_scanner(hist_data: dict, meta_map: dict) -> dict[str, dict]:
    """
    Returns {ticker: diagnostics_dict} for every scanned symbol.
    Records pass/fail and WHY each stock fails.
    """
    out = {}
    for sym, hist in hist_data.items():
        if sym in ("SPY", "QQQ"):
            continue
        if len(hist) < 215:
            continue
        try:
            close  = hist["Close"]
            volume = hist["Volume"]
            price  = float(close.iloc[-1])
            ma200  = _sma(close, 200)

            ema65_s  = close.ewm(span=65,  adjust=False).mean()
            ema88_s  = close.ewm(span=88,  adjust=False).mean()
            ema100_s = close.ewm(span=100, adjust=False).mean()
            ema65    = float(ema65_s.iloc[-1])
            ema88    = float(ema88_s.iloc[-1])
            ema100   = float(ema100_s.iloc[-1])
            srsi     = _stoch_rsi(close, 14)

            pct_from_ema65 = (price - ema65) / ema65 * 100 if ema65 else float("nan")
            ma_stacked_full = ema65 > ema88 > ema100
            ma_stacked_soft = ema65 > ema100  # our current rule

            # Average volume 50d
            avg_vol_50 = float(volume.tail(50).mean()) if len(volume) >= 50 else float("nan")

            fail_reasons = []
            if np.isnan(ma200):
                fail_reasons.append("ma200_nan")
            elif price <= ma200:
                fail_reasons.append("below_ma200")

            if not (ema65 > ema100):
                fail_reasons.append("ema65_not_above_ema100")

            if price < ema65:
                fail_reasons.append("below_ema65")

            if not np.isnan(pct_from_ema65) and pct_from_ema65 > 20.0:
                fail_reasons.append(f"too_extended_{pct_from_ema65:.1f}pct")

            if np.isnan(srsi):
                fail_reasons.append("srsi_nan")
            elif srsi > 30:
                fail_reasons.append(f"srsi_high_{srsi:.1f}")

            out[sym] = {
                "price":          round(price, 2),
                "ma200":          round(ma200, 2) if not np.isnan(ma200) else None,
                "ema65":          round(ema65, 2),
                "ema88":          round(ema88, 2),
                "ema100":         round(ema100, 2),
                "pct_from_ema65": round(pct_from_ema65, 1) if not np.isnan(pct_from_ema65) else None,
                "stoch_rsi":      srsi,
                "ma_stacked_full":    ma_stacked_full,
                "ma_stacked_soft":    ma_stacked_soft,
                "avg_vol_50d":    round(avg_vol_50) if not np.isnan(avg_vol_50) else None,
                "fail_reasons":   fail_reasons,
                "pass_all":       len(fail_reasons) == 0,
            }
        except Exception as e:
            pass

    return out


# ── Analysis ──────────────────────────────────────────────────────────────────

def analyse(btd_tickers: set, trend_tickers: set, btd_raw: list[dict], our_results: dict):
    our_pass    = {sym for sym, d in our_results.items() if d["pass_all"]}
    all_scanned = set(our_results.keys())

    overlap          = btd_tickers & our_pass
    false_pos        = our_pass - btd_tickers
    missing          = (btd_tickers & all_scanned) - our_pass
    btd_not_scanned  = btd_tickers - all_scanned

    print("\n" + "="*65)
    print("OVERLAP ANALYSIS")
    print("="*65)
    print(f"AskLiv BTD tickers:       {len(btd_tickers)}")
    print(f"Our passing tickers:      {len(our_pass)}")
    print(f"Overlap:                  {len(overlap)} ({len(overlap)/max(len(btd_tickers),1)*100:.0f}% of AskLiv)")
    print(f"False positives:          {len(false_pos)} (we pass, AskLiv doesn't)")
    print(f"Missing (we fail):        {len(missing)} (AskLiv has, we fail)")
    print(f"Not in our universe:      {len(btd_not_scanned)} (AskLiv has, not S&P1500)")

    # ── Why do we MISS tickers?
    print("\n" + "-"*65)
    print("MISSING TICKERS — why we fail them")
    print("-"*65)
    fail_counter: dict[str, int] = {}
    for sym in sorted(missing):
        d = our_results[sym]
        reasons = d["fail_reasons"]
        reason_str = [r.split("_nan")[0].split("_high_")[0].split("_")[0] for r in reasons]
        print(f"  {sym:6s}: srsi={d['stoch_rsi']:5.1f}  ext={str(d['pct_from_ema65']):>6}%  "
              f"stacked={d['ma_stacked_full']}  fails={', '.join(reasons[:3])}")
        for r in reasons:
            bucket = r.split("(")[0].split("_")[0] if "srsi" not in r else "srsi_too_high"
            fail_counter[bucket] = fail_counter.get(bucket, 0) + 1

    # Summarise
    fail_buckets: dict[str, int] = {}
    for sym in missing:
        for r in our_results[sym]["fail_reasons"]:
            if "srsi" in r:
                b = "srsi_too_high"
            elif "extended" in r:
                b = "too_extended"
            elif "ema65" in r and "not_above" in r:
                b = "ema_not_stacked"
            elif "below_ema65" in r:
                b = "below_ema65"
            elif "below_ma200" in r:
                b = "below_ma200"
            elif "ma200_nan" in r:
                b = "ma200_nan"
            else:
                b = r
            fail_buckets[b] = fail_buckets.get(b, 0) + 1
    print("\n  Failure buckets:")
    for k, v in sorted(fail_buckets.items(), key=lambda x: -x[1]):
        print(f"    {k}: {v}")

    # ── Tickers not in our universe
    if btd_not_scanned:
        print(f"\n  Not in S&P1500 ({len(btd_not_scanned)}): {', '.join(sorted(btd_not_scanned))}")

    # ── Trend Template overlap
    print("\n" + "-"*65)
    print("TREND TEMPLATE OVERLAP")
    print("-"*65)
    btd_in_trend = btd_tickers & trend_tickers
    fp_in_trend  = false_pos   & trend_tickers
    ok_in_trend  = overlap     & trend_tickers

    print(f"  AskLiv BTD in Trend Template:    {len(btd_in_trend)}/{len(btd_tickers)} "
          f"({len(btd_in_trend)/max(len(btd_tickers),1)*100:.0f}%)")
    print(f"  Our MATCHED in Trend Template:   {len(ok_in_trend)}/{len(overlap)} "
          f"({len(ok_in_trend)/max(len(overlap),1)*100:.0f}%)")
    print(f"  Our FALSE POS in Trend Template: {len(fp_in_trend)}/{len(false_pos)} "
          f"({len(fp_in_trend)/max(len(false_pos),1)*100:.0f}%)")

    # ── Simulate Trend Template as pre-filter
    print("\n  Simulation — add Trend Template pre-filter:")
    our_pass_trend = our_pass & trend_tickers
    ol_sim = btd_tickers & our_pass_trend
    fp_sim = our_pass_trend - btd_tickers
    print(f"    Our passing with trend filter:  {len(our_pass_trend)}")
    print(f"    Overlap:                        {len(ol_sim)} ({len(ol_sim)/max(len(btd_tickers),1)*100:.0f}% of AskLiv)")
    print(f"    False positives remaining:      {len(fp_sim)}")

    # ── Compare FP stats vs matched stats
    print("\n" + "-"*65)
    print("FALSE POSITIVES vs MATCHED — statistical comparison")
    print("-"*65)
    for label, group in [("MATCHED", overlap), ("FALSE POS", false_pos)]:
        data = [our_results[s] for s in group if s in our_results]
        if not data:
            continue
        srsi_vals = [d["stoch_rsi"] for d in data
                     if d.get("stoch_rsi") is not None and not np.isnan(d["stoch_rsi"])]
        ext_vals  = [d["pct_from_ema65"] for d in data if d.get("pct_from_ema65") is not None]
        vol_vals  = [d["avg_vol_50d"] for d in data if d.get("avg_vol_50d") is not None]
        stk_full  = sum(1 for d in data if d.get("ma_stacked_full"))
        print(f"\n  [{label}] n={len(data)}")
        if srsi_vals:
            print(f"    StochRSI:       min={min(srsi_vals):.1f}  "
                  f"mean={sum(srsi_vals)/len(srsi_vals):.1f}  max={max(srsi_vals):.1f}")
        if ext_vals:
            print(f"    pct_from_ema65: min={min(ext_vals):.1f}  "
                  f"mean={sum(ext_vals)/len(ext_vals):.1f}  max={max(ext_vals):.1f}")
        if vol_vals:
            med_vol = sorted(vol_vals)[len(vol_vals)//2]
            print(f"    avg_vol_50d:    median={med_vol:,.0f}  min={min(vol_vals):,.0f}")
        print(f"    MA stacked (65>88>100): {stk_full}/{len(data)}")

    # ── What volume threshold would eliminate most FPs?
    print("\n" + "-"*65)
    print("VOLUME THRESHOLD TEST (to cut false positives)")
    print("-"*65)
    for min_vol in [100_000, 200_000, 300_000, 500_000, 750_000, 1_000_000]:
        fp_after  = {s for s in false_pos
                     if our_results.get(s, {}).get("avg_vol_50d", 0) >= min_vol}
        ok_after  = {s for s in overlap
                     if our_results.get(s, {}).get("avg_vol_50d", 0) >= min_vol}
        print(f"  min_vol={min_vol//1000}k: overlap={len(ok_after)}/{len(overlap)}, "
              f"false_pos={len(fp_after)} (down from {len(false_pos)})")

    # ── Matched tickers
    print("\n" + "-"*65)
    print(f"MATCHED ({len(overlap)}): {', '.join(sorted(overlap))}")

    return {
        "overlap": sorted(overlap),
        "false_positives": sorted(false_pos),
        "missing": sorted(missing),
        "btd_not_in_universe": sorted(btd_not_scanned),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Livermore Buy the Dip — Diagnostic Run ===\n")

    # 1. Token
    print("Step 1: Obtaining AskLivermore token...")
    token = get_token()

    # 2. Fetch AskLivermore scanner data
    print("\nStep 2: Fetching scanner results from AskLivermore...")
    btd_raw    = fetch_scanner_raw("livermore_buy_the_dip", token)
    btd_tickers = set()
    for m in btd_raw:
        for key in ("ticker", "symbol", "Ticker", "Symbol"):
            if key in m:
                btd_tickers.add(str(m[key]).upper().strip())
                break
    print(f"  BTD: {len(btd_tickers)} tickers")

    # Save sample to inspect the raw keys
    if btd_raw:
        sample = btd_raw[:2]
        print(f"  Sample BTD item keys: {list(sample[0].keys())}")
        print(f"  Sample BTD item: {json.dumps(sample[0], default=str)[:500]}")

    trend_tickers = fetch_scanner_tickers("trend_template", token)

    # 3. Universe + history
    print("\nStep 3: Fetching universe + downloading history...")
    import yaml
    from src.free_scanner import get_universe, download_history

    config   = yaml.safe_load((BASE_DIR / "free_config.yaml").read_text())
    symbols, meta_map = get_universe(config)
    all_syms = ["SPY", "QQQ"] + [s for s in symbols if s not in ("SPY", "QQQ")]
    print(f"  Downloading {len(all_syms)} symbols (~5 min)...")
    hist_data = download_history(all_syms)
    print(f"  {len(hist_data)} symbols downloaded")

    # 4. Our scanner
    print("\nStep 4: Running diagnostic scanner...")
    our_results = run_our_scanner(hist_data, meta_map)
    our_pass    = [s for s, d in our_results.items() if d["pass_all"]]
    print(f"  Scanned {len(our_results)} symbols, {len(our_pass)} pass all filters")

    # 5. Analyse
    report = analyse(btd_tickers, trend_tickers, btd_raw, our_results)

    # Save
    out_path = BASE_DIR / ".tmp" / "btd_diagnosis.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved → {out_path}")


if __name__ == "__main__":
    main()
