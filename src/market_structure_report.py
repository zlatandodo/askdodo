"""
HTML report generator for the Market Structure Scanner.
"""
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif;
  background: #f0f4f8;
  color: #1a2a3a;
  font-size: 14px;
}
.container { max-width: 1200px; margin: 0 auto; padding: 24px 16px; }

header {
  background: linear-gradient(135deg, #1a365d 0%, #2b6cb0 100%);
  color: #fff;
  padding: 28px 32px;
  border-radius: 10px;
  margin-bottom: 24px;
}
header h1 { font-size: 22px; font-weight: 700; }
header .subtitle { font-size: 13px; color: #bee3f8; margin-top: 6px; }
header .params { font-size: 11px; color: #90cdf4; margin-top: 10px; line-height: 1.8; }

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.summary-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
  border-left: 4px solid #2b6cb0;
}
.summary-card .label { font-size: 11px; color: #6b7a8d; text-transform: uppercase; letter-spacing: 0.5px; }
.summary-card .value { font-size: 22px; font-weight: 700; color: #1a365d; margin-top: 4px; }

.hint { font-size: 11px; color: #6b7a8d; margin-bottom: 8px; }

.finviz-btn {
  display: inline-block;
  background: #2b6cb0;
  color: #fff;
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  padding: 10px 20px;
  border-radius: 6px;
  margin-bottom: 14px;
}
.finviz-btn:hover { background: #1a365d; }

.table-wrap {
  overflow-x: auto;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
  margin-bottom: 24px;
}
table { width: 100%; border-collapse: collapse; min-width: 900px; }
thead th {
  background: #1a365d;
  color: #fff;
  padding: 11px 12px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}
thead th.sortable { cursor: pointer; user-select: none; }
thead th.sortable:hover { background: #2b6cb0; }
thead th.sort-asc::after  { content: " ▲"; font-size: 9px; }
thead th.sort-desc::after { content: " ▼"; font-size: 9px; }

tbody tr:nth-child(even) { background: #f7fafc; }
tbody tr:hover { background: #ebf8ff; }
td { padding: 9px 12px; border-bottom: 1px solid #e8edf2; white-space: nowrap; }

.sym-link { color: #2b6cb0; text-decoration: none; font-weight: 700; font-size: 13px; }
.sym-link:hover { text-decoration: underline; }
.sym-icon { font-size: 9px; margin-left: 3px; opacity: 0.6; }

/* Signal badges */
.sig { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }
.sig-bms-fresh  { background: #c6f6d5; color: #276749; }
.sig-bms-recent { background: #bee3f8; color: #1a365d; }
.sig-bms-old    { background: #e9d8fd; color: #553c9a; }
.sig-hl         { background: #fefcbf; color: #7b6d00; }
.sig-uptrend    { background: #e2e8f0; color: #4a5568; }

/* Score colori */
.score-high { color: #276749; font-weight: 800; font-size: 15px; }
.score-mid  { color: #c05621; font-weight: 700; font-size: 15px; }
.score-low  { color: #4a5568; font-weight: 600; font-size: 14px; }

footer { text-align: center; color: #8a9ab0; font-size: 11px; margin-top: 32px; }
"""

SORT_JS = """
(function() {
  var table   = document.getElementById('ms-table');
  var headers = table.querySelectorAll('thead th.sortable');
  var tbody   = table.querySelector('tbody');
  var sortCol = 0;   // MS Score + Accum Score combinati
  var sortAsc = false;

  function sortTable(col, asc) {
    var rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort(function(a, b) {
      var av = a.cells[col].getAttribute('data-sort') || a.cells[col].textContent.trim();
      var bv = b.cells[col].getAttribute('data-sort') || b.cells[col].textContent.trim();
      var an = parseFloat(av), bn = parseFloat(bv);
      if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
      return asc ? av.localeCompare(bv) : bv.localeCompare(av);
    });
    rows.forEach(function(r) { tbody.appendChild(r); });
  }

  headers.forEach(function(th) {
    th.addEventListener('click', function() {
      var col = parseInt(th.getAttribute('data-col'));
      if (col === sortCol) { sortAsc = !sortAsc; }
      else { sortCol = col; sortAsc = false; }
      headers.forEach(function(h) { h.classList.remove('sort-asc','sort-desc'); });
      th.classList.add(sortAsc ? 'sort-asc' : 'sort-desc');
      sortTable(col, sortAsc);
    });
  });

  sortTable(sortCol, sortAsc);
})();
"""

_SIGNAL_LABELS = {
    "BMS_FRESH":    ("🟢 BMS FRESCO",   "sig-bms-fresh"),
    "BMS_FRESH_HL": ("🟢 BMS FRESCO + HL", "sig-bms-fresh"),
    "BMS_RECENT":   ("🔵 BMS RECENTE",  "sig-bms-recent"),
    "BMS_RECENT_HL":("🔵 BMS RECENTE + HL", "sig-bms-recent"),
    "BMS_OLD":      ("🟣 BMS DATATO",   "sig-bms-old"),
    "BMS_OLD_HL":   ("🟣 BMS DATATO + HL", "sig-bms-old"),
    "UPTREND_HL":   ("🟡 PULLBACK HL",  "sig-hl"),
    "UPTREND":      ("⚪ UPTREND",      "sig-uptrend"),
}


def _fmt(val, decimals=2, prefix="", suffix=""):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        return f"{prefix}{float(val):,.{decimals}f}{suffix}"
    except Exception:
        return str(val)


def _fmt_mcap(val_m) -> str:
    if val_m is None:
        return "—"
    try:
        m = float(val_m)
        return f"${m/1000:.1f}B" if m >= 1000 else f"${m:.0f}M"
    except Exception:
        return "—"


def _score_class(score) -> str:
    if score is None:
        return ""
    try:
        s = float(score)
        if s >= 65:
            return "score-high"
        if s >= 40:
            return "score-mid"
        return "score-low"
    except Exception:
        return ""


def generate_market_structure_html(results: list[dict], run_date: str, output_path: Path) -> Path:
    n = len(results)

    # Summary cards
    fresh  = sum(1 for r in results if "BMS_FRESH"  in r.get("signal", ""))
    recent = sum(1 for r in results if "BMS_RECENT" in r.get("signal", ""))
    hl     = sum(1 for r in results if "_HL"        in r.get("signal", ""))

    cards_html = "".join([
        f'<div class="summary-card"><div class="label">{l}</div><div class="value">{v}</div></div>'
        for l, v in [
            ("Setup totali",    str(n)),
            ("BMS Freschi",     str(fresh)),
            ("BMS Recenti",     str(recent)),
            ("Pullback HL",     str(hl)),
            ("Data run",        run_date),
        ]
    ])

    symbols    = [r["ticker"] for r in results]
    finviz_url = "https://finviz.com/screener.ashx?v=111&t=" + ",".join(symbols) if symbols else "#"

    # Table rows
    rows_html = ""
    for r in results:
        sym    = r.get("ticker", "")
        name   = r.get("name", sym)
        sector = r.get("sector") or "—"
        price  = r.get("price", 0)
        score  = r.get("ms_score", 0)
        signal = r.get("signal", "")
        struct = r.get("structure", "—")

        bms_ago   = r.get("bms_weeks_ago")
        bms_lvl   = r.get("bms_level")
        hh_since  = r.get("hh_since_bms")
        hl_dist   = r.get("hl_dist_pct")
        last_sl   = r.get("last_sl")
        last_sh   = r.get("last_sh")
        vol_r     = r.get("vol_ratio_w")
        mcap_m    = r.get("market_cap_m")
        accum     = r.get("accum_score", 0) or 0
        bms_vol   = r.get("bms_vol_ratio")
        base_contr= r.get("base_vol_contract")
        rs_spy    = r.get("rs_vs_spy")

        tv_url     = f"https://www.tradingview.com/chart/?symbol={sym}"
        label, css = _SIGNAL_LABELS.get(signal, (signal, "sig-uptrend"))
        score_cls  = _score_class(score)
        accum_cls  = _score_class(accum)

        bms_ago_str   = f"{bms_ago}w fa" if bms_ago is not None else "—"
        hh_since_str  = str(hh_since) if hh_since is not None else "—"
        hl_dist_str   = _fmt(hl_dist, 1, suffix="%") if hl_dist is not None else "—"
        bms_vol_str   = _fmt(bms_vol, 1, suffix="×") if bms_vol is not None else "—"
        contr_str     = f"-{base_contr:.0f}%" if base_contr and base_contr > 0 else ("+" + f"{abs(base_contr):.0f}%" if base_contr else "—")
        rs_str        = _fmt(rs_spy, 2) if rs_spy is not None else "—"

        # RS colore: verde se >1.05, rosso se <0.95
        rs_color = "#276749" if (rs_spy or 0) >= 1.05 else ("#c53030" if (rs_spy or 1) < 0.95 else "#4a5568")

        rows_html += f"""
        <tr>
          <td data-sort="{score + accum}" style="text-align:center">
            <div class="{score_cls}">{score}</div>
            <div style="font-size:10px;color:#718096">MS</div>
          </td>
          <td data-sort="{accum}" style="text-align:center">
            <div class="{accum_cls}">{accum}</div>
            <div style="font-size:10px;color:#718096">ACC</div>
          </td>
          <td data-sort="{sym}">
            <a class="sym-link" href="{tv_url}" target="_blank">{sym}<span class="sym-icon">↗</span></a>
            <br><small style="color:#6b7a8d;font-size:11px">{name}</small>
          </td>
          <td data-sort="{signal}"><span class="sig {css}">{label}</span></td>
          <td data-sort="{sector}" style="font-size:12px">{sector}</td>
          <td data-sort="{price}">{_fmt(price, 2, prefix="$")}</td>
          <td data-sort="{bms_ago or 9999}">{bms_ago_str}</td>
          <td data-sort="{hh_since or 0}">{hh_since_str}</td>
          <td data-sort="{hl_dist or 9999}">{hl_dist_str}</td>
          <td data-sort="{bms_vol or 0}" style="font-weight:600">{bms_vol_str}</td>
          <td data-sort="{base_contr or 0}">{contr_str}</td>
          <td data-sort="{rs_spy or 0}" style="color:{rs_color};font-weight:600">{rs_str}</td>
          <td data-sort="{vol_r or 0}">{_fmt(vol_r, 2, suffix="×")}</td>
          <td data-sort="{mcap_m or 0}">{_fmt_mcap(mcap_m)}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Market Structure Scanner — {run_date}</title>
  <style>{CSS}</style>
</head>
<body>
<div class="container">

  <header>
    <h1>📊 Market Structure Scanner</h1>
    <div class="subtitle">Scan del {run_date} &nbsp;|&nbsp; {n} setup &nbsp;|&nbsp; Universo S&amp;P 1500 &nbsp;|&nbsp; Timeframe: Weekly</div>
    <div class="params">
      <strong>Metodologia Mac (@MacnBTC):</strong> &nbsp;
      Swing highs/lows (N=3 weekly) &nbsp;·&nbsp;
      Struttura: HH+HL=uptrend, LH+LL=downtrend &nbsp;·&nbsp;
      BMS Bullish: rottura dell'ultimo Lower High &nbsp;·&nbsp;
      HL Entry: pullback al Higher Low in uptrend &nbsp;·&nbsp;
      Esclusi "crazy late" (≥4 HH dal BMS)
    </div>
  </header>

  <div class="summary-grid">{cards_html}</div>

  <a class="finviz-btn" href="{finviz_url}" target="_blank">📊 Apri tutti su Finviz</a>

  <p class="hint">
    💡 <strong>🟢 BMS FRESCO</strong> = rottura struttura &lt;4 settimane (max priorità) &nbsp;·&nbsp;
    <strong>🔵 BMS RECENTE</strong> = 4-12 settimane &nbsp;·&nbsp;
    <strong>🟡 PULLBACK HL</strong> = price vicino al supporto &nbsp;·&nbsp;
    Clicca intestazione per ordinare
  </p>

  <div class="table-wrap">
    <table id="ms-table">
      <thead>
        <tr>
          <th class="sortable sort-desc" data-col="0">MS Score ▼</th>
          <th class="sortable" data-col="1">Acc. Score</th>
          <th class="sortable" data-col="2">Ticker</th>
          <th class="sortable" data-col="3">Segnale</th>
          <th class="sortable" data-col="4">Settore</th>
          <th class="sortable" data-col="5">Prezzo</th>
          <th class="sortable" data-col="6">BMS (sett.)</th>
          <th class="sortable" data-col="7">HH dal BMS</th>
          <th class="sortable" data-col="8">Dist. HL</th>
          <th class="sortable" data-col="9">Vol BMS</th>
          <th class="sortable" data-col="10">Base Contr.</th>
          <th class="sortable" data-col="11">RS vs SPY</th>
          <th class="sortable" data-col="12">Vol sett.</th>
          <th class="sortable" data-col="13">Mkt Cap</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

  <footer>
    Market Structure Scanner &nbsp;·&nbsp; {run_date} &nbsp;·&nbsp;
    Basato sulla metodologia di Mac (@MacnBTC) &nbsp;·&nbsp;
    Non è consulenza finanziaria.
  </footer>
</div>
<script>{SORT_JS}</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    log.info(f"Market Structure report saved: {output_path}")
    return output_path
