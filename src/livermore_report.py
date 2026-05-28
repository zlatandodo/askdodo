"""
HTML report generator for the standalone Livermore Buy the Dip scanner.
Shows up to 20 tickers with the BTD-specific fields only.
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
.container { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }

header {
  background: linear-gradient(135deg, #064e3b 0%, #065f46 100%);
  color: #fff;
  padding: 28px 32px;
  border-radius: 10px;
  margin-bottom: 24px;
}
header h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
header .subtitle { font-size: 13px; color: #a7f3d0; margin-top: 6px; }
header .params { font-size: 11px; color: #6ee7b7; margin-top: 10px; line-height: 1.8; }

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
  border-left: 4px solid #10b981;
}
.summary-card .label { font-size: 11px; color: #6b7a8d; text-transform: uppercase; letter-spacing: 0.5px; }
.summary-card .value { font-size: 22px; font-weight: 700; color: #064e3b; margin-top: 4px; }

.hint {
  font-size: 11px; color: #6b7a8d;
  margin-bottom: 8px;
}

.table-wrap {
  overflow-x: auto;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
  margin-bottom: 24px;
}
table { width: 100%; border-collapse: collapse; min-width: 750px; }
thead th {
  background: #064e3b;
  color: #fff;
  padding: 11px 13px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}
thead th.sortable { cursor: pointer; user-select: none; }
thead th.sortable:hover { background: #065f46; }
thead th.sort-asc::after  { content: " ▲"; font-size: 9px; }
thead th.sort-desc::after { content: " ▼"; font-size: 9px; }

tbody tr:nth-child(even) { background: #f5f8fc; }
tbody tr:hover { background: #d1fae5; }
td { padding: 10px 13px; border-bottom: 1px solid #e8edf2; white-space: nowrap; }

.sym-link {
  color: #065f46;
  text-decoration: none;
  font-weight: 700;
  font-size: 13px;
}
.sym-link:hover { text-decoration: underline; }
.sym-icon { font-size: 9px; margin-left: 3px; opacity: 0.6; vertical-align: middle; }

.srsi-low  { color: #065f46; font-weight: 700; }   /* ≤ 10 — very oversold */
.srsi-mid  { color: #b45309; font-weight: 600; }   /* 10-20 */
.srsi-high { color: #1a2a3a; }                      /* 20-30 */

.ext-low  { color: #065f46; }   /* ≤ 2% from EMA65 */
.ext-mid  { color: #b45309; }   /* 2-8% */
.ext-high { color: #6b7a8d; }   /* > 8% */

.links-panel {
  background: #fff;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
  font-size: 12px;
  color: #4a5568;
  line-height: 2.2;
}
.links-panel strong {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #064e3b;
}
.finviz-btn {
  display: inline-block;
  background: #064e3b;
  color: #fff;
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  padding: 10px 20px;
  border-radius: 6px;
  margin-bottom: 14px;
  letter-spacing: 0.2px;
}
.finviz-btn:hover { background: #065f46; }

footer { text-align: center; color: #8a9ab0; font-size: 11px; margin-top: 32px; }

@media (max-width: 700px) {
  header { padding: 16px; }
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
  table { min-width: 600px; }
}
"""

