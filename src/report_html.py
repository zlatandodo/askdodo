"""
Generate a self-contained HTML report with inline CSS.
Modern design: Inter/system font, navy/white/green/red palette, mobile responsive.
"""
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

INLINE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif;
  background: #f0f4f8;
  color: #1a2a3a;
  font-size: 14px;
}
.container { max-width: 1200px; margin: 0 auto; padding: 24px 16px; }
header {
  background: #1B2A4A;
  color: #fff;
  padding: 24px 32px;
  border-radius: 8px;
  margin-bottom: 24px;
}
header h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
header .subtitle { font-size: 13px; color: #a0b0c8; margin-top: 4px; }

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.summary-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
}
.summary-card .label { font-size: 11px; color: #6b7a8d; text-transform: uppercase; letter-spacing: 0.5px; }
.summary-card .value { font-size: 22px; font-weight: 700; color: #1B2A4A; margin-top: 4px; }
.summary-card .value.green { color: #1a7f4b; }
.summary-card .value.red { color: #c0392b; }

h2 { font-size: 16px; font-weight: 600; margin-bottom: 12px; color: #1B2A4A; }

.table-wrap { overflow-x: auto; background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.07); margin-bottom: 24px; }
table { width: 100%; border-collapse: collapse; min-width: 700px; }
thead th {
  background: #1B2A4A;
  color: #fff;
  padding: 10px 12px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}
thead th.sortable {
  cursor: pointer;
  user-select: none;
}
thead th.sortable:hover { background: #2563eb; }
thead th.sort-asc::after  { content: " ▲"; font-size: 9px; opacity: 0.9; }
thead th.sort-desc::after { content: " ▼"; font-size: 9px; opacity: 0.9; }
tbody tr:nth-child(even) { background: #f5f8fc; }
tbody tr:hover { background: #e8f0fb; }
td { padding: 9px 12px; border-bottom: 1px solid #e8edf2; white-space: nowrap; }

.tier-a { background: #d4edda !important; font-weight: 700; color: #155724; }
.tier-b { background: #fff3cd !important; font-weight: 700; color: #856404; }
.tier-c { background: #f8d7da !important; font-weight: 700; color: #721c24; }

.score { font-weight: 700; color: #1B2A4A; }
.green-text { color: #1a7f4b; }
.red-text { color: #c0392b; }

.scanners-tag {
  font-size: 10px;
  font-weight: 600;
  border-radius: 4px;
  padding: 3px 7px;
  margin: 2px 2px;
  display: inline-block;
  white-space: nowrap;
  letter-spacing: 0.2px;
}
.sc-golden_pocket      { background: #fef3c7; color: #92400e; border: 1px solid #f59e0b; }
.sc-vcp                { background: #dbeafe; color: #1e40af; border: 1px solid #3b82f6; }
.sc-livermore_buy_the_dip { background: #d1fae5; color: #065f46; border: 1px solid #10b981; }
.sc-pocket_pivot       { background: #ede9fe; color: #5b21b6; border: 1px solid #8b5cf6; }
.sc-bull_flag          { background: #fee2e2; color: #991b1b; border: 1px solid #ef4444; }
.sc-cup_and_handle     { background: #fce7f3; color: #9d174d; border: 1px solid #ec4899; }
.sc-flat_base          { background: #f0fdf4; color: #166534; border: 1px solid #22c55e; }
.sc-sean_momentum      { background: #fdf4ff; color: #6b21a8; border: 1px solid #a855f7; }
.sc-default            { background: #f1f5f9; color: #334155; border: 1px solid #94a3b8; }

.strategy-badge {
  font-size: 10px;
  font-weight: 700;
  border-radius: 4px;
  padding: 2px 7px;
  display: inline-block;
  white-space: nowrap;
  margin-left: 4px;
}
.strategy-a { background: #2563eb; color: #fff; }
.strategy-b { background: #ea7c1b; color: #fff; }
.strategy-dual { background: #7c3aed; color: #fff; }

footer { text-align: center; color: #8a9ab0; font-size: 11px; margin-top: 32px; }

.tv-link {
  color: #2962FF;
  text-decoration: none;
  font-weight: 700;
  font-size: 13px;
}
.tv-link:hover { text-decoration: underline; }

.tv-icon {
  display: inline-block;
  font-size: 10px;
  color: #2962FF;
  margin-left: 4px;
  vertical-align: middle;
  opacity: 0.7;
}

.finviz-btn {
  display: inline-block;
  background: #1B2A4A;
  color: #fff;
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  padding: 10px 20px;
  border-radius: 6px;
  margin-bottom: 14px;
  letter-spacing: 0.2px;
}
.finviz-btn:hover { background: #2563eb; }

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 700px) {
  header { padding: 16px; }
  header h1 { font-size: 17px; }
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
  table { min-width: 500px; }
}
"""


def _fmt(val, decimals: int = 2, suffix: str = "", prefix: str = "") -> str:
    """Format a numeric value for display."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        return f"{prefix}{float(val):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(val)


def _fmt_mcap(val_m) -> str:
    """Format market cap in millions → '$X.XB' or '$XXXM'."""
    if val_m is None or (isinstance(val_m, float) and pd.isna(val_m)):
        return "—"
    try:
        m = float(val_m)
        if m >= 1_000:
            return f"${m / 1_000:.1f}B"
        return f"${m:.0f}M"
    except (TypeError, ValueError):
        return "—"


def _fmt_vol(val) -> str:
    """Format volume → '1.2M', '450K', etc."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        v = float(val)
        if v >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"{v / 1_000:.0f}K"
        return f"{v:.0f}"
    except (TypeError, ValueError):
        return "—"


def _tier_class(tier: str) -> str:
    return {"A": "tier-a", "B": "tier-b", "C": "tier-c"}.get(str(tier), "")


def _strategy_badge(strategy: str) -> str:
    """Return HTML badge for a strategy value."""
    strategy = str(strategy).upper()
    if strategy == "A":
        return '<span class="strategy-badge strategy-a">PULLBACK</span>'
    elif strategy == "B":
        return '<span class="strategy-badge strategy-b">MEAN REV</span>'
    elif strategy == "DUAL":
        return '<span class="strategy-badge strategy-dual">DUAL &#9733;</span>'
    return ""


SCANNER_LABELS = {
    "golden_pocket":          "🟡 Golden Pocket",
    "vcp":                    "🔵 VCP",
    "livermore_buy_the_dip":  "🟢 Livermore Dip",
    "pocket_pivot":           "🟣 Pocket Pivot",
    "bull_flag":              "🔴 Bull Flag",
    "cup_and_handle":         "🩷 Cup & Handle",
    "flat_base":              "🌿 Flat Base",
    "sean_momentum":          "🚀 Sean Momentum",
}


def _scanner_tags(scanners_hit: str) -> str:
    """Convert comma-separated scanner names to colored HTML badges."""
    if not scanners_hit or (isinstance(scanners_hit, float) and pd.isna(scanners_hit)):
        return "—"
    result = ""
    for s in str(scanners_hit).split(","):
        s = s.strip()
        if not s:
            continue
        label = SCANNER_LABELS.get(s, s.replace("_", " ").title())
        css = f"sc-{s}" if s in SCANNER_LABELS else "sc-default"
        result += f'<span class="scanners-tag {css}">{label}</span>'
    return result


def generate_html(
    watchlist_df: pd.DataFrame,
    portfolio_summary: dict,
    run_date: str,
    output_path: Path,
) -> Path:
    """
    Generate a self-contained HTML report and write it to output_path.
    Returns the output path.
    """
    n = len(watchlist_df)
    exposure = portfolio_summary.get("exposure_pct", 0)
    total_risk_pct = portfolio_summary.get("total_risk_pct", 0)
    capital = portfolio_summary.get("capital_usd", 100_000)
    tier_a = portfolio_summary.get("tier_a_count", 0)
    tier_b = portfolio_summary.get("tier_b_count", 0)

    # Build summary cards
    summary_cards = [
        ("Positions", str(n), ""),
        ("Exposure", f"{exposure}%", ""),
        ("Total Risk", f"{total_risk_pct}%", "red" if total_risk_pct > 5 else ""),
        ("Tier A", str(tier_a), "green"),
        ("Tier B", str(tier_b), ""),
        ("Capital", f"${capital:,.0f}", ""),
    ]

    cards_html = "\n".join(
        f'<div class="summary-card"><div class="label">{label}</div>'
        f'<div class="value {cls}">{val}</div></div>'
        for label, val, cls in summary_cards
    )

    # Build Finviz "open all" URL
    symbols_list = watchlist_df["symbol"].dropna().tolist() if not watchlist_df.empty else []
    finviz_url = "https://finviz.com/screener.ashx?v=111&t=" + ",".join(symbols_list) if symbols_list else "#"
    tv_multi_links = " &nbsp;|&nbsp; ".join(
        f'<a href="https://www.tradingview.com/chart/?symbol={s}" target="_blank">{s}</a>'
        for s in symbols_list
    )

    # Build table rows
    table_rows = ""
    for _, row in watchlist_df.iterrows():
        tier = str(row.get("tier", ""))
        tier_cls = _tier_class(tier)
        strategy = str(row.get("strategy", ""))
        strategy_html = _strategy_badge(strategy)
        sym = row.get("symbol", "")
        tv_url = f"https://www.tradingview.com/chart/?symbol={sym}"
        company = row.get("company_name") or ""
        sector = row.get("sector") or "—"
        # Raw numeric values for JS sorting (stored in data-sort attributes)
        raw_score  = row.get("conviction_score") or 0
        raw_price  = row.get("price") or 0
        raw_mcap   = row.get("market_cap_m") or 0      # millions
        raw_vol    = row.get("avg_vol_live") or 0
        raw_ars    = row.get("ars") or 0
        raw_size   = row.get("size_usd") or 0
        raw_risk   = row.get("risk_usd") or 0

        score = _fmt(row.get("conviction_score"), 1)
        price = _fmt(row.get("price"), 2, prefix="$")
        entry = _fmt(row.get("entry"), 2, prefix="$")
        stop = _fmt(row.get("stop"), 2, prefix="$")
        t1 = _fmt(row.get("target1"), 2, prefix="$")
        t2 = _fmt(row.get("target2"), 2, prefix="$")
        size = _fmt(row.get("size_usd"), 0, prefix="$")
        shares = str(int(row["size_shares"])) if row.get("size_shares") is not None and not pd.isna(row.get("size_shares", float("nan"))) else "—"
        size_pct = _fmt(row.get("size_pct"), 1, suffix="%")
        risk = _fmt(row.get("risk_usd"), 0, prefix="$")
        rr1 = _fmt(row.get("rr_t1"), 1, suffix="R")
        rr2 = _fmt(row.get("rr_t2"), 1, suffix="R")
        ars = _fmt(row.get("ars"), 0)
        earnings = str(row.get("next_earnings_date") or "—")
        scanners = _scanner_tags(row.get("scanners_hit", ""))
        mcap = _fmt_mcap(row.get("market_cap_m"))
        avg_vol = _fmt_vol(row.get("avg_vol_live"))

        table_rows += f"""
        <tr>
          <td data-sort="{sym}">
            <a class="tv-link" href="{tv_url}" target="_blank">{sym}<span class="tv-icon">↗</span></a>
            <br><small style="color:#6b7a8d">{company}</small>
          </td>
          <td style="min-width:200px">{scanners}</td>
          <td class="{tier_cls}" data-sort="{tier}">{tier}</td>
          <td data-sort="{sector}">{sector}</td>
          <td class="score" data-sort="{raw_score}">{score}</td>
          <td data-sort="{raw_price}">{price}</td>
          <td>{entry}</td>
          <td class="red-text">{stop}</td>
          <td class="green-text">{t1}</td>
          <td class="green-text">{t2}</td>
          <td data-sort="{raw_size}">{size}</td>
          <td>{shares}</td>
          <td>{size_pct}</td>
          <td data-sort="{raw_risk}">{risk}</td>
          <td>{rr1}</td>
          <td>{rr2}</td>
          <td data-sort="{raw_ars}">{ars}</td>
          <td data-sort="{raw_mcap}">{mcap}</td>
          <td data-sort="{raw_vol}">{avg_vol}</td>
          <td>{earnings}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AskLivermore Watchlist — {run_date}</title>
  <style>
{INLINE_CSS}
  </style>
</head>
<body>
<div class="container">
  <header>
    <h1>AskLivermore Watchlist</h1>
    <div class="subtitle">Generated {run_date} &nbsp;|&nbsp; {n} positions &nbsp;|&nbsp; Exposure {exposure}%</div>
  </header>

  <div class="summary-grid">
    {cards_html}
  </div>

  <div class="section-header">
    <h2>Watchlist</h2>
    <a class="finviz-btn" href="{finviz_url}" target="_blank">📊 Apri tutti su Finviz</a>
  </div>

  <div style="background:#fff; border-radius:8px; padding:14px 16px; margin-bottom:16px; box-shadow:0 1px 4px rgba(0,0,0,0.07); font-size:12px; color:#4a5568; line-height:2;">
    <strong style="color:#1B2A4A; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">📈 TradingView — Apri singolo chart:</strong><br>
    {tv_multi_links}
  </div>

  <div style="font-size:11px; color:#6b7a8d; margin-bottom:8px;">
    💡 <strong>Clicca su un'intestazione</strong> per ordinare la tabella (funziona aprendo il file HTML nel browser)
  </div>

  <div class="table-wrap">
    <table id="watchlist-table">
      <thead>
        <tr>
          <th class="sortable" data-col="0">Symbol</th>
          <th>Scanners</th>
          <th class="sortable" data-col="2">Tier</th>
          <th class="sortable" data-col="3">Sector</th>
          <th class="sortable sort-desc" data-col="4">Score ▼</th>
          <th class="sortable" data-col="5">Price</th>
          <th>Entry</th>
          <th>Stop</th>
          <th>T1</th>
          <th>T2</th>
          <th class="sortable" data-col="10">Size $</th>
          <th>Shares</th>
          <th>Size %</th>
          <th class="sortable" data-col="13">Risk $</th>
          <th>R:R T1</th>
          <th>R:R T2</th>
          <th class="sortable" data-col="16">ARS</th>
          <th class="sortable" data-col="17">Mkt Cap</th>
          <th class="sortable" data-col="18">Avg Vol (50d)</th>
          <th>Earnings</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </div>

  <footer>
    Generated by AskLivermore Auto-Funnel &nbsp;|&nbsp; {run_date}
    <br>This report is for informational purposes only. Not financial advice.
  </footer>
</div>

<script>
(function() {{
  var table    = document.getElementById('watchlist-table');
  var headers  = table.querySelectorAll('thead th.sortable');
  var tbody    = table.querySelector('tbody');
  var sortCol  = 4;   // default: Score
  var sortAsc  = false;

  function sortTable(colIdx, asc) {{
    var rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort(function(a, b) {{
      var aVal = a.cells[colIdx].getAttribute('data-sort') || a.cells[colIdx].textContent.trim();
      var bVal = b.cells[colIdx].getAttribute('data-sort') || b.cells[colIdx].textContent.trim();
      var aNum = parseFloat(aVal);
      var bNum = parseFloat(bVal);
      var isNum = !isNaN(aNum) && !isNaN(bNum);
      if (isNum) return asc ? aNum - bNum : bNum - aNum;
      return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    }});
    rows.forEach(function(r) {{ tbody.appendChild(r); }});
  }}

  headers.forEach(function(th) {{
    th.addEventListener('click', function() {{
      var col = parseInt(th.getAttribute('data-col'));
      if (col === sortCol) {{ sortAsc = !sortAsc; }}
      else {{ sortCol = col; sortAsc = false; }}

      headers.forEach(function(h) {{ h.classList.remove('sort-asc','sort-desc'); }});
      th.classList.add(sortAsc ? 'sort-asc' : 'sort-desc');
      sortTable(col, sortAsc);
    }});
  }});

  // Apply default sort on load
  sortTable(sortCol, sortAsc);
}})();
</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    log.info(f"HTML report saved: {output_path}")
    return output_path
