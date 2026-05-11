# SPRINT 1 REPORT — Fix + Deploy
**Data:** 11 maggio 2026
**Durata:** ~1 ora (incluso Sprint 0)

---

## ✅ OBIETTIVI RAGGIUNTI

### Bug fixati
| Bug | Fix applicato |
|---|---|
| `fetch_extra_assets()` — `float(Series)` su yfinance 1.3.0 | `.squeeze()` dopo `yf.download()['Close']` |
| `fetch_cot()` — URL CFTC 404 | Nuovo URL: `cftc.gov/files/dea/history/fut_disagg_txt_YYYY.zip` |
| COT colonna data rinominata | `Report_Date_as_MM_DD_YYYY` → `Report_Date_as_YYYY-MM-DD` |
| HES delisted in XLE components | Sostituito con DVN (Devon Energy) |

### Deploy produzione
| Item | Stato |
|---|---|
| Repository GitHub | ✅ https://github.com/zlatandodo/askdodo |
| GitHub Pages | ✅ https://zlatandodo.github.io/askdodo/ |
| Workflow settimanale | ✅ ogni domenica 22:00 ora italiana |
| Primo run manuale | ✅ completato con successo |
| Email configurata | ✅ dodo.ebayer@gmail.com |

---

## 📊 OUTPUT DASHBOARD PRODUZIONE (11 maggio 2026)

### Cruscotto: 🟡 GIALLO — LATE CYCLE / ATTENZIONE
| Indicatore | Valore | Stato |
|---|---|---|
| Chicago Fed (ISM proxy) | -0.20 | 🔴 Borderline recessione |
| HY Spreads OAS | 2.81% | 🟢 Credito sereno |
| Yield Curve 10Y-2Y | +0.48% | 🟢 Positiva |
| Copper/Gold Ratio | 0.00137 | 🟢 +14.67% 3M |
| Dollar Index (DXY) | 97.9 | 🟢 Debole, favorevole EM |
| MOVE Index | 67.2 | 🟢 Bond stabili |
| VIX | 17.2 | 🟢 Bassa volatilità |

### Quadrante: 🔴 STAGFLAZIONE
- Inflazione ancora sopra target Fed (CPI/PCE YoY > 2.5%)
- Crescita borderline (CFNAI -0.20)
- Azione: BUNKER MODE — oro, inflation-linked, cash

### COT Multi-Asset (Managed Money Net)
| Asset | Net | WoW | Sentiment |
|---|---|---|---|
| WTI Crude | +70,791 | -9,540 ↓ | BULLISH (ma distribuzione) |
| Natural Gas | -107,489 | -10,244 ↓ | BEARISH |
| Gold | +94,254 | +4,502 ↑ | BULLISH (accumulo) |
| Silver | +10,843 | +237 ↑ | BULLISH |
| Copper | +63,473 | +2,536 ↑ | BULLISH |

### Ranking settori
XLK **5/5 FORTE** (+12.71% RS4W) — tutto il resto 0–1/5 NEGATIVO.
Situazione anomala: Tech domina in contesto di stagflazione teorica.
Possibile divergenza da monitorare (AI rally strutturale vs macro deterioramento).

---

## ⚠️ ISSUE RESIDUE

| # | Descrizione | Priorità |
|---|---|---|
| 1 | COT S&P 500 E-mini assente — è nel file financial futures CFTC separato, non nel disaggregated commodities | 🟡 MEDIA |
| 2 | Node.js 20 deprecation warning nel workflow (da aggiornare a Node.js 24 entro giugno 2026) | 🟡 BASSA |

---

## 📋 PROPOSTA SPRINT 2

Indicatori sentiment mancanti:
1. **NAAIM Exposure Index** — scraper da naaim.org (CSV pubblico)
2. **CBOE Put/Call Ratio** — ticker `^CPCE` via yfinance (da testare)
3. **ISM Manufacturing PMI** — valutare TradingView Pro vs scraping
4. Aggiungere COT S&P 500 dal file financial futures CFTC

---

*Sprint 1 completato. Dashboard in produzione.*