SORT_JS = """
(function() {
  var table   = document.getElementById('btd-table');
  var headers = table.querySelectorAll('thead th.sortable');
  var tbody   = table.querySelector('tbody');
  var sortCol = 0;    // default: Bounce Score decrescente
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


def _fmt_vol(val) -> str:
    if val is None:
        return "—"
    try:
        v = float(val)
        if v >= 1_000_000:
            return f"{v/1_000_000:.1f}M"
        if v >= 1_000:
            return f"{v/1_000:.0f}K"
        return str(int(v))
    except Exception:
        return "—"


def _srsi_class(val) -> str:
    if val is None or pd.isna(val):
        return ""
    try:
        v = float(val)
        if v <= 10:
            return "srsi-low"
        if v <= 20:
            return "srsi-mid"
        return "srsi-high"
    except Exception:
        return ""


def _ext_class(val) -> str:
    if val is None:
        return ""
    try:
        v = float(val)
        if v <= 2:
            return "ext-low"
        if v <= 8:
            return "ext-mid"
        return "ext-high"
    except Exception:
        return ""


def generate_livermore_html(results: list[dict], run_date: str, output_path: Path) -> Path:
    """
    Generate a self-contained HTML report for Livermore Buy the Dip results.

    results : list of dicts from scan_livermore_buy_the_dip()
    """
    n = len(results)

    # Summary cards
    if results:
        avg_srsi = sum(r.get("stoch_rsi", 0) or 0 for r in results) / n
        avg_ext  = sum(r.get("pct_from_ema65", 0) or 0 for r in results) / n
    else:
        avg_srsi = avg_ext = 0

    cards = [
        ("Ticker trovati", str(n), ""),
        ("StochRSI medio", f"{avg_srsi:.1f}", ""),
        ("Ext. media EMA65", f"{avg_ext:.1f}%", ""),
        ("Data run", run_date, ""),
    ]
    cards_html = "\n".join(
        f'<div class="summary-card"><div class="label">{l}</div>'
        f'<div class="value">{v}</div></div>'
        for l, v, _ in cards
    )

    # TradingView + Finviz links
    symbols = [r["ticker"] for r in results]
    finviz_url = "https://finviz.com/screener.ashx?v=111&t=" + ",".join(symbols) if symbols else "#"
    tv_links = " &nbsp;|&nbsp; ".join(
        f'<a href="https://www.tradingview.com/chart/?symbol={s}" target="_blank">{s}</a>'
        for s in symbols
    )

    # Table rows
    rows_html = ""
    for r in results:
        sym     = r.get("ticker", "")
        name    = r.get("name", sym)
        sector  = r.get("sector") or "—"
        price   = r.get("price", 0)
        ma200   = r.get("ma200", 0)
        ema65   = r.get("ema65", 0)
        ema88   = r.get("ema88", 0)
        ema100  = r.get("ema100", 0)
        ext     = r.get("pct_from_ema65", 0)
        srsi    = r.get("stoch_rsi", 0)
        vol     = r.get("avg_vol_50", 0)
        mcap_m  = r.get("market_cap_m")
        bscore  = r.get("bounce_score", 0)

        tv_url   = f"https://www.tradingview.com/chart/?symbol={sym}"
        srsi_cls = _srsi_class(srsi)
        ext_cls  = _ext_class(ext)

        # Bounce score colore: verde ≥70, arancione ≥50, grigio <50
        bs_color = "#065f46" if bscore >= 70 else ("#b45309" if bscore >= 50 else "#4a5568")

        rows_html += f"""
        <tr>
          <td data-sort="{bscore}" style="font-weight:700;font-size:15px;color:{bs_color};text-align:center">{bscore}</td>
          <td data-sort="{sym}">
            <a class="sym-link" href="{tv_url}" target="_blank">{sym}<span class="sym-icon">↗</span></a>
            <br><small style="color:#6b7a8d;font-size:11px">{name}</small>
          </td>
          <td data-sort="{sector}">{sector}</td>
          <td data-sort="{price}">{_fmt(price, 2, prefix="$")}</td>
          <td data-sort="{srsi}" class="{srsi_cls}">{_fmt(srsi, 1)}</td>
          <td data-sort="{ext}" class="{ext_cls}">{_fmt(ext, 1, suffix="%")}</td>
          <td data-sort="{ema65}">{_fmt(ema65, 2, prefix="$")}</td>
          <td data-sort="{ema88}">{_fmt(ema88, 2, prefix="$")}</td>
          <td data-sort="{ema100}">{_fmt(ema100, 2, prefix="$")}</td>
          <td data-sort="{ma200}">{_fmt(ma200, 2, prefix="$")}</td>
          <td data-sort="{vol}">{_fmt_vol(vol)}</td>
          <td data-sort="{mcap_m or 0}">{_fmt_mcap(mcap_m)}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Livermore Buy the Dip — {run_date}</title>
  <style>{CSS}</style>
</head>
<body>
<div class="container">

  <header>
    <h1>🟢 Livermore Buy the Dip</h1>
    <div class="subtitle">Scan del {run_date} &nbsp;|&nbsp; {n} ticker &nbsp;|&nbsp; Universo S&amp;P 1500</div>
    <div class="params">
      <strong>Parametri (replicati da AskLivermore):</strong> &nbsp;
      Prezzo &gt; SMA200 &nbsp;·&nbsp;
      EMA65 &gt; EMA100 &nbsp;·&nbsp;
      Prezzo ≥ EMA65 &nbsp;·&nbsp;
      Distanza EMA65 ≤ 20% &nbsp;·&nbsp;
      <strong>StochRSI(14,14,3) ≤ 30</strong> [Wilder RMA] &nbsp;·&nbsp;
      Vol 50gg ≥ 200K
    </div>
  </header>

  <div class="summary-grid">{cards_html}</div>

  <a class="finviz-btn" href="{finviz_url}" target="_blank">📊 Apri tutti su Finviz</a>

  <div class="links-panel">
    <strong>📈 TradingView — chart singolo:</strong><br>
    {tv_links}
  </div>

  <p class="hint">💡 Ordinati per Bounce Score · Verde ≥70 · Arancione ≥50 · Clicca intestazione per riordinare</p>

  <div class="table-wrap">
    <table id="btd-table">
      <thead>
        <tr>
          <th class="sortable sort-desc" data-col="0">Bounce Score ▼</th>
          <th class="sortable" data-col="1">Ticker</th>
          <th class="sortable" data-col="2">Settore</th>
          <th class="sortable" data-col="3">Prezzo</th>
          <th class="sortable" data-col="4">StochRSI</th>
          <th class="sortable" data-col="5">Dist. EMA65</th>
          <th class="sortable" data-col="6">EMA65</th>
          <th class="sortable" data-col="7">EMA88</th>
          <th class="sortable" data-col="8">EMA100</th>
          <th class="sortable" data-col="9">SMA200</th>
          <th class="sortable" data-col="10">Vol 50gg</th>
          <th class="sortable" data-col="11">Mkt Cap</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

  <footer>
    Livermore Buy the Dip Scanner — replicato da AskLivermore &nbsp;|&nbsp; {run_date}<br>
    Solo scopo informativo. Non è un consiglio finanziario.
  </footer>
</div>
<script>{SORT_JS}</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    log.info(f"Livermore BTD report saved: {output_path}")
    return output_path
